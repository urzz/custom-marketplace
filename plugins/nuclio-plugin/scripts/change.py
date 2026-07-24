#!/usr/bin/env python3
"""
Nuclio v2 change, Plan, and State helper.

## Contents
- [CLI](#cli)
- [JSON command contract](#json-command-contract)
- [Path safety](#path-safety)
- [YAML safety](#yaml-safety)
- [Plan validation](#plan-validation)
- [State and Git helpers](#state-and-git-helpers)
- [Commands](#commands)
- [Legacy move](#legacy-move)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by dependency-specific tests via monkeypatching.
    yaml = None  # type: ignore[assignment]

COMMANDS = (
    "create",
    "list",
    "show",
    "validate-plan",
    "init-state",
    "status",
    "next-action",
    "start-task",
    "record-task",
    "record-review",
    "start-repair",
    "record-repair",
    "record-validation",
    "complete",
    "archive",
    "legacy-move",
)
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GLOB_CHARS = set("*?[]{}")
MAX_YAML_BYTES = 1024 * 1024
PLAN_TOP_KEYS = {
    "schema_version",
    "change_id",
    "revision",
    "risk_level",
    "review_policy",
    "repair_policy",
    "summary",
    "allowed_paths",
    "tasks",
}
TASK_KEYS = {"id", "name", "steps", "acceptance", "validation", "delegate", "review", "checkpoint_subject"}
ARCHIVE_ACTIVE_ARTIFACTS = ("change.md", "plan.yaml", "state.yaml")
ARCHIVE_REQUIRED_HEADINGS = ("Goal", "Outcome", "Validation", "Knowledge Updates")
RISK_LEVELS = {"low", "medium", "high"}
REVIEW_POLICIES = {"self", "final", "task-and-final"}
DELEGATES = {"main", "subagent", "auto"}
NEXT_DISPATCH_TASK = "DISPATCH_TASK"
NEXT_RUN_TASK_REVIEW = "RUN_TASK_REVIEW"
NEXT_RUN_FINAL_REVIEW = "RUN_FINAL_REVIEW"
NEXT_RUN_VALIDATION = "RUN_VALIDATION"
NEXT_REQUEST_REPAIR_DECISION = "REQUEST_REPAIR_DECISION"
NEXT_COMPLETE = "COMPLETE"
NEXT_HALT = "HALT"
V1_MARKER_FILES = {"contract.yaml", "context.jsonl", "state.json"}
V1_MARKER_DIRS = {"packets", "evidence"}
SKELETON_TEMPLATES = {
    "index.md": (
        "# Project Knowledge Index\n"
        "\n"
        "Nuclio v2 文档库用于保存可恢复的 change 摘要和经确认的长期项目知识；代码、配置、测试、CI 和 Git working tree 仍是执行事实。\n"
        "\n"
        "## Knowledge\n"
        "\n"
        "- `knowledge/project.md`: 产品目标、用户、术语和跨领域事实。\n"
        "- `knowledge/architecture.md`: 架构约束、系统边界和重要设计关系。\n"
        "- `knowledge/engineering.md`: 构建、测试、发布、协作和代码实践。\n"
        "\n"
        "## Changes\n"
        "\n"
        "Active changes live in `.dev-docs/changes/<change-id>/` with `change.md`, `plan.yaml`, and `state.yaml`.\n"
        "\n"
        "Completed changes move to `.dev-docs/changes/archive/<change-id>/` as a concise one-file `change.md` record; active `plan.yaml` and `state.yaml` are not retained in long-term archive.\n"
        "\n"
        "Do not create `.dev-docs/changes/index.md`; root index does not enumerate active or archived changes.\n"
        "\n"
        "## Legacy\n"
        "\n"
        "Legacy material lives under `.dev-docs/legacy/` and is not read by default.\n"
    ),
    "knowledge/project.md": (
        "# Project Knowledge\n"
        "\n"
        "This file records confirmed product goals, users, terminology, and cross-domain facts that remain useful across changes.\n"
        "\n"
        "## Confirmed Knowledge\n"
        "\n"
        "No confirmed project knowledge has been recorded yet.\n"
    ),
    "knowledge/architecture.md": (
        "# Architecture Knowledge\n"
        "\n"
        "This file records confirmed architecture constraints, system boundaries, and important design relationships that remain useful across changes.\n"
        "\n"
        "## Confirmed Knowledge\n"
        "\n"
        "No confirmed architecture knowledge has been recorded yet.\n"
    ),
    "knowledge/engineering.md": (
        "# Engineering Knowledge\n"
        "\n"
        "This file records confirmed build, test, release, collaboration, and code practice knowledge that remain useful across changes.\n"
        "\n"
        "## Confirmed Knowledge\n"
        "\n"
        "No confirmed engineering knowledge has been recorded yet.\n"
    ),
}


class NuclioError(Exception):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def docs(self) -> Path:
        return self.root / ".dev-docs"

    @property
    def changes(self) -> Path:
        return self.docs / "changes"

    @property
    def archive(self) -> Path:
        return self.changes / "archive"

    @property
    def legacy(self) -> Path:
        return self.docs / "legacy"

    @property
    def legacy_v1(self) -> Path:
        return self.legacy / "v1"

    @property
    def tmp(self) -> Path:
        return self.root / ".dev-docs-v1-legacy-tmp"


@dataclass(frozen=True)
class LegacyFeatures:
    is_v2: bool
    has_v1: bool
    has_changes_index: bool
    protocol_paths: tuple[str, ...]


# CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nuclio v2 change Plan/State helper")
    parser.add_argument("--project-root", default=".", help="project root path; defaults to current directory")
    subparsers = parser.add_subparsers(dest="command", metavar="{" + ",".join(COMMANDS) + "}", required=True)

    create = subparsers.add_parser("create", help="create one active change.md Spec")
    create.add_argument("--id", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--goal", required=True)
    create.add_argument("--related-change", action="append", default=[])
    create.add_argument("--date")
    create.set_defaults(func=cmd_create)

    list_cmd = subparsers.add_parser("list", help="list active change directories")
    list_cmd.set_defaults(func=cmd_list)

    show = subparsers.add_parser("show", help="show one change artifact")
    show.add_argument("--id", required=True)
    show.add_argument("--archived", action="store_true")
    show.add_argument("--artifact", choices=("change", "plan", "state"), default="change")
    show.set_defaults(func=cmd_show)

    validate_plan = subparsers.add_parser("validate-plan", help="validate plan.yaml")
    validate_plan.add_argument("--id")
    validate_plan.add_argument("--plan")
    validate_plan.set_defaults(func=cmd_validate_plan)

    init_state = subparsers.add_parser("init-state", help="initialize state.yaml after user approval")
    init_state.add_argument("--id", required=True)
    init_state.set_defaults(func=cmd_init_state)

    status = subparsers.add_parser("status", help="read current state.yaml")
    status.add_argument("--id", required=True)
    status.set_defaults(func=cmd_status)

    next_action = subparsers.add_parser("next-action", help="read current next action")
    next_action.add_argument("--id", required=True)
    next_action.set_defaults(func=cmd_next_action)

    start_task = subparsers.add_parser("start-task", help="freeze one Task base")
    start_task.add_argument("--id", required=True)
    start_task.add_argument("--task-id", required=True, type=int)
    start_task.add_argument("--executor", default="main", choices=tuple(sorted(DELEGATES)))
    start_task.set_defaults(func=cmd_start_task)

    record_task = subparsers.add_parser("record-task", help="record one Task checkpoint commit")
    record_task.add_argument("--id", required=True)
    record_task.add_argument("--task-id", required=True, type=int)
    record_task.add_argument("--validation-status", required=True, choices=("PASS", "FAIL"))
    record_task.add_argument("--validation-summary", required=True)
    record_task.set_defaults(func=cmd_record_task)

    record_review = subparsers.add_parser("record-review", help="record task or final review result")
    record_review.add_argument("--id", required=True)
    record_review.add_argument("--scope", required=True, choices=("task", "final"))
    record_review.add_argument("--task-id", type=int)
    record_review.add_argument("--status", required=True, choices=("PASS", "FAIL"))
    record_review.add_argument("--contract", default="")
    record_review.add_argument("--path", action="append", default=[])
    record_review.add_argument("--evidence", default="")
    record_review.set_defaults(func=cmd_record_review)

    start_repair = subparsers.add_parser("start-repair", help="start approved in-scope repair")
    start_repair.add_argument("--id", required=True)
    start_repair.add_argument("--source-gate", required=True, choices=(NEXT_RUN_TASK_REVIEW, NEXT_RUN_FINAL_REVIEW, NEXT_RUN_VALIDATION))
    start_repair.add_argument("--path", action="append", required=True)
    start_repair.add_argument("--decision", required=True)
    start_repair.add_argument("--evidence", required=True)
    start_repair.add_argument("--contract-unchanged", action="store_true", required=True)
    start_repair.set_defaults(func=cmd_start_repair)

    record_repair = subparsers.add_parser("record-repair", help="record one repair checkpoint commit")
    record_repair.add_argument("--id", required=True)
    record_repair.add_argument("--repair-id", required=True, type=int)
    record_repair.add_argument("--validation-status", required=True, choices=("PASS", "FAIL"))
    record_repair.add_argument("--validation-summary", required=True)
    record_repair.set_defaults(func=cmd_record_repair)

    record_validation = subparsers.add_parser("record-validation", help="record whole-change validation result")
    record_validation.add_argument("--id", required=True)
    record_validation.add_argument("--status", required=True, choices=("PASS", "FAIL"))
    record_validation.add_argument("--summary", required=True)
    record_validation.add_argument("--command", action="append", default=[])
    record_validation.add_argument("--path", action="append", default=[])
    record_validation.add_argument("--evidence", default="")
    record_validation.set_defaults(func=cmd_record_validation)

    complete = subparsers.add_parser("complete", help="mark state.yaml complete after all gates pass")
    complete.add_argument("--id", required=True)
    complete.set_defaults(func=cmd_complete)

    archive = subparsers.add_parser("archive", help="archive a completed change directory")
    archive.add_argument("--id", required=True)
    archive.set_defaults(func=cmd_archive)

    legacy = subparsers.add_parser("legacy-move", help="move a clear v1 .dev-docs tree under v2 legacy/v1")
    legacy.set_defaults(func=cmd_legacy_move)
    return parser


# JSON command contract

def emit_ok(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


def emit_error(exc: NuclioError) -> int:
    payload: dict[str, Any] = {"ok": False, "code": exc.code, "message": exc.message}
    if exc.details:
        payload["details"] = exc.details
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    return 1


# Path safety

def resolve_root(path: str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def validate_id(change_id: str) -> str:
    if not change_id:
        raise NuclioError("INVALID_CHANGE_ID", "change id is required")
    if any(ch in change_id for ch in GLOB_CHARS):
        raise NuclioError("INVALID_CHANGE_ID", f"invalid change id: {change_id}")
    if any(part in change_id for part in ("/", "\\")):
        raise NuclioError("INVALID_CHANGE_ID", f"invalid change id: {change_id}")
    if Path(change_id).is_absolute() or ".." in change_id:
        raise NuclioError("INVALID_CHANGE_ID", f"invalid change id: {change_id}")
    if not ID_RE.fullmatch(change_id):
        raise NuclioError("INVALID_CHANGE_ID", f"invalid change id: {change_id}")
    return change_id


def ensure_under_root(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise NuclioError("PATH_ESCAPE", f"path escapes project root: {path}") from exc
    return path


def active_change_dir(paths: Paths, change_id: str) -> Path:
    validate_id(change_id)
    return ensure_under_root(paths.changes / change_id, paths.root)


def archive_change_dir(paths: Paths, change_id: str) -> Path:
    validate_id(change_id)
    return ensure_under_root(paths.archive / change_id, paths.root)


def change_artifact_path(directory: Path, artifact: str) -> Path:
    names = {"change": "change.md", "plan": "plan.yaml", "state": "state.yaml"}
    return directory / names[artifact]


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def validate_allowed_path(value: Any) -> str:
    if not isinstance(value, str):
        raise NuclioError("INVALID_ALLOWED_PATH", "allowed_paths entries must be strings")
    if value != value.strip() or not value:
        raise NuclioError("INVALID_ALLOWED_PATH", f"invalid allowed path: {value!r}")
    if any(ch.isspace() for ch in value):
        raise NuclioError("INVALID_ALLOWED_PATH", f"allowed path contains whitespace: {value!r}")
    if "\\" in value or any(ch in value for ch in GLOB_CHARS):
        raise NuclioError("INVALID_ALLOWED_PATH", f"allowed path contains forbidden pattern syntax: {value}")
    if value.startswith("/") or value.startswith("./") or value in {".", ".."}:
        raise NuclioError("INVALID_ALLOWED_PATH", f"allowed path must be project-relative: {value}")
    path_parts = value[:-1].split("/") if value.endswith("/") else value.split("/")
    if not path_parts or any(part in {"", ".", ".."} for part in path_parts):
        raise NuclioError("INVALID_ALLOWED_PATH", f"allowed path contains invalid segment: {value}")
    return value


def path_is_allowed(path: str, allowed_paths: list[str]) -> bool:
    normalized = path.strip("/")
    return any(normalized.startswith(allowed) if allowed.endswith("/") else normalized == allowed for allowed in allowed_paths)


# YAML safety

class UniqueKeySafeLoader(yaml.SafeLoader if yaml is not None else object):  # type: ignore[misc,valid-type]
    pass


def _construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise NuclioError("DUPLICATE_YAML_KEY", f"duplicate YAML mapping key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


if yaml is not None:
    UniqueKeySafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def require_yaml() -> Any:
    if yaml is None:
        raise NuclioError("DEPENDENCY_MISSING", "PyYAML is required; install the 'yaml' Python package")
    return yaml


def read_yaml_file(path: Path) -> Any:
    yaml_module = require_yaml()
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise NuclioError("MISSING_ARTIFACT", f"missing YAML artifact: {path}") from exc
    if len(data) > MAX_YAML_BYTES:
        raise NuclioError("YAML_TOO_LARGE", f"YAML input exceeds {MAX_YAML_BYTES} bytes: {path}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NuclioError("INVALID_UTF8", f"YAML artifact must be UTF-8: {path}") from exc
    try:
        return yaml_module.load(text, Loader=UniqueKeySafeLoader)
    except NuclioError:
        raise
    except Exception as exc:
        raise NuclioError("INVALID_YAML", f"invalid YAML: {path}: {exc}") from exc


def dump_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    yaml_module = require_yaml()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = -1
    tmp_name = ""
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            yaml_module.safe_dump(data, handle, sort_keys=False, allow_unicode=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception as exc:
        if fd != -1:
            os.close(fd)
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except OSError:
                pass
        if isinstance(exc, NuclioError):
            raise
        raise NuclioError("STATE_WRITE_FAILED", f"failed to atomically write state: {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise NuclioError("MISSING_ARTIFACT", f"missing artifact: {path}") from exc


# Plan validation

def assert_exact_keys(mapping: dict[str, Any], expected: set[str], label: str) -> None:
    extra = sorted(set(mapping) - expected)
    missing = sorted(expected - set(mapping))
    if extra or missing:
        raise NuclioError("INVALID_SCHEMA", f"{label} schema keys mismatch", extra=extra, missing=missing)


def require_non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NuclioError("INVALID_SCHEMA", f"{field} must be a non-empty string")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        raise NuclioError("INVALID_SCHEMA", f"{field} contains control characters")
    return value


def require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise NuclioError("INVALID_SCHEMA", f"{field} must be a non-empty list")
    result: list[str] = []
    for item in value:
        result.append(require_non_empty_string(item, field))
    return result


def contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return bool(re.search(r"<[^>]+>", value) or "todo" in lowered or "tbd" in lowered or "placeholder" in lowered)
    if isinstance(value, list):
        return any(contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(contains_placeholder(item) for item in value.values())
    return False


def validate_plan_data(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise NuclioError("INVALID_SCHEMA", "plan must be a mapping")
    assert_exact_keys(plan, PLAN_TOP_KEYS, "plan")
    if plan["schema_version"] != 1:
        raise NuclioError("INVALID_SCHEMA", "schema_version must be 1")
    change_id = validate_id(require_non_empty_string(plan["change_id"], "change_id"))
    if not isinstance(plan["revision"], int) or isinstance(plan["revision"], bool) or plan["revision"] <= 0:
        raise NuclioError("INVALID_SCHEMA", "revision must be a positive integer")
    if plan["risk_level"] not in RISK_LEVELS:
        raise NuclioError("INVALID_SCHEMA", "risk_level must be low, medium, or high")
    if plan["review_policy"] not in REVIEW_POLICIES:
        raise NuclioError("INVALID_SCHEMA", "review_policy must be self, final, or task-and-final")
    if plan["risk_level"] == "high" and plan["review_policy"] != "task-and-final":
        raise NuclioError("RISK_REVIEW_MISMATCH", "high risk changes require task-and-final review")
    if plan["repair_policy"] != "in-scope":
        raise NuclioError("INVALID_SCHEMA", "repair_policy must be in-scope")
    require_non_empty_string(plan["summary"], "summary")
    if not isinstance(plan["allowed_paths"], list) or not plan["allowed_paths"]:
        raise NuclioError("INVALID_SCHEMA", "allowed_paths must be a non-empty list")
    allowed_paths = [validate_allowed_path(item) for item in plan["allowed_paths"]]
    if len(allowed_paths) != len(set(allowed_paths)):
        raise NuclioError("DUPLICATE_ALLOWED_PATH", "allowed_paths must not contain duplicates")
    if not isinstance(plan["tasks"], list) or not plan["tasks"]:
        raise NuclioError("INVALID_SCHEMA", "tasks must be a non-empty list")
    seen_ids: set[int] = set()
    previous_id = 0
    for task in plan["tasks"]:
        if not isinstance(task, dict):
            raise NuclioError("INVALID_SCHEMA", "each task must be a mapping")
        assert_exact_keys(task, TASK_KEYS, "task")
        task_id = task["id"]
        if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
            raise NuclioError("INVALID_SCHEMA", "task id must be a positive integer")
        if task_id in seen_ids or task_id <= previous_id:
            raise NuclioError("INVALID_SCHEMA", "tasks must be strictly ordered by unique positive id")
        seen_ids.add(task_id)
        previous_id = task_id
        require_non_empty_string(task["name"], "task.name")
        require_string_list(task["steps"], "task.steps")
        require_string_list(task["acceptance"], "task.acceptance")
        require_string_list(task["validation"], "task.validation")
        if task["delegate"] not in DELEGATES:
            raise NuclioError("INVALID_SCHEMA", "task.delegate must be main, subagent, or auto")
        if task["review"] not in REVIEW_POLICIES:
            raise NuclioError("INVALID_SCHEMA", "task.review must be self, final, or task-and-final")
        subject = require_non_empty_string(task["checkpoint_subject"], "task.checkpoint_subject")
        if "\n" in subject or "\r" in subject:
            raise NuclioError("INVALID_SCHEMA", "task.checkpoint_subject must be single-line")
    if contains_placeholder(plan):
        raise NuclioError("PLACEHOLDER_VALUE", "plan contains placeholder text")
    return plan


def validate_plan_file(path: Path) -> dict[str, Any]:
    return validate_plan_data(read_yaml_file(path))


def plan_task(plan: dict[str, Any], task_id: int) -> dict[str, Any]:
    for task in plan["tasks"]:
        if task["id"] == task_id:
            return task
    raise NuclioError("UNKNOWN_TASK", f"unknown task id: {task_id}")


# State and Git helpers

def git(paths: Paths, *args: str, allow_fail: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(paths.root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if not allow_fail and result.returncode != 0:
        raise NuclioError("GIT_ERROR", f"git {' '.join(args)} failed", stderr=result.stderr.strip())
    return result


def git_head(paths: Paths) -> str:
    return git(paths, "rev-parse", "HEAD").stdout.strip()


def index_is_clean(paths: Paths) -> bool:
    return git(paths, "diff", "--cached", "--quiet", allow_fail=True).returncode == 0


def require_clean_index(paths: Paths) -> None:
    if not index_is_clean(paths):
        raise NuclioError("DIRTY_INDEX", "git index must be empty")


def porcelain_paths(paths: Paths) -> list[tuple[str, str]]:
    result = git(paths, "status", "--porcelain=v1", "-z")
    fields = [field for field in result.stdout.split("\0") if field]
    parsed: list[tuple[str, str]] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        status = entry[:2]
        name = entry[3:]
        if status.startswith("R") or status.startswith("C"):
            index += 1
            if index < len(fields):
                name = fields[index]
        parsed.append((status, name))
        index += 1
    return parsed


def require_no_preexisting_allowed_dirty(paths: Paths, allowed_paths: list[str]) -> None:
    dirty_allowed = [name for _status, name in porcelain_paths(paths) if path_is_allowed(name, allowed_paths)]
    if dirty_allowed:
        raise NuclioError("DIRTY_ALLOWED_PATH", "allowed paths contain pre-existing worktree changes", paths=dirty_allowed)


def commit_subject(paths: Paths, commit: str = "HEAD") -> str:
    return git(paths, "log", "-1", "--format=%s", commit).stdout.rstrip("\n")


def commit_parent(paths: Paths, commit: str = "HEAD") -> str:
    return git(paths, "rev-parse", f"{commit}^").stdout.strip()


def commit_changed_paths(paths: Paths, commit: str = "HEAD") -> list[str]:
    output = git(paths, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).stdout
    return [line for line in output.splitlines() if line]


def state_path_for(paths: Paths, change_id: str) -> Path:
    return active_change_dir(paths, change_id) / "state.yaml"


def plan_path_for(paths: Paths, change_id: str) -> Path:
    return active_change_dir(paths, change_id) / "plan.yaml"


def spec_path_for(paths: Paths, change_id: str) -> Path:
    return active_change_dir(paths, change_id) / "change.md"


def load_state(paths: Paths, change_id: str) -> dict[str, Any]:
    data = read_yaml_file(state_path_for(paths, change_id))
    if not isinstance(data, dict):
        raise NuclioError("INVALID_STATE", "state.yaml must be a mapping")
    return data


def load_verified_state_and_plan(paths: Paths, change_id: str, *, allow_head_drift: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    state = load_state(paths, change_id)
    plan_path = plan_path_for(paths, change_id)
    spec_path = spec_path_for(paths, change_id)
    plan = validate_plan_file(plan_path)
    if state.get("schema_version") != 1 or state.get("change_id") != change_id:
        raise NuclioError("INVALID_STATE", "state identity mismatch")
    if state.get("plan_revision") != plan["revision"]:
        raise NuclioError("IDENTITY_DRIFT", "plan revision drift", state_revision=state.get("plan_revision"), plan_revision=plan["revision"])
    if state.get("plan_sha256") != sha256_file(plan_path):
        raise NuclioError("IDENTITY_DRIFT", "plan hash drift")
    if state.get("spec_sha256") != sha256_file(spec_path):
        raise NuclioError("IDENTITY_DRIFT", "spec hash drift")
    current = git_head(paths)
    if not allow_head_drift and state.get("current_head") != current:
        raise NuclioError("IDENTITY_DRIFT", "state current_head differs from git HEAD", state_head=state.get("current_head"), git_head=current)
    return state, plan


def write_state(paths: Paths, change_id: str, state: dict[str, Any]) -> None:
    state["current_head"] = git_head(paths)
    dump_yaml_atomic(state_path_for(paths, change_id), state)


def initial_task_states(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": task["id"],
            "status": "PENDING",
            "task_base": None,
            "task_head": None,
            "checkpoint_commit": None,
            "checkpoint_subject": task["checkpoint_subject"],
            "executor": None,
            "validation": None,
        }
        for task in plan["tasks"]
    ]


def state_task(state: dict[str, Any], task_id: int) -> dict[str, Any]:
    for task in state["tasks"]:
        if task["id"] == task_id:
            return task
    raise NuclioError("UNKNOWN_TASK", f"unknown task id: {task_id}")


def first_pending_task_id(state: dict[str, Any]) -> int | None:
    for task in state["tasks"]:
        if task["status"] == "PENDING":
            return task["id"]
    return None


def next_after_task_gate(state: dict[str, Any], plan: dict[str, Any]) -> str:
    pending = first_pending_task_id(state)
    if pending is not None:
        return NEXT_DISPATCH_TASK
    if plan["review_policy"] in {"final", "task-and-final"} and state["review"]["final"].get("status") != "PASS":
        return NEXT_RUN_FINAL_REVIEW
    if state["validation"].get("status") != "PASS":
        return NEXT_RUN_VALIDATION
    return NEXT_COMPLETE


def task_review_required(plan: dict[str, Any], task: dict[str, Any]) -> bool:
    return plan["review_policy"] == "task-and-final" or task["review"] == "task-and-final"


def pending_task_review_ids(state: dict[str, Any], plan: dict[str, Any]) -> list[int]:
    task_reviews = state["review"].get("task_reviews", {})
    return [
        task["id"]
        for task in plan["tasks"]
        if task_review_required(plan, task)
        and state_task(state, task["id"])["status"] == "DONE"
        and task_reviews.get(str(task["id"]), {}).get("status") != "PASS"
    ]


def require_all_commit_paths_allowed(changed_paths: list[str], allowed_paths: list[str]) -> None:
    if not changed_paths:
        raise NuclioError("EMPTY_CHECKPOINT", "checkpoint commit changed no files")
    outside = [path for path in changed_paths if not path_is_allowed(path, allowed_paths)]
    if outside:
        raise NuclioError("ALLOWED_PATH_VIOLATION", "checkpoint commit changed paths outside allowed_paths", paths=outside)


# Commands

def date_arg(value: str | None) -> str:
    if value is None:
        return _dt.date.today().isoformat()
    try:
        _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise NuclioError("INVALID_DATE", f"invalid date: {value}") from exc
    return value


def require_v2_skeleton(paths: Paths) -> None:
    required_files = [
        paths.docs / "index.md",
        paths.docs / "knowledge" / "project.md",
        paths.docs / "knowledge" / "architecture.md",
        paths.docs / "knowledge" / "engineering.md",
    ]
    required_dirs = [paths.changes, paths.archive, paths.legacy]
    for path in required_files:
        ensure_under_root(path, paths.root)
        if not path.is_file():
            raise NuclioError("MISSING_SKELETON", f"required file missing: {path}")
    for path in required_dirs:
        ensure_under_root(path, paths.root)
        if not path.is_dir():
            raise NuclioError("MISSING_SKELETON", f"required directory missing: {path}")


def cmd_create(args: argparse.Namespace, paths: Paths) -> int:
    change_id = validate_id(args.id)
    for related in args.related_change:
        validate_id(related)
    title = args.title.strip()
    goal = args.goal.strip()
    if not title:
        raise NuclioError("INVALID_INPUT", "title must be non-empty")
    if not goal:
        raise NuclioError("INVALID_INPUT", "goal must be non-empty")
    today = date_arg(args.date)
    require_v2_skeleton(paths)
    active_dir = active_change_dir(paths, change_id)
    archived_dir = archive_change_dir(paths, change_id)
    if active_dir.exists():
        raise NuclioError("CHANGE_EXISTS", f"active change already exists: {active_dir}")
    if archived_dir.exists():
        raise NuclioError("CHANGE_EXISTS", f"archived change already exists: {archived_dir}")
    active_dir.mkdir(parents=False)
    related = json.dumps(args.related_change, ensure_ascii=False)
    change = active_dir / "change.md"
    content = (
        "---\n"
        f"id: {change_id}\n"
        f"title: {title}\n"
        "status: active\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"related_changes: {related}\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Goal\n\n"
        f"{goal}\n\n"
        "## Context\n\n"
        "待补充必要背景。\n\n"
        "## Constraints\n\n"
        "待在计划批准前确认。\n\n"
        "## Non-goals\n\n"
        "待在计划批准前确认。\n\n"
        "## Acceptance Criteria\n\n"
        "待在计划批准前确认。\n"
    )
    change.write_text(content, encoding="utf-8")
    return emit_ok({"ok": True, "change_id": change_id, "path": rel(change, paths.root)})


def h1_title_from_text(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return "unknown"


def cmd_list(args: argparse.Namespace, paths: Paths) -> int:
    _ = args
    if not paths.changes.is_dir():
        raise NuclioError("MISSING_SKELETON", f"changes directory missing: {paths.changes}")
    entries: list[dict[str, Any]] = []
    for item in sorted(paths.changes.iterdir(), key=lambda p: p.name):
        if item.name == "archive":
            continue
        try:
            ensure_under_root(item, paths.root)
        except NuclioError:
            continue
        if not item.is_dir():
            continue
        change = item / "change.md"
        if not change.is_file():
            continue
        try:
            text = change.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        entry = {"change_id": item.name, "title": h1_title_from_text(text), "path": rel(change, paths.root)}
        state_path = item / "state.yaml"
        if state_path.is_file():
            try:
                state = read_yaml_file(state_path)
                if isinstance(state, dict):
                    entry["status"] = state.get("status", "unknown")
                    entry["phase"] = state.get("phase", "unknown")
                    entry["next_action"] = state.get("next_action", "unknown")
            except NuclioError:
                entry["status"] = "unknown"
        entries.append(entry)
    return emit_ok({"ok": True, "changes": entries})


def cmd_show(args: argparse.Namespace, paths: Paths) -> int:
    directory = archive_change_dir(paths, args.id) if args.archived else active_change_dir(paths, args.id)
    artifact = change_artifact_path(directory, args.artifact)
    if not artifact.is_file():
        raise NuclioError("MISSING_ARTIFACT", f"missing artifact: {artifact}")
    return emit_ok({"ok": True, "change_id": args.id, "artifact": args.artifact, "path": rel(artifact, paths.root), "content": artifact.read_text(encoding="utf-8")})


def cmd_validate_plan(args: argparse.Namespace, paths: Paths) -> int:
    if args.plan:
        plan_path = ensure_under_root(Path(args.plan).expanduser().resolve(strict=False), paths.root)
    elif args.id:
        plan_path = plan_path_for(paths, args.id)
    else:
        raise NuclioError("INVALID_INPUT", "validate-plan requires --id or --plan")
    plan = validate_plan_file(plan_path)
    return emit_ok(
        {
            "ok": True,
            "change_id": plan["change_id"],
            "revision": plan["revision"],
            "risk_level": plan["risk_level"],
            "review_policy": plan["review_policy"],
            "tasks": [task["id"] for task in plan["tasks"]],
            "allowed_paths": plan["allowed_paths"],
        }
    )


def cmd_init_state(args: argparse.Namespace, paths: Paths) -> int:
    change_id = validate_id(args.id)
    active_dir = active_change_dir(paths, change_id)
    if not active_dir.is_dir():
        raise NuclioError("MISSING_CHANGE", f"active change missing: {active_dir}")
    state_path = active_dir / "state.yaml"
    if state_path.exists():
        raise NuclioError("STATE_EXISTS", f"state already exists: {state_path}")
    plan_path = active_dir / "plan.yaml"
    spec_path = active_dir / "change.md"
    plan = validate_plan_file(plan_path)
    if plan["change_id"] != change_id:
        raise NuclioError("IDENTITY_DRIFT", "plan change_id does not match requested change")
    head = git_head(paths)
    state = {
        "schema_version": 1,
        "change_id": change_id,
        "plan_revision": plan["revision"],
        "plan_sha256": sha256_file(plan_path),
        "spec_sha256": sha256_file(spec_path),
        "repo_root": str(paths.root),
        "initial_head": head,
        "current_head": head,
        "status": "ACTIVE",
        "phase": "READY",
        "current_task_id": None,
        "next_action": NEXT_DISPATCH_TASK,
        "tasks": initial_task_states(plan),
        "review": {"task_reviews": {}, "final": {"status": "NOT_REQUIRED" if plan["review_policy"] == "self" else "PENDING"}},
        "validation": {"status": "PENDING", "commands": [], "summary": None},
        "repair": None,
        "blocker": None,
    }
    dump_yaml_atomic(state_path, state)
    return emit_ok({"ok": True, "change_id": change_id, "path": rel(state_path, paths.root), "next_action": NEXT_DISPATCH_TASK, "head": head})


def cmd_status(args: argparse.Namespace, paths: Paths) -> int:
    state, _plan = load_verified_state_and_plan(paths, args.id)
    return emit_ok({"ok": True, "change_id": args.id, "state": state})


def cmd_next_action(args: argparse.Namespace, paths: Paths) -> int:
    state, _plan = load_verified_state_and_plan(paths, args.id)
    return emit_ok({"ok": True, "change_id": args.id, "next_action": state["next_action"], "current_task_id": state.get("current_task_id")})


def cmd_start_task(args: argparse.Namespace, paths: Paths) -> int:
    state, plan = load_verified_state_and_plan(paths, args.id)
    if state["next_action"] != NEXT_DISPATCH_TASK:
        raise NuclioError("INVALID_TRANSITION", "next_action is not DISPATCH_TASK", next_action=state["next_action"])
    task = plan_task(plan, args.task_id)
    state_task_entry = state_task(state, args.task_id)
    if state_task_entry["status"] != "PENDING":
        raise NuclioError("INVALID_TRANSITION", "task is not pending")
    pending = first_pending_task_id(state)
    if pending != args.task_id:
        raise NuclioError("INVALID_TRANSITION", "tasks must start in plan order", expected=pending, actual=args.task_id)
    require_clean_index(paths)
    require_no_preexisting_allowed_dirty(paths, plan["allowed_paths"])
    head = git_head(paths)
    state_task_entry.update({"status": "IN_PROGRESS", "task_base": head, "executor": args.executor})
    state.update({"phase": "TASK_IN_PROGRESS", "current_task_id": args.task_id, "next_action": NEXT_HALT})
    write_state(paths, args.id, state)
    return emit_ok({"ok": True, "change_id": args.id, "task_id": args.task_id, "task_base": head, "checkpoint_subject": task["checkpoint_subject"]})


def cmd_record_task(args: argparse.Namespace, paths: Paths) -> int:
    state, plan = load_verified_state_and_plan(paths, args.id, allow_head_drift=True)
    task = plan_task(plan, args.task_id)
    entry = state_task(state, args.task_id)
    if entry["status"] != "IN_PROGRESS":
        raise NuclioError("INVALID_TRANSITION", "task is not in progress")
    if args.validation_status != "PASS":
        raise NuclioError("VALIDATION_FAILED", "record-task requires PASS validation")
    require_clean_index(paths)
    head = git_head(paths)
    parent = commit_parent(paths, "HEAD")
    if parent != entry["task_base"]:
        raise NuclioError("CHECKPOINT_PARENT_MISMATCH", "task checkpoint parent must equal task_base", expected=entry["task_base"], actual=parent)
    subject = commit_subject(paths, "HEAD")
    if subject != task["checkpoint_subject"]:
        raise NuclioError("CHECKPOINT_SUBJECT_MISMATCH", "task checkpoint subject mismatch", expected=task["checkpoint_subject"], actual=subject)
    changed_paths = commit_changed_paths(paths, "HEAD")
    require_all_commit_paths_allowed(changed_paths, plan["allowed_paths"])
    entry.update(
        {
            "status": "DONE",
            "task_head": head,
            "checkpoint_commit": head,
            "validation": {"status": "PASS", "summary": args.validation_summary},
        }
    )
    if task_review_required(plan, task):
        state["review"]["task_reviews"][str(args.task_id)] = {"status": "PENDING"}
        next_action = NEXT_RUN_TASK_REVIEW
        phase = "TASK_REVIEW_PENDING"
    else:
        next_action = next_after_task_gate(state, plan)
        phase = "READY" if next_action == NEXT_DISPATCH_TASK else next_action
    state.update({"phase": phase, "current_task_id": None, "next_action": next_action, "blocker": None})
    write_state(paths, args.id, state)
    return emit_ok({"ok": True, "change_id": args.id, "task_id": args.task_id, "checkpoint_commit": head, "changed_paths": changed_paths, "next_action": next_action})


def cmd_record_review(args: argparse.Namespace, paths: Paths) -> int:
    state, plan = load_verified_state_and_plan(paths, args.id)
    if args.scope == "task":
        if args.task_id is None:
            raise NuclioError("INVALID_INPUT", "task review requires --task-id")
        task = plan_task(plan, args.task_id)
        if not task_review_required(plan, task):
            raise NuclioError("REVIEW_NOT_REQUIRED", "task review is not required", task_id=args.task_id)
        expected_action = NEXT_RUN_TASK_REVIEW
    else:
        if args.task_id is not None:
            raise NuclioError("INVALID_INPUT", "final review does not accept --task-id")
        expected_action = NEXT_RUN_FINAL_REVIEW
    if state["next_action"] != expected_action:
        raise NuclioError("INVALID_TRANSITION", f"next_action is not {expected_action}", next_action=state["next_action"])
    if args.scope == "task":
        pending_reviews = pending_task_review_ids(state, plan)
        if pending_reviews != [args.task_id]:
            raise NuclioError("INVALID_TRANSITION", "task review does not match the pending task review", expected=pending_reviews[0] if pending_reviews else None, actual=args.task_id)
    if args.status == "FAIL":
        source_gate = expected_action
        state["blocker"] = {
            "source_gate": source_gate,
            "contract": args.contract,
            "paths": args.path,
            "evidence": args.evidence,
        }
        if args.scope == "task":
            state["review"]["task_reviews"][str(args.task_id)] = {"status": "FAIL", "contract": args.contract, "paths": args.path, "evidence": args.evidence}
        else:
            state["review"]["final"] = {"status": "FAIL", "contract": args.contract, "paths": args.path, "evidence": args.evidence}
        state.update({"phase": "REPAIR_DECISION_PENDING", "next_action": NEXT_REQUEST_REPAIR_DECISION})
    else:
        if args.scope == "task":
            state["review"]["task_reviews"][str(args.task_id)] = {"status": "PASS", "contract": args.contract, "evidence": args.evidence}
            next_action = next_after_task_gate(state, plan)
        else:
            state["review"]["final"] = {"status": "PASS", "contract": args.contract, "evidence": args.evidence}
            next_action = NEXT_RUN_VALIDATION if state["validation"].get("status") != "PASS" else NEXT_COMPLETE
        state.update({"phase": next_action, "next_action": next_action, "blocker": None})
    write_state(paths, args.id, state)
    return emit_ok({"ok": True, "change_id": args.id, "next_action": state["next_action"]})


def cmd_start_repair(args: argparse.Namespace, paths: Paths) -> int:
    state, plan = load_verified_state_and_plan(paths, args.id)
    if plan["repair_policy"] != "in-scope":
        raise NuclioError("INVALID_TRANSITION", "plan repair_policy is not in-scope")
    if state["next_action"] != NEXT_REQUEST_REPAIR_DECISION or not state.get("blocker"):
        raise NuclioError("INVALID_TRANSITION", "no repair decision is pending")
    if state["blocker"].get("source_gate") != args.source_gate:
        raise NuclioError("INVALID_TRANSITION", "source gate does not match blocker", expected=state["blocker"].get("source_gate"), actual=args.source_gate)
    repair_paths = [validate_allowed_path(path) for path in args.path]
    outside = [path for path in repair_paths if not path_is_allowed(path, plan["allowed_paths"])]
    if outside:
        raise NuclioError("ALLOWED_PATH_VIOLATION", "repair paths must stay inside allowed_paths", paths=outside)
    require_clean_index(paths)
    require_no_preexisting_allowed_dirty(paths, plan["allowed_paths"])
    repair_number = 1 if state.get("repair") is None else int(state["repair"].get("id", 0)) + 1
    subject = f"repair({args.id}): {args.source_gate.lower()} repair {repair_number}"
    head = git_head(paths)
    state["repair"] = {
        "id": repair_number,
        "status": "IN_PROGRESS",
        "source_gate": args.source_gate,
        "paths": repair_paths,
        "decision": args.decision,
        "evidence": args.evidence,
        "contract_unchanged": bool(args.contract_unchanged),
        "repair_base": head,
        "checkpoint_commit": None,
        "checkpoint_subject": subject,
        "closure_validation": None,
    }
    state.update({"phase": "REPAIR_IN_PROGRESS", "next_action": NEXT_HALT})
    write_state(paths, args.id, state)
    return emit_ok({"ok": True, "change_id": args.id, "repair_id": repair_number, "repair_base": head, "checkpoint_subject": subject})


def cmd_record_repair(args: argparse.Namespace, paths: Paths) -> int:
    state, plan = load_verified_state_and_plan(paths, args.id, allow_head_drift=True)
    repair = state.get("repair")
    if not isinstance(repair, dict) or repair.get("id") != args.repair_id or repair.get("status") != "IN_PROGRESS":
        raise NuclioError("INVALID_TRANSITION", "repair is not in progress")
    if args.validation_status != "PASS":
        raise NuclioError("VALIDATION_FAILED", "record-repair requires PASS closure validation")
    require_clean_index(paths)
    head = git_head(paths)
    parent = commit_parent(paths, "HEAD")
    if parent != repair["repair_base"]:
        raise NuclioError("CHECKPOINT_PARENT_MISMATCH", "repair checkpoint parent must equal repair_base", expected=repair["repair_base"], actual=parent)
    subject = commit_subject(paths, "HEAD")
    if subject != repair["checkpoint_subject"]:
        raise NuclioError("CHECKPOINT_SUBJECT_MISMATCH", "repair checkpoint subject mismatch", expected=repair["checkpoint_subject"], actual=subject)
    changed_paths = commit_changed_paths(paths, "HEAD")
    require_all_commit_paths_allowed(changed_paths, plan["allowed_paths"])
    source_gate = repair["source_gate"]
    repair.update({"status": "DONE", "checkpoint_commit": head, "closure_validation": {"status": "PASS", "summary": args.validation_summary}, "changed_paths": changed_paths})
    state.update({"phase": source_gate, "next_action": source_gate, "blocker": None})
    write_state(paths, args.id, state)
    return emit_ok({"ok": True, "change_id": args.id, "repair_id": args.repair_id, "checkpoint_commit": head, "changed_paths": changed_paths, "next_action": source_gate})


def cmd_record_validation(args: argparse.Namespace, paths: Paths) -> int:
    state, plan = load_verified_state_and_plan(paths, args.id)
    if state["next_action"] != NEXT_RUN_VALIDATION:
        raise NuclioError("INVALID_TRANSITION", "next_action is not RUN_VALIDATION", next_action=state["next_action"])
    if args.status == "FAIL":
        state["validation"] = {"status": "FAIL", "commands": args.command, "summary": args.summary, "paths": args.path, "evidence": args.evidence}
        state["blocker"] = {"source_gate": NEXT_RUN_VALIDATION, "contract": "validation", "paths": args.path, "evidence": args.evidence or args.summary}
        state.update({"phase": "REPAIR_DECISION_PENDING", "next_action": NEXT_REQUEST_REPAIR_DECISION})
    else:
        state["validation"] = {"status": "PASS", "commands": args.command, "summary": args.summary}
        state.update({"phase": NEXT_COMPLETE, "next_action": NEXT_COMPLETE, "blocker": None})
    write_state(paths, args.id, state)
    return emit_ok({"ok": True, "change_id": args.id, "next_action": state["next_action"]})


def cmd_complete(args: argparse.Namespace, paths: Paths) -> int:
    state, plan = load_verified_state_and_plan(paths, args.id)
    if state["next_action"] != NEXT_COMPLETE:
        raise NuclioError("INVALID_TRANSITION", "next_action is not COMPLETE", next_action=state["next_action"])
    not_done = [task["id"] for task in state["tasks"] if task["status"] != "DONE"]
    if not_done:
        raise NuclioError("INCOMPLETE_TASKS", "all tasks must be DONE", tasks=not_done)
    missing_reviews = [
        task["id"]
        for task in plan["tasks"]
        if task_review_required(plan, task)
        and state["review"]["task_reviews"].get(str(task["id"]), {}).get("status") != "PASS"
    ]
    if missing_reviews:
        raise NuclioError("REVIEW_NOT_PASSED", "all task reviews must pass", tasks=missing_reviews)
    if plan["review_policy"] in {"final", "task-and-final"} and state["review"]["final"].get("status") != "PASS":
        raise NuclioError("REVIEW_NOT_PASSED", "final review must pass")
    if state["validation"].get("status") != "PASS":
        raise NuclioError("VALIDATION_NOT_PASSED", "whole-change validation must pass")
    state.update({"status": "COMPLETED", "phase": "COMPLETED", "next_action": NEXT_COMPLETE, "current_task_id": None, "blocker": None})
    write_state(paths, args.id, state)
    return emit_ok({"ok": True, "change_id": args.id, "status": "COMPLETED", "head": state["current_head"]})


def archive_artifacts(directory: Path) -> list[str]:
    try:
        return sorted(path.name for path in directory.iterdir())
    except FileNotFoundError as exc:
        raise NuclioError("MISSING_CHANGE", f"active change missing: {directory}") from exc


def require_exact_archive_artifacts(directory: Path) -> None:
    artifacts = archive_artifacts(directory)
    expected = sorted(ARCHIVE_ACTIVE_ARTIFACTS)
    missing = [name for name in expected if name not in artifacts]
    unexpected = [name for name in artifacts if name not in expected]
    invalid_regular_files = [name for name in expected if name in artifacts and not (directory / name).is_file()]
    symlink_artifacts = [name for name in expected if name in artifacts and (directory / name).is_symlink()]
    if missing or unexpected or invalid_regular_files or symlink_artifacts:
        raise NuclioError(
            "UNEXPECTED_ARCHIVE_ARTIFACTS",
            "active change directory must contain exactly regular non-symlink change.md, plan.yaml, and state.yaml",
            missing=missing,
            unexpected=unexpected,
            invalid_regular_files=invalid_regular_files,
            symlink_artifacts=symlink_artifacts,
        )


def parse_markdown_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise NuclioError("UNDISTILLED_RECORD", "change.md must start with completed YAML frontmatter", frontmatter={})
    end = text.find("\n---\n", 4)
    if end == -1:
        raise NuclioError("UNDISTILLED_RECORD", "change.md frontmatter is not closed", frontmatter={})
    yaml_module = require_yaml()
    frontmatter_text = text[4:end]
    try:
        frontmatter = yaml_module.load(frontmatter_text, Loader=UniqueKeySafeLoader)
    except NuclioError:
        raise
    except Exception as exc:
        raise NuclioError("UNDISTILLED_RECORD", f"invalid change.md frontmatter: {exc}", frontmatter={}) from exc
    if not isinstance(frontmatter, dict):
        raise NuclioError("UNDISTILLED_RECORD", "change.md frontmatter must be a mapping", frontmatter={})
    body = text[end + len("\n---\n"):]
    return frontmatter, body


def markdown_heading_sections(body: str) -> dict[str, str]:
    headings = list(re.finditer(r"^##\s+(.+?)\s*$", body, flags=re.M))
    sections: dict[str, str] = {}
    for index, match in enumerate(headings):
        name = match.group(1).strip()
        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        sections[name] = body[start:end].strip()
    return sections


def require_distilled_change_record(paths: Paths, change_id: str) -> None:
    change = spec_path_for(paths, change_id)
    try:
        text = change.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise NuclioError("MISSING_ARTIFACT", f"missing artifact: {change}") from exc
    except UnicodeDecodeError as exc:
        raise NuclioError("INVALID_UTF8", f"change.md must be UTF-8: {change}") from exc
    if not text.strip():
        raise NuclioError("UNDISTILLED_RECORD", "change.md must be non-empty")
    frontmatter, body = parse_markdown_frontmatter(text)
    required_frontmatter = {"id", "title", "status", "created", "updated", "related_changes"}
    missing_frontmatter = sorted(required_frontmatter - set(frontmatter))
    if missing_frontmatter or frontmatter.get("id") != change_id or frontmatter.get("status") != "completed":
        raise NuclioError(
            "UNDISTILLED_RECORD",
            "change.md must have completed historical-record frontmatter",
            missing_frontmatter=missing_frontmatter,
            frontmatter={"id": frontmatter.get("id"), "status": frontmatter.get("status")},
        )
    if not isinstance(frontmatter.get("title"), str) or not frontmatter["title"].strip():
        raise NuclioError("UNDISTILLED_RECORD", "change.md completed frontmatter fields must be non-empty", empty_frontmatter=["title"])
    for field in ("created", "updated"):
        value = frontmatter.get(field)
        if isinstance(value, str):
            valid_date = bool(value.strip())
        else:
            valid_date = isinstance(value, _dt.date)
        if not valid_date:
            raise NuclioError("UNDISTILLED_RECORD", "change.md completed frontmatter fields must be non-empty", empty_frontmatter=[field])
    if not isinstance(frontmatter.get("related_changes"), list):
        raise NuclioError("UNDISTILLED_RECORD", "change.md related_changes frontmatter must be a list", frontmatter={"related_changes": frontmatter.get("related_changes")})
    sections = markdown_heading_sections(body)
    missing_headings = [heading for heading in ARCHIVE_REQUIRED_HEADINGS if heading not in sections]
    empty_headings = [heading for heading in ARCHIVE_REQUIRED_HEADINGS if heading in sections and not sections[heading].strip()]
    if missing_headings or empty_headings:
        raise NuclioError("UNDISTILLED_RECORD", "change.md must contain non-empty completed historical-record headings", missing_headings=missing_headings, empty_headings=empty_headings)


def load_archive_verified_state_and_plan(paths: Paths, change_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    state = load_state(paths, change_id)
    plan_path = plan_path_for(paths, change_id)
    plan = validate_plan_file(plan_path)
    if state.get("schema_version") != 1 or state.get("change_id") != change_id:
        raise NuclioError("INVALID_STATE", "state identity mismatch")
    if state.get("plan_revision") != plan["revision"]:
        raise NuclioError("IDENTITY_DRIFT", "plan revision drift", state_revision=state.get("plan_revision"), plan_revision=plan["revision"])
    if state.get("plan_sha256") != sha256_file(plan_path):
        raise NuclioError("IDENTITY_DRIFT", "plan hash drift")
    if state.get("status") != "COMPLETED" or state.get("phase") != "COMPLETED":
        raise NuclioError("CHANGE_NOT_COMPLETE", "change must be complete before archive")
    current = git_head(paths)
    if state.get("current_head") != current:
        raise NuclioError("IDENTITY_DRIFT", "state current_head differs from git HEAD", state_head=state.get("current_head"), git_head=current)
    if not isinstance(state.get("spec_sha256"), str) or not state["spec_sha256"]:
        raise NuclioError("IDENTITY_DRIFT", "state spec_sha256 is missing")
    require_distilled_change_record(paths, change_id)
    return state, plan


def prune_archive_execution_artifacts(target: Path, paths: Paths) -> list[str]:
    try:
        for name in ("plan.yaml", "state.yaml"):
            artifact = target / name
            if artifact.exists():
                artifact.unlink()
    except OSError as exc:
        remaining = archive_artifacts(target)
        raise NuclioError("ARCHIVE_PRUNE_FAILED", "archive pruning failed", archive_path=rel(target, paths.root), remaining_artifacts=remaining) from exc
    remaining = archive_artifacts(target)
    if remaining != ["change.md"]:
        raise NuclioError("ARCHIVE_PRUNE_FAILED", "archive pruning left unexpected artifacts", archive_path=rel(target, paths.root), remaining_artifacts=remaining)
    return remaining


def cmd_archive(args: argparse.Namespace, paths: Paths) -> int:
    change_id = validate_id(args.id)
    source = active_change_dir(paths, change_id)
    target = archive_change_dir(paths, change_id)
    if target.exists():
        raise NuclioError("ARCHIVE_EXISTS", f"archive target already exists: {target}")
    require_exact_archive_artifacts(source)
    load_archive_verified_state_and_plan(paths, change_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    retained = prune_archive_execution_artifacts(target, paths)
    return emit_ok({"ok": True, "change_id": change_id, "path": rel(target, paths.root), "retained_artifacts": retained})


# Legacy move

def v2_skeleton_exists(paths: Paths) -> bool:
    return (
        (paths.docs / "index.md").is_file()
        and (paths.docs / "knowledge" / "project.md").is_file()
        and (paths.docs / "knowledge" / "architecture.md").is_file()
        and (paths.docs / "knowledge" / "engineering.md").is_file()
        and paths.archive.is_dir()
        and paths.legacy.is_dir()
    )


def inspect_legacy_features(paths: Paths) -> LegacyFeatures:
    docs = paths.docs
    if not docs.exists() or not docs.is_dir():
        raise NuclioError("MISSING_DEV_DOCS", f".dev-docs directory missing: {docs}")
    protocol_paths: list[str] = []
    changes = paths.changes
    if changes.is_dir():
        for change_dir in sorted(changes.iterdir(), key=lambda p: p.name):
            if not change_dir.is_dir() or change_dir.name == "archive":
                continue
            for marker in V1_MARKER_FILES:
                marker_path = change_dir / marker
                if marker_path.exists():
                    protocol_paths.append(rel(marker_path, paths.root))
            for marker in V1_MARKER_DIRS:
                marker_path = change_dir / marker
                if marker_path.is_dir():
                    protocol_paths.append(rel(marker_path, paths.root))
    changes_index = (changes / "index.md").is_file()
    has_protocol = bool(protocol_paths)
    has_v1 = has_protocol or (changes_index and has_protocol)
    return LegacyFeatures(
        is_v2=v2_skeleton_exists(paths),
        has_v1=has_v1,
        has_changes_index=changes_index,
        protocol_paths=tuple(protocol_paths),
    )


def create_v2_skeleton(paths: Paths) -> list[Path]:
    created: list[Path] = []

    def make_dir(path: Path) -> None:
        if not path.exists():
            path.mkdir()
            created.append(path)

    def write_file(path: Path, content: str) -> None:
        if path.exists():
            raise NuclioError("SKELETON_CONFLICT", f"unexpected existing skeleton file: {path}")
        path.write_text(content, encoding="utf-8")
        created.append(path)

    make_dir(paths.docs)
    make_dir(paths.docs / "knowledge")
    make_dir(paths.changes)
    make_dir(paths.archive)
    make_dir(paths.legacy)
    for relative_path, content in SKELETON_TEMPLATES.items():
        write_file(paths.docs / relative_path, content)
    return created


def remove_empty_parents(path: Path, stop: Path) -> None:
    current = path
    while current != stop and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def cleanup_created_skeleton(created: Iterable[Path], paths: Paths) -> None:
    for path in reversed(list(created)):
        try:
            ensure_under_root(path, paths.root)
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        except (OSError, NuclioError):
            continue
    remove_empty_parents(paths.docs, paths.root)


def status_report(paths: Paths) -> str:
    return (
        f".dev-docs exists={paths.docs.exists()} "
        f".dev-docs-v1-legacy-tmp exists={paths.tmp.exists()} "
        f".dev-docs/legacy/v1 exists={paths.legacy_v1.exists()}"
    )


def cmd_legacy_move(args: argparse.Namespace, paths: Paths) -> int:
    _ = args
    features = inspect_legacy_features(paths)
    if features.is_v2 and features.has_v1:
        raise NuclioError("LEGACY_CONFLICT", "conflicting v1 and v2 .dev-docs features", protocol_paths=list(features.protocol_paths))
    if features.is_v2:
        raise NuclioError("ALREADY_V2", ".dev-docs is already v2")
    if not features.has_v1:
        raise NuclioError("NOT_CLEAR_V1", ".dev-docs is not a clear v1 tree")
    if paths.tmp.exists():
        raise NuclioError("TEMP_TARGET_EXISTS", f"temporary target exists: {paths.tmp}")
    if paths.legacy_v1.exists():
        raise NuclioError("LEGACY_TARGET_EXISTS", f"legacy target exists: {paths.legacy_v1}")

    created: list[Path] = []
    moved_to_tmp = False
    try:
        paths.docs.rename(paths.tmp)
        moved_to_tmp = True
        created = create_v2_skeleton(paths)
        paths.tmp.rename(paths.legacy_v1)
        return emit_ok({"ok": True, "path": rel(paths.legacy_v1, paths.root)})
    except Exception as exc:
        if moved_to_tmp:
            cleanup_created_skeleton(created, paths)
            if paths.tmp.exists() and not paths.docs.exists():
                try:
                    paths.tmp.rename(paths.docs)
                except OSError:
                    pass
        if isinstance(exc, NuclioError):
            raise
        raise NuclioError("LEGACY_MOVE_FAILED", f"legacy-move failed; {status_report(paths)}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = resolve_root(args.project_root)
    paths = Paths(root=root)
    try:
        return args.func(args, paths)
    except NuclioError as exc:
        return emit_error(exc)
    except OSError as exc:
        return emit_error(NuclioError("FILESYSTEM_ERROR", f"filesystem error: {exc}"))


if __name__ == "__main__":
    raise SystemExit(main())
