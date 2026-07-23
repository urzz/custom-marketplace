#!/usr/bin/env python3
"""Shared deterministic Plan contract validation for skill-forge scripts."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re

try:
    import yaml
except ImportError:  # pragma: no cover - command-line callers fail before tests run.
    yaml = None


RISK_LEVELS = {"L2", "L3"}
REVIEW_POLICIES = {"final-only", "task-and-final"}
META_REQUIRED_KEYS = {"model", "file_type", "requires_execution_check"}
FILE_OPERATIONS = ("create", "modify", "delete")
INVALID_PATH_MARKERS = set("*?[]{}")
LOWER_TASK_AND_FINAL_KEYWORDS = (
    "routing",
    "gate",
    "agent authority",
    "authority",
    "cross task",
    "cross-task",
    "interface",
    "review-state",
    "state",
    "helper",
    "not deterministic",
    "cannot deterministic",
    "无法由确定性测试充分证明",
    "路由",
    "门禁",
    "权限",
    "跨 task",
    "跨task",
    "接口",
    "状态",
)


class PlanContractError(Exception):
    """Expected Plan contract failure with a stable machine-readable code."""

    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class PlanContract:
    plan: dict
    tasks: dict
    task_order: list
    run_risk_level: str


def _require(condition, code, detail=None):
    if not condition:
        raise PlanContractError(code, detail)


def _non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


def valid_ownership_path(value):
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if "\\" in value or any(marker in value for marker in INVALID_PATH_MARKERS):
        return False
    if any(character.isspace() for character in value):
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        return False
    return path.as_posix() == value


def _risk_rank(risk_level):
    return {"L2": 2, "L3": 3}[risk_level]


def _validate_files(files):
    _require(isinstance(files, dict), "INVALID_PLAN_TASK")
    ownership = {}
    seen = set()
    for operation in FILE_OPERATIONS:
        paths = files.get(operation, [])
        _require(isinstance(paths, list), "INVALID_PLAN_TASK")
        normalized = []
        for path in paths:
            _require(valid_ownership_path(path), "INVALID_OWNERSHIP_PATH", path)
            _require(path not in seen, "DUPLICATE_OWNERSHIP_PATH", path)
            seen.add(path)
            normalized.append(path)
        ownership[operation] = normalized
    extra = set(files) - set(FILE_OPERATIONS)
    _require(not extra, "INVALID_PLAN_TASK", sorted(extra))
    return ownership


def _task_text(raw):
    parts = []
    for key in ("name", "interfaces", "steps", "acceptance_criteria"):
        value = raw.get(key)
        parts.append(str(value))
    return "\n".join(parts).lower()


def _requires_task_and_final(raw):
    text = _task_text(raw)
    return any(keyword in text for keyword in LOWER_TASK_AND_FINAL_KEYWORDS)


def _validate_meta(raw):
    meta = raw.get("meta")
    _require(isinstance(meta, dict), "INVALID_PLAN_TASK_META")
    _require(META_REQUIRED_KEYS <= set(meta), "INVALID_PLAN_TASK_META")
    _require(_non_empty_string(meta.get("model")), "INVALID_PLAN_TASK_META")
    _require(_non_empty_string(meta.get("file_type")), "INVALID_PLAN_TASK_META")
    _require(type(meta.get("requires_execution_check")) is bool, "INVALID_PLAN_TASK_META")
    risk_level = meta.get("risk_level", "L3")
    review_policy = meta.get("review_policy", "task-and-final")
    _require(risk_level in RISK_LEVELS, "INVALID_RISK_LEVEL", risk_level)
    _require(review_policy in REVIEW_POLICIES, "INVALID_REVIEW_POLICY", review_policy)
    if risk_level == "L3":
        _require(review_policy == "task-and-final", "INVALID_REVIEW_POLICY", review_policy)
    if risk_level == "L2" and review_policy == "final-only":
        _require(not _requires_task_and_final(raw), "INVALID_REVIEW_POLICY", review_policy)
    normalized = dict(meta)
    normalized["risk_level"] = risk_level
    normalized["review_policy"] = review_policy
    return normalized


def validate_plan(plan):
    _require(isinstance(plan, dict), "INVALID_PLAN")
    tasks = plan.get("tasks")
    _require(isinstance(tasks, list) and tasks, "INVALID_PLAN_TASKS")
    parsed = {}
    normalized_tasks = []
    task_order = []
    run_risk_level = "L2"
    for raw in tasks:
        _require(isinstance(raw, dict), "INVALID_PLAN_TASK")
        _require("id" in raw, "INVALID_PLAN_TASK")
        task_id = str(raw["id"])
        _require(task_id not in parsed, "DUPLICATE_TASK_ID", task_id)
        _require(_non_empty_string(raw.get("name")), "INVALID_PLAN_TASK")
        ownership = _validate_files(raw.get("files", {}))
        interfaces = raw.get("interfaces", {})
        _require(isinstance(interfaces, dict), "INVALID_PLAN_TASK")
        steps = raw.get("steps")
        acceptance = raw.get("acceptance_criteria")
        _require(isinstance(steps, list) and all(_non_empty_string(item) for item in steps), "INVALID_PLAN_TASK")
        _require(
            isinstance(acceptance, list) and all(_non_empty_string(item) for item in acceptance),
            "INVALID_PLAN_TASK",
        )
        meta = _validate_meta(raw)
        if _risk_rank(meta["risk_level"]) > _risk_rank(run_risk_level):
            run_risk_level = meta["risk_level"]
        normalized = dict(raw)
        normalized["files"] = ownership
        normalized["interfaces"] = interfaces
        normalized["meta"] = meta
        normalized_tasks.append(normalized)
        task_order.append(task_id)
        parsed[task_id] = normalized
    if run_risk_level == "L3":
        for task_id in task_order:
            review_policy = parsed[task_id]["meta"]["review_policy"]
            _require(review_policy == "task-and-final", "INVALID_REVIEW_POLICY", review_policy)
    normalized_plan = dict(plan)
    normalized_plan["tasks"] = normalized_tasks
    return PlanContract(
        plan=normalized_plan,
        tasks=parsed,
        task_order=task_order,
        run_risk_level=run_risk_level,
    )


def load_plan_contract(path):
    if yaml is None:
        raise PlanContractError("INVALID_PLAN", "requires pyyaml")
    plan_path = Path(path)
    try:
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PlanContractError("INVALID_PLAN", str(exc)) from exc
    except OSError as exc:
        raise PlanContractError("INVALID_PLAN", str(exc)) from exc
    return validate_plan(plan)


def expected_task_subject(scope, task_id, task_name):
    return f"feat({scope}): [Task {task_id}] {task_name}"


def expected_fix_subject(scope, task_id, attempt):
    return f"fix({scope}): [Task {task_id} Fix {attempt}] address authorized findings"


def find_skill_forge_run_dir(path):
    resolved = Path(path).expanduser().resolve()
    parts = resolved.parts
    for index, part in enumerate(parts[:-1]):
        if part == ".skill-forge" and index + 1 < len(parts):
            return Path(*parts[: index + 2])
    return None


def path_is_within(child, parent):
    child_path = Path(child).expanduser().resolve()
    parent_path = Path(parent).expanduser().resolve()
    try:
        child_path.relative_to(parent_path)
    except ValueError:
        return False
    return True
