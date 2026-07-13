#!/usr/bin/env python3
"""Deterministic Nuclio state helper.

This helper only inspects gate readiness and performs explicit preserve/merge
state updates. It is not a Nuclio runtime, daemon, hook, MCP server, background
automation, or gate approval system.
"""

import argparse
import copy
import hashlib
import json
import pathlib
import re
import sys


MISSING_FILES_FOR_CHANGE = ("state.json", "plan.yaml", "context/implement.jsonl")
ALLOWED_REPLACE_OBJECT_PATHS = {"implementation.approved_control_plane"}
TASK_STATUS_ALLOWLIST = {"pending", "in_progress", "completed", "blocked"}
BLOCKER_KIND_ALLOWLIST = {"design_revision", "resolved_evidence"}
RECORD_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
CONTEXT_REF_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
PATH_GLOB_CHARS = set("*?[")
URI_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
BROAD_PROJECT_PATHS = {".", "./", ".dev-docs", ".dev-docs/", ".dev-docs\\"}
FORBIDDEN_MUTATION_ROOTS = (".git", ".dev-docs/changes", ".superpowers/sdd")



class StateHelperError(Exception):
    """Expected command error that should be reported as JSON."""

    def __init__(self, message, *, detail=None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports parse errors as JSON."""

    def error(self, message):
        raise StateHelperError("parse error", detail=message)


def print_json(payload):
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def path_text(path):
    return str(path)


def load_json_file(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise StateHelperError("state file not found", detail=path_text(path)) from exc
    except json.JSONDecodeError as exc:
        raise StateHelperError("invalid JSON", detail=str(exc)) from exc
    except OSError as exc:
        raise StateHelperError("failed to read state file", detail=str(exc)) from exc


def load_json_object_file(path, label):
    data = load_json_file(path)
    if not isinstance(data, dict):
        raise StateHelperError(f"{label} must be a JSON object", detail=path_text(path))
    return data


def load_json_object_text(raw, label):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StateHelperError(f"invalid {label} JSON", detail=str(exc)) from exc
    if not isinstance(data, dict):
        raise StateHelperError(f"{label} must be a JSON object")
    return data


def load_json_string_array_text(raw, label):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StateHelperError(f"invalid {label} JSON", detail=str(exc)) from exc
    if not isinstance(data, list):
        raise StateHelperError(f"{label} must be a JSON array")
    seen = set()
    for item in data:
        if not isinstance(item, str):
            raise StateHelperError(f"{label} must contain only string IDs")
        if item in seen:
            raise StateHelperError(f"{label} contains duplicate Task ID", detail=item)
        seen.add(item)
    return data


def serialize_json_file_payload(data):
    try:
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        payload.encode("utf-8")
        return payload
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise StateHelperError("failed to serialize state JSON", detail=str(exc)) from exc


def write_json_file(path, data):
    payload = serialize_json_file_payload(data)
    try:
        with path.open("w", encoding="utf-8") as handle:
            handle.write(payload)
    except OSError as exc:
        raise StateHelperError("failed to write state file", detail=str(exc)) from exc


def object_summary(value):
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return {}


def inspect_state(args):
    if args.change is None and args.state is None:
        raise StateHelperError("either --change or --state is required")
    if args.change is not None and args.state is not None:
        raise StateHelperError("use only one of --change or --state")

    missing_files = []
    if args.change is not None:
        change_path = args.change
        state_path = change_path / "state.json"
        missing_files = [name for name in MISSING_FILES_FOR_CHANGE if not (change_path / name).is_file()]
    else:
        state_path = args.state
        change_path = state_path.parent

    state = load_json_object_file(state_path, "state")

    print_json(
        {
            "ok": True,
            "state_path": path_text(state_path),
            "change_path": path_text(change_path),
            "phase": state.get("phase"),
            "status": state.get("status"),
            "current_task": copy.deepcopy(state.get("current_task")),
            "gates": object_summary(state.get("gates", {})),
            "artifacts": object_summary(state.get("artifacts", {})),
            "tasks": object_summary(state.get("tasks", {})),
            "implementation": object_summary(state.get("implementation", {})),
            "evidence": object_summary(state.get("evidence", {})),
            "active": copy.deepcopy(state.get("active")),
            "missing_files": missing_files,
        }
    )
    return 0


def check_gate(args):
    gate = args.gate
    state = load_json_object_file(args.state, "state")

    if args.authorized:
        print_json(
            {
                "ok": True,
                "gate": gate,
                "ready": True,
                "reason": "current-turn authorization supplied",
            }
        )
        return 0

    gates = state.get("gates")
    if not isinstance(gates, dict):
        reason = "state.gates is missing or not an object"
    else:
        value = gates.get(gate)
        if value == "approved":
            print_json(
                {
                    "ok": True,
                    "gate": gate,
                    "ready": True,
                    "reason": "gate approved in state",
                }
            )
            return 0
        if gate not in gates:
            reason = "gate missing in state"
        else:
            reason = f"gate is {value!r}, not 'approved'"

    print_json({"ok": True, "gate": gate, "ready": False, "reason": reason})
    return 0


def recursive_merge(base, patch):
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = recursive_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def patch_sets_gate_approval(patch):
    gates = patch.get("gates")
    if not isinstance(gates, dict):
        return False
    for value in gates.values():
        if value == "approved":
            return True
    return False


def merge_state(args):
    state = load_json_object_file(args.state, "state")
    patch = load_json_object_text(args.patch, "patch")

    if patch_sets_gate_approval(patch) and not args.allow_approval:
        raise StateHelperError("patch sets gate approval without --allow-approval")

    merged = recursive_merge(state, patch)
    write_json_file(args.state, merged)
    print_json({"ok": True, "state_path": path_text(args.state), "updated": True})
    return 0


def validate_implementation_parent(state):
    if "implementation" in state and not isinstance(state["implementation"], dict):
        raise StateHelperError("state.implementation must be a JSON object when present")


def validate_task_status(task_id, task):
    if not isinstance(task, dict):
        raise StateHelperError("state.tasks entries must be JSON objects", detail=task_id)
    status = task.get("status")
    if not isinstance(status, str):
        raise StateHelperError("state.tasks entries must have string status", detail=task_id)
    if status not in TASK_STATUS_ALLOWLIST:
        raise StateHelperError("state.tasks entries must use canonical status", detail=task_id)
    return status


def validate_optional_record_id(task_id, task, field):
    value = task.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not RECORD_ID_PATTERN.fullmatch(value):
        raise StateHelperError(
            f"state.tasks entries {field} must be null or sha256 plus 64 lowercase hex characters",
            detail=task_id,
        )
    return value


def validate_authorization_exclusivity(task_id, manual_repair_authorization, design_revision_authorization):
    if manual_repair_authorization is not None and design_revision_authorization is not None:
        raise StateHelperError(
            "state.tasks entries manual_repair_authorization and design_revision_authorization must not both be non-null",
            detail=task_id,
        )


def is_non_negative_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_safe_project_relative_path(value, label):
    if not isinstance(value, str) or not value:
        raise StateHelperError(f"{label} must be a non-empty project-relative path")
    if value.strip() != value:
        raise StateHelperError(f"{label} must not have surrounding whitespace")
    if value in BROAD_PROJECT_PATHS or value == "~" or value.startswith(("~/", "~\\")):
        raise StateHelperError(f"{label} must be a specific project-relative path")
    if URI_SCHEME_PATTERN.match(value):
        raise StateHelperError(f"{label} must not be a URI")
    if "\\" in value or "//" in value:
        raise StateHelperError(f"{label} must use forward-slash project-relative path")
    if value.startswith("./") or "/./" in value:
        raise StateHelperError(f"{label} must not contain dot segments")
    path = pathlib.PurePosixPath(value)
    windows_path = pathlib.PureWindowsPath(value)
    if path.is_absolute() or windows_path.is_absolute() or windows_path.drive or value.startswith("\\"):
        raise StateHelperError(f"{label} must be project-relative")
    if value.endswith(("/", "\\")):
        raise StateHelperError(f"{label} must not end with a separator")
    if any(char in value for char in PATH_GLOB_CHARS):
        raise StateHelperError(f"{label} must not contain glob characters")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise StateHelperError(f"{label} must not contain empty, dot, or dot-dot segments")
    if ".." in path.parts or ".." in windows_path.parts or path.as_posix() != value:
        raise StateHelperError(f"{label} must be a normalized project-relative path")


def validate_mutation_target_path(value, label):
    validate_safe_project_relative_path(value, label)
    if any(value == root or value.startswith(root + "/") for root in FORBIDDEN_MUTATION_ROOTS):
        raise StateHelperError(f"{label} must not target workflow or VCS control paths")


def validate_blocker_evidence_path(value):
    validate_safe_project_relative_path(value, "blocked Task blocker.evidence")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise StateHelperError("blocked Task blocker.evidence must not contain ASCII control characters")


def validate_canonical_blocker(task_id, task):
    blocker = task.get("blocker")
    if not isinstance(blocker, dict):
        raise StateHelperError("blocked Task blocker must be a canonical object", detail=task_id)
    kind = blocker.get("kind")
    if kind not in BLOCKER_KIND_ALLOWLIST:
        raise StateHelperError("blocked Task blocker.kind must be design_revision or resolved_evidence", detail=task_id)
    for field in ("code", "reason"):
        value = blocker.get(field)
        if not isinstance(value, str) or value == "":
            raise StateHelperError(f"blocked Task blocker.{field} must be a non-empty string", detail=task_id)
    validate_blocker_evidence_path(blocker.get("evidence"))
    if not is_positive_integer(blocker.get("blocker_occurrence")):
        raise StateHelperError("blocked Task blocker.blocker_occurrence must be a positive integer", detail=task_id)
    blocker_record_id = blocker.get("blocker_record_id")
    if not isinstance(blocker_record_id, str) or not RECORD_ID_PATTERN.fullmatch(blocker_record_id):
        raise StateHelperError(
            "blocked Task blocker.blocker_record_id must be sha256 plus 64 lowercase hex characters",
            detail=task_id,
        )
    task_reason = task.get("reason")
    if not isinstance(task_reason, str) or task_reason == "":
        raise StateHelperError("blocked Task reason must be a non-empty string", detail=task_id)
    if task_reason != blocker.get("reason"):
        raise StateHelperError("blocked Task reason must equal blocker.reason", detail=task_id)
    return kind


def validate_current_task_pointer(state, tasks):
    current_task = state.get("current_task")
    if current_task is None:
        return None
    if not isinstance(current_task, dict):
        raise StateHelperError("state.current_task must be null or a canonical object")
    if set(current_task.keys()) != {"id", "attempt", "status"}:
        raise StateHelperError("state.current_task must be canonical {id,attempt,status} shape")
    task_id = current_task.get("id")
    attempt = current_task.get("attempt")
    status = current_task.get("status")
    if not isinstance(task_id, str) or task_id == "":
        raise StateHelperError("state.current_task.id must be a non-empty string")
    if task_id not in tasks:
        raise StateHelperError("state.current_task.id must reference state.tasks", detail=task_id)
    if not is_non_negative_integer(attempt):
        raise StateHelperError("state.current_task.attempt must be a non-negative integer", detail=task_id)
    if not isinstance(status, str):
        raise StateHelperError("state.current_task.status must be a string", detail=task_id)
    task = tasks[task_id]
    task_attempts = task.get("attempts")
    if not is_non_negative_integer(task_attempts):
        raise StateHelperError("state.tasks entry attempts must be a non-negative integer", detail=task_id)
    if task_attempts != attempt:
        raise StateHelperError("state.current_task.attempt must match state.tasks entry attempts", detail=task_id)
    if task.get("status") != status:
        raise StateHelperError("state.current_task.status must match state.tasks entry", detail=task_id)
    return current_task


def get_or_create_implementation(updated):
    if "implementation" not in updated:
        updated["implementation"] = {}
    return updated["implementation"]


def replace_object(args):
    if not args.allow_approval:
        raise StateHelperError("object replacement requires --allow-approval")
    if args.object_path not in ALLOWED_REPLACE_OBJECT_PATHS:
        raise StateHelperError("object path is not allowlisted", detail=args.object_path)

    state = load_json_object_file(args.state, "state")
    value = load_json_object_text(args.value, "value")
    parent_key, child_key = args.object_path.split(".", 1)
    if parent_key != "implementation":
        raise StateHelperError("object path parent is not supported", detail=parent_key)
    validate_implementation_parent(state)

    updated = copy.deepcopy(state)
    parent = get_or_create_implementation(updated)
    parent[child_key] = copy.deepcopy(value)

    write_json_file(args.state, updated)
    print_json(
        {
            "ok": True,
            "state_path": path_text(args.state),
            "replaced_object_path": args.object_path,
            "updated": True,
        }
    )
    return 0


CONTRACT_TASK_FIELDS = {
    "id", "depends_on", "acceptance", "verification", "context_refs",
    "mutation_targets", "ownership_handoffs",
}
CONTRACT_CHANGE_FIELDS = CONTRACT_TASK_FIELDS - {"id"}
CURRENT_EVIDENCE_FIELDS = {
    "task_scope_fingerprint", "review_clean_fingerprint", "review_clean_marker",
    "current_fingerprint", "current_review_fingerprint",
}
CURRENT_SNAPSHOT_REF_FIELDS = {
    "completion_snapshot_refs", "dependency_handoff_snapshot_refs", "live_snapshot_refs",
}
SNAPSHOT_REF_COMMON_FIELDS = {"evidence_path", "record_hash", "path", "path_id"}
SNAPSHOT_PATH_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SNAPSHOT_RECORD_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SNAPSHOT_FILE_PATTERNS = {
    "completion_snapshot_refs": re.compile(
        r"^completion-(?P<task>[A-Za-z0-9][A-Za-z0-9_-]*)-(?P<path_id>[0-9a-f]{64})-a(?P<attempt>[0-9]+)-r(?P<review_cycle>[0-9]+)\.json$"
    ),
    "dependency_handoff_snapshot_refs": re.compile(
        r"^dependency-(?P<from_task>[A-Za-z0-9][A-Za-z0-9_-]*)-to-(?P<task>[A-Za-z0-9][A-Za-z0-9_-]*)-(?P<path_id>[0-9a-f]{64})-a(?P<attempt>[0-9]+)-r(?P<review_cycle>[0-9]+)\.json$"
    ),
    "live_snapshot_refs": re.compile(
        r"^live-(?P<task>[A-Za-z0-9][A-Za-z0-9_-]*)-(?P<path_id>[0-9a-f]{64})-a(?P<attempt>[0-9]+)-r(?P<review_cycle>[0-9]+)\.json$"
    ),
}


def canonical_json_identity(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise StateHelperError("task contract contains unpaired Unicode surrogate") from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def context_ref_looks_like_path(value):
    return (
        value.startswith((".", "/", "\\", "~"))
        or "/" in value
        or "\\" in value
        or pathlib.PureWindowsPath(value).drive
        or URI_SCHEME_PATTERN.match(value) is not None
    )


def validate_context_ref(value, label):
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        raise StateHelperError(f"{label}.tasks contains invalid context ref")
    if context_ref_looks_like_path(value):
        validate_safe_project_relative_path(value, f"{label}.tasks context ref")
    elif CONTEXT_REF_ID_PATTERN.fullmatch(value) is None:
        raise StateHelperError(f"{label}.tasks contains invalid context ref")


def validate_task_contract(contract, label):
    if not isinstance(contract, dict):
        raise StateHelperError(f"{label} must be a JSON object")
    if set(contract) != {"plan_order", "tasks", "ownership_table"}:
        raise StateHelperError(f"{label} must have canonical fields")
    plan_order = contract["plan_order"]
    task_entries = contract["tasks"]
    ownership_table = contract["ownership_table"]
    if not isinstance(plan_order, list) or not all(isinstance(item, str) and item for item in plan_order):
        raise StateHelperError(f"{label}.plan_order must be a string ID array")
    if len(plan_order) != len(set(plan_order)):
        raise StateHelperError(f"{label}.plan_order contains duplicate Task ID")
    if not isinstance(task_entries, list):
        raise StateHelperError(f"{label}.tasks must be an array")
    if not isinstance(ownership_table, list):
        raise StateHelperError(f"{label}.ownership_table must be an array")

    by_id = {}
    for task in task_entries:
        if not isinstance(task, dict) or set(task) != CONTRACT_TASK_FIELDS:
            raise StateHelperError(f"{label}.tasks entries must have canonical fields")
        task_id = task.get("id")
        if (
            not isinstance(task_id, str) or TASK_ID_PATTERN.fullmatch(task_id) is None
            or task_id in by_id
        ):
            raise StateHelperError(f"{label}.tasks contains invalid or duplicate Task ID", detail=task_id)
        for field in ("depends_on", "acceptance", "context_refs", "mutation_targets", "ownership_handoffs"):
            if not isinstance(task[field], list):
                raise StateHelperError(f"{label}.tasks {field} must be an array", detail=task_id)
        if not task["acceptance"] or any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in task["acceptance"]
        ):
            raise StateHelperError(f"{label}.tasks acceptance must contain canonical non-empty strings", detail=task_id)
        verification = task["verification"]
        if not isinstance(verification, dict) or not set(verification).issubset({"commands", "notes"}) or "commands" not in verification:
            raise StateHelperError(f"{label}.tasks verification must have canonical fields", detail=task_id)
        commands = verification["commands"]
        notes = verification.get("notes")
        if not isinstance(commands, list) or any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in commands
        ):
            raise StateHelperError(f"{label}.tasks verification commands must be a canonical string array", detail=task_id)
        if notes is not None and (
            not isinstance(notes, str) or not notes or notes != notes.strip()
        ):
            raise StateHelperError(f"{label}.tasks verification notes must be a canonical non-empty string", detail=task_id)
        if not commands and notes is None:
            raise StateHelperError(f"{label}.tasks verification must not be empty", detail=task_id)
        for context_ref in task["context_refs"]:
            try:
                validate_context_ref(context_ref, label)
            except StateHelperError as exc:
                if exc.detail is None:
                    exc.detail = task_id
                raise
        by_id[task_id] = task
    if plan_order != [task["id"] for task in task_entries] or set(plan_order) != set(by_id):
        raise StateHelperError(f"{label} plan_order must exactly match tasks")

    task_ids = set(by_id)
    declared_handoffs = []
    owners_by_path = {}
    for task_id, task in by_id.items():
        dependencies = task["depends_on"]
        if any(
            not isinstance(item, str) or TASK_ID_PATTERN.fullmatch(item) is None or item not in task_ids
            for item in dependencies
        ):
            raise StateHelperError(f"{label} contains unknown dependency", detail=task_id)
        if task_id in dependencies or len(dependencies) != len(set(dependencies)):
            raise StateHelperError(f"{label} contains self or duplicate dependency", detail=task_id)
        targets = task["mutation_targets"]
        seen_targets = set()
        for path in targets:
            validate_mutation_target_path(path, f"{label}.tasks mutation target")
            if path in seen_targets:
                raise StateHelperError(f"{label} contains duplicate mutation target", detail=task_id)
            seen_targets.add(path)
            owners_by_path.setdefault(path, []).append(task_id)
        if targets != sorted(targets):
            raise StateHelperError(f"{label}.tasks mutation_targets must be in canonical sorted order", detail=task_id)
        seen_task_handoffs = set()
        for handoff in task["ownership_handoffs"]:
            if not isinstance(handoff, dict) or set(handoff) != {"path", "from_task", "to_task"}:
                raise StateHelperError(f"{label} contains invalid ownership handoff", detail=task_id)
            path = handoff["path"]
            from_task = handoff["from_task"]
            to_task = handoff["to_task"]
            validate_mutation_target_path(path, f"{label}.tasks ownership handoff path")
            if (
                not isinstance(from_task, str) or TASK_ID_PATTERN.fullmatch(from_task) is None
                or not isinstance(to_task, str) or TASK_ID_PATTERN.fullmatch(to_task) is None
                or from_task not in task_ids or to_task not in task_ids
            ):
                raise StateHelperError(f"{label} contains unknown handoff owner", detail=task_id)
            edge = (path, from_task, to_task)
            if from_task == to_task or edge in seen_task_handoffs or to_task != task_id:
                raise StateHelperError(f"{label} contains invalid or duplicate ownership handoff", detail=task_id)
            seen_task_handoffs.add(edge)
            declared_handoffs.append(edge)
        canonical_task_handoffs = sorted(
            task["ownership_handoffs"],
            key=lambda item: (item["path"], item["from_task"], item["to_task"]),
        )
        if task["ownership_handoffs"] != canonical_task_handoffs:
            raise StateHelperError(
                f"{label}.tasks ownership_handoffs must be in canonical sorted order",
                detail=task_id,
            )

    visit_state = {}
    def visit(task_id):
        state = visit_state.get(task_id, 0)
        if state == 1:
            raise StateHelperError(f"{label} contains dependency cycle", detail=task_id)
        if state == 2:
            return
        visit_state[task_id] = 1
        for dependency in by_id[task_id]["depends_on"]:
            visit(dependency)
        visit_state[task_id] = 2
    for task_id in plan_order:
        visit(task_id)

    def transitively_depends_on(task_id, dependency_id):
        stack = list(by_id[task_id]["depends_on"])
        visited = set()
        while stack:
            current = stack.pop()
            if current == dependency_id:
                return True
            if current not in visited:
                visited.add(current)
                stack.extend(by_id[current]["depends_on"])
        return False

    rows_by_path = {}
    table_handoffs = []
    for row in ownership_table:
        if not isinstance(row, dict) or set(row) != {"path", "owners", "handoffs", "final_owner"}:
            raise StateHelperError(f"{label}.ownership_table entries must have canonical fields")
        path = row["path"]
        validate_mutation_target_path(path, f"{label}.ownership_table path")
        if path in rows_by_path:
            raise StateHelperError(f"{label}.ownership_table contains duplicate path", detail=path)
        owners = row["owners"]
        handoffs = row["handoffs"]
        if not isinstance(owners, list) or not owners:
            raise StateHelperError(f"{label}.ownership_table owners must be a non-empty array", detail=path)
        if any(
            not isinstance(owner, str) or TASK_ID_PATTERN.fullmatch(owner) is None or owner not in task_ids
            for owner in owners
        ):
            raise StateHelperError(f"{label} contains unknown owner", detail=path)
        if len(owners) != len(set(owners)):
            raise StateHelperError(f"{label} owners must be unique", detail=path)
        final_owner = row["final_owner"]
        if (
            not isinstance(final_owner, str) or TASK_ID_PATTERN.fullmatch(final_owner) is None
            or final_owner not in task_ids or final_owner != owners[-1]
        ):
            raise StateHelperError(f"{label} contains invalid final owner", detail=path)
        if not isinstance(handoffs, list):
            raise StateHelperError(f"{label}.ownership_table handoffs must be an array", detail=path)
        expected = [(path, left, right) for left, right in zip(owners, owners[1:])]
        actual = []
        for handoff in handoffs:
            if not isinstance(handoff, dict) or set(handoff) != {"path", "from_task", "to_task"}:
                raise StateHelperError(f"{label} contains invalid ownership table handoff", detail=path)
            handoff_path = handoff["path"]
            from_task = handoff["from_task"]
            to_task = handoff["to_task"]
            validate_mutation_target_path(handoff_path, f"{label}.ownership_table handoff path")
            if (
                not isinstance(from_task, str) or TASK_ID_PATTERN.fullmatch(from_task) is None
                or not isinstance(to_task, str) or TASK_ID_PATTERN.fullmatch(to_task) is None
                or from_task not in task_ids or to_task not in task_ids
            ):
                raise StateHelperError(f"{label} contains invalid ownership table handoff", detail=path)
            edge = (handoff_path, from_task, to_task)
            if edge[0] != path or edge[1] == edge[2]:
                raise StateHelperError(f"{label} contains invalid ownership table handoff", detail=path)
            actual.append(edge)
        if actual != expected or len(actual) != len(set(actual)):
            raise StateHelperError(f"{label} ownership handoffs must exactly connect adjacent owners", detail=path)
        for _, from_task, to_task in actual:
            if not transitively_depends_on(to_task, from_task):
                raise StateHelperError(f"{label} handoff target must depend on source", detail=f"{from_task}->{to_task}")
        rows_by_path[path] = row
        table_handoffs.extend(actual)

    if ownership_table != sorted(ownership_table, key=lambda row: row["path"]):
        raise StateHelperError(f"{label}.ownership_table must be in canonical path order")
    if set(rows_by_path) != set(owners_by_path):
        raise StateHelperError(f"{label} ownership rows must exactly match mutation targets")
    for path, owners in owners_by_path.items():
        if set(rows_by_path[path]["owners"]) != set(owners):
            raise StateHelperError(f"{label} ownership owners must exactly match mutation targets", detail=path)
    seen_declared_edges = set()
    for edge in declared_handoffs:
        if edge in seen_declared_edges:
            raise StateHelperError(f"{label} contains duplicate ownership handoff", detail=f"{edge[0]}:{edge[1]}->{edge[2]}")
        seen_declared_edges.add(edge)
    if set(table_handoffs) != seen_declared_edges:
        raise StateHelperError(f"{label} ownership rows and Task handoffs must exactly match")
    return by_id


def validate_current_snapshot_refs(task_id, field, refs):
    if not isinstance(refs, list):
        raise StateHelperError(
            f"state.tasks entries {field} must be an array when present",
            detail=task_id,
        )
    expected_fields = set(SNAPSHOT_REF_COMMON_FIELDS)
    dependency = field == "dependency_handoff_snapshot_refs"
    if dependency:
        expected_fields.add("incoming_edge")
    canonical_keys = []
    seen_paths = set()
    seen_edges = set()
    seen_evidence_paths = set()
    seen_record_hashes = set()
    for index, ref in enumerate(refs):
        detail = f"{task_id}:{field}[{index}]"
        if not isinstance(ref, dict) or set(ref) != expected_fields:
            raise StateHelperError(
                f"state.tasks entries {field} items must have exact canonical fields",
                detail=detail,
            )
        evidence_path = ref["evidence_path"]
        path = ref["path"]
        path_id = ref["path_id"]
        record_hash = ref["record_hash"]
        validate_safe_project_relative_path(evidence_path, f"state.tasks entries {field} evidence_path")
        validate_safe_project_relative_path(path, f"state.tasks entries {field} path")
        if not isinstance(path_id, str) or SNAPSHOT_PATH_ID_PATTERN.fullmatch(path_id) is None:
            raise StateHelperError(f"state.tasks entries {field} path_id must be 64 lowercase hex", detail=detail)
        expected_path_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
        if path_id != expected_path_id:
            raise StateHelperError(f"state.tasks entries {field} path_id must equal sha256(path UTF-8)", detail=detail)
        if not isinstance(record_hash, str) or SNAPSHOT_RECORD_HASH_PATTERN.fullmatch(record_hash) is None:
            raise StateHelperError(f"state.tasks entries {field} record_hash must be sha256 plus 64 lowercase hex", detail=detail)

        evidence = pathlib.PurePosixPath(evidence_path)
        expected_parent = pathlib.PurePosixPath("evidence", "tasks", task_id, "snapshots")
        if evidence.parent != expected_parent:
            raise StateHelperError(f"state.tasks entries {field} evidence_path must use the fixed Task snapshots directory", detail=detail)
        filename_match = SNAPSHOT_FILE_PATTERNS[field].fullmatch(evidence.name)
        if filename_match is None:
            raise StateHelperError(f"state.tasks entries {field} evidence_path filename must match snapshot kind", detail=detail)
        filename_identity = filename_match.groupdict()
        if filename_identity["task"] != task_id or filename_identity["path_id"] != path_id:
            raise StateHelperError(f"state.tasks entries {field} evidence_path identity must match ref", detail=detail)

        edge_key = None
        if dependency:
            edge = ref["incoming_edge"]
            if not isinstance(edge, dict) or set(edge) != {"path", "from", "to"}:
                raise StateHelperError(f"state.tasks entries {field} incoming_edge must be exact canonical object", detail=detail)
            edge_path = edge["path"]
            from_task = edge["from"]
            to_task = edge["to"]
            if (
                not isinstance(from_task, str) or TASK_ID_PATTERN.fullmatch(from_task) is None
                or not isinstance(to_task, str) or TASK_ID_PATTERN.fullmatch(to_task) is None
                or not isinstance(edge_path, str)
            ):
                raise StateHelperError(f"state.tasks entries {field} incoming_edge must contain canonical Task IDs and path", detail=detail)
            if edge_path != path or to_task != task_id or filename_identity["from_task"] != from_task:
                raise StateHelperError(f"state.tasks entries {field} incoming_edge identity must match path, Task, and filename", detail=detail)
            edge_key = (path, from_task, to_task)
            if edge_key in seen_edges:
                raise StateHelperError(f"state.tasks entries {field} contains duplicate incoming edge", detail=detail)
            seen_edges.add(edge_key)
            canonical_keys.append(edge_key)
        else:
            canonical_keys.append(path)

        if path in seen_paths:
            raise StateHelperError(f"state.tasks entries {field} contains duplicate path", detail=detail)
        if evidence_path in seen_evidence_paths:
            raise StateHelperError(f"state.tasks entries {field} contains duplicate evidence_path", detail=detail)
        if record_hash in seen_record_hashes:
            raise StateHelperError(f"state.tasks entries {field} contains ambiguous duplicate record_hash", detail=detail)
        seen_paths.add(path)
        seen_evidence_paths.add(evidence_path)
        seen_record_hashes.add(record_hash)
    if canonical_keys != sorted(canonical_keys):
        raise StateHelperError(f"state.tasks entries {field} must be in canonical order", detail=task_id)


def required_affected_tasks(old_contract, new_contract):
    old_by_id = validate_task_contract(old_contract, "state approved_task_contract")
    new_by_id = validate_task_contract(new_contract, "task-contract")
    old_ids = set(old_by_id)
    new_ids = set(new_by_id)
    if old_ids != new_ids:
        raise StateHelperError(
            "old/new Task ID sets must be exactly equal; close or start another change to restructure Tasks",
            detail={"added_task_ids": sorted(new_ids - old_ids), "deleted_task_ids": sorted(old_ids - new_ids)},
        )

    direct = set()
    for task_id in old_ids:
        old_task = old_by_id[task_id]
        new_task = new_by_id[task_id]
        if any(old_task[field] != new_task[field] for field in CONTRACT_CHANGE_FIELDS):
            direct.add(task_id)
        if old_task["depends_on"] != new_task["depends_on"]:
            direct.update(old_task["depends_on"])
            direct.update(new_task["depends_on"])
        for field in ("ownership_handoffs",):
            if old_task[field] != new_task[field]:
                for handoff in old_task[field] + new_task[field]:
                    direct.update((handoff["from_task"], handoff["to_task"]))

    old_rows = {row["path"]: row for row in old_contract["ownership_table"]}
    new_rows = {row["path"]: row for row in new_contract["ownership_table"]}
    for path in set(old_rows) | set(new_rows):
        old_row = old_rows.get(path)
        new_row = new_rows.get(path)
        if old_row != new_row:
            for row in (old_row, new_row):
                if row:
                    direct.update(row["owners"])
                    direct.add(row["final_owner"])

    reverse = {task_id: set() for task_id in old_ids}
    for contract_by_id in (old_by_id, new_by_id):
        for task_id, task in contract_by_id.items():
            for dependency in task["depends_on"]:
                reverse[dependency].add(task_id)
    affected = set(direct)
    stack = list(direct)
    while stack:
        for dependent in reverse[stack.pop()]:
            if dependent not in affected:
                affected.add(dependent)
                stack.append(dependent)
    return [task_id for task_id in new_contract["plan_order"] if task_id in affected]


def prepare_design_revision_contract(args, state, approved_control_plane):
    gates = state.get("gates")
    if not isinstance(gates, dict):
        raise StateHelperError("state.gates must be a JSON object")
    if gates.get("design") != "pending":
        raise StateHelperError("state.gates.design must be pending")
    if getattr(args, "unblock_tasks", None) is not None:
        raise StateHelperError("--unblock-tasks must not be combined with contract revision arguments")
    new_contract = load_json_object_text(args.task_contract, "task-contract")
    try:
        declared = json.loads(args.affected_tasks)
    except json.JSONDecodeError as exc:
        raise StateHelperError("invalid affected-tasks JSON", detail=str(exc)) from exc
    if not isinstance(declared, list):
        raise StateHelperError("affected-tasks must be a JSON array")
    if not all(isinstance(item, str) for item in declared):
        raise StateHelperError("affected-tasks must contain only string IDs")
    seen_declared = set()
    duplicate_declared_set = set()
    for item in declared:
        if item in seen_declared:
            duplicate_declared_set.add(item)
        else:
            seen_declared.add(item)
    duplicate_declared = sorted(duplicate_declared_set)
    if not isinstance(args.revision_reason, str) or not args.revision_reason.strip():
        raise StateHelperError("revision-reason must be a non-empty string")
    validate_implementation_parent(state)
    implementation = state.get("implementation")
    if not isinstance(implementation, dict) or "approved_task_contract" not in implementation:
        raise StateHelperError("state.implementation.approved_task_contract must be present")
    old_contract = implementation["approved_task_contract"]
    required = required_affected_tasks(old_contract, new_contract)
    old_contract_identity = canonical_json_identity(old_contract)
    new_contract_identity = canonical_json_identity(new_contract)
    if old_contract_identity == new_contract_identity:
        raise StateHelperError(
            "contract revision mode requires a changed canonical task contract identity; use legacy context-only --unblock-tasks",
            detail={"contract_identity": old_contract_identity},
        )
    task_ids = set(new_contract["plan_order"])
    unknown = set(declared) - task_ids
    missing = set(required) - set(declared)
    extra = set(declared) - set(required)
    if duplicate_declared or unknown or missing or extra:
        raise StateHelperError(
            "affected-tasks must exactly match deterministic required affected Tasks",
            detail={
                "missing_affected_tasks": [item for item in required if item in missing],
                "extra_affected_tasks": [item for item in new_contract["plan_order"] if item in extra] + sorted(unknown),
                "duplicate_affected_tasks": duplicate_declared,
            },
        )

    tasks = state.get("tasks")
    if not isinstance(tasks, dict):
        raise StateHelperError("state.tasks must be a JSON object")
    for task_id, task in tasks.items():
        status = validate_task_status(task_id, task)
        manual = validate_optional_record_id(task_id, task, "manual_repair_authorization")
        revision = validate_optional_record_id(task_id, task, "design_revision_authorization")
        validate_authorization_exclusivity(task_id, manual, revision)
        for field in CURRENT_SNAPSHOT_REF_FIELDS:
            if field in task:
                validate_current_snapshot_refs(task_id, field, task[field])
        if status == "blocked":
            validate_canonical_blocker(task_id, task)
    validate_current_task_pointer(state, tasks)
    if set(tasks) != task_ids:
        raise StateHelperError("state.tasks Task ID set must match approved task contract")
    in_progress_affected = [task_id for task_id in required if tasks[task_id]["status"] == "in_progress"]
    if in_progress_affected:
        raise StateHelperError(
            "affected Tasks must not be in_progress during design revision approval",
            detail=in_progress_affected,
        )
    completed = implementation.get("completed_tasks", [])
    if not isinstance(completed, list):
        raise StateHelperError("state.implementation.completed_tasks must be an array")
    seen_completed = set()
    for task_id in completed:
        if not isinstance(task_id, str):
            raise StateHelperError("state.implementation.completed_tasks must contain only string Task IDs")
        if TASK_ID_PATTERN.fullmatch(task_id) is None or task_id not in task_ids:
            raise StateHelperError("state.implementation.completed_tasks contains unknown Task ID", detail=task_id)
        if task_id in seen_completed:
            raise StateHelperError("state.implementation.completed_tasks contains duplicate Task ID", detail=task_id)
        seen_completed.add(task_id)
    revisions = implementation.get("design_revisions", [])
    if not isinstance(revisions, list):
        raise StateHelperError("state.implementation.design_revisions must be an array")
    return {
        "state": state,
        "approved_control_plane": approved_control_plane,
        "new_contract": new_contract,
        "old_contract": old_contract,
        "required": required,
        "declared": declared,
        "completed": completed,
        "revisions": revisions,
    }


def build_design_revision_update(args, prepared):
    state = prepared["state"]
    approved_control_plane = prepared["approved_control_plane"]
    new_contract = prepared["new_contract"]
    old_contract = prepared["old_contract"]
    required = prepared["required"]
    completed = prepared["completed"]

    updated = copy.deepcopy(state)
    updated_impl = updated["implementation"]
    updated_impl["approved_control_plane"] = copy.deepcopy(approved_control_plane)
    updated_impl["approved_task_contract"] = copy.deepcopy(new_contract)
    invalidated = {}
    affected_set = set(required)
    for task_id in required:
        task = updated["tasks"][task_id]
        evidence = {
            field: copy.deepcopy(task[field])
            for field in CURRENT_EVIDENCE_FIELDS | CURRENT_SNAPSHOT_REF_FIELDS
            if field in task
        }
        invalidated[task_id] = evidence
        for field in CURRENT_EVIDENCE_FIELDS:
            task.pop(field, None)
        for field in CURRENT_SNAPSHOT_REF_FIELDS:
            task[field] = []
        task["status"] = "pending"
        task["revalidation"] = "required"
        task["manual_repair_authorization"] = None
        task["design_revision_authorization"] = None
        if task.get("blocker") is not None:
            task["blocker"] = None
            task["reason"] = None
    updated_impl["completed_tasks"] = [task_id for task_id in completed if task_id not in affected_set]
    revisions = updated_impl.setdefault("design_revisions", [])
    revisions.append({
        "reason": args.revision_reason,
        "declared_affected_tasks": list(required),
        "required_affected_tasks": list(required),
        "old_contract_identity": canonical_json_identity(old_contract),
        "new_contract_identity": canonical_json_identity(new_contract),
        "invalidated_evidence": invalidated,
    })
    updated["gates"]["design"] = "approved"
    if isinstance(updated.get("current_task"), dict) and updated["current_task"].get("id") in affected_set:
        updated["current_task"] = None
    serialize_json_file_payload(updated)
    return updated


def approve_design_revision_contract(args, prepared):
    updated = build_design_revision_update(args, prepared)
    write_json_file(args.state, updated)
    print_json({
        "ok": True, "state_path": path_text(args.state),
        "approved_control_plane_replaced": True, "approved_task_contract_replaced": True,
        "required_affected_tasks": prepared["required"], "updated": True,
    })
    return 0


def validate_design_revision(args):
    state = load_json_object_file(args.state, "state")
    approved_control_plane = load_json_object_text(args.approved_control_plane, "approved-control-plane")
    prepared = prepare_design_revision_contract(args, state, approved_control_plane)
    build_design_revision_update(args, prepared)
    print_json({
        "ok": True,
        "state_path": path_text(args.state),
        "required_affected_tasks": prepared["required"],
        "declared_affected_tasks": prepared["declared"],
        "old_contract_identity": canonical_json_identity(prepared["old_contract"]),
        "new_contract_identity": canonical_json_identity(prepared["new_contract"]),
        "approved_control_plane_identity": canonical_json_identity(approved_control_plane),
        "updated": False,
    })
    return 0


def approve_design_revision(args):
    if not args.allow_approval:
        raise StateHelperError("design revision approval requires --allow-approval")

    state = load_json_object_file(args.state, "state")
    approved_control_plane = load_json_object_text(args.approved_control_plane, "approved-control-plane")

    gates = state.get("gates")
    if not isinstance(gates, dict):
        raise StateHelperError("state.gates must be a JSON object")
    if gates.get("design") != "pending":
        raise StateHelperError("state.gates.design must be pending")

    contract_args = (args.task_contract, args.affected_tasks, args.revision_reason)
    if any(value is not None for value in contract_args):
        if not all(value is not None for value in contract_args):
            raise StateHelperError("--task-contract, --affected-tasks, and --revision-reason are required together")
        prepared = prepare_design_revision_contract(args, state, approved_control_plane)
        return approve_design_revision_contract(args, prepared)
    if args.unblock_tasks is None:
        raise StateHelperError("either contract revision arguments or --unblock-tasks are required")
    unblock_tasks = load_json_string_array_text(args.unblock_tasks, "unblock-tasks")

    tasks = state.get("tasks")
    if not isinstance(tasks, dict):
        raise StateHelperError("state.tasks must be a JSON object")

    design_revision_blocked_task_ids = []
    design_revision_authorized_task_ids = []
    for task_id, task in tasks.items():
        status = validate_task_status(task_id, task)
        manual_repair_authorization = validate_optional_record_id(task_id, task, "manual_repair_authorization")
        design_revision_authorization = validate_optional_record_id(task_id, task, "design_revision_authorization")
        validate_authorization_exclusivity(task_id, manual_repair_authorization, design_revision_authorization)
        if status == "blocked":
            if validate_canonical_blocker(task_id, task) == "design_revision":
                design_revision_blocked_task_ids.append(task_id)
        elif status == "pending" and design_revision_authorization is not None:
            design_revision_authorized_task_ids.append(task_id)
    validate_current_task_pointer(state, tasks)

    design_eligible_task_ids = design_revision_blocked_task_ids + design_revision_authorized_task_ids
    requested = set(unblock_tasks)
    design_eligible_tasks = set(design_eligible_task_ids)
    if requested != design_eligible_tasks:
        missing = sorted(design_eligible_tasks - requested)
        extra = sorted(requested - design_eligible_tasks)
        detail = {"missing_design_eligible_tasks": missing, "non_design_eligible_tasks": extra}
        raise StateHelperError(
            "unblock-tasks must exactly match design_revision blocked Tasks and pending design_revision_authorization Tasks",
            detail=detail,
        )
    validate_implementation_parent(state)

    updated = copy.deepcopy(state)
    implementation = get_or_create_implementation(updated)
    updated_gates = updated["gates"]
    updated_tasks = updated["tasks"]

    implementation["approved_control_plane"] = copy.deepcopy(approved_control_plane)
    updated_gates["design"] = "approved"
    for task_id in unblock_tasks:
        task = updated_tasks[task_id]
        task["status"] = "pending"
        task["manual_repair_authorization"] = None
        task["design_revision_authorization"] = None
        if task_id in design_revision_blocked_task_ids:
            task["blocker"] = None
            task["reason"] = None
    current_task = updated.get("current_task")
    if isinstance(current_task, dict) and current_task.get("id") in design_eligible_tasks:
        updated["current_task"] = None

    write_json_file(args.state, updated)
    print_json(
        {
            "ok": True,
            "state_path": path_text(args.state),
            "approved_control_plane_replaced": True,
            "unblocked_tasks": unblock_tasks,
            "updated": True,
        }
    )
    return 0


def build_parser():
    parser = JsonArgumentParser(description="Deterministic Nuclio state helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect-state")
    inspect_parser.add_argument("--change", type=pathlib.Path)
    inspect_parser.add_argument("--state", type=pathlib.Path)
    inspect_parser.set_defaults(func=inspect_state)

    check_parser = subparsers.add_parser("check-gate")
    check_parser.add_argument("--state", type=pathlib.Path, required=True)
    check_parser.add_argument("--gate", required=True)
    check_parser.add_argument("--authorized", action="store_true")
    check_parser.set_defaults(func=check_gate)

    merge_parser = subparsers.add_parser("merge-state")
    merge_parser.add_argument("--state", type=pathlib.Path, required=True)
    merge_parser.add_argument("--patch", required=True)
    merge_parser.add_argument("--allow-approval", action="store_true")
    merge_parser.set_defaults(func=merge_state)

    replace_parser = subparsers.add_parser("replace-object")
    replace_parser.add_argument("--state", type=pathlib.Path, required=True)
    replace_parser.add_argument("--object-path", required=True)
    replace_parser.add_argument("--value", required=True)
    replace_parser.add_argument("--allow-approval", action="store_true")
    replace_parser.set_defaults(func=replace_object)

    validate_revision_parser = subparsers.add_parser("validate-design-revision")
    validate_revision_parser.add_argument("--state", type=pathlib.Path, required=True)
    validate_revision_parser.add_argument("--approved-control-plane", required=True)
    validate_revision_parser.add_argument("--task-contract", required=True)
    validate_revision_parser.add_argument("--affected-tasks", required=True)
    validate_revision_parser.add_argument("--revision-reason", required=True)
    validate_revision_parser.set_defaults(func=validate_design_revision)

    approve_parser = subparsers.add_parser("approve-design-revision")
    approve_parser.add_argument("--state", type=pathlib.Path, required=True)
    approve_parser.add_argument("--approved-control-plane", required=True)
    approve_parser.add_argument("--unblock-tasks")
    approve_parser.add_argument("--task-contract")
    approve_parser.add_argument("--affected-tasks")
    approve_parser.add_argument("--revision-reason")
    approve_parser.add_argument("--allow-approval", action="store_true")
    approve_parser.set_defaults(func=approve_design_revision)

    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.func(args)
    except StateHelperError as exc:
        payload = {"ok": False, "error": exc.message}
        if exc.detail is not None:
            payload["detail"] = exc.detail
        print_json(payload)
        return 1


if __name__ == "__main__":
    sys.exit(main())
