#!/usr/bin/env python3
"""
Nuclio deterministic packet helper.

## Contents

- [Protocol errors and JSON helpers](#protocol-errors-and-json-helpers)
- [Input loading and freshness validation](#input-loading-and-freshness-validation)
- [Role packet builders](#role-packet-builders)
- [Packet writes and identity](#packet-writes-and-identity)
- [CLI](#cli)

The helper derives bounded worker, reviewer, completion and finish packets from
already validated contract, context and state identities. It writes only the
explicit output packet path, refuses to overwrite an existing attempt artifact,
never writes product/knowledge/Gate/state files, and never grants approval or
review/fix authority beyond the role-specific packet fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

try:  # pragma: no cover - exercised through tests when jsonschema is present
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

HASH_CHARS = set("0123456789abcdef")
INDEX_TARGETS = {".dev-docs/index.md", ".dev-docs/index.json", ".dev-docs/changes/index.md"}
FINISH_TARGET_GROUPS = ("knowledge_targets", "archive_targets", "index_targets")
FINISH_TARGET_FIELDS = {"path", "before_sha256", "proposed_after_summary", "reason", "source_evidence", "target_language", "language_source"}


class ProtocolError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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


def _language_tag(value: Any, where: str, code: str = "INVALID_INPUT") -> str:
    try:
        text = _non_empty(value, where)
    except ProtocolError as exc:
        raise ProtocolError(code, exc.message, exc.details) from exc
    parts = text.split("-")
    valid = 2 <= len(parts[0]) <= 8 and parts[0].isalpha()
    valid = valid and all(1 <= len(part) <= 8 and part.isalnum() for part in parts[1:])
    if not valid:
        raise ProtocolError(code, f"{where} must be a BCP-47 style language tag")
    return text


def _require_sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in HASH_CHARS for ch in value):
        raise ProtocolError("INVALID_IDENTITY", f"{where} must be a lowercase sha256")
    return value


def _require_version(value: Any, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ProtocolError("INVALID_STATE_VERSION", f"{where} must be a positive integer")
    return value


def _load_json_value(raw: str, where: str) -> Any:
    text = raw.strip()
    if text.startswith(("{", "[", '"')):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProtocolError("INVALID_JSON_ARGUMENT", f"{where} is not valid JSON") from exc
    path = Path(raw)
    if path.suffix.lower() == ".md":
        raise ProtocolError("INVALID_JSON_ARGUMENT", f"{where} must be canonical JSON, not Markdown", {"path": raw})
    if not path.exists() or not path.is_file():
        raise ProtocolError("INPUT_NOT_FOUND", f"{where} path must name an existing file", {"path": raw})
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError("INVALID_JSON_FILE", f"{where} file is not valid JSON", {"path": raw}) from exc


def normalize_path(value: Any, where: str = "path") -> str:
    raw = _non_empty(value, where)
    if raw.startswith(("/", "~")) or raw in {"", ".", "./", "plugins", "src", "docs", ".dev-docs", ".git"}:
        raise ProtocolError("INVALID_PATH", "path must be a bounded repo-relative concrete file", {"path": raw})
    if any(char in raw for char in "*?[]{}"):
        raise ProtocolError("INVALID_PATH", "path must not contain glob characters", {"path": raw})
    parts = PurePosixPath(raw).parts
    if ".." in parts or raw.endswith("/"):
        raise ProtocolError("INVALID_PATH", "path must not traverse or name a directory", {"path": raw})
    normalized = posixpath.normpath(raw)
    if normalized != raw or normalized == ".git" or normalized.startswith(".git/"):
        raise ProtocolError("INVALID_PATH", "path must be normalized and must not touch .git", {"path": raw})
    return normalized


def _repo(path: str | Path) -> Path:
    repo = Path(path).resolve()
    if not repo.exists() or not repo.is_dir():
        raise ProtocolError("INVALID_REPO", "repo must be an existing directory", {"repo": str(path)})
    return repo


def _contract_identity(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "change_id": _non_empty(contract.get("change_id"), "contract.change_id"),
        "contract_sha256": _require_sha(contract.get("sha256", contract.get("contract_sha256")), "contract.sha256"),
        "contract_version": _non_empty(contract.get("version", contract.get("contract_version", "v1")), "contract.version"),
        "output_language": _language_tag(contract.get("output_language"), "contract.output_language"),
    }


def _context_identity(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "context_fingerprint": _require_sha(context.get("fingerprint", context.get("context_fingerprint")), "context.fingerprint"),
        "entries": [str(item) for item in context.get("entries", [])],
    }


def _fresh_inputs(contract: dict[str, Any], context: dict[str, Any], state: dict[str, Any], expected_state_version: int | None = None) -> dict[str, Any]:
    contract = _require_object(contract, "contract")
    context = _require_object(context, "context")
    state = _require_object(state, "state")
    contract_id = _contract_identity(contract)
    context_id = _context_identity(context)
    state_version = _require_version(state.get("state_version"), "state.state_version")
    if expected_state_version is not None and state_version != expected_state_version:
        raise ProtocolError("STALE_STATE", "state_version does not match expected freshness baseline", {"expected": expected_state_version, "actual": state_version})
    state_contract = _require_object(state.get("contract"), "state.contract")
    state_context = _require_object(state.get("context"), "state.context")
    if state.get("change_id") != contract_id["change_id"]:
        raise ProtocolError("STALE_CONTRACT", "contract change_id does not match state")
    if state_contract.get("sha256") != contract_id["contract_sha256"]:
        raise ProtocolError("STALE_CONTRACT", "contract hash does not match state", {"expected": state_contract.get("sha256"), "actual": contract_id["contract_sha256"]})
    if state_context.get("fingerprint") != context_id["context_fingerprint"]:
        raise ProtocolError("STALE_CONTEXT", "context fingerprint does not match state", {"expected": state_context.get("fingerprint"), "actual": context_id["context_fingerprint"]})
    return {"change_id": contract_id["change_id"], "contract_sha256": contract_id["contract_sha256"], "output_language": contract_id["output_language"], "context_fingerprint": context_id["context_fingerprint"], "context_entries": context_id["entries"], "state_version": state_version}


def _task_contract(contract: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in contract.get("tasks", []):
        if str(task.get("id")) == str(task_id):
            return _require_object(task, "task")
    raise ProtocolError("UNKNOWN_TASK", "task is not present in contract", {"task_id": task_id})


def _task_state(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in state.get("tasks", []):
        if str(task.get("id")) == str(task_id):
            return _require_object(task, "state task")
    raise ProtocolError("UNKNOWN_TASK", "task is not present in state", {"task_id": task_id})


def _ownership_from_task(task: dict[str, Any]) -> list[dict[str, Any]]:
    ownership = []
    for raw in _require_list(task.get("mutation_targets"), "task.mutation_targets"):
        item = _require_object(raw, "task.mutation_targets[]")
        mode = _non_empty(item.get("mode"), "mutation_targets[].mode")
        if mode not in {"create", "modify", "delete"}:
            raise ProtocolError("INVALID_MUTATION_TARGET", "mutation target mode is invalid")
        ownership.append({"path": normalize_path(item.get("path"), "mutation_targets[].path"), "mode": mode})
    if not ownership:
        raise ProtocolError("INVALID_MUTATION_TARGET", "task mutation_targets must not be empty")
    return ownership


def _check_ownership_matches_state(state_task: dict[str, Any], ownership: list[dict[str, Any]]) -> None:
    expected = sorted(normalize_path(path, "state.task.ownership[]") for path in _require_list(state_task.get("ownership"), "state.task.ownership"))
    actual = sorted(item["path"] for item in ownership)
    if expected != actual:
        raise ProtocolError("STALE_OWNERSHIP", "task ownership in contract does not match state", {"expected": expected, "actual": actual})


def acceptance_ids(contract: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(_require_list(contract.get("acceptance"), "contract.acceptance"), 1):
        if isinstance(raw, dict) and isinstance(raw.get("id"), str) and raw["id"].strip():
            acceptance_id = raw["id"].strip()
        else:
            acceptance_id = f"A{index}"
        if acceptance_id in seen:
            raise ProtocolError("INVALID_ACCEPTANCE", "contract acceptance ids must be unique", {"id": acceptance_id})
        seen.add(acceptance_id)
        result.append(acceptance_id)
    if not result:
        raise ProtocolError("INCOMPLETE_ACCEPTANCE", "contract acceptance must not be empty")
    return result


def _validated_acceptance_index(contract: dict[str, Any], acceptance_index: list[Any]) -> list[dict[str, Any]]:
    expected = acceptance_ids(contract)
    expected_set = set(expected)
    entries: dict[str, dict[str, Any]] = {}
    for raw in _require_list(acceptance_index, "acceptance_index"):
        item = _require_object(raw, "acceptance_index[]")
        acceptance_id = _non_empty(item.get("id"), "acceptance_index[].id")
        if acceptance_id in entries:
            raise ProtocolError("INCOMPLETE_ACCEPTANCE", "acceptance index must not contain duplicate ids", {"id": acceptance_id})
        if acceptance_id not in expected_set:
            raise ProtocolError("INCOMPLETE_ACCEPTANCE", "acceptance index contains an unexpected id", {"id": acceptance_id, "expected": expected})
        if item.get("accepted") is not True:
            raise ProtocolError("INCOMPLETE_ACCEPTANCE", "completion packet requires 100% contract acceptance index", {"id": acceptance_id})
        entries[acceptance_id] = dict(item)
    missing = sorted(expected_set - set(entries))
    if missing:
        raise ProtocolError("INCOMPLETE_ACCEPTANCE", "acceptance index must cover every contract acceptance id", {"missing": missing})
    return [entries[item] for item in expected]


def _state_task_heads(state: dict[str, Any]) -> dict[str, str]:
    metadata: dict[str, Any] = {}
    for event in state.get("history", []):
        if event.get("event") == "INITIALIZED" and isinstance(event.get("reason"), str):
            try:
                loaded = json.loads(event["reason"])
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                metadata = loaded
                break
    raw_heads = metadata.get("heads", {}) if isinstance(metadata, dict) else {}
    heads: dict[str, str] = {}
    for task in _require_list(state.get("tasks"), "state.tasks"):
        task_id = str(_require_object(task, "state.tasks[]").get("id"))
        if task_id in raw_heads:
            heads[task_id] = _non_empty(raw_heads[task_id], f"state.heads.{task_id}")
        elif task.get("head") is not None:
            heads[task_id] = _non_empty(task.get("head"), f"state.tasks[{task_id}].head")
        elif task.get("task_head") is not None:
            heads[task_id] = _non_empty(task.get("task_head"), f"state.tasks[{task_id}].task_head")
        else:
            raise ProtocolError("STALE_HEAD", "state is missing a completed Task head", {"task_id": task_id})
    return heads


def _checks(task: dict[str, Any], contract: dict[str, Any], include_change_wide: bool = False) -> dict[str, Any]:
    task_checks = _require_object(task.get("checks", {}), "task.checks") if task else {}
    validation = _require_object(contract.get("validation", {}), "contract.validation")
    result = {"focused": task_checks.get("focused", validation.get("focused", [])), "full": task_checks.get("full", validation.get("full", []))}
    if include_change_wide:
        result["change_wide"] = validation.get("change_wide", [])
    return result


def _context_ids(context: Any, audience: str) -> list[str]:
    if isinstance(context, dict) and isinstance(context.get("split"), dict):
        return [str(item.get("id")) for item in context["split"].get(audience, []) if isinstance(item, dict) and item.get("id")]
    if isinstance(context, dict) and isinstance(context.get("entries"), list):
        return [str(item) for item in context["entries"]]
    return []


def _context_paths(context: Any, audience: str) -> list[str]:
    if isinstance(context, dict) and isinstance(context.get("split"), dict):
        return [normalize_path(item.get("path"), f"context.{audience}.path") for item in context["split"].get(audience, []) if isinstance(item, dict) and item.get("path")]
    return []


def _self_hash(value: dict[str, Any], self_field: str) -> str:
    return sha256_value({key: value[key] for key in sorted(value) if key != self_field})


def _dev_docs_target_path(value: Any, where: str, group: str) -> str:
    path = normalize_path(value, where)
    if group == "knowledge_targets":
        if not path.startswith(".dev-docs/knowledge/"):
            raise ProtocolError("KNOWLEDGE_TARGET_OVERREACH", "knowledge targets must use .dev-docs/knowledge/", {"path": path})
    elif group == "archive_targets":
        if not path.startswith(".dev-docs/archive/"):
            raise ProtocolError("KNOWLEDGE_TARGET_OVERREACH", "archive targets must use .dev-docs/archive/", {"path": path})
    elif group == "index_targets":
        if path not in INDEX_TARGETS:
            raise ProtocolError("KNOWLEDGE_TARGET_OVERREACH", "index targets must use the approved index files", {"path": path})
    else:
        raise ProtocolError("INVALID_FINISH_PLAN", "unknown finish target group", {"group": group})
    if path.startswith(".dev-docs/changes/") and path != ".dev-docs/changes/index.md":
        raise ProtocolError("KNOWLEDGE_TARGET_OVERREACH", "finish targets must not write change-local evidence paths", {"path": path})
    return path


def _finish_targets(finish_plan: dict[str, Any], group: str, output_language: str) -> list[dict[str, Any]]:
    result = []
    for raw in _require_list(finish_plan.get(group), f"finish_plan.{group}"):
        item = _require_object(raw, f"finish_plan.{group}[]")
        missing = sorted(FINISH_TARGET_FIELDS - set(item))
        extras = sorted(set(item) - FINISH_TARGET_FIELDS)
        if missing or extras:
            code = "UNKNOWN_TARGET_LANGUAGE" if any(field in missing for field in ("target_language", "language_source")) else "INVALID_FINISH_PLAN"
            raise ProtocolError(code, "finish target shape mismatch", {"group": group, "missing": missing, "extra": extras})
        before = item.get("before_sha256")
        path = _dev_docs_target_path(item.get("path"), f"finish_plan.{group}[].path", group)
        language_source = item.get("language_source")
        if language_source not in {"contract_output_language", "existing_target", "user_confirmed"}:
            raise ProtocolError("UNKNOWN_TARGET_LANGUAGE", "finish target language_source must be declared before packet derivation", {"group": group, "source": language_source})
        target_language = _language_tag(item.get("target_language"), f"finish_plan.{group}[].target_language", "UNKNOWN_TARGET_LANGUAGE")
        if before is None:
            if target_language != output_language or language_source != "contract_output_language":
                raise ProtocolError("INVALID_TARGET_LANGUAGE", "new finish targets must use packet output_language from contract", {"group": group, "target_language": target_language, "output_language": output_language, "language_source": language_source})
        elif language_source == "contract_output_language":
            raise ProtocolError("INVALID_TARGET_LANGUAGE", "existing finish targets must use existing_target or user_confirmed language_source", {"group": group, "language_source": language_source})
        result.append({
            "path": path,
            "before_sha256": _require_sha(before, f"finish_plan.{group}[].before_sha256") if before is not None else None,
            "proposed_after_summary": _non_empty(item.get("proposed_after_summary"), f"finish_plan.{group}[].proposed_after_summary"),
            "reason": _non_empty(item.get("reason"), f"finish_plan.{group}[].reason"),
            "source_evidence": _require_sha(item.get("source_evidence"), f"finish_plan.{group}[].source_evidence"),
            "target_language": target_language,
            "language_source": language_source,
        })
    return result


def _finish_plan_details(finish_plan: dict[str, Any], output_language: str) -> dict[str, Any]:
    proposal = finish_plan.get("knowledge_proposal")
    if proposal is None:
        proposal = finish_plan.get("proposal")
    if isinstance(proposal, str):
        if not proposal.strip():
            raise ProtocolError("INVALID_FINISH_PLAN", "finish plan knowledge_proposal must be non-empty")
        proposal = proposal.strip()
    elif isinstance(proposal, list):
        if not proposal:
            raise ProtocolError("INVALID_FINISH_PLAN", "finish plan knowledge_proposal must be non-empty")
    elif isinstance(proposal, dict):
        if not proposal:
            raise ProtocolError("INVALID_FINISH_PLAN", "finish plan knowledge_proposal must be non-empty")
    else:
        raise ProtocolError("INVALID_FINISH_PLAN", "finish plan knowledge_proposal must be a non-empty string, array or object")
    archive_intent = _non_empty(finish_plan.get("archive_intent"), "finish_plan.archive_intent")
    grouped_targets = {group: _finish_targets(finish_plan, group, output_language) for group in FINISH_TARGET_GROUPS}
    if not any(grouped_targets.values()):
        raise ProtocolError("INVALID_FINISH_PLAN", "finish plan must include at least one approved target")
    all_paths = [item["path"] for group in FINISH_TARGET_GROUPS for item in grouped_targets[group]]
    if len(all_paths) != len(set(all_paths)):
        raise ProtocolError("INVALID_FINISH_PLAN", "finish targets must not duplicate or overlap", {"paths": sorted(all_paths)})
    return {"knowledge_proposal": proposal, **grouped_targets, "archive_intent": archive_intent}


def _range(base: str, head: str | None = None, expected_dirty_state: str = "clean") -> dict[str, Any]:
    result = {"base_head": _non_empty(base, "base"), "expected_dirty_state": expected_dirty_state}
    if head is not None:
        result["new_head"] = _non_empty(head, "head")
    return result


def schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "packet.schema.json"


def validate_packet_schema(packet: dict[str, Any]) -> None:
    if jsonschema is None:
        return
    schema = json.loads(schema_path().read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(packet)
    except jsonschema.ValidationError as exc:
        raise ProtocolError("INVALID_PACKET_SCHEMA", "generated packet does not conform to packet.schema.json", {"path": "/".join(str(part) for part in exc.absolute_path), "message": exc.message}) from exc


def _finalize_packet(packet: dict[str, Any]) -> dict[str, Any]:
    packet["packet_id"] = _packet_id(packet)
    validate_packet_schema(packet)
    return packet


def worker_packet(repo_path: str | Path, contract: dict[str, Any], context: dict[str, Any], state: dict[str, Any], task_id: str, base: str, head: str, handoff_snapshots: list[Any], expected_state_version: int | None = None) -> dict[str, Any]:
    _repo(repo_path)
    fresh = _fresh_inputs(contract, context, state, expected_state_version)
    task = _task_contract(contract, task_id)
    state_task = _task_state(state, task_id)
    ownership = _ownership_from_task(task)
    _check_ownership_matches_state(state_task, ownership)
    worker_context = _context_ids(context, "worker")
    if not worker_context:
        worker_context = fresh["context_entries"]
    packet = {
        "schema_version": 1,
        "role": "worker",
        "change_id": fresh["change_id"],
        "contract_sha256": fresh["contract_sha256"],
        "context_fingerprint": fresh["context_fingerprint"],
        "state_version": fresh["state_version"],
        "output_language": fresh["output_language"],
        "task_id": str(task_id),
        "ownership": ownership,
        "range": _range(base, expected_dirty_state="clean"),
        "snapshots": _require_list(handoff_snapshots, "handoff_snapshots"),
        "checks": _checks(task, contract),
        "handoffs": sorted(set(task.get("handoffs", {}).get("inputs", []) + worker_context)),
    }
    return _finalize_packet(packet)


def reviewer_packet(repo_path: str | Path, contract: dict[str, Any], context: dict[str, Any], state: dict[str, Any], task_id: str, base: str, head: str, mutation_map_doc: dict[str, Any], validation_evidence: dict[str, Any], interface_snapshots: list[Any], expected_state_version: int | None = None) -> dict[str, Any]:
    _repo(repo_path)
    fresh = _fresh_inputs(contract, context, state, expected_state_version)
    task = _task_contract(contract, task_id)
    state_task = _task_state(state, task_id)
    ownership = _ownership_from_task(task)
    _check_ownership_matches_state(state_task, ownership)
    mutation = _require_object(mutation_map_doc.get("mutation_map", mutation_map_doc), "mutation_map")
    blockers = mutation.get("blockers", [])
    if blockers:
        raise ProtocolError("MUTATION_OVERREACH", "reviewer packet cannot be derived for overreaching mutation map", {"blockers": blockers})
    review_context = _context_ids(context, "reviewer")
    packet = {
        "schema_version": 1,
        "role": "reviewer",
        "change_id": fresh["change_id"],
        "contract_sha256": fresh["contract_sha256"],
        "context_fingerprint": fresh["context_fingerprint"],
        "state_version": fresh["state_version"],
        "output_language": fresh["output_language"],
        "task_id": str(task_id),
        "ownership": [{"path": item["path"], "mode": "read"} for item in ownership],
        "range": _range(base, head, expected_dirty_state="clean"),
        "snapshots": _require_list(interface_snapshots, "interface_snapshots"),
        "checks": _checks(task, contract),
        "review_targets": sorted(set(mutation.get("changed_paths", []) + review_context + list(validation_evidence.get("evidence_paths", [])))),
        "mutation_map_sha256": _require_sha(mutation.get("sha256"), "mutation_map.sha256"),
    }
    return _finalize_packet(packet)


def completion_packet(repo_path: str | Path, contract: dict[str, Any], context: dict[str, Any], state: dict[str, Any], base: str, head: str, mutation_map_doc: dict[str, Any], completed_tasks: list[Any], acceptance_index: list[Any], validation_evidence: dict[str, Any], remaining_risks: list[Any], expected_state_version: int | None = None) -> dict[str, Any]:
    _repo(repo_path)
    fresh = _fresh_inputs(contract, context, state, expected_state_version)
    state_task_items = _require_list(state.get("tasks"), "state.tasks")
    if any(_require_object(task, "state.tasks[]").get("status") != "completed" for task in state_task_items):
        raise ProtocolError("TASKS_INCOMPLETE", "completion packet requires all state tasks completed")
    state_ids = {str(_require_object(task, "state.tasks[]").get("id")) for task in state_task_items}
    expected_heads = _state_task_heads(state)
    task_heads: dict[str, str] = {}
    task_evidence: dict[str, str] = {}
    for raw in _require_list(completed_tasks, "completed_tasks"):
        item = _require_object(raw, "completed_tasks[]")
        task_id = _non_empty(str(item.get("task_id", "")), "completed_tasks[].task_id")
        if task_id in task_heads:
            raise ProtocolError("INVALID_INPUT", "completed_tasks must not contain duplicate task ids", {"task_id": task_id})
        task_heads[task_id] = _non_empty(item.get("head"), "completed_tasks[].head")
        task_evidence[task_id] = _require_sha(item.get("evidence_sha256"), "completed_tasks[].evidence_sha256")
    completed_ids = set(task_heads)
    evidence_ids = set(task_evidence)
    if completed_ids != state_ids or evidence_ids != state_ids:
        raise ProtocolError("TASKS_INCOMPLETE", "completion packet must include every completed Task head/evidence", {"expected": sorted(state_ids), "actual_heads": sorted(completed_ids), "actual_evidence": sorted(evidence_ids)})
    if task_heads != expected_heads:
        raise ProtocolError("STALE_HEAD", "completion task_heads must match state current Task heads", {"expected": expected_heads, "actual": task_heads})
    accepted = _validated_acceptance_index(contract, acceptance_index)
    acceptance_index_sha256 = sha256_value(accepted)
    task_evidence_sha256 = sha256_value(dict(sorted(task_evidence.items())))
    mutation = _require_object(mutation_map_doc.get("mutation_map", mutation_map_doc), "mutation_map")
    if mutation.get("blockers"):
        raise ProtocolError("MUTATION_OVERREACH", "completion packet cannot be derived with overreach blockers", {"blockers": mutation.get("blockers")})
    handoffs = []
    for task_id, task_head in sorted(task_heads.items()):
        handoffs.append(f"task:{task_id}@{task_head}")
        handoffs.append(f"evidence:{task_evidence[task_id]}")
    handoffs.extend(_context_ids(context, "completion"))
    handoffs.extend(str(item) for item in validation_evidence.get("evidence_paths", []))
    handoffs.extend(f"risk:{idx}" for idx, _ in enumerate(remaining_risks, 1))
    implementation_range = {"base": _non_empty(base, "base"), "head": _non_empty(head, "head")}
    packet = {
        "schema_version": 1,
        "role": "completion",
        "change_id": fresh["change_id"],
        "contract_sha256": fresh["contract_sha256"],
        "context_fingerprint": fresh["context_fingerprint"],
        "state_version": fresh["state_version"],
        "output_language": fresh["output_language"],
        "task_heads": dict(sorted(task_heads.items())),
        "implementation_range": implementation_range,
        "acceptance_index_sha256": acceptance_index_sha256,
        "task_evidence": dict(sorted(task_evidence.items())),
        "task_evidence_sha256": task_evidence_sha256,
        "range": _range(base, head, expected_dirty_state="clean"),
        "checks": {"focused": contract.get("validation", {}).get("focused", []), "full": contract.get("validation", {}).get("full", []), "change_wide": contract.get("validation", {}).get("change_wide", [])},
        "handoffs": sorted(set(handoffs)),
        "mutation_map_sha256": _require_sha(mutation.get("sha256"), "mutation_map.sha256"),
    }
    return _finalize_packet(packet)


def _compare_identity(actual: dict[str, Any], expected: dict[str, Any], keys: tuple[str, ...], code: str) -> None:
    mismatches = {key: {"expected": expected.get(key), "actual": actual.get(key)} for key in keys if expected.get(key) is not None and actual.get(key) != expected.get(key)}
    if mismatches:
        raise ProtocolError(code, "finish packet identity drift", mismatches)


def _finish_payload(doc: dict[str, Any], key: str) -> dict[str, Any]:
    return _require_object(doc.get(key, doc), key)


def finish_packet(repo_path: str | Path, contract: dict[str, Any], context: dict[str, Any], state: dict[str, Any], base: str, head: str, decision_doc: dict[str, Any], completion_identity_doc: dict[str, Any], finish_plan: dict[str, Any], knowledge_snapshots: list[Any], expected_state_version: int | None = None) -> dict[str, Any]:
    _repo(repo_path)
    fresh = _fresh_inputs(contract, context, state, expected_state_version)
    decision_doc = _require_object(decision_doc, "decision")
    decision = _finish_payload(decision_doc, "decision")
    completion_identity_doc = _require_object(completion_identity_doc, "completion_identity_doc")
    completion = _finish_payload(completion_identity_doc, "completion_identity")
    finish_plan = _require_object(finish_plan, "finish_plan")
    details = _finish_plan_details(finish_plan, fresh["output_language"])

    expected_plan_sha = _self_hash(finish_plan, "finish_plan_sha256")
    plan_sha = _require_sha(finish_plan.get("finish_plan_sha256"), "finish_plan.finish_plan_sha256")
    if plan_sha != expected_plan_sha:
        raise ProtocolError("STALE_FINISH_PLAN", "finish plan self hash is stale", {"expected": expected_plan_sha, "actual": plan_sha})

    completion_sha = _require_sha(completion.get("completion_sha256"), "completion_identity.completion_sha256")
    decision_sha = _require_sha(decision.get("decision_sha256"), "decision.decision_sha256")
    decision_state_version = _require_version(decision.get("decision_state_version"), "decision.decision_state_version")
    current_identity = {"contract_sha256": fresh["contract_sha256"], "context_fingerprint": fresh["context_fingerprint"]}
    if "contract_sha256" in completion_identity_doc:
        _compare_identity(completion_identity_doc, current_identity, ("contract_sha256", "context_fingerprint"), "STALE_COMPLETION")
    _compare_identity(completion, current_identity, ("contract_sha256", "context_fingerprint"), "STALE_COMPLETION")
    if "contract_sha256" in decision_doc:
        _compare_identity(decision_doc, current_identity, ("contract_sha256", "context_fingerprint"), "STALE_DECISION")
    _compare_identity(finish_plan, current_identity, ("contract_sha256", "context_fingerprint"), "STALE_FINISH_PLAN")

    if finish_plan.get("decision_sha256") != decision_sha:
        raise ProtocolError("STALE_DECISION", "finish plan decision identity is stale")
    if finish_plan.get("completion_sha256") != completion_sha:
        raise ProtocolError("STALE_COMPLETION", "finish plan completion identity is stale")
    plan_expected = {
        "completion_sha256": completion_sha,
        "decision_sha256": decision_sha,
        "mutation_map_sha256": completion.get("mutation_map_sha256"),
        "acceptance_index_sha256": completion.get("acceptance_index_sha256"),
        "implementation_range": completion.get("implementation_range"),
        "task_heads": completion.get("task_heads"),
        "decision_state_version": decision_state_version,
    }
    _compare_identity(finish_plan, plan_expected, tuple(plan_expected), "STALE_FINISH_PLAN")
    _compare_identity(decision, {"completion_sha256": completion_sha}, ("completion_sha256",), "STALE_DECISION")

    state_completion = state.get("completion") if isinstance(state.get("completion"), dict) else {}
    state_decision = state.get("decision") if isinstance(state.get("decision"), dict) else {}
    state_completion_expected = {key: completion.get(key) for key in ("contract_sha256", "context_fingerprint", "completion_sha256", "mutation_map_sha256", "acceptance_index_sha256", "implementation_range", "task_heads")}
    _compare_identity(state_completion, state_completion_expected, tuple(state_completion_expected), "STALE_COMPLETION")
    state_decision_expected = {**state_completion_expected, "decision_sha256": decision_sha, "finish_plan_sha256": plan_sha, "decision_state_version": decision_state_version}
    _compare_identity(state_decision, state_decision_expected, tuple(state_decision_expected), "STALE_DECISION")
    gate = state.get("gates", {}).get("finish", {}) if isinstance(state.get("gates"), dict) else {}
    if gate.get("status") != "approved" or gate.get("decision_sha256") != decision_sha:
        raise ProtocolError("STALE_DECISION", "finish packet requires the approved finish decision identity")

    finish_context_paths = _context_paths(context, "finish")
    snapshots = list(_require_list(knowledge_snapshots, "knowledge_snapshots"))
    snapshots.extend({"path": path, "state": "present"} for path in finish_context_paths)
    packet = {
        "schema_version": 1,
        "role": "finish",
        "change_id": fresh["change_id"],
        "contract_sha256": fresh["contract_sha256"],
        "context_fingerprint": fresh["context_fingerprint"],
        "state_version": fresh["state_version"],
        "output_language": fresh["output_language"],
        "range": _range(base, head, expected_dirty_state="clean"),
        "snapshots": snapshots,
        "completion_sha256": completion_sha,
        "decision_sha256": decision_sha,
        "finish_plan_sha256": plan_sha,
        **details,
    }
    return _finalize_packet(packet)


def _packet_id(packet_without_or_with_id: dict[str, Any]) -> str:
    body = {key: value for key, value in packet_without_or_with_id.items() if key != "packet_id"}
    return sha256_value(body)


def write_packet(output_path: str | Path, packet: dict[str, Any]) -> dict[str, Any]:
    output = Path(output_path)
    if output.exists():
        raise ProtocolError("OUTPUT_EXISTS", "packet output already exists; refusing to overwrite attempt artifact", {"path": str(output)})
    output.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json(packet) + "\n"
    fd = None
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=str(output.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, output)
        tmp_name = None
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return {"packet_id": packet["packet_id"], "packet_sha256": sha256_value(packet), "role": packet["role"], "path": str(output)}


def _common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--repo", required=True)
    p.add_argument("--contract-json", required=True)
    p.add_argument("--context-json", required=True)
    p.add_argument("--state-json", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--expected-state-version", type=int)


def _ok(payload: dict[str, Any]) -> int:
    sys.stdout.write(canonical_json({"ok": True, **payload}) + "\n")
    return 0


def _err(error: ProtocolError) -> int:
    sys.stderr.write(canonical_json({"ok": False, "code": error.code, "message": error.message, "details": error.details}) + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive Nuclio role packets")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("worker")
    _common_args(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--handoff-snapshots-json", default="[]")

    p = sub.add_parser("reviewer")
    _common_args(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--mutation-map-json", required=True)
    p.add_argument("--validation-evidence-json", default="{}")
    p.add_argument("--interface-snapshots-json", default="[]")

    p = sub.add_parser("completion")
    _common_args(p)
    p.add_argument("--mutation-map-json", required=True)
    p.add_argument("--completed-tasks-json", required=True)
    p.add_argument("--acceptance-index-json", required=True)
    p.add_argument("--validation-evidence-json", default="{}")
    p.add_argument("--remaining-risks-json", default="[]")

    p = sub.add_parser("finish")
    _common_args(p)
    p.add_argument("--decision-json", required=True)
    p.add_argument("--completion-identity-json", required=True)
    p.add_argument("--finish-plan-json", required=True)
    p.add_argument("--knowledge-snapshots-json", default="[]")

    args = parser.parse_args(argv)
    try:
        contract = _load_json_value(args.contract_json, "contract")
        context = _load_json_value(args.context_json, "context")
        state = _load_json_value(args.state_json, "state")
        if args.command == "worker":
            packet = worker_packet(args.repo, contract, context, state, args.task_id, args.base, args.head, _load_json_value(args.handoff_snapshots_json, "handoff snapshots"), args.expected_state_version)
        elif args.command == "reviewer":
            packet = reviewer_packet(args.repo, contract, context, state, args.task_id, args.base, args.head, _load_json_value(args.mutation_map_json, "mutation map"), _load_json_value(args.validation_evidence_json, "validation evidence"), _load_json_value(args.interface_snapshots_json, "interface snapshots"), args.expected_state_version)
        elif args.command == "completion":
            packet = completion_packet(args.repo, contract, context, state, args.base, args.head, _load_json_value(args.mutation_map_json, "mutation map"), _load_json_value(args.completed_tasks_json, "completed tasks"), _load_json_value(args.acceptance_index_json, "acceptance index"), _load_json_value(args.validation_evidence_json, "validation evidence"), _load_json_value(args.remaining_risks_json, "remaining risks"), args.expected_state_version)
        elif args.command == "finish":
            packet = finish_packet(args.repo, contract, context, state, args.base, args.head, _load_json_value(args.decision_json, "decision"), _load_json_value(args.completion_identity_json, "completion identity"), _load_json_value(args.finish_plan_json, "finish plan"), _load_json_value(args.knowledge_snapshots_json, "knowledge snapshots"), args.expected_state_version)
        else:  # pragma: no cover
            raise ProtocolError("INVALID_COMMAND", "unknown command")
        return _ok({"identity": write_packet(args.output, packet)})
    except ProtocolError as exc:
        return _err(exc)


if __name__ == "__main__":
    raise SystemExit(main())
