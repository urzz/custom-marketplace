#!/usr/bin/env python3
"""Validate the compact Skill Forge Plan contract."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by environments without PyYAML.
    yaml = None


SCHEMA_VERSION = 1
MAX_PLAN_BYTES = 1_000_000
MAX_SPEC_BYTES = 256_000
MAX_TASKS = 200
ROOT_KEYS = {"schema_version", "spec", "spec_sha256", "impacts", "tasks"}
IMPACT_KEYS = {
    "trigger_or_behavior_changed",
    "script_changed",
    "agent_permissions_changed",
    "external_side_effects_changed",
}
TASK_KEYS = {"id", "name", "files", "steps", "acceptance", "checks"}
FILE_OPERATIONS = ("create", "modify", "delete")
INVALID_PATH_MARKERS = set("*?[]{}")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
INLINE_PATH_NOTE_RE = re.compile(
    r"\s+\((?:new|existing|create|modify|delete|新增|现有|创建|修改|删除)(?:[^)]*)\)$",
    re.IGNORECASE,
)
PLACEHOLDER_RE = re.compile(
    r"(?i)(?:\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b|待补充|待定|\[(?:TODO|TBD|FIXME|PLACEHOLDER)[^]]*\])"
)


class PlanContractError(Exception):
    """Expected validation failure with a stable code."""

    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _require(condition, code, detail=None):
    if not condition:
        raise PlanContractError(code, detail)


def _exact_keys(value, expected, code):
    _require(isinstance(value, dict), code)
    actual = set(value)
    _require(actual == expected, code, {"expected": sorted(expected), "actual": sorted(map(str, actual))})


def _non_empty_string(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _contains_placeholder(value, embedded=True):
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if stripped.upper() in {"TODO", "TBD", "FIXME", "PLACEHOLDER"} or stripped in {"待补充", "待定"}:
        return True
    if stripped.startswith("[") and stripped.endswith("]") and not stripped.startswith("[ "):
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    return embedded and PLACEHOLDER_RE.search(stripped) is not None


def _validate_string_list(value, code, detail, embedded_placeholders=True):
    _require(isinstance(value, list) and value, code, detail)
    for item in value:
        _require(_non_empty_string(item), code, detail)
        _require(not _contains_placeholder(item, embedded=embedded_placeholders), "PLACEHOLDER_FOUND", item)


def valid_repo_path(value):
    if not _non_empty_string(value):
        return False
    if "\\" in value or "\x00" in value or any(marker in value for marker in INVALID_PATH_MARKERS):
        return False
    if INLINE_PATH_NOTE_RE.search(value):
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        return False
    return path.as_posix() == value


def _read_limited(path, limit, code):
    try:
        size = path.stat().st_size
        _require(size <= limit, "INPUT_TOO_LARGE", f"{path}: {size} bytes")
        return path.read_bytes()
    except PlanContractError:
        raise
    except OSError as exc:
        raise PlanContractError(code, str(exc)) from exc


def hash_spec(path):
    spec_path = Path(path).expanduser().resolve()
    return hashlib.sha256(_read_limited(spec_path, MAX_SPEC_BYTES, "INVALID_SPEC")).hexdigest()


if yaml is not None:
    class UniqueKeyLoader(yaml.SafeLoader):
        """SafeLoader variant that rejects aliases and duplicate mapping keys."""

        def compose_node(self, parent, index):
            if self.check_event(yaml.AliasEvent):
                raise PlanContractError("YAML_ALIAS_NOT_ALLOWED")
            return super().compose_node(parent, index)


    def _construct_unique_mapping(loader, node, deep=False):
        loader.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as exc:
                raise PlanContractError("INVALID_YAML_KEY", str(key)) from exc
            if duplicate:
                raise PlanContractError("DUPLICATE_YAML_KEY", str(key))
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping


    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        _construct_unique_mapping,
    )


def _load_yaml(path):
    if yaml is None:
        raise PlanContractError("MISSING_DEPENDENCY", "install PyYAML")
    raw = _read_limited(path, MAX_PLAN_BYTES, "INVALID_PLAN")
    try:
        return yaml.load(raw.decode("utf-8"), Loader=UniqueKeyLoader)
    except PlanContractError:
        raise
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise PlanContractError("INVALID_YAML", str(exc)) from exc


def _resolve_within_repo(repo_root, relative_path):
    target = (repo_root / relative_path).resolve()
    try:
        target.relative_to(repo_root)
    except ValueError as exc:
        raise PlanContractError("PATH_OUTSIDE_REPO", relative_path) from exc
    return target


def _validate_files(files, repo_root, owned_paths):
    _exact_keys(files, set(FILE_OPERATIONS), "INVALID_FILES")
    normalized = {}
    for operation in FILE_OPERATIONS:
        paths = files[operation]
        _require(isinstance(paths, list), "INVALID_FILES", operation)
        normalized[operation] = []
        for path in paths:
            _require(valid_repo_path(path), "INVALID_REPO_PATH", path)
            _require(not _contains_placeholder(path), "PLACEHOLDER_FOUND", path)
            _require(path not in owned_paths, "OWNERSHIP_OVERLAP", path)
            owned_paths.add(path)
            target = _resolve_within_repo(repo_root, path)
            if operation == "create":
                _require(not target.exists(), "CREATE_PATH_EXISTS", path)
            else:
                _require(target.exists(), f"{operation.upper()}_PATH_MISSING", path)
            normalized[operation].append(path)
    return normalized


def validate_plan(plan_path, repo_root):
    repo = Path(repo_root).expanduser().resolve()
    _require(repo.is_dir(), "INVALID_REPO_ROOT", str(repo))

    path = Path(plan_path).expanduser().resolve()
    try:
        relative_plan = path.relative_to(repo)
    except ValueError as exc:
        raise PlanContractError("PLAN_OUTSIDE_REPO", str(path)) from exc
    _require(
        len(relative_plan.parts) == 3
        and relative_plan.parts[0] == ".skill-forge"
        and relative_plan.name == "plan.yaml",
        "INVALID_PLAN_PATH",
        str(path),
    )

    plan = _load_yaml(path)
    _exact_keys(plan, ROOT_KEYS, "INVALID_PLAN_SCHEMA")
    _require(plan["schema_version"] == SCHEMA_VERSION, "INVALID_SCHEMA_VERSION", plan["schema_version"])
    _require(plan["spec"] == "spec.md", "INVALID_SPEC_REFERENCE", plan["spec"])
    _require(isinstance(plan["spec_sha256"], str) and SHA256_RE.fullmatch(plan["spec_sha256"]),
             "INVALID_SPEC_SHA256", plan["spec_sha256"])

    spec_path = (path.parent / plan["spec"]).resolve()
    try:
        spec_path.relative_to(repo)
    except ValueError as exc:
        raise PlanContractError("SPEC_OUTSIDE_REPO", str(spec_path)) from exc
    _require(spec_path.parent == path.parent, "INVALID_SPEC_REFERENCE", plan["spec"])
    actual_hash = hash_spec(spec_path)
    _require(plan["spec_sha256"] == actual_hash, "SPEC_HASH_MISMATCH",
             {"expected": plan["spec_sha256"], "actual": actual_hash})

    _exact_keys(plan["impacts"], IMPACT_KEYS, "INVALID_IMPACTS")
    for key, value in plan["impacts"].items():
        _require(type(value) is bool, "INVALID_IMPACT_VALUE", key)

    tasks = plan["tasks"]
    _require(isinstance(tasks, list) and tasks, "INVALID_TASKS")
    _require(len(tasks) <= MAX_TASKS, "TOO_MANY_TASKS", len(tasks))
    task_ids = set()
    owned_paths = set()
    counts = {operation: 0 for operation in FILE_OPERATIONS}
    for task in tasks:
        _exact_keys(task, TASK_KEYS, "INVALID_TASK_SCHEMA")
        task_id = task["id"]
        _require(type(task_id) is int and task_id > 0, "INVALID_TASK_ID", task_id)
        _require(task_id not in task_ids, "DUPLICATE_TASK_ID", task_id)
        task_ids.add(task_id)
        _require(_non_empty_string(task["name"]), "INVALID_TASK_NAME", task_id)
        _require(not _contains_placeholder(task["name"]), "PLACEHOLDER_FOUND", task["name"])
        files = _validate_files(task["files"], repo, owned_paths)
        for operation in FILE_OPERATIONS:
            counts[operation] += len(files[operation])
        _validate_string_list(task["steps"], "INVALID_STEPS", task_id)
        _validate_string_list(task["acceptance"], "INVALID_ACCEPTANCE", task_id)
        _validate_string_list(task["checks"], "INVALID_CHECKS", task_id, embedded_placeholders=False)

    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "spec_sha256": actual_hash,
        "task_count": len(tasks),
        "file_counts": counts,
        "impacts": plan["impacts"],
    }


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="校验精简 Skill Forge Plan 合同。")
    subparsers = parser.add_subparsers(dest="command", required=True)
    hash_parser = subparsers.add_parser("hash-spec", help="计算 Spec 的 SHA-256。")
    hash_parser.add_argument("spec_path")
    validate_parser = subparsers.add_parser("validate", help="校验 plan.yaml 及其 Spec 引用。")
    validate_parser.add_argument("plan_path")
    validate_parser.add_argument("--repo-root", required=True)
    return parser.parse_args(argv)


def _format_detail(detail):
    if detail is None:
        return ""
    if isinstance(detail, (dict, list)):
        return json.dumps(detail, ensure_ascii=False, sort_keys=True)
    return str(detail)


def main(argv=None):
    args = _parse_args(argv)
    try:
        if args.command == "hash-spec":
            print(hash_spec(args.spec_path))
        else:
            print(json.dumps(validate_plan(args.plan_path, args.repo_root), ensure_ascii=False, sort_keys=True))
        return 0
    except PlanContractError as exc:
        detail = _format_detail(exc.detail)
        suffix = f": {detail}" if detail else ""
        print(f"ERROR[{exc.code}]{suffix}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
