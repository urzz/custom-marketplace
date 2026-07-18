#!/usr/bin/env python3
"""
Nuclio Next deterministic evidence helper.

## Contents

- [Protocol errors and JSON helpers](#protocol-errors-and-json-helpers)
- [Path, repository and hash helpers](#path-repository-and-hash-helpers)
- [Snapshot and fingerprint evidence](#snapshot-and-fingerprint-evidence)
- [Git mutation map and task evidence validation](#git-mutation-map-and-task-evidence-validation)
- [Completion, decision and finish validation](#completion-decision-and-finish-validation)
- [CLI](#cli)

The helper emits deterministic JSON evidence identities using only the Python
standard library. It reads files and Git object state but never writes product,
knowledge, Gate, state or evidence files. Mutation maps fail closed when actual
base..head or dirty paths exceed the current Task mutation_targets; reviewer text
or PASS claims cannot authorize overreach.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
VCS_RE = re.compile(r"^[0-9a-fA-F][0-9a-fA-F._/-]{0,127}$")
DECISION_SECTIONS = ("Completion Verdict", "Remaining Risks", "Knowledge Proposal", "Archive Decision")
BROAD_PATHS = {"", ".", "./", "plugins", "src", "docs", ".dev-docs", ".git"}


class ProtocolError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_INPUT", f"{where} must be an object")
    return value


def _require_list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProtocolError("INVALID_INPUT", f"{where} must be a list")
    return value


def _non_empty(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("INVALID_INPUT", f"{where} must be a non-empty string")
    return value.strip()


def _require_sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ProtocolError("INVALID_IDENTITY", f"{where} must be a lowercase sha256")
    return value


def _require_vcs(value: Any, where: str) -> str:
    text = _non_empty(value, where)
    if not VCS_RE.fullmatch(text):
        raise ProtocolError("INVALID_VCS_REF", f"{where} must be a bounded VCS ref")
    return text


def _load_json_value(raw: str, where: str) -> Any:
    text = raw.strip()
    if text.startswith(("{", "[", '"')):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProtocolError("INVALID_JSON_ARGUMENT", f"{where} is not valid JSON") from exc
    path = Path(raw)
    if not path.exists() or not path.is_file():
        raise ProtocolError("INPUT_NOT_FOUND", f"{where} path must name an existing file", {"path": raw})
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError("INVALID_JSON_FILE", f"{where} file is not valid JSON", {"path": raw}) from exc


def _repo(path: str | Path) -> Path:
    repo = Path(path).resolve()
    if not repo.exists() or not repo.is_dir():
        raise ProtocolError("INVALID_REPO", "repo must be an existing directory", {"repo": str(path)})
    return repo


def normalize_path(value: Any, where: str = "path") -> str:
    raw = _non_empty(value, where)
    if raw.startswith(("/", "~")) or raw in BROAD_PATHS:
        raise ProtocolError("INVALID_PATH", "path must be a bounded repo-relative concrete file", {"path": raw})
    if any(char in raw for char in "*?[]{}"):
        raise ProtocolError("INVALID_PATH", "path must not contain glob characters", {"path": raw})
    parts = PurePosixPath(raw).parts
    if ".." in parts or raw.endswith("/"):
        raise ProtocolError("INVALID_PATH", "path must not traverse or name a directory", {"path": raw})
    normalized = posixpath.normpath(raw)
    if normalized != raw or normalized in BROAD_PATHS or normalized == ".git" or normalized.startswith(".git/"):
        raise ProtocolError("INVALID_PATH", "path must be normalized and must not touch .git", {"path": raw})
    return normalized


def _file_sha(repo: Path, relpath: str) -> str | None:
    path = repo / relpath
    if not path.exists():
        return None
    if not path.is_file():
        raise ProtocolError("INVALID_PATH", "path must name a concrete file", {"path": relpath})
    return sha256_bytes(path.read_bytes())


def _git(repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise ProtocolError("GIT_ERROR", "git command failed", {"command": args, "stderr": proc.stderr.strip()})
    return proc


def _git_blob_sha(repo: Path, rev: str, relpath: str) -> str | None:
    proc = _git(repo, ["show", f"{rev}:{relpath}"], check=False)
    if proc.returncode != 0:
        return None
    return sha256_bytes(proc.stdout.encode("utf-8"))


def _path_sha(path: str, sha: str | None) -> dict[str, str] | None:
    return None if sha is None else {"path": path, "sha256": sha}


def snapshot(repo_path: str | Path, paths: list[Any], deleted_paths: list[Any] | None = None) -> dict[str, Any]:
    repo = _repo(repo_path)
    deleted = {normalize_path(item, "deleted_paths[]") for item in (deleted_paths or [])}
    entries = []
    for raw in paths:
        rel = normalize_path(raw)
        sha = _file_sha(repo, rel)
        if rel in deleted:
            if sha is not None:
                raise ProtocolError("INVALID_SNAPSHOT", "deleted snapshot path still exists", {"path": rel})
            entry = {"path": rel, "state": "deleted"}
        elif sha is None:
            entry = {"path": rel, "state": "absent"}
        else:
            entry = {"path": rel, "state": "present", "sha256": sha}
        entries.append(entry)
    entries.sort(key=lambda item: item["path"])
    return {"schema_version": 1, "snapshots": entries, "snapshot_sha256": sha256_value(entries)}


def fingerprint(contract_sha256: str, context_fingerprint: str, state_version: int, task_head: str, snapshots: list[Any], expected: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(state_version, int) or isinstance(state_version, bool) or state_version < 1:
        raise ProtocolError("INVALID_STATE_VERSION", "state_version must be a positive integer")
    identity = {
        "contract_sha256": _require_sha(contract_sha256, "contract_sha256"),
        "context_fingerprint": _require_sha(context_fingerprint, "context_fingerprint"),
        "state_version": state_version,
        "task_head": _non_empty(task_head, "task_head"),
        "snapshots_sha256": sha256_value(_require_list(snapshots, "snapshots")),
    }
    identity["fingerprint"] = sha256_value(identity)
    if expected is not None:
        expected = _require_object(expected, "expected")
        mismatches = {key: {"expected": expected.get(key), "actual": identity.get(key)} for key in ("contract_sha256", "context_fingerprint", "state_version", "task_head", "fingerprint") if key in expected and expected.get(key) != identity.get(key)}
        if mismatches:
            raise ProtocolError("STALE_FINGERPRINT", "fingerprint identity drift", mismatches)
    return {"schema_version": 1, "identity": identity}


def _target_map(targets: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in targets:
        if isinstance(raw, str):
            path = normalize_path(raw, "mutation_targets[]")
            mode = "modify"
        else:
            item = _require_object(raw, "mutation_targets[]")
            path = normalize_path(item.get("path"), "mutation_targets[].path")
            mode = _non_empty(item.get("mode"), "mutation_targets[].mode")
            if mode not in {"create", "modify", "delete"}:
                raise ProtocolError("INVALID_MUTATION_TARGET", "mutation target mode is invalid", {"path": path, "mode": mode})
        if path in result:
            raise ProtocolError("INVALID_MUTATION_TARGET", "duplicate mutation target", {"path": path})
        result[path] = mode
    if not result:
        raise ProtocolError("INVALID_MUTATION_TARGET", "mutation targets must not be empty")
    return result


def _dirty_paths(repo: Path) -> dict[str, str]:
    proc = _git(repo, ["status", "--porcelain=v1", "--untracked-files=all"])
    paths: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if not line:
            continue
        status = line[:2]
        raw_path = line[3:]
        if " -> " in raw_path or status[0] == "R" or status[1] == "R" or status[0] == "C" or status[1] == "C":
            parts = raw_path.split(" -> ", 1)
            if len(parts) != 2:
                raise ProtocolError("INVALID_GIT_STATUS", "rename/copy status must include source and destination")
            source = normalize_path(parts[0].strip().strip('"'), "dirty rename source")
            destination = normalize_path(parts[1].strip().strip('"'), "dirty rename destination")
            paths[source] = "delete"
            paths[destination] = "create"
        else:
            path = normalize_path(raw_path.strip().strip('"'), "dirty path")
            if status == "??" or status[0] == "A" or status[1] == "A":
                paths[path] = "create"
            elif status[0] == "D" or status[1] == "D":
                paths[path] = "delete"
            else:
                paths[path] = "modify"
    return paths


def _diff_entries(repo: Path, base: str, head: str) -> dict[str, dict[str, Any]]:
    proc = _git(repo, ["diff", "--name-status", "--find-renames", base, head])
    entries: dict[str, dict[str, Any]] = {}
    for line in proc.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        code = parts[0]
        if code.startswith(("R", "C")):
            if len(parts) != 3:
                raise ProtocolError("INVALID_GIT_DIFF", "rename/copy diff must include source and destination")
            source = normalize_path(parts[1], "git diff rename source")
            destination = normalize_path(parts[2], "git diff rename destination")
            source_before_sha = _git_blob_sha(repo, base, source)
            destination_after_sha = _git_blob_sha(repo, head, destination)
            entries[source] = {"path": source, "mode": "delete", "before": _path_sha(source, source_before_sha), "after": None, "dirty": False, "source_status": code}
            entries[destination] = {"path": destination, "mode": "create", "before": None, "after": _path_sha(destination, destination_after_sha), "dirty": False, "source_status": code}
            continue
        path = normalize_path(parts[-1], "git diff path")
        before_sha = _git_blob_sha(repo, base, path)
        after_sha = _git_blob_sha(repo, head, path)
        if code.startswith("A"):
            mode = "create"
        elif code.startswith("D"):
            mode = "delete"
        else:
            mode = "modify" if before_sha != after_sha else "modify"
        entries[path] = {"path": path, "mode": mode, "before": _path_sha(path, before_sha), "after": _path_sha(path, after_sha), "dirty": False}
    return entries


def mutation_map(repo_path: str | Path, base: str, head: str, mutation_targets: list[Any], dirty_paths: list[Any] | None = None) -> dict[str, Any]:
    repo = _repo(repo_path)
    base = _require_vcs(base, "base")
    head = _require_vcs(head, "head")
    targets = _target_map(mutation_targets)
    entries = _diff_entries(repo, base, head)
    dirty = _dirty_paths(repo)
    for item in dirty_paths or []:
        rel = normalize_path(item, "dirty_paths[]")
        dirty.setdefault(rel, "modify")
    for path, dirty_mode in dirty.items():
        before_sha = _git_blob_sha(repo, base, path)
        after_sha = _file_sha(repo, path)
        if before_sha is None and after_sha is not None:
            mode = "create"
        elif before_sha is not None and after_sha is None:
            mode = "delete"
        else:
            mode = "modify"
        entries[path] = {"path": path, "mode": mode if dirty_mode != "delete" else mode, "before": _path_sha(path, before_sha), "after": _path_sha(path, after_sha), "dirty": True}
    ordered = [entries[path] for path in sorted(entries)]
    blockers = []
    for entry in ordered:
        expected = targets.get(entry["path"])
        if expected is None:
            blockers.append({"id": "MUTATION_OVERREACH", "severity": "blocking", "path": entry["path"], "reason": "changed path is outside mutation_targets"})
        elif expected != entry["mode"]:
            blockers.append({"id": "MUTATION_MODE_MISMATCH", "severity": "blocking", "path": entry["path"], "reason": "changed mode does not match mutation_targets", "expected_mode": expected, "actual_mode": entry["mode"]})
    body = {"base_head": base, "new_head": head, "entries": ordered, "changed_paths": [entry["path"] for entry in ordered], "dirty_paths": sorted(dirty), "mutation_targets": [{"path": path, "mode": mode} for path, mode in sorted(targets.items())], "blockers": blockers, "result": "blocked" if blockers else "ok"}
    body["sha256"] = sha256_value({key: body[key] for key in sorted(body) if key != "sha256"})
    return {"schema_version": 1, "kind": "mutation_map", "mutation_map": body}


def validate_task_evidence(evidence: dict[str, Any], mutation_map_doc: dict[str, Any]) -> dict[str, Any]:
    evidence = _require_object(evidence, "evidence")
    mutation = _require_object(mutation_map_doc.get("mutation_map", mutation_map_doc), "mutation_map")
    blockers = list(mutation.get("blockers", []))
    if blockers:
        raise ProtocolError("MUTATION_OVERREACH", "mutation map contains blocking overreach", {"blockers": blockers})
    changed = sorted(_require_list(evidence.get("changed_paths"), "evidence.changed_paths"))
    actual = sorted(mutation.get("changed_paths", []))
    if changed != actual:
        raise ProtocolError("EVIDENCE_MISMATCH", "evidence changed_paths do not match mutation map", {"expected": actual, "actual": changed})
    if "mutation_map_sha256" in evidence and evidence["mutation_map_sha256"] != mutation.get("sha256"):
        raise ProtocolError("EVIDENCE_MISMATCH", "evidence mutation_map_sha256 is stale", {"expected": mutation.get("sha256"), "actual": evidence["mutation_map_sha256"]})
    return {"schema_version": 1, "valid": True, "task_id": evidence.get("task_id"), "mutation_map_sha256": mutation.get("sha256"), "changed_paths": actual, "validation_sha256": sha256_value({"evidence": evidence, "mutation_map_sha256": mutation.get("sha256")})}


def completion_identity(state: dict[str, Any], contract_sha256: str, context_fingerprint: str, base: str, head: str, acceptance_index: list[Any], completed_tasks: list[Any]) -> dict[str, Any]:
    state = _require_object(state, "state")
    state_tasks = [str(task.get("id")) for task in _require_list(state.get("tasks"), "state.tasks")]
    if any(task.get("status") != "completed" for task in state.get("tasks", [])):
        raise ProtocolError("TASKS_INCOMPLETE", "all tasks must be completed before completion identity")
    task_heads: dict[str, str] = {}
    evidence_ids: dict[str, str] = {}
    for raw in completed_tasks:
        item = _require_object(raw, "completed_tasks[]")
        task_id = str(item.get("task_id", "")).strip()
        if task_id not in state_tasks:
            raise ProtocolError("UNKNOWN_TASK", "completed task is not present in state", {"task_id": task_id})
        task_heads[task_id] = _non_empty(item.get("head"), "completed_tasks[].head")
        if "evidence_sha256" in item:
            evidence_ids[task_id] = _require_sha(item["evidence_sha256"], "completed_tasks[].evidence_sha256")
    if set(task_heads) != set(state_tasks):
        raise ProtocolError("TASKS_INCOMPLETE", "completed task heads must cover every state task", {"expected": sorted(state_tasks), "actual": sorted(task_heads)})
    accepted = []
    for raw in acceptance_index:
        item = _require_object(raw, "acceptance_index[]")
        if item.get("accepted") is not True:
            raise ProtocolError("INCOMPLETE_ACCEPTANCE", "acceptance index must be 100% accepted", {"item": item.get("id")})
        accepted.append(item)
    if not accepted:
        raise ProtocolError("INCOMPLETE_ACCEPTANCE", "acceptance index must not be empty")
    acceptance_sha = sha256_value(sorted(accepted, key=lambda item: str(item.get("id"))))
    identity = {
        "contract_sha256": _require_sha(contract_sha256, "contract_sha256"),
        "context_fingerprint": _require_sha(context_fingerprint, "context_fingerprint"),
        "state_version": state.get("state_version"),
        "task_heads": dict(sorted(task_heads.items())),
        "task_evidence_sha256": sha256_value(dict(sorted(evidence_ids.items()))),
        "implementation_range": {"base": _require_vcs(base, "base"), "head": _require_vcs(head, "head")},
        "acceptance_index_sha256": acceptance_sha,
    }
    identity["completion_sha256"] = sha256_value(identity)
    return {"schema_version": 1, "completion_identity": identity}


def decision_hash(decision: dict[str, Any], completion_identity_doc: dict[str, Any]) -> dict[str, Any]:
    decision = _require_object(decision, "decision")
    missing = [section for section in DECISION_SECTIONS if section not in decision]
    if missing:
        raise ProtocolError("INVALID_DECISION", "decision must contain the four fixed sections", {"missing": missing})
    canonical_decision = {section: decision[section] for section in DECISION_SECTIONS}
    completion = completion_identity_doc.get("completion_identity", completion_identity_doc)
    body = {"completion_identity": completion, "decision": canonical_decision}
    return {"schema_version": 1, "decision_sha256": sha256_value(body), "decision_sections": list(DECISION_SECTIONS), "completion_sha256": completion.get("completion_sha256")}


def _plan_targets(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for group_name in ("knowledge_targets", "archive_targets"):
        for raw in plan.get(group_name, []):
            item = _require_object(raw, f"{group_name}[]")
            path = normalize_path(item.get("path"), f"{group_name}[].path")
            if path in targets:
                raise ProtocolError("INVALID_FINISH_PLAN", "finish target appears more than once", {"path": path})
            targets[path] = {"path": path, "group": group_name, "before_sha256": item.get("before_sha256")}
            if targets[path]["before_sha256"] is not None:
                _require_sha(targets[path]["before_sha256"], f"{group_name}[].before_sha256")
    return targets


def validate_finish_apply(decision_sha256: str, finish_plan: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    decision_sha256 = _require_sha(decision_sha256, "decision_sha256")
    finish_plan = _require_object(finish_plan, "finish_plan")
    journal = _require_object(journal, "journal")
    if _require_sha(journal.get("decision_sha256"), "journal.decision_sha256") != decision_sha256:
        raise ProtocolError("STALE_DECISION", "journal decision identity is stale")
    if finish_plan.get("decision_sha256") and finish_plan["decision_sha256"] != decision_sha256:
        raise ProtocolError("STALE_DECISION", "finish plan decision identity is stale")
    if finish_plan.get("approval_identity") != journal.get("approval_identity"):
        raise ProtocolError("STALE_APPROVAL", "finish apply approval identity is stale")
    targets = _plan_targets(finish_plan)
    entries = {}
    for raw in _require_list(journal.get("entries"), "journal.entries"):
        item = _require_object(raw, "journal.entries[]")
        path = normalize_path(item.get("path"), "journal.entries[].path")
        if path not in targets:
            raise ProtocolError("KNOWLEDGE_TARGET_OVERREACH", "finish journal writes a target not approved by Knowledge Proposal or Archive Decision", {"path": path})
        if path in entries:
            raise ProtocolError("INVALID_FINISH_JOURNAL", "duplicate finish journal path", {"path": path})
        before = item.get("before_sha256")
        after = item.get("after_sha256")
        if before is not None:
            _require_sha(before, "journal.entries[].before_sha256")
        if after is not None:
            _require_sha(after, "journal.entries[].after_sha256")
        expected_before = targets[path].get("before_sha256")
        if expected_before != before:
            raise ProtocolError("STALE_TARGET", "finish journal before identity does not match approved target", {"path": path, "expected": expected_before, "actual": before})
        if item.get("apply_result") not in {"applied", "unchanged"}:
            raise ProtocolError("INVALID_FINISH_JOURNAL", "finish journal apply_result must be applied or unchanged", {"path": path})
        archive_result = item.get("archive_result")
        if archive_result not in {"archived", "not_applicable"}:
            raise ProtocolError("INVALID_FINISH_JOURNAL", "finish journal archive_result is invalid", {"path": path})
        if targets[path]["group"] == "archive_targets" and archive_result != "archived":
            raise ProtocolError("INVALID_FINISH_JOURNAL", "archive target requires archived archive_result", {"path": path})
        if targets[path]["group"] == "knowledge_targets" and archive_result != "not_applicable":
            raise ProtocolError("INVALID_FINISH_JOURNAL", "knowledge target requires not_applicable archive_result", {"path": path})
        entries[path] = item
    missing = sorted(set(targets) - set(entries))
    if missing:
        raise ProtocolError("MISSING_FINISH_TARGET", "finish journal must cover every approved target", {"paths": missing})
    body = {"decision_sha256": decision_sha256, "finish_plan_sha256": sha256_value(finish_plan), "entries": [entries[path] for path in sorted(entries)]}
    return {"schema_version": 1, "valid": True, "journal_sha256": sha256_value(body), "covered_paths": sorted(entries)}


def _ok(payload: dict[str, Any]) -> int:
    sys.stdout.write(canonical_json({"ok": True, **payload}) + "\n")
    return 0


def _err(error: ProtocolError) -> int:
    sys.stderr.write(canonical_json({"ok": False, "code": error.code, "message": error.message, "details": error.details}) + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive Nuclio Next evidence identity")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("snapshot")
    p.add_argument("--repo", required=True)
    p.add_argument("--paths-json", required=True)
    p.add_argument("--deleted-paths-json", default="[]")

    p = sub.add_parser("fingerprint")
    p.add_argument("--contract-sha256", required=True)
    p.add_argument("--context-fingerprint", required=True)
    p.add_argument("--state-version", type=int, required=True)
    p.add_argument("--task-head", required=True)
    p.add_argument("--snapshots-json", required=True)
    p.add_argument("--expected-json")

    p = sub.add_parser("mutation-map")
    p.add_argument("--repo", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--mutation-targets-json", required=True)
    p.add_argument("--dirty-paths-json", default="[]")

    p = sub.add_parser("validate-task-evidence")
    p.add_argument("--evidence-json", required=True)
    p.add_argument("--mutation-map-json", required=True)

    p = sub.add_parser("completion-identity")
    p.add_argument("--state-json", required=True)
    p.add_argument("--contract-sha256", required=True)
    p.add_argument("--context-fingerprint", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--acceptance-index-json", required=True)
    p.add_argument("--completed-tasks-json", required=True)

    p = sub.add_parser("decision-hash")
    p.add_argument("--decision-json", required=True)
    p.add_argument("--completion-identity-json", required=True)

    p = sub.add_parser("validate-finish-apply")
    p.add_argument("--decision-sha256", required=True)
    p.add_argument("--finish-plan-json", required=True)
    p.add_argument("--journal-json", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            return _ok(snapshot(args.repo, _load_json_value(args.paths_json, "paths"), _load_json_value(args.deleted_paths_json, "deleted paths")))
        if args.command == "fingerprint":
            expected = _load_json_value(args.expected_json, "expected") if args.expected_json else None
            return _ok(fingerprint(args.contract_sha256, args.context_fingerprint, args.state_version, args.task_head, _load_json_value(args.snapshots_json, "snapshots"), expected))
        if args.command == "mutation-map":
            return _ok(mutation_map(args.repo, args.base, args.head, _load_json_value(args.mutation_targets_json, "mutation targets"), _load_json_value(args.dirty_paths_json, "dirty paths")))
        if args.command == "validate-task-evidence":
            return _ok(validate_task_evidence(_load_json_value(args.evidence_json, "evidence"), _load_json_value(args.mutation_map_json, "mutation map")))
        if args.command == "completion-identity":
            return _ok(completion_identity(_load_json_value(args.state_json, "state"), args.contract_sha256, args.context_fingerprint, args.base, args.head, _load_json_value(args.acceptance_index_json, "acceptance index"), _load_json_value(args.completed_tasks_json, "completed tasks")))
        if args.command == "decision-hash":
            return _ok(decision_hash(_load_json_value(args.decision_json, "decision"), _load_json_value(args.completion_identity_json, "completion identity")))
        if args.command == "validate-finish-apply":
            return _ok(validate_finish_apply(args.decision_sha256, _load_json_value(args.finish_plan_json, "finish plan"), _load_json_value(args.journal_json, "journal")))
        raise ProtocolError("INVALID_COMMAND", "unknown command")
    except ProtocolError as exc:
        return _err(exc)


if __name__ == "__main__":
    raise SystemExit(main())
