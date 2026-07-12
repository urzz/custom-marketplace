#!/usr/bin/env python3
"""Deterministic Nuclio state helper.

This helper only inspects gate readiness and performs explicit preserve/merge
state updates. It is not a Nuclio runtime, daemon, hook, MCP server, background
automation, or gate approval system.
"""

import argparse
import copy
import json
import pathlib
import re
import sys


MISSING_FILES_FOR_CHANGE = ("state.json", "plan.yaml", "context/implement.jsonl")
ALLOWED_REPLACE_OBJECT_PATHS = {"implementation.approved_control_plane"}
TASK_STATUS_ALLOWLIST = {"pending", "in_progress", "completed", "blocked"}
BLOCKER_KIND_ALLOWLIST = {"design_revision", "resolved_evidence"}
RECORD_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")



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


def write_json_file(path, data):
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
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
    if not isinstance(value, str) or value == "":
        raise StateHelperError(f"{label} must be a non-empty project-relative path")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise StateHelperError(f"{label} must not contain ASCII control characters")
    if "\\" in value:
        raise StateHelperError(f"{label} must use forward-slash project-relative path")
    if value.startswith("/") or value.startswith("//"):
        raise StateHelperError(f"{label} must be project-relative")
    if value.startswith("~"):
        raise StateHelperError(f"{label} must not use home-relative path")
    if "://" in value:
        raise StateHelperError(f"{label} must not be a URI")
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        raise StateHelperError(f"{label} must not be a Windows absolute path")
    parts = value.split("/")
    if any(part == "" for part in parts):
        raise StateHelperError(f"{label} must not contain empty path segments")
    if any(part in {".", ".."} for part in parts):
        raise StateHelperError(f"{label} must not contain dot or dot-dot segments")


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
    validate_safe_project_relative_path(blocker.get("evidence"), "blocked Task blocker.evidence")
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


def approve_design_revision(args):
    if not args.allow_approval:
        raise StateHelperError("design revision approval requires --allow-approval")

    state = load_json_object_file(args.state, "state")
    approved_control_plane = load_json_object_text(args.approved_control_plane, "approved-control-plane")
    unblock_tasks = load_json_string_array_text(args.unblock_tasks, "unblock-tasks")

    gates = state.get("gates")
    if not isinstance(gates, dict):
        raise StateHelperError("state.gates must be a JSON object")
    if gates.get("design") != "pending":
        raise StateHelperError("state.gates.design must be pending")

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

    approve_parser = subparsers.add_parser("approve-design-revision")
    approve_parser.add_argument("--state", type=pathlib.Path, required=True)
    approve_parser.add_argument("--approved-control-plane", required=True)
    approve_parser.add_argument("--unblock-tasks", required=True)
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
