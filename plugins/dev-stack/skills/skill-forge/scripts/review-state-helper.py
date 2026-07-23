#!/usr/bin/env python3
"""Deterministic file-backed review/fix state machine for skill-forge."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

from plan_contract import (
    PlanContractError,
    expected_fix_subject,
    expected_task_subject,
    load_plan_contract,
    valid_ownership_path,
)


SCHEMA_VERSION = 1
GATES = (
    "TASK_REVIEW", "FINAL_REVIEW", "STRUCTURAL_VALIDATION",
    "BEHAVIORAL_VALIDATION",
)
FINAL_GATES = set(GATES[1:])
HALTED_PREFIX = "HALTED_"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ReviewStateError(Exception):
    """Expected protocol failure with a stable machine-readable code."""

    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def print_json(payload, stream=sys.stdout):
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stream)


def load_json_object(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewStateError("INVALID_JSON", str(exc)) from exc
    if not isinstance(payload, dict):
        raise ReviewStateError("INVALID_JSON_OBJECT", str(path))
    return payload


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def require(condition, code, detail=None):
    if not condition:
        raise ReviewStateError(code, detail)


def run_git(repo_root, *args):
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ReviewStateError("GIT_ERROR", detail)
    return result.stdout.strip()


def is_full_sha(value):
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def validate_commit(repo_root, sha):
    require(is_full_sha(sha), "INVALID_SHA", sha)
    result = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{sha}^{{commit}}"],
        text=True,
        capture_output=True,
        check=False,
    )
    require(result.returncode == 0, "INVALID_SHA", sha)


def current_head(repo_root):
    head = run_git(repo_root, "rev-parse", "HEAD")
    require(is_full_sha(head), "INVALID_SHA", head)
    return head


def require_ancestor(repo_root, base, head):
    result = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", base, head],
        text=True,
        capture_output=True,
        check=False,
    )
    require(result.returncode == 0, "NOT_ANCESTOR", {"base": base, "head": head})


def history_event(event, before, after, task_id=None, gate=None, attempt=None,
                  base_sha=None, head_sha=None, finding_ids=None):
    return {
        "event": event,
        "from": before,
        "to": after,
        "task_id": task_id,
        "gate": gate,
        "attempt": attempt,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "finding_ids": sorted(finding_ids or []),
    }


def append_history(state, event, before, after, **kwargs):
    state["history"].append(history_event(event, before, after, **kwargs))


def validate_top_level(state):
    require(
        set(state) == {"schema_version", "workflow", "artifacts", "tasks", "findings", "history"},
        "INVALID_STATE_SCHEMA",
    )
    require(state["schema_version"] == SCHEMA_VERSION, "INVALID_STATE_SCHEMA")
    require(isinstance(state["workflow"], dict), "INVALID_STATE_SCHEMA")
    require(isinstance(state["artifacts"], dict), "INVALID_STATE_SCHEMA")
    require(isinstance(state["tasks"], dict), "INVALID_STATE_SCHEMA")
    require(isinstance(state["findings"], dict), "INVALID_STATE_SCHEMA")
    require(isinstance(state["history"], list), "INVALID_STATE_SCHEMA")
    workflow_keys = {
        "scope", "ticket", "repo_root", "initial_base", "current_head",
        "spec_path", "spec_sha256", "plan_path", "plan_sha256",
        "rubric_snapshot_path", "rubric_sha256", "status", "current_gate",
        "current_task_id",
    }
    require(workflow_keys <= set(state["workflow"]), "INVALID_STATE_SCHEMA")
    require(
        isinstance(state["artifacts"].get("task_order"), list)
        and isinstance(state["artifacts"].get("gate_attempts"), dict)
        and isinstance(state["artifacts"].get("controller_resolutions", []), list),
        "INVALID_STATE_SCHEMA",
    )


def load_and_validate_state(path, repo_root=None, check_hashes=True):
    state = load_json_object(path)
    validate_top_level(state)
    workflow = state["workflow"]
    stored_root = Path(workflow.get("repo_root", "")).resolve()
    if repo_root is not None:
        require(Path(repo_root).resolve() == stored_root, "REPO_ROOT_MISMATCH")
    require(stored_root.is_dir(), "INVALID_REPO", str(stored_root))
    if check_hashes:
        for path_key, hash_key in (
            ("spec_path", "spec_sha256"),
            ("plan_path", "plan_sha256"),
            ("rubric_snapshot_path", "rubric_sha256"),
        ):
            artifact = Path(workflow.get(path_key, ""))
            if not artifact.is_file() or sha256_file(artifact) != workflow.get(hash_key):
                raise ReviewStateError("ARTIFACT_HASH_DRIFT", str(artifact))
    hydrate_legacy_state_contract(state)
    return state


def hydrate_legacy_state_contract(state):
    try:
        contract = load_plan_contract(state["workflow"]["plan_path"])
    except PlanContractError as exc:
        raise ReviewStateError(exc.code, exc.detail) from exc
    state["artifacts"].setdefault("run_risk_level", contract.run_risk_level)
    scope = state["workflow"].get("scope")
    for task_id, task in state["tasks"].items():
        raw = contract.tasks.get(str(task_id))
        require(raw is not None, "INVALID_STATE_SCHEMA", task_id)
        meta = raw["meta"]
        task.setdefault("risk_level", meta["risk_level"])
        task.setdefault("review_policy", meta["review_policy"])
        task.setdefault("expected_subject", expected_task_subject(scope, task_id, raw["name"]))
        task.setdefault("deterministic_evidence", [])


def parse_tasks(contract):
    parsed = {}
    for task_id in contract.task_order:
        raw = contract.tasks[task_id]
        meta = raw["meta"]
        parsed[task_id] = {
            "status": "READY",
            "task_base": None,
            "task_head": None,
            "ownership": raw["files"],
            "risk_level": meta["risk_level"],
            "review_policy": meta["review_policy"],
            "expected_subject": None,
            "fix_budget": {"maximum": 2, "used": 0, "remaining": 2},
            "review_attempt": 0,
            "fix_attempt": 0,
            "open_blocking_findings": [],
            "resolved_findings": [],
            "baseline_findings": [],
            "authorized_finding_ids": [],
            "previous_open_blocker_fingerprints": [],
            "cannot_verify": [],
            "deterministic_evidence": [],
        }
    return parsed


def cmd_init(args):
    state_path = Path(args.state)
    repo_root = Path(args.repo_root).resolve()
    require(not state_path.exists(), "STATE_EXISTS", str(state_path))
    require((repo_root / ".git").exists(), "INVALID_REPO", str(repo_root))
    for path in (args.spec, args.plan, args.rubric_source):
        require(Path(path).is_file(), "FILE_NOT_FOUND", str(path))
    snapshot = Path(args.rubric_snapshot)
    require(not snapshot.exists(), "RUBRIC_SNAPSHOT_EXISTS", str(snapshot))
    validate_commit(repo_root, args.initial_base)
    require(current_head(repo_root) == args.initial_base, "HEAD_MISMATCH")
    try:
        contract = load_plan_contract(args.plan)
    except PlanContractError as exc:
        raise ReviewStateError(exc.code, exc.detail) from exc
    tasks = parse_tasks(contract)
    for task_id in contract.task_order:
        task = tasks[task_id]
        raw = contract.tasks[task_id]
        task["expected_subject"] = expected_task_subject(args.scope, task_id, raw["name"])

    snapshot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.rubric_source, snapshot)
    first_task = next(iter(tasks))
    workflow = {
        "scope": args.scope,
        "ticket": None if args.ticket.lower() == "none" else args.ticket,
        "repo_root": str(repo_root),
        "initial_base": args.initial_base,
        "current_head": args.initial_base,
        "spec_path": str(Path(args.spec).resolve()),
        "spec_sha256": sha256_file(args.spec),
        "plan_path": str(Path(args.plan).resolve()),
        "plan_sha256": sha256_file(args.plan),
        "rubric_snapshot_path": str(snapshot.resolve()),
        "rubric_sha256": sha256_file(snapshot),
        "status": "READY",
        "current_gate": "TASK_IMPLEMENTATION",
        "current_task_id": int(first_task) if first_task.isdigit() else first_task,
    }
    state = {
        "schema_version": SCHEMA_VERSION,
        "workflow": workflow,
        "artifacts": {
            "task_order": list(tasks),
            "run_risk_level": contract.run_risk_level,
            "gate_attempts": {gate: 0 for gate in FINAL_GATES},
            "controller_resolutions": [],
        },
        "tasks": tasks,
        "findings": {},
        "history": [history_event(
            "INITIALIZED", None, "READY", task_id=workflow["current_task_id"],
            gate="TASK_IMPLEMENTATION", attempt=0,
            base_sha=args.initial_base, head_sha=args.initial_base,
        )],
    }
    try:
        atomic_write_json(state_path, state)
    except Exception:
        snapshot.unlink(missing_ok=True)
        raise
    return {"state": str(state_path.resolve()), "task_count": len(tasks)}


def task_for(state, task_id):
    task = state["tasks"].get(str(task_id))
    require(task is not None, "UNKNOWN_TASK", str(task_id))
    return task


def task_paths(task):
    return {
        path for operation in ("create", "modify", "delete")
        for path in task["ownership"][operation]
    }


def transition_task(state, task_id, status):
    task = task_for(state, task_id)
    before = task["status"]
    task["status"] = status
    state["workflow"]["status"] = status
    return before


def cmd_start_task(args, state):
    task = task_for(state, args.task_id)
    workflow = state["workflow"]
    require(task["status"] == "READY", "INVALID_TRANSITION")
    require(str(workflow["current_task_id"]) == str(args.task_id), "INVALID_TRANSITION")
    head = current_head(workflow["repo_root"])
    require(args.expected_head == workflow["current_head"] == head, "HEAD_MISMATCH")
    task["task_base"] = head
    task["task_head"] = head
    before = transition_task(state, args.task_id, "IMPLEMENTING")
    workflow["current_gate"] = "TASK_IMPLEMENTATION"
    append_history(state, "TASK_STARTED", before, "IMPLEMENTING", task_id=args.task_id,
                   gate="TASK_IMPLEMENTATION", attempt=0, base_sha=head, head_sha=head)
    return {"task_id": args.task_id, "task_base": head, "task_head": head, "status": "IMPLEMENTING"}


def validate_head_change(repo_root, base, head):
    validate_commit(repo_root, base)
    validate_commit(repo_root, head)
    require(base != head, "HEAD_NOT_CHANGED")
    require(current_head(repo_root) == head, "HEAD_MISMATCH")
    require_ancestor(repo_root, base, head)


def commit_count(repo_root, base, head):
    return int(run_git(repo_root, "rev-list", "--count", f"{base}..{head}"))


def commit_subject(repo_root, head):
    return run_git(repo_root, "log", "-1", "--format=%s", head)


def validate_single_commit_subject(repo_root, base, head, expected_subject):
    require(commit_count(repo_root, base, head) == 1, "COMMIT_COUNT_MISMATCH")
    require(commit_subject(repo_root, head) == expected_subject, "COMMIT_SUBJECT_MISMATCH")


def derive_expected_fix_subject_for_task(state, task_id, task):
    return expected_fix_subject(state["workflow"]["scope"], task_id, task["fix_attempt"])


def expected_fix_subject_for_task(state, task_id, task):
    stored = task.get("expected_fix_subject")
    if non_empty_string(stored):
        return stored
    return derive_expected_fix_subject_for_task(state, task_id, task)


def load_optional_json(path):
    if path is None:
        return None
    return load_json_object(path)


def validate_deterministic_evidence(payload, task_id, base_sha, head_sha):
    require(isinstance(payload, dict), "INVALID_DETERMINISTIC_EVIDENCE")
    evidence = payload.get("checks", payload)
    if isinstance(evidence, dict):
        evidence = [evidence]
    require(isinstance(evidence, list) and evidence, "INVALID_DETERMINISTIC_EVIDENCE")
    normalized = []
    for item in evidence:
        require(isinstance(item, dict), "INVALID_DETERMINISTIC_EVIDENCE")
        require(str(item.get("task_id")) == str(task_id), "INVALID_DETERMINISTIC_EVIDENCE")
        require(item.get("base_sha") == base_sha, "BASE_MISMATCH")
        require(item.get("head_sha") == head_sha, "HEAD_MISMATCH")
        require(non_empty_string(item.get("command")), "INVALID_DETERMINISTIC_EVIDENCE")
        require(protocol_integer(item.get("exit_code")), "INVALID_DETERMINISTIC_EVIDENCE")
        require(non_empty_string(item.get("result_summary")), "INVALID_DETERMINISTIC_EVIDENCE")
        artifact = item.get("artifact_identity")
        require(
            (isinstance(artifact, dict) and bool(artifact)) or non_empty_string(artifact),
            "INVALID_DETERMINISTIC_EVIDENCE",
        )
        if item["exit_code"] != 0:
            raise ReviewStateError("DETERMINISTIC_CHECK_FAILED", item)
        normalized.append(copy.deepcopy(item))
    return normalized


def changed_paths(repo_root, base, head):
    output = run_git(repo_root, "diff", "--name-only", f"{base}..{head}")
    return [line for line in output.splitlines() if line]


def require_owned_diff(state, task, base, head):
    paths = changed_paths(state["workflow"]["repo_root"], base, head)
    outside = sorted(set(paths) - task_paths(task))
    require(not outside, "OWNERSHIP_VIOLATION", outside)
    return paths


def cmd_record_implementation(args, state):
    task = task_for(state, args.task_id)
    require(task["status"] == "IMPLEMENTING", "INVALID_TRANSITION")
    require(Path(args.report).is_file(), "REPORT_NOT_FOUND", args.report)
    require(args.base_head == task["task_base"] == task["task_head"], "BASE_MISMATCH")
    validate_head_change(state["workflow"]["repo_root"], args.base_head, args.new_head)
    paths = require_owned_diff(state, task, args.base_head, args.new_head)
    validate_single_commit_subject(
        state["workflow"]["repo_root"], args.base_head, args.new_head, task["expected_subject"]
    )
    evidence_payload = load_optional_json(args.deterministic_evidence)
    if task["review_policy"] == "final-only":
        evidence = validate_deterministic_evidence(evidence_payload, args.task_id, args.base_head, args.new_head)
        task["deterministic_evidence"] = evidence
        task["task_head"] = args.new_head
        state["workflow"]["current_head"] = args.new_head
        before = task["status"]
        advance_after_pass(state, str(args.task_id), {
            "gate": "TASK_REVIEW",
            "attempt": 0,
            "base_sha": args.base_head,
            "head_sha": args.new_head,
        })
        state["history"][-1]["event"] = "DETERMINISTIC_TASK_PASSED"
        state["history"][-1]["from"] = before
        return {"task_id": args.task_id, "changed_paths": paths, "status": state["workflow"]["status"]}
    require(evidence_payload is None, "INVALID_DETERMINISTIC_EVIDENCE")
    task["task_head"] = args.new_head
    task["review_attempt"] = 1
    state["workflow"]["current_head"] = args.new_head
    before = transition_task(state, args.task_id, "REVIEWING")
    state["workflow"]["current_gate"] = "TASK_REVIEW"
    append_history(state, "IMPLEMENTATION_RECORDED", before, "REVIEWING", task_id=args.task_id,
                   gate="TASK_REVIEW", attempt=1, base_sha=task["task_base"],
                   head_sha=args.new_head)
    return {"task_id": args.task_id, "changed_paths": paths, "status": "REVIEWING"}


def validate_fix_report(report, task, args):
    status = report.get("status")
    if status != "FIXED":
        require(status in {"BLOCKED", "NO_PROGRESS", "NEEDS_CONTEXT"}, "INVALID_FIX_REPORT")
        return status
    require(report.get("attempt") == task["fix_attempt"], "ATTEMPT_MISMATCH")
    require(report.get("base_head_sha") == args.base_head, "BASE_MISMATCH")
    require(report.get("new_head_sha") == args.new_head, "HEAD_MISMATCH")
    findings = report.get("findings")
    require(isinstance(findings, list), "INVALID_FIX_REPORT")
    ids = [finding.get("id") for finding in findings if isinstance(finding, dict)]
    require(sorted(ids) == sorted(task["authorized_finding_ids"]), "FINDING_SET_MISMATCH")
    for finding in findings:
        closure = finding.get("closure_test")
        require(
            isinstance(finding.get("action"), str)
            and isinstance(finding.get("changed_paths"), list)
            and isinstance(closure, dict)
            and isinstance(closure.get("command"), str)
            and isinstance(closure.get("exit_code"), int)
            and isinstance(closure.get("output"), str),
            "INVALID_FIX_REPORT",
        )
    return status


def cmd_record_fix(args, state):
    task = task_for(state, args.task_id)
    require(task["status"] == "FIXING", "INVALID_TRANSITION")
    require(Path(args.report).is_file(), "REPORT_NOT_FOUND", args.report)
    report = load_json_object(args.report)
    status = report.get("status")
    if status == "FIXED":
        validate_head_change(state["workflow"]["repo_root"], args.base_head, args.new_head)
        validate_single_commit_subject(
            state["workflow"]["repo_root"],
            args.base_head,
            args.new_head,
            expected_fix_subject_for_task(state, str(args.task_id), task),
        )
        expected_base = (
            state["workflow"]["current_head"]
            if state["workflow"]["current_gate"] in FINAL_GATES
            else task["task_head"]
        )
        require(args.base_head == expected_base, "BASE_MISMATCH")
        paths = require_owned_diff(state, task, args.base_head, args.new_head)
        validate_fix_report(report, task, args)
        task["task_head"] = args.new_head
        task["review_attempt"] += 1
        state["workflow"]["current_head"] = args.new_head
        before = transition_task(state, args.task_id, "REVIEWING")
        gate = state["workflow"]["current_gate"]
        append_history(state, "FIX_RECORDED", before, "REVIEWING", task_id=args.task_id,
                       gate=gate, attempt=task["review_attempt"], base_sha=task["task_base"],
                       head_sha=args.new_head, finding_ids=task["authorized_finding_ids"])
        return {"task_id": args.task_id, "changed_paths": paths, "status": "REVIEWING"}

    validate_fix_report(report, task, args)
    halted = {
        "BLOCKED": "HALTED_SCOPE_BLOCKED",
        "NO_PROGRESS": "HALTED_NO_PROGRESS",
        "NEEDS_CONTEXT": "HALTED_NEEDS_DECISION",
    }[status]
    before = transition_task(state, args.task_id, halted)
    append_history(state, "FIX_HALTED", before, halted, task_id=args.task_id,
                   gate=state["workflow"]["current_gate"], attempt=task["fix_attempt"],
                   base_sha=task["task_base"], head_sha=task["task_head"],
                   finding_ids=task["authorized_finding_ids"])
    return {"task_id": args.task_id, "status": halted}


def normalize_path(path):
    if not isinstance(path, str):
        return ""
    return PurePosixPath(path.strip().replace("\\", "/")).as_posix()


def non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


def protocol_integer(value):
    return type(value) is int


def valid_command_result(value):
    return (
        isinstance(value, dict)
        and non_empty_string(value.get("command"))
        and protocol_integer(value.get("exit_code"))
        and isinstance(value.get("output"), str)
    )


def finding_reference(finding):
    contract = finding.get("contract_ref")
    rubric = finding.get("rubric_ref")
    require(
        non_empty_string(contract) != non_empty_string(rubric)
        and (contract is None or non_empty_string(contract))
        and (rubric is None or non_empty_string(rubric)),
        "INVALID_FINDING_SCHEMA",
    )
    return contract or rubric


def finding_fingerprint(finding):
    owner = finding.get("owner_task_id")
    parts = (
        str(owner) if owner is not None else "",
        finding["rule_id"],
        normalize_path(finding["path"]),
        finding_reference(finding),
        finding["failure_key"],
    )
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def validate_closure_actual(finding):
    actual = finding.get("closure_test", {}).get("actual")
    return valid_command_result(actual)


def validate_evidence(value):
    require(valid_command_result(value), "INVALID_FINDING_SCHEMA")


def validate_finding(raw, observation):
    required = {
        "id", "owner_task_id", "source_gate", "attempt", "rule_id", "failure_key",
        "severity", "blocking", "origin", "status", "summary", "path",
        "required_fix_paths", "base_evidence", "head_evidence", "closure_test",
        "observations", "resolution",
    }
    require(isinstance(raw, dict) and required <= set(raw), "INVALID_FINDING_SCHEMA")
    require(non_empty_string(raw["id"]), "INVALID_FINDING_SCHEMA")
    owner = raw["owner_task_id"]
    require(owner is None or isinstance(owner, str) or protocol_integer(owner),
            "INVALID_FINDING_SCHEMA")
    if observation["gate"] == "TASK_REVIEW":
        require(owner is not None, "INVALID_FINDING_SCHEMA")
    require(
        isinstance(raw["source_gate"], str)
        and raw["source_gate"] in GATES
        and raw["source_gate"] == observation["gate"],
        "INVALID_FINDING_SCHEMA",
    )
    require(protocol_integer(raw["attempt"]), "INVALID_FINDING_SCHEMA")
    require(raw["attempt"] == observation["attempt"], "INVALID_FINDING_SCHEMA")
    require(non_empty_string(raw["rule_id"]), "INVALID_FINDING_SCHEMA")
    require(non_empty_string(raw["failure_key"]), "INVALID_FINDING_SCHEMA")
    require(non_empty_string(raw["summary"]), "INVALID_FINDING_SCHEMA")
    require(non_empty_string(raw["path"]), "INVALID_FINDING_SCHEMA")
    require(
        isinstance(raw["severity"], str)
        and raw["severity"] in {"CRITICAL", "IMPORTANT", "MINOR"},
        "INVALID_FINDING_SCHEMA",
    )
    require(
        isinstance(raw["origin"], str)
        and raw["origin"] in {"NEW", "REGRESSION", "BASELINE", "OUT_OF_CONTRACT"},
        "INVALID_FINDING_SCHEMA",
    )
    require(
        isinstance(raw["status"], str)
        and raw["status"] in {"OPEN", "RESOLVED", "BASELINE"},
        "INVALID_FINDING_SCHEMA",
    )
    require(isinstance(raw["blocking"], bool), "INVALID_FINDING_SCHEMA")
    require(isinstance(raw["required_fix_paths"], list), "INVALID_FINDING_SCHEMA")
    for path in raw["required_fix_paths"]:
        require(valid_ownership_path(path), "INVALID_FINDING_SCHEMA")
    actionable = (
        raw["status"] == "OPEN"
        and raw["origin"] in {"NEW", "REGRESSION"}
        and raw["blocking"]
        and raw["severity"] in {"CRITICAL", "IMPORTANT"}
    )
    if actionable:
        require(
            bool(raw["required_fix_paths"])
            and len(set(raw["required_fix_paths"])) == len(raw["required_fix_paths"]),
            "INVALID_FINDING_SCHEMA",
        )
    validate_evidence(raw["base_evidence"])
    validate_evidence(raw["head_evidence"])
    closure = raw["closure_test"]
    require(isinstance(closure, dict), "INVALID_FINDING_SCHEMA")
    validate_evidence(closure.get("expected"))
    actual = closure.get("actual")
    require(actual is None or valid_command_result(actual), "INVALID_FINDING_SCHEMA")
    require(
        isinstance(raw["observations"], list)
        and all(
            isinstance(item, dict)
            and non_empty_string(item.get("risk"))
            and non_empty_string(item.get("check"))
            for item in raw["observations"]
        ),
        "INVALID_FINDING_SCHEMA",
    )
    require(raw["resolution"] is None or isinstance(raw["resolution"], dict),
            "INVALID_FINDING_SCHEMA")
    finding_reference(raw)
    if raw["status"] == "RESOLVED":
        require(validate_closure_actual(raw), "INVALID_CLOSURE_EVIDENCE")


def owner_for_required_paths(state, paths):
    owners = []
    for task_id, task in state["tasks"].items():
        if set(paths) <= task_paths(task):
            owners.append(task_id)
    return owners


def relevant_task_id(state, observation):
    if observation["gate"] == "TASK_REVIEW":
        require(observation.get("task_id") is not None, "INVALID_OBSERVATION_SCHEMA")
        return str(observation["task_id"])
    return None


def validate_observation(state, observation):
    schema_version = observation.get("schema_version")
    require(
        protocol_integer(schema_version) and schema_version == SCHEMA_VERSION,
        "INVALID_OBSERVATION_SCHEMA",
    )
    gate = observation.get("gate")
    require(isinstance(gate, str) and gate in GATES, "INVALID_OBSERVATION_SCHEMA")
    verdict = observation.get("verdict")
    require(
        isinstance(verdict, str) and verdict in {"PASS", "FAIL"},
        "INVALID_OBSERVATION_SCHEMA",
    )
    require(isinstance(observation.get("findings"), list), "INVALID_OBSERVATION_SCHEMA")
    require(isinstance(observation.get("cannot_verify"), list), "INVALID_OBSERVATION_SCHEMA")
    require(isinstance(observation.get("controller_resolutions"), list), "INVALID_OBSERVATION_SCHEMA")
    require(observation.get("rubric_sha256") == state["workflow"]["rubric_sha256"],
            "RUBRIC_MISMATCH")
    require(state["workflow"]["current_gate"] == gate, "INVALID_TRANSITION")
    require(is_full_sha(observation.get("base_sha")), "INVALID_SHA")
    require(is_full_sha(observation.get("head_sha")), "INVALID_SHA")
    if gate == "TASK_REVIEW":
        task = task_for(state, observation.get("task_id"))
        require(task["status"] == "REVIEWING", "INVALID_TRANSITION")
        expected_base = task["task_base"]
        expected_head = task["task_head"]
        expected_attempt = task["review_attempt"]
    else:
        expected_base = state["workflow"]["initial_base"]
        expected_head = state["workflow"]["current_head"]
        expected_attempt = (
            task_for(state, state["workflow"]["current_task_id"])["review_attempt"]
            if state["workflow"]["status"] == "REVIEWING"
            else state["artifacts"]["gate_attempts"][gate]
        )
    require(observation.get("base_sha") == expected_base, "BASE_MISMATCH")
    require(observation.get("head_sha") == expected_head, "HEAD_MISMATCH")
    require(current_head(state["workflow"]["repo_root"]) == expected_head, "HEAD_MISMATCH")
    attempt = observation.get("attempt")
    require(protocol_integer(attempt), "INVALID_OBSERVATION_SCHEMA")
    require(attempt == expected_attempt, "ATTEMPT_MISMATCH")
    for finding in observation["findings"]:
        validate_finding(finding, observation)
    return task if gate == "TASK_REVIEW" else None


def blocker_eligible(finding):
    return (
        finding["status"] == "OPEN"
        and finding["origin"] in {"NEW", "REGRESSION"}
        and finding["blocking"]
        and finding["severity"] in {"CRITICAL", "IMPORTANT"}
    )


def find_existing_by_fingerprint(state, fingerprint):
    for finding_id, existing in state["findings"].items():
        if existing.get("fingerprint") == fingerprint:
            return finding_id, existing
    return None, None


def resolve_owner(state, finding, observation, task):
    if not blocker_eligible(finding):
        if observation["gate"] == "TASK_REVIEW":
            return str(observation["task_id"])
        owners = owner_for_required_paths(state, finding["required_fix_paths"])
        if len(owners) == 1:
            finding["owner_task_id"] = int(owners[0]) if owners[0].isdigit() else owners[0]
            return owners[0]
        return None
    if observation["gate"] == "TASK_REVIEW":
        require(str(finding["owner_task_id"]) == str(observation["task_id"]),
                "INVALID_FINDING_SCHEMA")
        paths = finding["required_fix_paths"]
        if not set(paths) <= task_paths(task):
            return "SCOPE_BLOCKED"
        return str(observation["task_id"])
    owners = owner_for_required_paths(state, finding["required_fix_paths"])
    if len(owners) != 1:
        return "NEEDS_DECISION"
    finding["owner_task_id"] = int(owners[0]) if owners[0].isdigit() else owners[0]
    return owners[0]


def set_halted(state, task_id, halted, event, observation, finding_ids=None):
    task = task_for(state, task_id) if task_id is not None else None
    before = task["status"] if task else state["workflow"]["status"]
    if task:
        task["status"] = halted
    state["workflow"]["status"] = halted
    append_history(state, event, before, halted, task_id=task_id,
                   gate=observation["gate"], attempt=observation["attempt"],
                   base_sha=observation["base_sha"], head_sha=observation["head_sha"],
                   finding_ids=finding_ids)


def next_task(state, current_task_id):
    order = state["artifacts"]["task_order"]
    index = order.index(str(current_task_id))
    return order[index + 1] if index + 1 < len(order) else None


def import_findings(state, observation, task):
    imported_ids = []
    blocking_by_owner = {}
    contract_dispute = False
    needs_decision = False
    scope_blocked = False
    for raw in observation["findings"]:
        finding = copy.deepcopy(raw)
        if finding["origin"] == "BASELINE":
            finding["blocking"] = False
            finding["status"] = "BASELINE"
        elif finding["severity"] == "MINOR" or not finding["blocking"]:
            finding["blocking"] = False
        if finding["origin"] == "OUT_OF_CONTRACT":
            contract_dispute = True
            finding["blocking"] = False

        owner = resolve_owner(state, finding, observation, task)
        if owner == "NEEDS_DECISION":
            needs_decision = True
        elif owner == "SCOPE_BLOCKED":
            scope_blocked = True
        fingerprint = finding_fingerprint(finding)
        existing_same_id = state["findings"].get(finding["id"])
        if existing_same_id and existing_same_id.get("fingerprint") != fingerprint:
            raise ReviewStateError("FINDING_ID_COLLISION", finding["id"])
        canonical_id, previous = find_existing_by_fingerprint(state, fingerprint)
        if previous and previous.get("status") == "RESOLVED" and finding["status"] == "OPEN":
            finding["origin"] = "REGRESSION"
        finding["fingerprint"] = fingerprint
        if previous:
            history = copy.deepcopy(previous.get("observation_history", []))
        else:
            history = []
        history.append({
            "gate": observation["gate"],
            "attempt": observation["attempt"],
            "status": finding["status"],
            "head_sha": observation["head_sha"],
            "observed_id": finding["id"],
        })
        canonical_id = canonical_id or finding["id"]
        finding["id"] = canonical_id
        finding["observation_history"] = history
        state["findings"][canonical_id] = finding
        if canonical_id not in imported_ids:
            imported_ids.append(canonical_id)
        if finding["status"] == "BASELINE" and owner not in {None, "NEEDS_DECISION", "SCOPE_BLOCKED"}:
            owner_task = task_for(state, owner)
            if canonical_id not in owner_task["baseline_findings"]:
                owner_task["baseline_findings"].append(canonical_id)
        if finding["status"] == "RESOLVED" and owner not in {None, "NEEDS_DECISION", "SCOPE_BLOCKED"}:
            owner_task = task_for(state, owner)
            if canonical_id not in owner_task["resolved_findings"]:
                owner_task["resolved_findings"].append(canonical_id)
        if blocker_eligible(finding) and owner not in {None, "NEEDS_DECISION", "SCOPE_BLOCKED"}:
            owner_blockers = blocking_by_owner.setdefault(owner, [])
            if canonical_id not in owner_blockers:
                owner_blockers.append(canonical_id)
    return imported_ids, blocking_by_owner, contract_dispute, needs_decision, scope_blocked


def validate_targeted_rereview(state, observation):
    targeted_ids = []
    for task in state["tasks"].values():
        targeted_ids.extend(task["authorized_finding_ids"])
    if not targeted_ids:
        return set(), set()
    observations = {finding["id"]: finding for finding in observation["findings"]}
    missing = sorted(set(targeted_ids) - set(observations))
    require(not missing, "MISSING_TARGETED_FINDING", missing)
    for finding_id in targeted_ids:
        require(observations[finding_id]["status"] in {"OPEN", "RESOLVED"},
                "INVALID_FINDING_SCHEMA")
    previous = {
        state["findings"][finding_id]["fingerprint"]
        for finding_id in targeted_ids
        if finding_id in state["findings"] and state["findings"][finding_id]["status"] == "OPEN"
    }
    current = set()
    for finding_id in targeted_ids:
        finding = observations[finding_id]
        if finding["status"] != "OPEN":
            continue
        candidate = copy.deepcopy(finding)
        if observation["gate"] in FINAL_GATES:
            owners = owner_for_required_paths(state, candidate["required_fix_paths"])
            require(len(owners) == 1, "INVALID_FINDING_SCHEMA")
            candidate["owner_task_id"] = int(owners[0]) if owners[0].isdigit() else owners[0]
        current.add(finding_fingerprint(candidate))
    return previous, current


def advance_after_pass(state, task_id, observation):
    task = task_for(state, task_id)
    before = task["status"]
    task["status"] = "PASSED"
    task["open_blocking_findings"] = []
    task["authorized_finding_ids"] = []
    following = next_task(state, task_id)
    if following is not None:
        state["workflow"]["current_task_id"] = int(following) if following.isdigit() else following
        state["workflow"]["status"] = "READY"
        state["workflow"]["current_gate"] = "TASK_IMPLEMENTATION"
        after = "READY"
    else:
        state["workflow"]["status"] = "FINAL_REVIEW"
        state["workflow"]["current_gate"] = "FINAL_REVIEW"
        state["workflow"]["current_task_id"] = None
        after = "FINAL_REVIEW"
    append_history(state, "TASK_REVIEW_PASSED", before, after, task_id=task_id,
                   gate="TASK_REVIEW", attempt=observation["attempt"],
                   base_sha=observation["base_sha"], head_sha=observation["head_sha"])


def advance_final_gate(state, observation):
    gate = observation["gate"]
    next_gate = {
        "FINAL_REVIEW": "STRUCTURAL_VALIDATION",
        "STRUCTURAL_VALIDATION": "BEHAVIORAL_VALIDATION",
        "BEHAVIORAL_VALIDATION": "SQUASH_APPROVAL",
    }[gate]
    before = state["workflow"]["status"]
    state["workflow"]["status"] = next_gate
    state["workflow"]["current_gate"] = next_gate
    append_history(state, "GATE_PASSED", before, next_gate, gate=gate,
                   attempt=observation["attempt"], base_sha=observation["base_sha"],
                   head_sha=observation["head_sha"])


def validate_controller_resolutions(state, observation):
    cannot = observation["cannot_verify"]
    resolutions = observation["controller_resolutions"]
    cannot_ids = []
    for item in cannot:
        require(isinstance(item, dict) and non_empty_string(item.get("id")),
                "INVALID_CONTROLLER_RESOLUTION")
        cannot_ids.append(item["id"])
    require(len(cannot_ids) == len(set(cannot_ids)), "INVALID_CONTROLLER_RESOLUTION")
    resolution_ids = []
    for item in resolutions:
        require(
            isinstance(item, dict)
            and non_empty_string(item.get("id"))
            and non_empty_string(item.get("action"))
            and non_empty_string(item.get("reason")),
            "INVALID_CONTROLLER_RESOLUTION",
        )
        resolution_ids.append(item["id"])
    require(len(resolution_ids) == len(set(resolution_ids)), "INVALID_CONTROLLER_RESOLUTION")
    require(set(resolution_ids) <= set(cannot_ids), "INVALID_CONTROLLER_RESOLUTION")
    existing_ids = {
        item.get("id") for item in state["artifacts"].get("controller_resolutions", [])
        if isinstance(item, dict)
    }
    require(not (set(resolution_ids) & existing_ids), "INVALID_CONTROLLER_RESOLUTION")
    if resolutions:
        state["artifacts"].setdefault("controller_resolutions", []).extend(
            copy.deepcopy(resolutions)
        )
    return [item for item in cannot if item["id"] not in set(resolution_ids)]


def cmd_import_review(args, state):
    observation = load_json_object(args.observation)
    task = validate_observation(state, observation)
    previous_open, current_targeted_open = validate_targeted_rereview(state, observation)
    imported_ids, blockers, dispute, needs_decision, scope_blocked = import_findings(
        state, observation, task
    )
    gate = observation["gate"]
    if gate in FINAL_GATES:
        state["artifacts"]["gate_attempts"][gate] = observation["attempt"]

    affected_task_id = str(observation["task_id"]) if gate == "TASK_REVIEW" else None
    if dispute:
        if affected_task_id is None:
            affected_task_id = next(iter(blockers), None)
        set_halted(state, affected_task_id, "HALTED_CONTRACT_DISPUTE",
                   "CONTRACT_DISPUTE", observation, imported_ids)
        return {"status": "HALTED_CONTRACT_DISPUTE", "finding_ids": sorted(imported_ids)}
    if needs_decision:
        set_halted(state, affected_task_id, "HALTED_NEEDS_DECISION",
                   "OWNER_NEEDS_DECISION", observation, imported_ids)
        return {"status": "HALTED_NEEDS_DECISION", "finding_ids": sorted(imported_ids)}
    if scope_blocked:
        set_halted(state, affected_task_id, "HALTED_SCOPE_BLOCKED",
                   "SCOPE_BLOCKED", observation, imported_ids)
        return {"status": "HALTED_SCOPE_BLOCKED", "finding_ids": sorted(imported_ids)}

    unresolved_cannot = validate_controller_resolutions(state, observation)
    if unresolved_cannot:
        target_id = affected_task_id or next(iter(blockers), None)
        if target_id is not None:
            task_for(state, target_id)["cannot_verify"] = unresolved_cannot
        set_halted(state, target_id, "HALTED_NEEDS_DECISION",
                   "CANNOT_VERIFY", observation, imported_ids)
        return {"status": "HALTED_NEEDS_DECISION", "cannot_verify": unresolved_cannot}

    open_ids = sorted(finding_id for ids in blockers.values() for finding_id in ids)
    resolved_ids = {
        finding["id"] for finding in observation["findings"]
        if finding.get("status") == "RESOLVED"
    }
    for candidate in state["tasks"].values():
        candidate["open_blocking_findings"] = [
            finding_id for finding_id in candidate["open_blocking_findings"]
            if finding_id not in resolved_ids
        ]
    if previous_open:
        all_current_fingerprints = {
            state["findings"][finding_id]["fingerprint"] for finding_id in open_ids
        }
        new_fingerprints = all_current_fingerprints - previous_open
        if previous_open <= current_targeted_open and new_fingerprints:
            target_id = next(iter(blockers), affected_task_id)
            set_halted(state, target_id, "HALTED_REGRESSION",
                       "REGRESSION_NO_REDUCTION", observation, open_ids)
            return {"status": "HALTED_REGRESSION", "finding_ids": open_ids}
        if previous_open == current_targeted_open:
            target_id = next(iter(blockers), affected_task_id)
            set_halted(state, target_id, "HALTED_NO_PROGRESS",
                       "NO_PROGRESS", observation, open_ids)
            return {"status": "HALTED_NO_PROGRESS", "finding_ids": open_ids}

    if open_ids:
        if len(blockers) != 1:
            affected = affected_task_id or next(iter(blockers), None)
            set_halted(state, affected, "HALTED_NEEDS_DECISION",
                       "AMBIGUOUS_FIX_OWNER", observation, open_ids)
            return {"status": "HALTED_NEEDS_DECISION", "finding_ids": open_ids}
        owner = next(iter(blockers))
        owner_task = task_for(state, owner)
        owner_task["open_blocking_findings"] = sorted(blockers[owner])
        owner_task["previous_open_blocker_fingerprints"] = sorted(
            state["findings"][finding_id]["fingerprint"] for finding_id in blockers[owner]
        )
        owner_task["authorized_finding_ids"] = []
        before = owner_task["status"]
        owner_task["status"] = "FIX_REQUIRED"
        state["workflow"]["status"] = "FIX_REQUIRED"
        state["workflow"]["current_task_id"] = int(owner) if owner.isdigit() else owner
        state["workflow"]["current_gate"] = gate
        append_history(state, "REVIEW_FAILED", before, "FIX_REQUIRED", task_id=owner,
                       gate=gate, attempt=observation["attempt"],
                       base_sha=observation["base_sha"], head_sha=observation["head_sha"],
                       finding_ids=open_ids)
        return {"status": "FIX_REQUIRED", "task_id": owner, "finding_ids": open_ids}

    require(observation["verdict"] == "PASS", "VERDICT_FINDING_MISMATCH")
    if affected_task_id is not None:
        task_for(state, affected_task_id)["cannot_verify"] = []
    if gate == "TASK_REVIEW":
        advance_after_pass(state, str(observation["task_id"]), observation)
    else:
        owner_id = state["workflow"]["current_task_id"]
        for candidate in state["tasks"].values():
            candidate["authorized_finding_ids"] = []
            candidate["open_blocking_findings"] = []
        if owner_id is not None:
            owner = task_for(state, owner_id)
            owner["status"] = "PASSED"
            owner["previous_open_blocker_fingerprints"] = []
            owner["cannot_verify"] = []
        state["workflow"]["current_task_id"] = None
        advance_final_gate(state, observation)
        if owner_id is not None:
            state["history"][-1]["task_id"] = int(owner_id) if str(owner_id).isdigit() else owner_id
            state["history"][-1]["finding_ids"] = sorted(resolved_ids)
    return {"status": state["workflow"]["status"], "finding_ids": sorted(imported_ids)}


def cmd_needs_fix(args, state):
    task = task_for(state, args.task_id)
    ids = sorted(task["open_blocking_findings"])
    allowed = task["status"] == "FIX_REQUIRED" and bool(ids) and task["fix_budget"]["remaining"] > 0
    return {
        "task_id": args.task_id,
        "finding_ids": ids,
        "owner_task_id": args.task_id,
        "used": task["fix_budget"]["used"],
        "remaining": task["fix_budget"]["remaining"],
        "allowed": allowed,
    }


def cmd_authorize_fix(args, state):
    task = task_for(state, args.task_id)
    require(task["status"] == "FIX_REQUIRED", "INVALID_TRANSITION")
    try:
        supplied = json.loads(args.finding_ids_json)
    except json.JSONDecodeError as exc:
        raise ReviewStateError("INVALID_FINDING_IDS", str(exc)) from exc
    require(isinstance(supplied, list) and all(isinstance(item, str) for item in supplied),
            "INVALID_FINDING_IDS")
    expected = sorted(task["open_blocking_findings"])
    require(sorted(supplied) == expected and len(set(supplied)) == len(supplied),
            "FINDING_SET_MISMATCH")
    if task["fix_budget"]["remaining"] <= 0:
        before = task["status"]
        task["status"] = "HALTED_BUDGET_EXHAUSTED"
        state["workflow"]["status"] = "HALTED_BUDGET_EXHAUSTED"
        append_history(state, "FIX_BUDGET_EXHAUSTED", before, "HALTED_BUDGET_EXHAUSTED",
                       task_id=args.task_id, gate=state["workflow"]["current_gate"],
                       attempt=task["fix_attempt"], base_sha=task["task_base"],
                       head_sha=task["task_head"], finding_ids=expected)
        raise ReviewStateError("FIX_BUDGET_EXHAUSTED", {"persist_state": state})
    task["fix_budget"]["used"] += 1
    task["fix_budget"]["remaining"] -= 1
    task["fix_attempt"] += 1
    task["authorized_finding_ids"] = expected
    task["expected_fix_subject"] = derive_expected_fix_subject_for_task(state, str(args.task_id), task)
    before = transition_task(state, args.task_id, "FIXING")
    append_history(state, "FIX_AUTHORIZED", before, "FIXING", task_id=args.task_id,
                   gate=state["workflow"]["current_gate"], attempt=task["fix_attempt"],
                   base_sha=task["task_base"], head_sha=task["task_head"],
                   finding_ids=expected)
    return {"task_id": args.task_id, "finding_ids": expected, "attempt": task["fix_attempt"]}


def next_action(state):
    status = state["workflow"]["status"]
    gate = state["workflow"]["current_gate"]
    if status == "REVIEWING" and gate in FINAL_GATES:
        return {
            "FINAL_REVIEW": "RUN_FINAL_REVIEW",
            "STRUCTURAL_VALIDATION": "RUN_STRUCTURAL_VALIDATION",
            "BEHAVIORAL_VALIDATION": "RUN_BEHAVIORAL_VALIDATION",
        }[gate]
    if status == "READY":
        return "DISPATCH_IMPLEMENTER"
    if status == "IMPLEMENTING":
        return "DISPATCH_IMPLEMENTER"
    if status == "REVIEWING":
        return "DISPATCH_REVIEWER"
    if status == "FIX_REQUIRED":
        return "DISPATCH_FIXER"
    if status == "FIXING":
        return "DISPATCH_FIXER"
    if status == "FINAL_REVIEW":
        return "RUN_FINAL_REVIEW"
    if status == "STRUCTURAL_VALIDATION":
        return "RUN_STRUCTURAL_VALIDATION"
    if status == "BEHAVIORAL_VALIDATION":
        return "RUN_BEHAVIORAL_VALIDATION"
    if status == "SQUASH_APPROVAL":
        return "REQUEST_SQUASH_APPROVAL"
    if status in {"COMPLETE", "COMPLETE_UNSQUASHED"}:
        return "COMPLETE"
    if status.startswith(HALTED_PREFIX):
        return "HALT"
    return "HALT"


def cmd_advance_gate(args, state):
    workflow = state["workflow"]
    require(args.gate == "SQUASH_APPROVAL", "INVALID_GATE")
    require(workflow["status"] == workflow["current_gate"] == "SQUASH_APPROVAL",
            "INVALID_TRANSITION")
    require(args.result in {"SQUASHED", "UNSQUASHED"}, "INVALID_RESULT")
    validate_commit(workflow["repo_root"], args.head)
    actual = current_head(workflow["repo_root"])
    require(actual == args.head, "HEAD_MISMATCH")
    if args.result == "UNSQUASHED":
        require(args.head == workflow["current_head"], "HEAD_MISMATCH")
        status = "COMPLETE_UNSQUASHED"
    else:
        status = "COMPLETE"
        workflow["current_head"] = args.head
    before = workflow["status"]
    workflow["status"] = status
    append_history(state, "SQUASH_DECISION_RECORDED", before, status,
                   gate="SQUASH_APPROVAL", attempt=1,
                   base_sha=workflow["initial_base"], head_sha=args.head)
    return {"status": status, "head": args.head}


def cmd_status(args, state):
    current_id = state["workflow"]["current_task_id"]
    task = state["tasks"].get(str(current_id)) if current_id is not None else None
    budget = task["fix_budget"] if task else None
    blockers = task["open_blocking_findings"] if task else []
    return {
        "workflow": state["workflow"],
        "current_task": task,
        "budget": budget,
        "open_blocking_findings": blockers,
        "next_action": next_action(state),
    }


def cmd_review_package(args):
    repo = Path(args.repo_root).resolve()
    require(repo.is_dir(), "INVALID_REPO")
    validate_commit(repo, args.base)
    validate_commit(repo, args.head)
    require(args.base != args.head, "HEAD_NOT_CHANGED")
    require_ancestor(repo, args.base, args.head)
    output = Path(args.output)
    require(not output.exists(), "OUTPUT_EXISTS", str(output))
    commits = run_git(repo, "log", "--oneline", "--reverse", f"{args.base}..{args.head}")
    stat = run_git(repo, "diff", "--stat", f"{args.base}..{args.head}")
    diff = run_git(repo, "diff", "-U10", f"{args.base}..{args.head}")
    text = "\n".join([
        f"# Review package: {args.base}..{args.head}", "", "## Commits", "",
        commits, "", "## Files changed", "", stat, "", "## Diff", "", diff, "",
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise ReviewStateError("OUTPUT_EXISTS", str(output)) from exc
    commit_count = int(run_git(repo, "rev-list", "--count", f"{args.base}..{args.head}"))
    return {
        "output": str(output.resolve()),
        "base": args.base,
        "head": args.head,
        "commit_count": commit_count,
        "size_bytes": output.stat().st_size,
    }


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    command = subparsers.add_parser("init")
    for option in ("state", "repo-root", "spec", "plan", "rubric-source", "rubric-snapshot",
                   "scope", "ticket", "initial-base"):
        command.add_argument(f"--{option}", required=True)

    command = subparsers.add_parser("start-task")
    command.add_argument("--state", required=True)
    command.add_argument("--task-id", required=True)
    command.add_argument("--expected-head", required=True)

    command = subparsers.add_parser("record-implementation")
    command.add_argument("--state", required=True)
    command.add_argument("--task-id", required=True)
    command.add_argument("--base-head", required=True)
    command.add_argument("--new-head", required=True)
    command.add_argument("--report", required=True)
    command.add_argument("--deterministic-evidence")

    command = subparsers.add_parser("record-fix")
    command.add_argument("--state", required=True)
    command.add_argument("--task-id", required=True)
    command.add_argument("--base-head", required=True)
    command.add_argument("--new-head", required=True)
    command.add_argument("--report", required=True)

    command = subparsers.add_parser("import-review")
    command.add_argument("--state", required=True)
    command.add_argument("--observation", required=True)

    command = subparsers.add_parser("needs-fix")
    command.add_argument("--state", required=True)
    command.add_argument("--task-id", required=True)

    command = subparsers.add_parser("authorize-fix")
    command.add_argument("--state", required=True)
    command.add_argument("--task-id", required=True)
    command.add_argument("--finding-ids-json", required=True)

    command = subparsers.add_parser("advance-gate")
    command.add_argument("--state", required=True)
    command.add_argument("--gate", required=True)
    command.add_argument("--result", required=True)
    command.add_argument("--head", required=True)

    for name in ("next-action", "status"):
        command = subparsers.add_parser(name)
        command.add_argument("--state", required=True)

    command = subparsers.add_parser("review-package")
    command.add_argument("--repo-root", required=True)
    command.add_argument("--base", required=True)
    command.add_argument("--head", required=True)
    command.add_argument("--output", required=True)
    return parser


def dispatch(args):
    if args.command == "init":
        return cmd_init(args), None
    if args.command == "review-package":
        return cmd_review_package(args), None
    state = load_and_validate_state(args.state)
    if args.command == "start-task":
        payload = cmd_start_task(args, state)
    elif args.command == "record-implementation":
        payload = cmd_record_implementation(args, state)
    elif args.command == "record-fix":
        payload = cmd_record_fix(args, state)
    elif args.command == "import-review":
        payload = cmd_import_review(args, state)
    elif args.command == "needs-fix":
        return cmd_needs_fix(args, state), None
    elif args.command == "authorize-fix":
        payload = cmd_authorize_fix(args, state)
    elif args.command == "advance-gate":
        payload = cmd_advance_gate(args, state)
    elif args.command == "next-action":
        return {"action": next_action(state)}, None
    elif args.command == "status":
        return cmd_status(args, state), None
    else:
        raise ReviewStateError("UNKNOWN_COMMAND")
    return payload, state


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload, state = dispatch(args)
        if state is not None:
            atomic_write_json(args.state, state)
        print_json({"ok": True, **payload})
        return 0
    except ReviewStateError as exc:
        persist = exc.detail.get("persist_state") if isinstance(exc.detail, dict) else None
        if persist is not None and hasattr(args, "state"):
            atomic_write_json(args.state, persist)
            detail = {key: value for key, value in exc.detail.items() if key != "persist_state"}
        else:
            detail = exc.detail
        error = {"ok": False, "code": exc.code}
        if detail not in (None, {}):
            error["detail"] = detail
        print_json(error, sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
