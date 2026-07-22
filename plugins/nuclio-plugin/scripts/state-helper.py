#!/usr/bin/env python3
"""
Nuclio deterministic state transition helper.

## Contents

- [Protocol errors and JSON helpers](#protocol-errors-and-json-helpers)
- [State loading and atomic writes](#state-loading-and-atomic-writes)
- [Identity and task metadata](#identity-and-task-metadata)
- [Inspection and routing](#inspection-and-routing)
- [Contract Gate transitions](#contract-gate-transitions)
- [Task and fixer transitions](#task-and-fixer-transitions)
- [Completion and Finish transitions](#completion-and-finish-transitions)
- [CLI](#cli)

The helper is the only writer for `.dev-docs/changes/<change-id>/state.json`.
It never edits contract, context, evidence, product or knowledge files. Every mutation uses an
optimistic expected state version and an atomic temporary-file replace. Invalid
transport, stale artifact identity, illegal observation and invalid transition
errors fail closed; budget is consumed only by a valid fixer authorization.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

NEXT_ACTIONS = {
    "DRAFT_CONTRACT",
    "REQUEST_CONTRACT_APPROVAL",
    "DISPATCH_IMPLEMENTER",
    "DISPATCH_REVIEWER",
    "DISPATCH_FIXER",
    "RUN_COMPLETION_REVIEW",
    "REQUEST_FINISH_DECISION",
    "REBUILD_FINISH_HANDOFF",
    "APPLY_FINISH",
    "HALT",
    "COMPLETE",
}
TASK_STATUSES = {"pending", "ready", "implementing", "reviewing", "fixing", "completed", "blocked", "rejected"}
STATE_STATUSES = {"idle", "drafting_contract", "contract_pending", "ready_to_execute", "executing", "completing", "decision_pending", "folding", "archived", "repair_required", "context_stale", "deferred", "rejected"}
FINISH_DECISIONS = {"accept", "request_changes", "defer", "reject"}
CONTRACT_APPROVAL_ALIASES = {"approve": "approve", "批准": "approve", "同意": "approve", "继续": "approve"}
FINISH_DECISION_ALIASES = {"accept": "accept", "同意": "accept", "request_changes": "request_changes", "要求修改": "request_changes", "defer": "defer", "暂缓": "defer", "reject": "reject", "拒绝": "reject"}
HASH_RE = "0123456789abcdef"
MUTATION_MODES = {"create", "modify", "delete"}
SCRIPTS_DIR = Path(__file__).resolve().parent
PACKET_SCHEMA = SCRIPTS_DIR.parent / "schemas" / "packet.schema.json"
STATE_SCHEMA = SCRIPTS_DIR.parent / "schemas" / "state.schema.json"


def _load_evidence_helper():
    helper_path = SCRIPTS_DIR / "evidence-helper.py"
    spec = importlib.util.spec_from_file_location("nuclio_evidence_helper_for_state", helper_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json_schema_helper():
    helper_path = SCRIPTS_DIR / "json-schema-helper.py"
    spec = importlib.util.spec_from_file_location("nuclio_json_schema_helper", helper_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


JSON_SCHEMA_HELPER = _load_json_schema_helper()
EVIDENCE_HELPER = _load_evidence_helper()


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


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in HASH_RE for ch in value)


def _require_sha(value: Any, where: str) -> str:
    if not _is_sha(value):
        raise ProtocolError("INVALID_IDENTITY", f"{where} must be a lowercase sha256")
    return value


def _non_empty(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("INVALID_INPUT", f"{where} must be a non-empty string")
    return value.strip()


def _normalize_exact_alias(value: Any, aliases: dict[str, str], where: str, code: str, message: str) -> str:
    token = _non_empty(value, where)
    if token not in aliases:
        raise ProtocolError(code, message)
    return aliases[token]


def _require_object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_INPUT", f"{where} must be an object")
    return value


def _require_list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProtocolError("INVALID_INPUT", f"{where} must be a list")
    return value


def load_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists() or not state_path.is_file():
        raise ProtocolError("STATE_NOT_FOUND", "state path must name an existing file", {"path": str(path)})
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError("INVALID_STATE_JSON", "state is not valid JSON") from exc
    validate_state_shape(state)
    return state


def _validate_state_schema(state: Any) -> None:
    try:
        JSON_SCHEMA_HELPER.validate_instance(STATE_SCHEMA, state)
    except JSON_SCHEMA_HELPER.SchemaValidationError as exc:
        raise ProtocolError("INVALID_STATE_SCHEMA", "state does not conform to canonical state.schema.json", exc.details()) from exc


def validate_state_shape(state: Any) -> None:
    if not isinstance(state, dict):
        raise ProtocolError("INVALID_STATE", "state root must be an object")
    required = {"schema_version", "state_version", "change_id", "status", "contract", "context", "gates", "tasks", "blockers", "fix_budgets", "history"}
    missing = sorted(required - set(state))
    if missing:
        raise ProtocolError("INVALID_STATE", "state is missing required fields", {"fields": missing})
    if not isinstance(state["state_version"], int) or isinstance(state["state_version"], bool) or state["state_version"] < 1:
        raise ProtocolError("INVALID_STATE", "state_version must be positive")
    if state["status"] not in STATE_STATUSES:
        raise ProtocolError("INVALID_STATE", "invalid status", {"status": state["status"]})
    _artifact_identity(state["contract"])
    _context_identity(state["context"])
    if not isinstance(state["tasks"], list):
        raise ProtocolError("INVALID_STATE", "tasks must be a list")
    for task in state["tasks"]:
        if not isinstance(task, dict) or task.get("status") not in TASK_STATUSES:
            raise ProtocolError("INVALID_STATE", "task status is invalid")
        ownership = task.get("ownership")
        if not isinstance(ownership, list) or not ownership or any(not isinstance(path, str) or not path.strip() for path in ownership):
            raise ProtocolError("INVALID_STATE", "task ownership must be a non-empty list of paths")
        if task["status"] in {"implementing", "reviewing", "fixing", "completed", "blocked", "rejected"}:
            _require_sha(task.get("packet_sha256"), "task.packet_sha256")
        elif "packet_sha256" in task and not _is_sha(task.get("packet_sha256")):
            raise ProtocolError("INVALID_STATE", "pending/ready task packet_sha256 must be omitted or a lowercase sha256")
    if state["status"] in {"context_stale", "deferred", "rejected"} and any(task["status"] == "completed" for task in state["tasks"]):
        raise ProtocolError("INVALID_STATE", "schema forbids completed tasks in stale/deferred/rejected states")
    _validate_state_schema(state)


def _write_state_atomic(path: str | Path, state: dict[str, Any]) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json(state) + "\n"
    fd = None
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{state_path.name}.", suffix=".tmp", dir=str(state_path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, state_path)
        tmp_name = None
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _check_version(state: dict[str, Any], expected_version: int) -> None:
    if state["state_version"] != expected_version:
        raise ProtocolError("VERSION_MISMATCH", "expected state version does not match current state", {"expected": expected_version, "actual": state["state_version"]})


def _commit(path: str | Path, before: dict[str, Any], after: dict[str, Any], action: str, reason: str | None = None, **event_fields: Any) -> dict[str, Any]:
    event = {"event": action, "from": before.get("status"), "to": after.get("status"), "state_version": before["state_version"] + 1}
    if reason:
        event["reason"] = reason
    if "artifact_sha256" in event_fields:
        event["artifact_sha256"] = event_fields["artifact_sha256"]
    event_reason = event_fields.get("event_reason")
    if event_reason is not None:
        event["reason"] = event_reason if isinstance(event_reason, str) else canonical_json(event_reason)
    after["state_version"] = before["state_version"] + 1
    after.setdefault("history", []).append(event)
    validate_state_shape(after)
    _write_state_atomic(path, after)
    return after


def _language_tag(value: Any, where: str) -> str:
    text = _non_empty(value, where)
    parts = text.split("-")
    valid = 2 <= len(parts[0]) <= 8 and parts[0].isalpha()
    valid = valid and all(1 <= len(part) <= 8 and part.isalnum() for part in parts[1:])
    if not valid:
        raise ProtocolError("INVALID_OUTPUT_LANGUAGE", f"{where} must be a BCP-47 style language tag")
    return text


def _artifact_identity(raw: dict[str, Any]) -> dict[str, str]:
    raw = _require_object(raw, "contract identity")
    return {"path": _non_empty(raw.get("path"), "contract.path"), "sha256": _require_sha(raw.get("sha256"), "contract.sha256"), "version": _non_empty(raw.get("version"), "contract.version"), "output_language": _language_tag(raw.get("output_language"), "contract.output_language")}


def _context_identity(raw: dict[str, Any]) -> dict[str, Any]:
    raw = _require_object(raw, "context identity")
    entries = [_non_empty(item, "context.entries[]") for item in _require_list(raw.get("entries"), "context.entries")]
    if len(entries) != len(set(entries)):
        raise ProtocolError("INVALID_CONTEXT", "context entries must be unique")
    return {"path": _non_empty(raw.get("path"), "context.path"), "fingerprint": _require_sha(raw.get("fingerprint"), "context.fingerprint"), "entries": entries}


def _ownership_objects(raw_ownership: Any, where: str = "task.ownership") -> list[dict[str, str]]:
    ownership = []
    for raw in _require_list(raw_ownership, where):
        item = _require_object(raw, f"{where}[]")
        keys = set(item)
        if keys != {"path", "mode"}:
            raise ProtocolError("INVALID_TASK_GRAPH", "task ownership entries must contain only path and mode", {"fields": sorted(keys)})
        path = _non_empty(item.get("path"), f"{where}[].path")
        mode = _non_empty(item.get("mode"), f"{where}[].mode")
        if mode not in MUTATION_MODES:
            raise ProtocolError("INVALID_TASK_GRAPH", "task ownership mode is invalid", {"mode": mode})
        ownership.append({"path": path, "mode": mode})
    if not ownership:
        raise ProtocolError("INVALID_TASK_GRAPH", "task ownership must not be empty")
    return ownership


def _validate_packet_schema(packet: Any) -> None:
    try:
        JSON_SCHEMA_HELPER.validate_instance(PACKET_SCHEMA, packet)
    except JSON_SCHEMA_HELPER.SchemaValidationError as exc:
        raise ProtocolError("INVALID_PACKET_SCHEMA", "packet does not conform to canonical packet.schema.json", exc.details()) from exc


def _task_metadata_from_graph(task_graph: list[Any]) -> list[dict[str, Any]]:
    tasks = []
    seen = set()
    for raw in task_graph:
        item = _require_object(raw, "task graph item")
        if "packet_sha256" in item:
            raise ProtocolError("INVALID_TASK_GRAPH", "task graph must not contain packet_sha256")
        task_id = str(item.get("id", "")).strip()
        if not task_id or task_id in seen:
            raise ProtocolError("INVALID_TASK_GRAPH", "task ids must be unique and non-empty")
        seen.add(task_id)
        owner = _non_empty(item.get("owner"), "task.owner")
        deps = [str(dep).strip() for dep in _require_list(item.get("dependencies", []), "task.dependencies")]
        if any(not dep for dep in deps) or len(deps) != len(set(deps)):
            raise ProtocolError("INVALID_TASK_GRAPH", "dependencies must be unique non-empty ids")
        ownership = _ownership_objects(item.get("ownership"), "task.ownership")
        tasks.append({"id": task_id, "owner": owner, "dependencies": deps, "ownership": ownership})
    ids = {task["id"] for task in tasks}
    for task in tasks:
        for dep in task["dependencies"]:
            if dep not in ids:
                raise ProtocolError("DANGLING_DEPENDENCY", "dependency does not exist", {"task_id": task["id"], "dependency": dep})
    visited: set[str] = set()
    visiting: set[str] = set()
    by_id = {task["id"]: task for task in tasks}

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ProtocolError("DEPENDENCY_CYCLE", "dependency cycle detected", {"task_id": task_id})
        if task_id in visited:
            return
        visiting.add(task_id)
        for dep in by_id[task_id]["dependencies"]:
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)

    for task in tasks:
        visit(task["id"])
    return tasks


def _metadata(state: dict[str, Any]) -> dict[str, Any]:
    for event in state.get("history", []):
        if event.get("event") == "INITIALIZED" and isinstance(event.get("reason"), str):
            try:
                metadata = json.loads(event["reason"])
            except json.JSONDecodeError:
                continue
            if isinstance(metadata, dict):
                return metadata
    raise ProtocolError("MISSING_METADATA", "state initialization metadata is missing")


def _task_meta(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in _metadata(state).get("tasks", []):
        if task.get("id") == task_id:
            return task
    raise ProtocolError("UNKNOWN_TASK", "task id is not present", {"task_id": task_id})


def _task_state(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in state["tasks"]:
        if str(task.get("id")) == task_id:
            return task
    raise ProtocolError("UNKNOWN_TASK", "task id is not present", {"task_id": task_id})


def _all_deps_complete(state: dict[str, Any], task_id: str) -> bool:
    meta = _task_meta(state, task_id)
    return all(_task_state(state, dep)["status"] == "completed" for dep in meta["dependencies"])


def _eligible_task(state: dict[str, Any]) -> dict[str, Any] | None:
    for task in state["tasks"]:
        if task["status"] == "ready" and _all_deps_complete(state, str(task["id"])):
            return task
    return None


def _refresh_ready_tasks(state: dict[str, Any]) -> None:
    for task in state["tasks"]:
        if task["status"] == "pending" and _all_deps_complete(state, str(task["id"])):
            task["status"] = "ready"


def _owner_for_task(state: dict[str, Any], task_id: str) -> str:
    return _task_meta(state, task_id)["owner"]


def _ownership_for_task(state: dict[str, Any], task_id: str) -> list[dict[str, str]]:
    return copy.deepcopy(_task_meta(state, task_id)["ownership"])


def _packet_id(packet_without_or_with_id: dict[str, Any]) -> str:
    body = {key: value for key, value in packet_without_or_with_id.items() if key != "packet_id"}
    return sha256_value(body)


def _validate_worker_packet(state: dict[str, Any], task_id: str, packet: Any) -> tuple[dict[str, Any], str]:
    _validate_packet_schema(packet)
    packet = _require_object(packet, "worker packet")
    if packet.get("schema_version") != 1:
        raise ProtocolError("INVALID_PACKET", "worker packet schema_version must be 1")
    if packet.get("role") != "worker":
        raise ProtocolError("INVALID_PACKET_ROLE", "packet role must be worker")
    packet_id = _require_sha(packet.get("packet_id"), "packet.packet_id")
    actual_packet_id = _packet_id(packet)
    if packet_id != actual_packet_id:
        raise ProtocolError("PACKET_ID_MISMATCH", "packet_id does not match canonical packet content", {"expected": actual_packet_id, "actual": packet_id})
    if packet.get("change_id") != state["change_id"]:
        raise ProtocolError("STALE_PACKET", "packet change_id does not match state")
    if packet.get("contract_sha256") != state["contract"]["sha256"]:
        raise ProtocolError("STALE_PACKET", "packet contract_sha256 does not match state")
    if packet.get("context_fingerprint") != state["context"]["fingerprint"]:
        raise ProtocolError("STALE_PACKET", "packet context_fingerprint does not match state")
    if packet.get("state_version") != state["state_version"]:
        raise ProtocolError("STALE_PACKET", "packet state_version does not match current state", {"expected": state["state_version"], "actual": packet.get("state_version")})
    if packet.get("output_language") != state["contract"]["output_language"]:
        raise ProtocolError("STALE_PACKET", "packet output_language does not match Contract identity")
    if str(packet.get("task_id")) != str(task_id):
        raise ProtocolError("WRONG_TASK", "packet task_id does not match requested task")
    try:
        packet_ownership = _ownership_objects(packet.get("ownership"), "packet.ownership")
    except ProtocolError as exc:
        if exc.code == "INVALID_TASK_GRAPH":
            raise ProtocolError("STALE_OWNERSHIP", exc.message, exc.details) from exc
        raise
    if packet_ownership != _ownership_for_task(state, str(task_id)):
        raise ProtocolError("STALE_OWNERSHIP", "packet ownership does not match state metadata", {"expected": _ownership_for_task(state, str(task_id)), "actual": packet_ownership})
    return packet, sha256_value(packet)


def _open_blockers(state: dict[str, Any], task_id: str | None = None) -> list[dict[str, Any]]:
    blockers = [blocker for blocker in state.get("blockers", []) if blocker.get("severity") == "blocking"]
    if task_id is None:
        return blockers
    prefix = f"{task_id}:"
    return [blocker for blocker in blockers if str(blocker.get("id", "")).startswith(prefix) or blocker.get("task_id") == task_id]


def _set_blockers(state: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    state["blockers"] = blockers


def _demote_completed_for_schema(state: dict[str, Any], status: str = "blocked") -> None:
    for task in state.get("tasks", []):
        if task.get("status") == "completed":
            task["status"] = status


def inspect_state(state_or_path: dict[str, Any] | str | Path) -> dict[str, Any]:
    state = load_state(state_or_path) if isinstance(state_or_path, (str, Path)) else state_or_path
    validate_state_shape(state)
    current = None
    for task in state["tasks"]:
        if task["status"] in {"ready", "implementing", "reviewing", "fixing"}:
            current = task["id"]
            break
    return {
        "status": state["status"],
        "state_version": state["state_version"],
        "contract_fresh": state["gates"]["contract"].get("status") == "approved" and state["gates"]["contract"].get("artifact_sha256") == state["contract"]["sha256"],
        "finish_fresh": state["gates"]["finish"].get("status") == "approved" and bool(state.get("decision", {}).get("approved")),
        "current_task": current,
        "blockers": copy.deepcopy(state.get("blockers", [])),
        "budgets": copy.deepcopy(state.get("fix_budgets", {})),
        "decision_fresh": bool(state.get("decision", {}).get("approved")) and state["status"] in {"folding", "archived"},
        "next_action": next_action(state)["action"],
    }


def _finish_change_root_for_state(state: dict[str, Any], state_or_path: dict[str, Any] | str | Path) -> Path | None:
    if isinstance(state_or_path, (str, Path)):
        return Path(state_or_path).resolve().parent
    try:
        metadata = _metadata(state)
    except ProtocolError:
        return None
    raw = metadata.get("finish_change_root")
    if isinstance(raw, str) and raw.strip():
        return Path(raw).resolve()
    return None


def _has_canonical_finish_identity(state: dict[str, Any]) -> bool:
    decision = state.get("decision") if isinstance(state.get("decision"), dict) else {}
    completion = state.get("completion") if isinstance(state.get("completion"), dict) else {}
    return all(_is_sha(decision.get(key)) for key in ("decision_sha256", "finish_plan_sha256", "completion_sha256")) and _is_sha(completion.get("completion_sha256")) and isinstance(decision.get("decision_state_version"), int)


def _finish_route(state: dict[str, Any], state_or_path: dict[str, Any] | str | Path) -> dict[str, Any]:
    if not _has_canonical_finish_identity(state):
        return {"action": "REBUILD_FINISH_HANDOFF", "status": state["status"], "state_version": state["state_version"], "code": "LEGACY_FINISH_HANDOFF"}
    change_root = _finish_change_root_for_state(state, state_or_path)
    if change_root is None:
        return {"action": "HALT", "status": state["status"], "state_version": state["state_version"], "code": "CHANGE_ROOT_REQUIRED"}
    readiness = _readiness(change_root, state)
    if readiness.get("ready") is True:
        if readiness.get("decision_sha256") != state["decision"].get("decision_sha256") or readiness.get("finish_plan_sha256") != state["decision"].get("finish_plan_sha256") or readiness.get("decision_state_version") != state["decision"].get("decision_state_version"):
            return {"action": "HALT", "status": state["status"], "state_version": state["state_version"], "code": "STALE_DECISION"}
        return {"action": "REQUEST_FINISH_DECISION", "status": state["status"], "state_version": state["state_version"], "readiness": readiness}
    return {"action": "HALT", "status": state["status"], "state_version": state["state_version"], "code": readiness.get("failure_code") or "FINISH_HANDOFF_NOT_READY", "readiness": readiness}


def next_action(state_or_path: dict[str, Any] | str | Path) -> dict[str, Any]:
    state = load_state(state_or_path) if isinstance(state_or_path, (str, Path)) else state_or_path
    status = state["status"]
    action = "HALT"
    if status == "idle":
        action = "DRAFT_CONTRACT"
    elif status == "drafting_contract":
        action = "DRAFT_CONTRACT"
    elif status == "contract_pending":
        action = "REQUEST_CONTRACT_APPROVAL"
    elif status == "ready_to_execute":
        action = "DISPATCH_IMPLEMENTER" if _eligible_task(state) is not None else "RUN_COMPLETION_REVIEW"
    elif status == "executing":
        reviewing = any(task["status"] == "reviewing" for task in state["tasks"])
        fixing = any(task["status"] == "fixing" for task in state["tasks"])
        implementing_or_ready = any(task["status"] in {"ready", "implementing"} for task in state["tasks"])
        if reviewing:
            action = "DISPATCH_REVIEWER"
        elif fixing:
            action = "DISPATCH_FIXER"
        elif implementing_or_ready:
            action = "DISPATCH_IMPLEMENTER"
        elif all(task["status"] == "completed" for task in state["tasks"]):
            action = "RUN_COMPLETION_REVIEW"
        else:
            action = "HALT"
    elif status == "repair_required":
        action = "DISPATCH_FIXER" if any(task["status"] in {"blocked", "fixing"} for task in state["tasks"]) and state.get("blockers") else "RUN_COMPLETION_REVIEW" if all(task["status"] == "completed" for task in state["tasks"]) else "HALT"
    elif status == "completing":
        action = "RUN_COMPLETION_REVIEW"
    elif status == "decision_pending":
        return _finish_route(state, state_or_path)
    elif status == "folding":
        action = "APPLY_FINISH"
    elif status == "archived":
        action = "COMPLETE"
    elif status in {"context_stale", "deferred", "rejected"}:
        action = "HALT"
    if action not in NEXT_ACTIONS:  # pragma: no cover
        raise ProtocolError("INVALID_NEXT_ACTION", "internal next action is not allowed")
    return {"action": action, "status": status, "state_version": state["state_version"]}


def init_state(path: str | Path, contract: dict[str, Any], context: dict[str, Any], task_graph: list[Any]) -> dict[str, Any]:
    contract_id = _artifact_identity(contract)
    context_id = _context_identity(context)
    tasks_meta = _task_metadata_from_graph(task_graph)
    tasks = []
    budgets: dict[str, dict[str, int]] = {}
    for index, task in enumerate(tasks_meta):
        tasks.append({"id": task["id"], "status": "ready" if index == 0 and not task["dependencies"] else "pending", "ownership": [item["path"] for item in task["ownership"]]})
        budgets.setdefault(task["owner"], {"maximum": 2, "used": 0, "remaining": 2})
    state = {
        "schema_version": 1,
        "state_version": 1,
        "change_id": _non_empty(contract.get("change_id", "unknown-change"), "change_id"),
        "status": "contract_pending",
        "contract": contract_id,
        "context": context_id,
        "gates": {"contract": {"status": "pending", "artifact_sha256": contract_id["sha256"], "context_fingerprint": context_id["fingerprint"], "state_version": 1}, "finish": {"status": "none"}},
        "tasks": tasks,
        "blockers": [],
        "fix_budgets": dict(sorted(budgets.items())),
        "history": [{"event": "INITIALIZED", "from": None, "to": "contract_pending", "state_version": 1, "artifact_sha256": contract_id["sha256"], "reason": canonical_json({"tasks": tasks_meta, "context_fingerprint": context_id["fingerprint"], "contract_sha256": contract_id["sha256"]})}],
    }
    validate_state_shape(state)
    _write_state_atomic(path, state)
    return state


def approve_contract(path: str | Path, expected_version: int, contract: dict[str, Any], context: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    if before["status"] != "contract_pending":
        raise ProtocolError("CONTRACT_NOT_PENDING", "Contract Gate is not pending")
    contract_id = _artifact_identity(contract)
    context_id = _context_identity(context)
    if contract_id != before["contract"]:
        after = copy.deepcopy(before)
        after["status"] = "drafting_contract"
        after["gates"]["contract"] = {"status": "stale", "artifact_sha256": before["contract"]["sha256"], "state_version": before["state_version"], "notes": "contract identity drift"}
        _commit(path, before, after, "CONTRACT_STALE", event_reason={"expected": before["contract"], "actual": contract_id})
        raise ProtocolError("STALE_CONTRACT", "contract identity does not match state; approval invalidated")
    if context_id != before["context"]:
        after = copy.deepcopy(before)
        after["status"] = "context_stale"
        after["gates"]["contract"] = {"status": "stale", "artifact_sha256": before["contract"]["sha256"], "context_fingerprint": before["context"]["fingerprint"], "state_version": before["state_version"], "notes": "context fingerprint drift"}
        _commit(path, before, after, "CONTEXT_STALE", event_reason={"expected": before["context"], "actual": context_id})
        raise ProtocolError("STALE_CONTEXT", "context identity does not match state; approval invalidated")
    approval = _require_object(approval, "approval")
    approval_id = _non_empty(approval.get("approval_id"), "approval.approval_id")
    approved_at = _non_empty(approval.get("approved_at"), "approval.approved_at")
    approval_token = _normalize_exact_alias(approval.get("token"), CONTRACT_APPROVAL_ALIASES, "approval.token", "INVALID_CONTRACT_APPROVAL", "approval token must be exact approve/批准/同意/继续")
    after = copy.deepcopy(before)
    after["status"] = "ready_to_execute"
    notes = {k: v for k, v in approval.items() if k not in {"approval_id", "approved_at"}}
    notes["token"] = approval_token
    after["gates"]["contract"] = {"status": "approved", "artifact_sha256": contract_id["sha256"], "context_fingerprint": context_id["fingerprint"], "state_version": before["state_version"], "approval_id": approval_id, "approved_at": approved_at, "notes": canonical_json(notes)}
    return _commit(path, before, after, "CONTRACT_APPROVED", artifact_sha256=contract_id["sha256"])


def _require_contract_approved(state: dict[str, Any]) -> None:
    gate = state["gates"]["contract"]
    if gate.get("status") != "approved" or gate.get("artifact_sha256") != state["contract"]["sha256"] or gate.get("context_fingerprint") != state["context"]["fingerprint"]:
        raise ProtocolError("CONTRACT_NOT_APPROVED", "fresh Contract approval is required before execution")


def start_task(path: str | Path, expected_version: int, task_id: str, packet_json: dict[str, Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    _require_contract_approved(before)
    if before["status"] not in {"ready_to_execute", "executing"}:
        raise ProtocolError("INVALID_TRANSITION", "task can start only from execution-ready state")
    task_id = str(task_id)
    task = _task_state(before, task_id)
    current_packet = task.get("packet_sha256")
    if task["status"] == "implementing" and current_packet:
        _validate_packet_schema(packet_json)
        retry_packet = _require_object(packet_json, "worker packet")
        retry_sha = sha256_value(retry_packet)
        if retry_sha == current_packet:
            if _packet_id(retry_packet) != _require_sha(retry_packet.get("packet_id"), "packet.packet_id"):
                raise ProtocolError("PACKET_ID_MISMATCH", "packet_id does not match canonical packet content")
            return before
        raise ProtocolError("PACKET_ALREADY_BOUND", "task is already bound to a different packet")
    packet, packet_sha256 = _validate_worker_packet(before, task_id, packet_json)
    if current_packet and current_packet != packet_sha256:
        raise ProtocolError("PACKET_ALREADY_BOUND", "task is already bound to a different packet")
    if task["status"] not in {"ready", "pending"}:
        raise ProtocolError("TASK_NOT_READY", "task is not ready to start")
    if not _all_deps_complete(before, task_id):
        raise ProtocolError("DEPENDENCY_NOT_COMPLETE", "task dependencies are not complete")
    after = copy.deepcopy(before)
    after_task = _task_state(after, task_id)
    after_task["packet_sha256"] = packet_sha256
    after_task["status"] = "implementing"
    after["status"] = "executing"
    return _commit(path, before, after, "TASK_STARTED", event_reason={"task_id": task_id, "packet_sha256": packet_sha256, "packet_id": packet["packet_id"]})


def record_implementation(path: str | Path, expected_version: int, evidence: dict[str, Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    evidence = _require_object(evidence, "implementation evidence")
    task_id = str(evidence.get("task_id", ""))
    task = _task_state(before, task_id)
    if "packet_sha256" not in task:
        raise ProtocolError("PACKET_UNBOUND", "task is not bound to a worker packet")
    if before["status"] != "executing" or task["status"] not in {"implementing", "fixing"}:
        raise ProtocolError("TASK_NOT_IMPLEMENTING", "task is not accepting implementation evidence")
    if task["packet_sha256"] != _require_sha(evidence.get("packet_sha256"), "packet_sha256"):
        raise ProtocolError("PACKET_MISMATCH", "implementation packet identity is stale")
    impl_sha = _require_sha(evidence.get("implementation_sha256"), "implementation_sha256")
    changed = _require_list(evidence.get("changed_paths"), "changed_paths")
    allowed = set(task["ownership"])
    if any(path_item not in allowed for path_item in changed):
        raise ProtocolError("OWNERSHIP_VIOLATION", "changed paths exceed task ownership", {"changed_paths": changed, "ownership": sorted(allowed)})
    after = copy.deepcopy(before)
    after_task = _task_state(after, task_id)
    after_task["status"] = "reviewing"
    after_task["implementation_sha256"] = impl_sha
    metadata = _metadata(after)
    metadata.setdefault("heads", {})[task_id] = _non_empty(evidence.get("new_head"), "new_head")
    metadata.setdefault("implementations", {})[task_id] = {"base_head": _non_empty(evidence.get("base_head"), "base_head"), "new_head": _non_empty(evidence.get("new_head"), "new_head"), "implementation_sha256": impl_sha}
    _update_initial_metadata(after, metadata)
    return _commit(path, before, after, "IMPLEMENTATION_RECORDED", artifact_sha256=impl_sha, event_reason={"task_id": task_id, "new_head": evidence.get("new_head")})


def _update_initial_metadata(state: dict[str, Any], metadata: dict[str, Any]) -> None:
    for event in state["history"]:
        if event.get("event") == "INITIALIZED":
            event["reason"] = canonical_json(metadata)
            return
    raise ProtocolError("MISSING_METADATA", "state initialization metadata is missing")


def _normalize_finding(raw: dict[str, Any], task_id: str) -> dict[str, Any]:
    raw = _require_object(raw, "finding")
    finding_id = _non_empty(raw.get("id"), "finding.id")
    severity = raw.get("severity")
    if severity not in {"info", "warning", "blocking"}:
        raise ProtocolError("INVALID_REVIEW", "finding severity is invalid")
    owner = _non_empty(raw.get("owner"), "finding.owner") if "owner" in raw else ""
    reason = _non_empty(raw.get("reason", "blocking finding"), "finding.reason")
    normalized = {"id": f"{task_id}:{finding_id}", "severity": severity, "reason": reason}
    if owner:
        normalized["owner"] = owner
    if "fingerprint" in raw:
        normalized["reason"] = reason + " fingerprint=" + _non_empty(raw["fingerprint"], "finding.fingerprint")
    if "path" in raw:
        normalized["reason"] += " path=" + _non_empty(raw["path"], "finding.path")
    return normalized


def import_task_review(path: str | Path, expected_version: int, review: dict[str, Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    review = _require_object(review, "review")
    task_id = str(review.get("task_id", ""))
    task = _task_state(before, task_id)
    if before["status"] != "executing" or task["status"] != "reviewing":
        raise ProtocolError("TASK_NOT_REVIEWING", "task is not awaiting review")
    review_sha = _require_sha(review.get("review_sha256"), "review_sha256")
    verdict = review.get("verdict")
    if verdict not in {"PASS", "FAIL"}:
        raise ProtocolError("INVALID_REVIEW", "review verdict must be PASS or FAIL")
    after = copy.deepcopy(before)
    after_task = _task_state(after, task_id)
    after_task["review_sha256"] = review_sha
    if verdict == "PASS":
        after_task["status"] = "completed"
        after["blockers"] = [blocker for blocker in after["blockers"] if not str(blocker.get("id", "")).startswith(f"{task_id}:")]
        _refresh_ready_tasks(after)
        after["status"] = "ready_to_execute" if _eligible_task(after) is not None else "executing"
        return _commit(path, before, after, "TASK_REVIEW_PASSED", artifact_sha256=review_sha, event_reason={"task_id": task_id})
    findings = [_normalize_finding(item, task_id) for item in _require_list(review.get("findings"), "findings")]
    blocking = [finding for finding in findings if finding["severity"] == "blocking"]
    if not blocking:
        raise ProtocolError("INVALID_REVIEW", "FAIL review requires a blocking finding")
    owner = _owner_for_task(before, task_id)
    for finding in blocking:
        if finding.get("owner") and finding["owner"] != owner:
            raise ProtocolError("CROSS_OWNER_FINDING", "blocking finding belongs to a different owner", {"expected_owner": owner, "actual_owner": finding.get("owner")})
    after_task["status"] = "blocked"
    after["status"] = "repair_required"
    after["blockers"] = [blocker for blocker in after["blockers"] if not str(blocker.get("id", "")).startswith(f"{task_id}:")] + blocking
    return _commit(path, before, after, "TASK_REVIEW_FAILED", artifact_sha256=review_sha, event_reason={"task_id": task_id, "findings": [item["id"] for item in blocking]})


def needs_fix(path: str | Path, expected_version: int, task_id: str, finding_ids: list[Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    task_id = str(task_id)
    task = _task_state(before, task_id)
    if before["status"] != "repair_required" or task["status"] != "blocked":
        raise ProtocolError("FIX_NOT_NEEDED", "task is not in a fixable blocked state")
    wanted = {str(item) for item in finding_ids}
    open_ids = {str(blocker["id"]).split(":", 1)[-1] for blocker in _open_blockers(before, task_id)}
    if not wanted or not wanted <= open_ids:
        raise ProtocolError("FINDING_NOT_OPEN", "fix request must name open blocking findings")
    after = copy.deepcopy(before)
    return _commit(path, before, after, "FIX_NEEDED", event_reason={"task_id": task_id, "finding_ids": sorted(wanted)})


def authorize_fix(path: str | Path, expected_version: int, task_id: str, finding_ids: list[Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    task_id = str(task_id)
    task = _task_state(before, task_id)
    owner = _owner_for_task(before, task_id)
    budget = before["fix_budgets"].get(owner)
    if not budget or budget["remaining"] <= 0:
        raise ProtocolError("BUDGET_EXHAUSTED", "shared owner fix budget is exhausted", {"owner": owner})
    if before["status"] != "repair_required" or task["status"] != "blocked":
        raise ProtocolError("FIX_NOT_NEEDED", "task is not in a fixable blocked state")
    wanted = {str(item) for item in finding_ids}
    blockers = _open_blockers(before, task_id)
    open_ids = {str(blocker["id"]).split(":", 1)[-1] for blocker in blockers}
    if not wanted or not wanted <= open_ids:
        raise ProtocolError("FINDING_NOT_OPEN", "fix authorization must name open blocking findings")
    after = copy.deepcopy(before)
    after_task = _task_state(after, task_id)
    after_task["status"] = "fixing"
    after["status"] = "executing"
    after_budget = after["fix_budgets"][owner]
    after_budget["used"] += 1
    after_budget["remaining"] = max(0, after_budget["maximum"] - after_budget["used"])
    metadata = _metadata(after)
    metadata.setdefault("authorized_findings", {})[task_id] = sorted(wanted)
    _update_initial_metadata(after, metadata)
    return _commit(path, before, after, "FIX_AUTHORIZED", event_reason={"task_id": task_id, "finding_ids": sorted(wanted), "owner": owner})


def record_fix(path: str | Path, expected_version: int, evidence: dict[str, Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    evidence = _require_object(evidence, "fix evidence")
    task_id = str(evidence.get("task_id", ""))
    task = _task_state(before, task_id)
    if before["status"] != "executing" or task["status"] != "fixing":
        raise ProtocolError("TASK_NOT_FIXING", "task is not accepting fix evidence")
    metadata = _metadata(before)
    old_head = metadata.get("heads", {}).get(task_id)
    base_head = _non_empty(evidence.get("base_head"), "base_head")
    if not old_head or base_head != old_head:
        raise ProtocolError("STALE_HEAD", "fix base_head must match current Task head", {"task_id": task_id, "current_task_head": old_head, "base_head": base_head})
    new_head = _non_empty(evidence.get("new_head"), "new_head")
    impl_sha = _require_sha(evidence.get("implementation_sha256"), "implementation_sha256")
    if old_head == new_head and task.get("implementation_sha256") == impl_sha:
        raise ProtocolError("NO_PROGRESS", "fix evidence does not change head or implementation identity")
    return record_implementation(path, expected_version, evidence)


def _require_completion_identity(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    required_fields = {"contract_sha256", "context_fingerprint", "task_heads", "implementation_range", "acceptance_index_sha256"}
    missing = sorted(required_fields - set(payload))
    if missing:
        raise ProtocolError("INVALID_IDENTITY", "completion identity is incomplete", {"fields": missing})
    contract_sha = _require_sha(payload.get("contract_sha256"), "completion.contract_sha256")
    context_fingerprint = _require_sha(payload.get("context_fingerprint"), "completion.context_fingerprint")
    if contract_sha != state["contract"]["sha256"] or context_fingerprint != state["context"]["fingerprint"]:
        raise ProtocolError("INVALID_IDENTITY", "completion contract/context identity is stale")
    metadata = _metadata(state)
    expected_heads = copy.deepcopy(metadata.get("heads", {}))
    task_heads = _require_object(payload.get("task_heads"), "completion.task_heads")
    if task_heads != expected_heads or set(task_heads) != {str(task["id"]) for task in state["tasks"]}:
        raise ProtocolError("INVALID_IDENTITY", "completion task_heads must exactly match all Task heads")
    implementation_range = _require_object(payload.get("implementation_range"), "completion.implementation_range")
    _non_empty(implementation_range.get("base"), "completion.implementation_range.base")
    _non_empty(implementation_range.get("head"), "completion.implementation_range.head")
    acceptance_index_sha = _require_sha(payload.get("acceptance_index_sha256"), "completion.acceptance_index_sha256")
    return {
        "contract_sha256": contract_sha,
        "context_fingerprint": context_fingerprint,
        "task_heads": copy.deepcopy(task_heads),
        "implementation_range": copy.deepcopy(implementation_range),
        "acceptance_index_sha256": acceptance_index_sha,
    }


def _wrap_evidence_error(exc: Exception) -> ProtocolError:
    code = getattr(exc, "code", "FINISH_HANDOFF_INVALID")
    message = getattr(exc, "message", str(exc))
    details = getattr(exc, "details", {})
    return ProtocolError(code, message, details)


def _absolute_change_root(raw: Any) -> Path:
    text = _non_empty(raw, "change_root")
    path = Path(text)
    if not path.is_absolute():
        raise ProtocolError("CHANGE_ROOT_REQUIRED", "change_root must be an absolute path")
    if not path.exists() or not path.is_dir():
        raise ProtocolError("CHANGE_ROOT_NOT_FOUND", "change_root must name an existing directory", {"change_root": text})
    return path.resolve()


def _read_handoff_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise ProtocolError("MISSING_FINISH_HANDOFF", "required finish handoff artifact is missing", {"artifact": label, "path": str(path)})
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError("INVALID_JSON_FILE", "finish handoff artifact is not valid JSON", {"artifact": label, "path": str(path)}) from exc
    return _require_object(value, label)


def _finish_handoff_docs(change_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        _read_handoff_json(change_root / "completion.json", "completion.json"),
        _read_handoff_json(change_root / "decision.json", "decision.json"),
        _read_handoff_json(change_root / "finish-plan.json", "finish-plan.json"),
    )


def _repo_for_change_root(change_root: Path) -> Path:
    if len(change_root.parents) >= 3:
        return change_root.parents[2]
    return change_root


def _validate_finish_handoff(state: dict[str, Any], change_root: Path) -> dict[str, Any]:
    completion_doc, decision_doc, finish_plan = _finish_handoff_docs(change_root)
    try:
        return EVIDENCE_HELPER.validate_finish_handoff(
            state,
            completion_doc,
            decision_doc,
            finish_plan,
            {"completion_md": change_root / "completion.md", "decision_md": change_root / "decision.md", "repo": _repo_for_change_root(change_root)},
        )
    except Exception as exc:
        if exc.__class__.__name__ == "ProtocolError":
            raise _wrap_evidence_error(exc) from exc
        raise


def _readiness(change_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    try:
        return EVIDENCE_HELPER.finish_readiness(change_root, state["contract"]["sha256"], state["context"]["fingerprint"])
    except Exception as exc:
        if exc.__class__.__name__ == "ProtocolError":
            raise _wrap_evidence_error(exc) from exc
        raise


def _completion_identity_from_doc(completion_doc: dict[str, Any], state_version: int) -> dict[str, Any]:
    completion = _require_object(completion_doc.get("completion"), "completion evidence")
    return {
        "contract_sha256": _require_sha(completion_doc.get("contract_sha256"), "completion.contract_sha256"),
        "context_fingerprint": _require_sha(completion_doc.get("context_fingerprint"), "completion.context_fingerprint"),
        "completion_sha256": _require_sha(completion.get("completion_sha256"), "completion.completion_sha256"),
        "proposal_sha256": _require_sha(completion.get("proposal_sha256"), "completion.proposal_sha256"),
        "mutation_map_sha256": _require_sha(completion.get("mutation_map_sha256"), "completion.mutation_map_sha256"),
        "task_heads": copy.deepcopy(_require_object(completion.get("task_heads"), "completion.task_heads")),
        "implementation_range": copy.deepcopy(_require_object(completion.get("implementation_range"), "completion.implementation_range")),
        "acceptance_index_sha256": _require_sha(completion.get("acceptance_index_sha256"), "completion.acceptance_index_sha256"),
        "state_version": state_version,
    }


def _decision_identity_from_handoff(completion_identity: dict[str, Any], decision_doc: dict[str, Any], finish_plan: dict[str, Any], state_version: int, approved: bool = False) -> dict[str, Any]:
    decision = _require_object(decision_doc.get("decision"), "decision evidence")
    return {
        **copy.deepcopy(completion_identity),
        "decision_sha256": _require_sha(decision.get("decision_sha256"), "decision.decision_sha256"),
        "finish_plan_sha256": _require_sha(finish_plan.get("finish_plan_sha256"), "finish_plan.finish_plan_sha256"),
        "decision_state_version": _positive_int(decision.get("decision_state_version"), "decision.decision_state_version"),
        "state_version": state_version,
        "approved": approved,
    }


def _positive_int(value: Any, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ProtocolError("INVALID_STATE_VERSION", f"{where} must be a positive integer")
    return value


def start_completion(path: str | Path, expected_version: int, packet: dict[str, Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    if before["status"] not in {"ready_to_execute", "executing"}:
        raise ProtocolError("INVALID_TRANSITION", "completion can start only after execution")
    if not all(task["status"] == "completed" for task in before["tasks"]):
        raise ProtocolError("TASKS_INCOMPLETE", "all tasks must be PASS before completion")
    packet = _require_object(packet, "completion packet")
    identity = _require_completion_identity(before, packet)
    after = copy.deepcopy(before)
    after["status"] = "completing"
    metadata = _metadata(after)
    metadata["completion_packet"] = copy.deepcopy(packet)
    metadata["completion_identity"] = identity
    _update_initial_metadata(after, metadata)
    return _commit(path, before, after, "COMPLETION_STARTED", event_reason={"packet_sha256": sha256_value(packet)})


def record_completion(path: str | Path, expected_version: int, completion: dict[str, Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    if before["status"] != "completing":
        raise ProtocolError("COMPLETION_NOT_RUNNING", "completion is not running")
    completion = _require_object(completion, "completion")
    verdict = completion.get("verdict")
    after = copy.deepcopy(before)
    if verdict == "FAIL":
        owner = _non_empty(completion.get("blocking_owner"), "blocking_owner")
        finding_id = _non_empty(completion.get("finding_id", "completion-blocker"), "finding_id")
        reason = _non_empty(completion.get("reason", "completion blocker"), "reason")
        owner_tasks = [task for task in after["tasks"] if _owner_for_task(after, str(task["id"])) == owner]
        if not owner_tasks:
            raise ProtocolError("INVALID_COMPLETION", "completion blocker owner does not map to a Task")
        task_id = _non_empty(completion.get("task_id", owner_tasks[0]["id"]), "task_id")
        if task_id not in {str(task["id"]) for task in owner_tasks}:
            raise ProtocolError("INVALID_COMPLETION", "completion blocker task_id does not belong to owner")
        blocker = {"id": f"{task_id}:{finding_id}", "task_id": task_id, "severity": "blocking", "reason": reason, "owner": owner, "source_gate": "COMPLETION"}
        after["status"] = "repair_required"
        _task_state(after, task_id)["status"] = "blocked"
        after["blockers"].append(blocker)
        after.pop("decision", None)
        after.pop("completion", None)
        metadata = _metadata(after)
        metadata.pop("completion_packet", None)
        metadata.pop("completion_identity", None)
        metadata.pop("completion", None)
        _update_initial_metadata(after, metadata)
        return _commit(path, before, after, "COMPLETION_FAILED", event_reason={"task_id": task_id, "finding_id": finding_id, "owner": owner})
    if verdict != "PASS":
        raise ProtocolError("INVALID_COMPLETION", "completion verdict must be PASS or FAIL")
    identity = _require_completion_identity(after, completion)
    metadata = _metadata(after)
    packet_identity = metadata.get("completion_identity")
    if packet_identity != identity:
        raise ProtocolError("INVALID_IDENTITY", "completion PASS identity must match completion packet")
    change_root = _absolute_change_root(completion.get("change_root") or completion.get("CHANGE_ROOT"))
    completion_doc, decision_doc, finish_plan = _finish_handoff_docs(change_root)
    projected = copy.deepcopy(after)
    projected["status"] = "decision_pending"
    projected["state_version"] = before["state_version"] + 1
    projected_completion = _completion_identity_from_doc(completion_doc, before["state_version"])
    projected_decision = _decision_identity_from_handoff(projected_completion, decision_doc, finish_plan, before["state_version"], False)
    projected["completion"] = projected_completion
    projected["decision"] = projected_decision
    metadata["completion"] = copy.deepcopy(completion)
    metadata["finish_change_root"] = str(change_root)
    _update_initial_metadata(projected, metadata)
    _validate_finish_handoff(projected, change_root)
    return _commit(path, before, projected, "COMPLETION_PASSED", artifact_sha256=projected_completion["proposal_sha256"])


def record_finish_handoff(path: str | Path, expected_version: int, change_root: str | Path) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    if before["status"] != "decision_pending":
        raise ProtocolError("DECISION_NOT_PENDING", "Finish handoff can be rebuilt only while decision is pending")
    if _has_canonical_finish_identity(before):
        raise ProtocolError("FINISH_HANDOFF_ALREADY_CANONICAL", "canonical Finish handoff identity is already recorded")
    change_root_path = _absolute_change_root(change_root)
    completion_doc, decision_doc, finish_plan = _finish_handoff_docs(change_root_path)
    after = copy.deepcopy(before)
    after["state_version"] = before["state_version"] + 1
    completion_identity = _completion_identity_from_doc(completion_doc, before["state_version"])
    after["completion"] = completion_identity
    after["decision"] = _decision_identity_from_handoff(completion_identity, decision_doc, finish_plan, before["state_version"], False)
    metadata = _metadata(after)
    metadata["finish_change_root"] = str(change_root_path)
    _update_initial_metadata(after, metadata)
    _validate_finish_handoff(after, change_root_path)
    return _commit(path, before, after, "FINISH_HANDOFF_REBUILT", artifact_sha256=after["decision"]["finish_plan_sha256"])


def finish_decision(path: str | Path, expected_version: int, decision: str, metadata_in: dict[str, Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    if before["status"] != "decision_pending" or "completion" not in before or "decision" not in before:
        raise ProtocolError("DECISION_NOT_PENDING", "Finish decision is not pending")
    decision = _normalize_exact_alias(decision, FINISH_DECISION_ALIASES, "decision", "INVALID_FINISH_DECISION", "decision must be exact accept/request_changes/defer/reject or 同意/要求修改/暂缓/拒绝")
    metadata_in = _require_object(metadata_in, "decision metadata")
    change_root = _absolute_change_root(metadata_in.get("change_root") or metadata_in.get("CHANGE_ROOT"))
    readiness = _readiness(change_root, before)
    if readiness.get("ready") is not True:
        raise ProtocolError(readiness.get("failure_code") or "FINISH_HANDOFF_NOT_READY", "Finish handoff readiness failed", {"readiness": readiness})
    after = copy.deepcopy(before)
    generated_decision = _require_object(before.get("decision"), "generated decision")
    decision_sha = _require_sha(metadata_in.get("decision_sha256"), "decision_sha256")
    finish_plan_sha = _require_sha(metadata_in.get("finish_plan_sha256"), "finish_plan_sha256")
    expected_decision_state_version = _positive_int(metadata_in.get("expected_decision_state_version", readiness.get("decision_state_version")), "expected_decision_state_version")
    if decision_sha != readiness.get("decision_sha256") or decision_sha != _require_sha(generated_decision.get("decision_sha256"), "generated decision.decision_sha256"):
        raise ProtocolError("STALE_DECISION", "Finish decision identity is stale")
    if finish_plan_sha != readiness.get("finish_plan_sha256") or finish_plan_sha != generated_decision.get("finish_plan_sha256"):
        raise ProtocolError("STALE_FINISH_PLAN", "Finish plan identity is stale")
    if expected_decision_state_version != readiness.get("decision_state_version") or expected_decision_state_version != generated_decision.get("decision_state_version"):
        raise ProtocolError("STALE_DECISION", "Finish accept expected decision state version is stale")
    decided_at = _non_empty(metadata_in.get("decided_at", "unknown"), "decided_at")
    notes = copy.deepcopy(metadata_in)
    notes["decision"] = decision
    notes["readiness"] = {"decision_sha256": readiness.get("decision_sha256"), "finish_plan_sha256": readiness.get("finish_plan_sha256"), "decision_state_version": readiness.get("decision_state_version")}
    if decision == "accept":
        after["status"] = "folding"
        after_decision = copy.deepcopy(generated_decision)
        after_decision["approved"] = True
        after_decision["state_version"] = before["state_version"]
        after["decision"] = after_decision
        approval_identity = _non_empty(metadata_in.get("approval_identity", f"accept:{decided_at}"), "approval_identity")
        notes["approval_identity"] = approval_identity
        after["gates"]["finish"] = {"status": "approved", "artifact_sha256": decision_sha, "decision_sha256": decision_sha, "state_version": before["state_version"], "approval_id": approval_identity, "approved_at": decided_at, "notes": canonical_json(notes)}
        action = "FINISH_ACCEPTED"
    elif decision == "request_changes":
        after["status"] = "ready_to_execute"
        after_decision = copy.deepcopy(generated_decision)
        after_decision["approved"] = False
        after["decision"] = after_decision
        after["gates"]["finish"] = {"status": "stale", "decision_sha256": decision_sha, "state_version": before["state_version"], "notes": canonical_json(notes)}
        action = "FINISH_REQUEST_CHANGES"
    elif decision == "defer":
        after["status"] = "deferred"
        _demote_completed_for_schema(after, "blocked")
        after_decision = copy.deepcopy(generated_decision)
        after_decision["approved"] = False
        after["decision"] = after_decision
        after["gates"]["finish"] = {"status": "deferred", "decision_sha256": decision_sha, "state_version": before["state_version"], "notes": canonical_json(notes)}
        action = "FINISH_DEFERRED"
    else:
        after["status"] = "rejected"
        _demote_completed_for_schema(after, "rejected")
        after_decision = copy.deepcopy(generated_decision)
        after_decision["approved"] = False
        after["decision"] = after_decision
        after["gates"]["finish"] = {"status": "rejected", "decision_sha256": decision_sha, "state_version": before["state_version"], "notes": canonical_json(notes)}
        action = "FINISH_REJECTED"
    metadata = _metadata(after)
    metadata["finish_change_root"] = str(change_root)
    _update_initial_metadata(after, metadata)
    return _commit(path, before, after, action, artifact_sha256=decision_sha, event_reason=notes)


def record_finish_apply(path: str | Path, expected_version: int, journal: dict[str, Any]) -> dict[str, Any]:
    before = load_state(path)
    _check_version(before, expected_version)
    if before["status"] != "folding" or before["gates"]["finish"].get("status") != "approved":
        raise ProtocolError("FINISH_NOT_ACCEPTED", "fresh Finish accept is required before archive")
    journal = _require_object(journal, "finish apply journal")
    required = {"decision_sha256", "finish_plan_sha256", "approval_identity", "journal_sha256", "verified"}
    missing = sorted(required - set(journal))
    if missing:
        raise ProtocolError("INVALID_FINISH_JOURNAL", "finish apply journal shape mismatch", {"missing": missing})
    decision_sha = _require_sha(journal.get("decision_sha256"), "decision_sha256")
    finish_plan_sha = _require_sha(journal.get("finish_plan_sha256"), "finish_plan_sha256")
    if decision_sha != before["decision"]["decision_sha256"] or decision_sha != before["gates"]["finish"].get("decision_sha256"):
        raise ProtocolError("STALE_DECISION", "finish apply decision identity is stale")
    if finish_plan_sha != before["decision"].get("finish_plan_sha256"):
        raise ProtocolError("STALE_FINISH_PLAN", "finish apply finish plan identity is stale")
    notes = before["gates"]["finish"].get("notes", "{}")
    try:
        finish_meta = json.loads(notes)
    except json.JSONDecodeError as exc:
        raise ProtocolError("INVALID_DECISION_METADATA", "finish decision metadata is invalid") from exc
    approval_identity = _non_empty(journal.get("approval_identity"), "approval_identity")
    if approval_identity != finish_meta.get("approval_identity"):
        raise ProtocolError("STALE_DECISION", "finish apply approval identity is stale")
    if journal.get("verified") is not True:
        raise ProtocolError("APPLY_NOT_VERIFIED", "finish apply journal must be verified")
    journal_sha = _require_sha(journal.get("journal_sha256"), "journal_sha256")
    after = copy.deepcopy(before)
    after["status"] = "archived"
    return _commit(path, before, after, "FINISH_APPLIED", artifact_sha256=journal_sha, event_reason={"journal_sha256": journal_sha, "decision_sha256": decision_sha, "finish_plan_sha256": finish_plan_sha, "approval_identity": approval_identity})


def _json_arg(value: str, where: str) -> Any:
    text = value.strip()
    if text.startswith(("{", "[", '"')):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProtocolError("INVALID_JSON_ARGUMENT", f"{where} is not valid JSON") from exc
    path = Path(value)
    if not path.exists() or not path.is_file():
        raise ProtocolError("INPUT_NOT_FOUND", f"{where} path must name an existing file", {"path": value})
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProtocolError("INVALID_JSON_FILE", f"{where} file is not valid JSON", {"path": value}) from exc


def _ok(payload: dict[str, Any]) -> int:
    sys.stdout.write(canonical_json({"ok": True, **payload}) + "\n")
    return 0


def _err(error: ProtocolError) -> int:
    sys.stderr.write(canonical_json({"ok": False, "code": error.code, "message": error.message, "details": error.details}) + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Advance Nuclio state transitions")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.add_argument("state")
    p.add_argument("--contract-identity-json", required=True)
    p.add_argument("--context-identity-json", required=True)
    p.add_argument("--task-graph-json", required=True)

    for name in ("inspect", "next-action"):
        p = sub.add_parser(name)
        p.add_argument("state")

    p = sub.add_parser("approve-contract")
    p.add_argument("state")
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--contract-identity-json", required=True)
    p.add_argument("--context-identity-json", required=True)
    p.add_argument("--approval-json", required=True)

    p = sub.add_parser("start-task")
    p.add_argument("state")
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--packet-json", required=True)

    for name, arg in (("record-implementation", "--evidence-json"), ("record-fix", "--evidence-json")):
        p = sub.add_parser(name)
        p.add_argument("state")
        p.add_argument("--expected-version", type=int, required=True)
        p.add_argument(arg, required=True)

    p = sub.add_parser("record-completion")
    p.add_argument("state")
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--completion-json", required=True)
    p.add_argument("--change-root", required=True)

    p = sub.add_parser("record-finish-handoff")
    p.add_argument("state")
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--change-root", required=True)

    p = sub.add_parser("record-finish-apply")
    p.add_argument("state")
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--journal-json", required=True)

    p = sub.add_parser("import-task-review")
    p.add_argument("state")
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--review-json", required=True)

    for name in ("needs-fix", "authorize-fix"):
        p = sub.add_parser(name)
        p.add_argument("state")
        p.add_argument("--expected-version", type=int, required=True)
        p.add_argument("--task-id", required=True)
        p.add_argument("--finding-ids-json", required=True)

    p = sub.add_parser("start-completion")
    p.add_argument("state")
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--packet-json", required=True)

    p = sub.add_parser("finish-decision")
    p.add_argument("state")
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--decision", required=True)
    p.add_argument("--metadata-json", required=True)
    p.add_argument("--change-root", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return _ok({"state": init_state(args.state, _json_arg(args.contract_identity_json, "contract identity"), _json_arg(args.context_identity_json, "context identity"), _json_arg(args.task_graph_json, "task graph"))})
        if args.command == "inspect":
            return _ok({"inspect": inspect_state(args.state)})
        if args.command == "next-action":
            return _ok({"next_action": next_action(args.state)})
        if args.command == "approve-contract":
            return _ok({"state": approve_contract(args.state, args.expected_version, _json_arg(args.contract_identity_json, "contract identity"), _json_arg(args.context_identity_json, "context identity"), _json_arg(args.approval_json, "approval"))})
        if args.command == "start-task":
            return _ok({"state": start_task(args.state, args.expected_version, args.task_id, _json_arg(args.packet_json, "packet"))})
        if args.command == "record-implementation":
            return _ok({"state": record_implementation(args.state, args.expected_version, _json_arg(args.evidence_json, "evidence"))})
        if args.command == "import-task-review":
            return _ok({"state": import_task_review(args.state, args.expected_version, _json_arg(args.review_json, "review"))})
        if args.command == "needs-fix":
            return _ok({"state": needs_fix(args.state, args.expected_version, args.task_id, _json_arg(args.finding_ids_json, "finding ids"))})
        if args.command == "authorize-fix":
            return _ok({"state": authorize_fix(args.state, args.expected_version, args.task_id, _json_arg(args.finding_ids_json, "finding ids"))})
        if args.command == "record-fix":
            return _ok({"state": record_fix(args.state, args.expected_version, _json_arg(args.evidence_json, "evidence"))})
        if args.command == "start-completion":
            return _ok({"state": start_completion(args.state, args.expected_version, _json_arg(args.packet_json, "packet"))})
        if args.command == "record-completion":
            completion = _json_arg(args.completion_json, "completion")
            completion.setdefault("change_root", args.change_root)
            return _ok({"state": record_completion(args.state, args.expected_version, completion)})
        if args.command == "record-finish-handoff":
            return _ok({"state": record_finish_handoff(args.state, args.expected_version, args.change_root)})
        if args.command == "finish-decision":
            metadata = _json_arg(args.metadata_json, "decision metadata")
            metadata.setdefault("change_root", args.change_root)
            return _ok({"state": finish_decision(args.state, args.expected_version, args.decision, metadata)})
        if args.command == "record-finish-apply":
            raw_journal = args.journal_json.strip()
            if not raw_journal.startswith(("{", "[", '"')) and Path(raw_journal).suffix == ".md":
                raise ProtocolError("INVALID_FINISH_JOURNAL", "--journal-json must name verified finish-apply.json, not markdown")
            return _ok({"state": record_finish_apply(args.state, args.expected_version, _json_arg(args.journal_json, "journal"))})
        raise ProtocolError("INVALID_COMMAND", "unknown command")
    except ProtocolError as exc:
        return _err(exc)


if __name__ == "__main__":
    raise SystemExit(main())
