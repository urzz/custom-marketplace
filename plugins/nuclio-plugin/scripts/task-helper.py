#!/usr/bin/env python3
"""Strict deterministic Nuclio task helper.

This helper validates a narrow plan/context manifest subset and extracts one task
brief. It does not execute tasks, read manifest target content, mutate state, or
approve gates.
"""

import argparse
import json
import pathlib
import re
import sys


TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
CONTEXT_REF_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
TASK_HEADER_RE = re.compile(r"^  - id: ([A-Za-z0-9][A-Za-z0-9_-]*)$")
REQUIRED_TASK_FIELDS = ("title", "depends_on", "acceptance", "verification", "rollback")
CANONICAL_TASK_FIELDS = ("status", "files_hint", "context_refs")
ALLOWED_TASK_FIELDS = set(REQUIRED_TASK_FIELDS) | set(CANONICAL_TASK_FIELDS)
ALLOWED_TASK_STATUSES = {"pending", "in_progress", "blocked", "completed"}
GLOB_CHARS = set("*?[")
URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
BROAD_PATHS = {".", "./", ".dev-docs", ".dev-docs/", ".dev-docs\\"}
ALLOWED_MODES = {"required", "jit"}
REQUIRED_MANIFEST_KEYS = {"path", "kind", "mode", "reason"}


class TaskHelperError(Exception):
    def __init__(self, message, *, detail=None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise TaskHelperError("parse error", detail=message)


def print_json(payload):
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def path_text(path):
    return str(path)


def read_text(path, label):
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TaskHelperError(f"missing {label}", detail=path_text(path)) from exc
    except UnicodeDecodeError as exc:
        raise TaskHelperError(f"failed to read {label}", detail=str(exc)) from exc
    except OSError as exc:
        raise TaskHelperError(f"failed to read {label}", detail=str(exc)) from exc


def load_json_object(path, label):
    raw = read_text(path, label)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TaskHelperError(f"invalid {label} JSON", detail=str(exc)) from exc
    if not isinstance(data, dict):
        raise TaskHelperError(f"{label} must be object", detail=path_text(path))
    return data


def split_inline_list(raw):
    value = raw.strip()
    if not (value.startswith("[") and value.endswith("]")):
        raise TaskHelperError("depends_on must be an inline list or nested scalar list")
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [part.strip() for part in inner.split(",")]


def parse_canonical_list(raw, nested_items):
    if raw == "[]":
        if nested_items:
            raise TaskHelperError("invalid task block line", detail="mixed canonical list forms")
        return []
    if raw:
        raise TaskHelperError("invalid task block line", detail="canonical lists only allow inline [] or nested items")
    if not nested_items:
        raise TaskHelperError("missing canonical list")
    return nested_items


def non_empty_text_scalar(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return bool(value[1:-1].strip())
    return bool(value.strip())


def parse_task_block(block_lines):
    header_match = TASK_HEADER_RE.fullmatch(block_lines[0])
    if header_match is None:
        raise TaskHelperError("invalid tasks block")
    task_id = header_match.group(1)

    fields = {}
    current_field = None
    verification_commands = False
    verification_commands_seen = False
    verification_inline_commands = False
    acceptance_items = []
    depends_on_nested = []
    files_hint_items = []
    context_ref_items = []
    verification_command_items = []
    verification_notes = None
    rollback_strategy = None

    for line in block_lines[1:]:
        if not line:
            continue
        if "\t" in line:
            raise TaskHelperError("invalid task block line", detail=repr(line))

        field_match = re.fullmatch(r"    ([A-Za-z_][A-Za-z0-9_]*):(.*)", line)
        if field_match is not None:
            field, raw = field_match.groups()
            if field not in ALLOWED_TASK_FIELDS:
                raise TaskHelperError("invalid task block line", detail=line)
            if field in fields:
                raise TaskHelperError("duplicate task field", detail=f"{task_id}.{field}")
            fields[field] = raw.strip()
            current_field = field
            verification_commands = False
            verification_commands_seen = False
            verification_inline_commands = False
            continue

        scalar_item = re.fullmatch(r"      - (.+)", line)
        if scalar_item is not None and current_field in {"depends_on", "acceptance", "files_hint", "context_refs"}:
            value = scalar_item.group(1).strip()
            if not value:
                raise TaskHelperError("invalid task block line", detail=line)
            if current_field == "depends_on":
                depends_on_nested.append(value)
            elif current_field == "acceptance":
                acceptance_items.append(value)
            elif current_field == "files_hint":
                if '"' in value or "'" in value:
                    raise TaskHelperError("invalid task path", detail=value)
                files_hint_items.append(value)
            else:
                if '"' in value or "'" in value:
                    raise TaskHelperError("invalid task path", detail=value)
                context_ref_items.append(value)
            continue

        if current_field == "verification":
            if line in {"      commands:", "      commands: []"}:
                if verification_commands_seen:
                    raise TaskHelperError("invalid task block line", detail="duplicate verification commands")
                verification_commands_seen = True
                verification_commands = True
                verification_inline_commands = line.endswith("[]")
                continue
            if line.startswith("      commands:"):
                raise TaskHelperError("invalid task block line", detail=line)
            notes_match = re.fullmatch(r"      notes: (.+)", line)
            if notes_match is not None:
                notes = notes_match.group(1).strip()
                if not non_empty_text_scalar(notes):
                    raise TaskHelperError("missing verification", detail=task_id)
                verification_notes = notes
                verification_commands = False
                continue
            command_match = re.fullmatch(r"        - (.+)", line)
            if verification_commands and command_match is not None:
                if verification_inline_commands:
                    raise TaskHelperError("invalid task block line", detail="mixed verification command forms")
                command = command_match.group(1).strip()
                if not command:
                    raise TaskHelperError("missing verification", detail=task_id)
                verification_command_items.append(command)
                continue

        if current_field == "rollback":
            strategy_match = re.fullmatch(r"      strategy: (.+)", line)
            if strategy_match is not None:
                rollback_strategy = strategy_match.group(1).strip()
                continue

        raise TaskHelperError("invalid task block line", detail=repr(line))

    for field in REQUIRED_TASK_FIELDS:
        if field not in fields:
            raise TaskHelperError(f"missing {field}", detail=task_id)

    present_canonical_fields = set(fields) & set(CANONICAL_TASK_FIELDS)
    if present_canonical_fields:
        for field in CANONICAL_TASK_FIELDS:
            if field not in fields:
                raise TaskHelperError(f"missing {field}", detail=task_id)

    if "status" in fields and fields["status"] not in ALLOWED_TASK_STATUSES:
        raise TaskHelperError("invalid task status", detail=f"{task_id}.status")

    if "files_hint" in fields:
        files_hint = parse_canonical_list(fields["files_hint"], files_hint_items)
        for item in files_hint:
            validate_project_path(item, "invalid task path")

    if "context_refs" in fields:
        context_refs = parse_canonical_list(fields["context_refs"], context_ref_items)
        for item in context_refs:
            validate_context_ref(item)

    dep_raw = fields["depends_on"]
    if dep_raw:
        depends_on = split_inline_list(dep_raw)
        if depends_on_nested:
            raise TaskHelperError("invalid task block line", detail="mixed depends_on forms")
    else:
        depends_on = depends_on_nested
    for dep in depends_on:
        if TASK_ID_RE.fullmatch(dep) is None:
            raise TaskHelperError("invalid dependency id", detail=dep)

    if fields["acceptance"] or not acceptance_items:
        raise TaskHelperError("missing acceptance", detail=task_id)
    if fields["verification"] or not (verification_command_items or verification_notes):
        raise TaskHelperError("missing verification", detail=task_id)
    if fields["rollback"] or not rollback_strategy:
        raise TaskHelperError("missing rollback", detail=task_id)

    return {"id": task_id, "depends_on": depends_on, "block": "\n".join(block_lines)}


def parse_plan(plan_path):
    raw = read_text(plan_path, "plan.yaml")
    lines = raw.splitlines()
    tasks_index = None
    for index, line in enumerate(lines):
        if line == "tasks:":
            tasks_index = index
            break
    if tasks_index is None:
        raise TaskHelperError("plan.yaml missing top-level tasks")

    blocks = []
    current = None
    in_tasks = True
    for line in lines[tasks_index + 1:]:
        if not in_tasks:
            break
        if line.startswith("  - id:"):
            if current is not None:
                blocks.append(current)
            current = [line]
            continue
        if line and not line.startswith(" "):
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*:.*", line):
                if current is not None:
                    blocks.append(current)
                    current = None
                in_tasks = False
                break
            raise TaskHelperError("invalid task block line", detail=repr(line))
        if current is None:
            if line.strip():
                raise TaskHelperError("invalid tasks block")
            continue
        if line.strip().startswith("- id:"):
            raise TaskHelperError("invalid tasks block")
        current.append(line)
    if current is not None:
        blocks.append(current)
    if not blocks:
        raise TaskHelperError("invalid tasks block")

    tasks = []
    seen = set()
    for block in blocks:
        task = parse_task_block(block)
        if task["id"] in seen:
            raise TaskHelperError("duplicate task id", detail=task["id"])
        seen.add(task["id"])
        tasks.append(task)

    task_ids = {task["id"] for task in tasks}
    for task in tasks:
        for dep in task["depends_on"]:
            if dep not in task_ids:
                raise TaskHelperError("unknown dependency", detail=f"{task['id']} depends on {dep}")
    detect_cycle(tasks)
    return tasks


def detect_cycle(tasks):
    deps = {task["id"]: list(task["depends_on"]) for task in tasks}
    visiting = set()
    visited = set()

    def visit(task_id):
        if task_id in visiting:
            raise TaskHelperError("dependency cycle", detail=task_id)
        if task_id in visited:
            return
        visiting.add(task_id)
        for dep in deps[task_id]:
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)

    for task in tasks:
        visit(task["id"])


def validate_project_path(value, error="invalid manifest path"):
    if not isinstance(value, str) or not value:
        raise TaskHelperError(error, detail=repr(value))
    if value in BROAD_PATHS or value == "~" or value.startswith(("~/", "~\\")):
        raise TaskHelperError(error, detail=value)
    if URI_SCHEME_RE.match(value):
        raise TaskHelperError(error, detail=value)
    path = pathlib.PurePosixPath(value)
    windows_path = pathlib.PureWindowsPath(value)
    if path.is_absolute() or windows_path.is_absolute() or windows_path.drive or value.startswith("\\"):
        raise TaskHelperError(error, detail=value)
    if value.endswith(("/", "\\")):
        raise TaskHelperError(error, detail=value)
    if any(char in value for char in GLOB_CHARS):
        raise TaskHelperError(error, detail=value)
    if ".." in path.parts or ".." in windows_path.parts:
        raise TaskHelperError(error, detail=value)


def validate_manifest_path(value):
    validate_project_path(value, "invalid manifest path")


def context_ref_looks_like_path(value):
    return (
        value.startswith((".", "/", "\\", "~"))
        or "/" in value
        or "\\" in value
        or pathlib.PureWindowsPath(value).drive
        or URI_SCHEME_RE.match(value) is not None
    )


def validate_context_ref(value):
    if not isinstance(value, str) or not value.strip():
        raise TaskHelperError("invalid task path", detail=repr(value))
    if context_ref_looks_like_path(value):
        validate_project_path(value, "invalid task path")
    elif CONTEXT_REF_ID_RE.fullmatch(value) is None:
        raise TaskHelperError("invalid task path", detail=value)


def normalize_manifest_entry(entry, plan_task_ids):
    if not isinstance(entry, dict):
        raise TaskHelperError("manifest entry must be object")
    missing = sorted(REQUIRED_MANIFEST_KEYS - set(entry))
    if missing:
        raise TaskHelperError("manifest entry missing required keys", detail=", ".join(missing))
    validate_manifest_path(entry["path"])
    for field in ("kind", "reason"):
        if not isinstance(entry[field], str) or not entry[field].strip():
            raise TaskHelperError(f"invalid {field}", detail=repr(entry[field]))
    if not isinstance(entry["mode"], str) or entry["mode"] not in ALLOWED_MODES:
        raise TaskHelperError("invalid mode", detail=repr(entry["mode"]))

    tasks = entry.get("tasks", ["*"])
    if not isinstance(tasks, list) or not all(isinstance(task, str) for task in tasks):
        raise TaskHelperError("tasks must be a string array")
    if not tasks:
        raise TaskHelperError("tasks must be a string array")
    for task in tasks:
        if task != "*" and task not in plan_task_ids:
            raise TaskHelperError("unknown task", detail=task)

    normalized = dict(entry)
    normalized["tasks"] = tasks
    return normalized


def load_manifest(path, plan_task_ids):
    raw = read_text(path, path.name)
    entries = []
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TaskHelperError("invalid JSONL", detail=f"{path_text(path)}:{line_number}: {exc}") from exc
        entries.append(normalize_manifest_entry(entry, plan_task_ids))
    return entries


def load_change(change_path):
    state = load_json_object(change_path / "state.json", "state")
    tasks = parse_plan(change_path / "plan.yaml")
    task_ids = {task["id"] for task in tasks}
    implement_entries = load_manifest(change_path / "context" / "implement.jsonl", task_ids)
    verify_entries = load_manifest(change_path / "context" / "verify.jsonl", task_ids)
    return state, tasks, implement_entries, verify_entries


def validate_change(args):
    state, tasks, implement_entries, verify_entries = load_change(args.change)
    del state
    print_json(
        {
            "ok": True,
            "change_path": path_text(args.change),
            "task_order": [task["id"] for task in tasks],
            "task_count": len(tasks),
            "implement_manifest_entries": len(implement_entries),
            "verify_manifest_entries": len(verify_entries),
        }
    )
    return 0


def matching_entries(entries, task_id):
    return [entry for entry in entries if "*" in entry["tasks"] or task_id in entry["tasks"]]


def render_task_brief(change_path, state, task, manifest_entries):
    manifest_jsonl = "\n".join(
        json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in manifest_entries
    )
    if manifest_jsonl:
        manifest_jsonl += "\n"
    design_gate = None
    gates = state.get("gates")
    if isinstance(gates, dict):
        design_gate = gates.get("design")
    task_id = task["id"]
    return (
        f"# Nucl.io Task Brief: {task_id}\n\n"
        "## Gate and State Summary\n\n"
        f"- Change: `{path_text(change_path)}`\n"
        f"- Phase: `{state.get('phase')}`\n"
        f"- Status: `{state.get('status')}`\n"
        f"- Design Gate: `{design_gate}`\n\n"
        "## Original Task Definition\n\n"
        "```yaml\n"
        f"{task['block']}\n"
        "```\n\n"
        "## Matching Context Manifest Entries\n\n"
        "```jsonl\n"
        f"{manifest_jsonl}"
        "```\n\n"
        "## Evidence Output Contract\n\n"
        f"- Brief: `evidence/tasks/{task_id}/task-brief.md`\n"
        f"- Implementer report: `evidence/tasks/{task_id}/implementer.md`\n"
        f"- Validation: `evidence/tasks/{task_id}/validation.md`\n"
        f"- Review: `evidence/tasks/{task_id}/review.md`\n"
        "- Loaded context must be reported as project-relative paths.\n"
    )


def extract_task(args):
    state, tasks, implement_entries, verify_entries = load_change(args.change)
    del verify_entries
    task_by_id = {task["id"]: task for task in tasks}
    task = task_by_id.get(args.task)
    if task is None:
        raise TaskHelperError("unknown task extraction", detail=args.task)
    brief = render_task_brief(args.change, state, task, matching_entries(implement_entries, args.task))
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(brief, encoding="utf-8")
    except OSError as exc:
        raise TaskHelperError("failed to write output", detail=str(exc)) from exc
    print_json({"ok": True, "change_path": path_text(args.change), "task": args.task, "output": path_text(args.output)})
    return 0


def build_parser():
    parser = JsonArgumentParser(description="Deterministic Nuclio task helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-change")
    validate_parser.add_argument("--change", type=pathlib.Path, required=True)
    validate_parser.set_defaults(func=validate_change)

    extract_parser = subparsers.add_parser("extract-task")
    extract_parser.add_argument("--change", type=pathlib.Path, required=True)
    extract_parser.add_argument("--task", required=True)
    extract_parser.add_argument("--output", type=pathlib.Path, required=True)
    extract_parser.set_defaults(func=extract_task)

    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.func(args)
    except TaskHelperError as exc:
        payload = {"ok": False, "error": exc.message}
        if exc.detail is not None:
            payload["detail"] = exc.detail
        print_json(payload)
        return 1


if __name__ == "__main__":
    sys.exit(main())
