#!/usr/bin/env python3
"""
Nuclio Next deterministic contract helper.

## Contents

- [Protocol errors](#protocol-errors)
- [YAML subset parser](#yaml-subset-parser)
- [Contract validation](#contract-validation)
- [Derived outputs](#derived-outputs)
- [CLI](#cli)

This helper intentionally implements a small, safe YAML subset with Python's
standard library only. It accepts mappings, lists, scalar strings/integers,
booleans, null, quoted scalars, inline empty lists/maps, comments, and blank
lines. Anchors, aliases, tags, multiline scalars, flow collections other than
[]/{} and other YAML features are rejected fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


class ProtocolError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class _Container:
    def __init__(self, kind: str, indent: int, value: Any):
        self.kind = kind
        self.indent = indent
        self.value = value


def _strip_comment(line: str) -> str:
    quote = None
    escaped = False
    for i, char in enumerate(line):
        if quote:
            if char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = None
            escaped = False
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    if quote:
        raise ProtocolError("INVALID_YAML", "unterminated quoted scalar")
    return line


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if text == "":
        raise ProtocolError("INVALID_YAML", "empty scalar is not allowed")
    if text.startswith(("&", "*", "!")) or text in {"|", ">"}:
        raise ProtocolError("UNSUPPORTED_YAML_FEATURE", "anchors, aliases, tags and multiline scalars are not supported")
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text.startswith("[") or text.startswith("{"):
        raise ProtocolError("UNSUPPORTED_YAML_FEATURE", "flow collections other than [] and {} are not supported")
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except ValueError as exc:  # pragma: no cover - regex prevents this
            raise ProtocolError("INVALID_YAML", "invalid integer") from exc
    if ": " in text:
        raise ProtocolError("UNSUPPORTED_YAML_FEATURE", "inline mappings are not supported")
    return text


def _split_key_value(text: str) -> tuple[str, str | None]:
    quote = None
    escaped = False
    for i, char in enumerate(text):
        if quote:
            if char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = None
            escaped = False
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char == ":":
            key = text[:i].strip()
            rest = text[i + 1 :].strip()
            if not key:
                raise ProtocolError("INVALID_YAML", "mapping key cannot be empty")
            return key, rest if rest != "" else None
    raise ProtocolError("INVALID_YAML", "expected mapping key")


def _next_significant(lines: list[tuple[int, str]], start: int) -> str | None:
    for _, text in lines[start:]:
        stripped = text.strip()
        if stripped:
            return stripped
    return None


def parse_yaml_subset(text: str) -> dict[str, Any]:
    logical: list[tuple[int, str]] = []
    for number, original in enumerate(text.splitlines(), 1):
        if "\t" in original:
            raise ProtocolError("INVALID_YAML", "tabs are not allowed", {"line": number})
        stripped_comment = _strip_comment(original).rstrip()
        if not stripped_comment.strip():
            continue
        indent = len(stripped_comment) - len(stripped_comment.lstrip(" "))
        if indent % 2 != 0:
            raise ProtocolError("INVALID_YAML", "indentation must use multiples of two spaces", {"line": number})
        logical.append((indent, stripped_comment.lstrip(" ")))
    if not logical:
        raise ProtocolError("INVALID_CONTRACT", "contract must not be empty")
    if logical[0][0] != 0 or logical[0][1].startswith("-"):
        raise ProtocolError("INVALID_CONTRACT", "contract root must be a mapping")

    root: dict[str, Any] = {}
    stack: list[_Container] = [_Container("dict", -2, root)]

    for index, (indent, text_line) in enumerate(logical):
        while stack and indent <= stack[-1].indent:
            stack.pop()
        if not stack:
            raise ProtocolError("INVALID_YAML", "invalid indentation")
        parent = stack[-1]
        if text_line.startswith("- "):
            if parent.kind != "list":
                raise ProtocolError("INVALID_YAML", "list item without list parent")
            item_text = text_line[2:].strip()
            if item_text == "":
                raise ProtocolError("INVALID_YAML", "empty list item is not supported")
            if ":" in item_text and not item_text.startswith(("'", '"')):
                key, rest = _split_key_value(item_text)
                item: dict[str, Any] = {}
                if key in item:
                    raise ProtocolError("INVALID_YAML", "duplicate mapping key")
                if rest is None:
                    next_text = _next_significant(logical, index + 1)
                    child = [] if next_text and next_text.startswith("- ") else {}
                    item[key] = child
                    parent.value.append(item)
                    stack.append(_Container("dict", indent, item))
                    stack.append(_Container("list" if isinstance(child, list) else "dict", indent, child))
                else:
                    item[key] = _parse_scalar(rest)
                    parent.value.append(item)
                    stack.append(_Container("dict", indent, item))
            else:
                parent.value.append(_parse_scalar(item_text))
            continue

        if parent.kind != "dict":
            raise ProtocolError("INVALID_YAML", "mapping item without mapping parent")
        key, rest = _split_key_value(text_line)
        if key in parent.value:
            raise ProtocolError("INVALID_YAML", "duplicate mapping key", {"key": key})
        if rest is None:
            next_text = _next_significant(logical, index + 1)
            child = [] if next_text and next_text.startswith("- ") else {}
            parent.value[key] = child
            stack.append(_Container("list" if isinstance(child, list) else "dict", indent, child))
        else:
            parent.value[key] = _parse_scalar(rest)
    if not isinstance(root, dict) or not root:
        raise ProtocolError("INVALID_CONTRACT", "contract root must be a non-empty mapping")
    return root


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _require_keys(obj: dict[str, Any], required: set[str], allowed: set[str], where: str) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise ProtocolError("UNKNOWN_AUTHORITY_FIELD", f"unknown fields in {where}", {"fields": unknown})
    missing = sorted(required - set(obj))
    if missing:
        raise ProtocolError("INVALID_CONTRACT_SHAPE", f"missing fields in {where}", {"fields": missing})


def _non_empty_string(value: Any, where: str, code: str = "INVALID_CONTRACT_SHAPE") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(code, f"{where} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, where: str, min_items: int = 0) -> list[str]:
    if not isinstance(value, list) or len(value) < min_items:
        raise ProtocolError("INVALID_CONTRACT_SHAPE", f"{where} must be a list")
    return [_non_empty_string(item, f"{where}[]") for item in value]


def _check_list(value: Any, where: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ProtocolError("EMPTY_VALIDATION", f"{where} must not be empty")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ProtocolError("INVALID_CONTRACT_SHAPE", f"{where} items must be objects")
        _require_keys(item, {"name", "command"}, {"name", "command", "required"}, where)
        name = _non_empty_string(item["name"], f"{where}.name")
        command = _string_list(item["command"], f"{where}.command", 1)
        normalized = {"name": name, "command": command}
        if "required" in item:
            if not isinstance(item["required"], bool):
                raise ProtocolError("INVALID_CONTRACT_SHAPE", f"{where}.required must be boolean")
            normalized["required"] = item["required"]
        result.append(normalized)
    return result


def normalize_mutation_path(path: Any) -> str:
    raw = _non_empty_string(path, "mutation_targets.path")
    if raw.startswith(("/", "~")) or raw in {".", "./", ""}:
        raise ProtocolError("INVALID_MUTATION_PATH", "mutation target must be a repo-relative file path", {"path": raw})
    if any(char in raw for char in "*?[]{}"):
        raise ProtocolError("INVALID_MUTATION_PATH", "mutation target must not contain glob characters", {"path": raw})
    parts = PurePosixPath(raw).parts
    if ".." in parts or raw.endswith("/"):
        raise ProtocolError("INVALID_MUTATION_PATH", "mutation target must not traverse or name a directory root", {"path": raw})
    normalized = posixpath.normpath(raw)
    if normalized != raw or normalized in {".", "docs", "src", "plugins", ".dev-docs"}:
        raise ProtocolError("INVALID_MUTATION_PATH", "mutation target must be a concrete normalized file path", {"path": raw})
    if normalized == ".git" or normalized.startswith(".git/"):
        raise ProtocolError("INVALID_MUTATION_PATH", "mutation target must not touch .git", {"path": raw})
    if normalized == ".dev-docs/changes" or normalized.startswith(".dev-docs/changes/"):
        raise ProtocolError("INVALID_MUTATION_PATH", "mutation target must not touch .dev-docs/changes", {"path": raw})
    if normalized == ".superpowers/sdd" or normalized.startswith(".superpowers/sdd/"):
        raise ProtocolError("INVALID_MUTATION_PATH", "mutation target must not touch .superpowers/sdd", {"path": raw})
    return normalized


def _validate_intent(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "intent must be an object")
    _require_keys(value, {"goals", "non_goals", "confirmed_answers"}, {"goals", "non_goals", "confirmed_answers"}, "intent")
    answers = value["confirmed_answers"]
    if not isinstance(answers, list):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "confirmed_answers must be a list")
    normalized_answers = []
    for answer in answers:
        if not isinstance(answer, dict):
            raise ProtocolError("INVALID_CONTRACT_SHAPE", "confirmed_answers items must be objects")
        _require_keys(answer, {"question", "answer"}, {"question", "answer"}, "confirmed_answers[]")
        normalized_answers.append({"question": _non_empty_string(answer["question"], "question"), "answer": _non_empty_string(answer["answer"], "answer")})
    return {"goals": _string_list(value["goals"], "intent.goals", 1), "non_goals": _string_list(value["non_goals"], "intent.non_goals"), "confirmed_answers": normalized_answers}


def _validate_design(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "design must be an object")
    fields = {"boundaries", "data_flow", "contracts", "tradeoffs"}
    _require_keys(value, fields, fields, "design")
    return {key: _non_empty_string(value[key], f"design.{key}") for key in sorted(fields)}


def _validate_task(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "task must be an object")
    required = {"id", "name", "owner", "dependencies", "mutation_targets", "handoffs", "checks", "rollback"}
    allowed = required | {"review", "fix_budget", "model", "notes"}
    _require_keys(raw, required, allowed, "tasks[]")
    task_id = str(raw["id"]).strip()
    if not task_id:
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "task id must be non-empty")
    owner = _non_empty_string(raw["owner"], "task.owner", "NO_OWNER_ACCEPTANCE")
    if not isinstance(raw["dependencies"], list):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "dependencies must be a list")
    dependencies = [str(dep).strip() for dep in raw["dependencies"]]
    if any(not dep for dep in dependencies) or len(dependencies) != len(set(dependencies)):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "dependencies must contain unique non-empty ids")
    targets_raw = raw["mutation_targets"]
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "mutation_targets must be non-empty")
    targets = []
    for target in targets_raw:
        if not isinstance(target, dict):
            raise ProtocolError("INVALID_CONTRACT_SHAPE", "mutation_targets items must be objects")
        _require_keys(target, {"path", "mode"}, {"path", "mode", "reason"}, "mutation_targets[]")
        mode = target["mode"]
        if mode not in {"create", "modify", "delete"}:
            raise ProtocolError("INVALID_CONTRACT_SHAPE", "mutation target mode is invalid")
        normalized = {"path": normalize_mutation_path(target["path"]), "mode": mode}
        if "reason" in target:
            normalized["reason"] = _non_empty_string(target["reason"], "mutation_targets.reason")
        targets.append(normalized)
    handoffs_raw = raw["handoffs"]
    if not isinstance(handoffs_raw, dict):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "handoffs must be an object")
    _require_keys(handoffs_raw, {"inputs", "outputs"}, {"inputs", "outputs", "report", "evidence", "review_package"}, "handoffs")
    handoffs = {"inputs": _string_list(handoffs_raw["inputs"], "handoffs.inputs"), "outputs": _string_list(handoffs_raw["outputs"], "handoffs.outputs")}
    for optional in ("report", "review_package"):
        if optional in handoffs_raw:
            handoffs[optional] = _non_empty_string(handoffs_raw[optional], f"handoffs.{optional}")
    if "evidence" in handoffs_raw:
        handoffs["evidence"] = _string_list(handoffs_raw["evidence"], "handoffs.evidence")
    checks_raw = raw["checks"]
    if not isinstance(checks_raw, dict):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "checks must be an object")
    _require_keys(checks_raw, {"focused", "full"}, {"focused", "full"}, "checks")
    task = {
        "id": task_id,
        "name": _non_empty_string(raw["name"], "task.name"),
        "owner": owner,
        "dependencies": dependencies,
        "mutation_targets": targets,
        "handoffs": handoffs,
        "checks": {"focused": _check_list(checks_raw["focused"], "checks.focused"), "full": _check_list(checks_raw["full"], "checks.full")},
        "rollback": _non_empty_string(raw["rollback"], "task.rollback"),
    }
    for optional in ("review", "model", "notes"):
        if optional in raw:
            task[optional] = _non_empty_string(raw[optional], f"task.{optional}")
    if "fix_budget" in raw:
        if not isinstance(raw["fix_budget"], int) or raw["fix_budget"] < 0:
            raise ProtocolError("INVALID_CONTRACT_SHAPE", "fix_budget must be a non-negative integer")
        task["fix_budget"] = raw["fix_budget"]
    return task


def _validate_context_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "context_policy must be an object")
    _require_keys(value, {"required", "jit", "forbidden", "budget"}, {"required", "jit", "forbidden", "budget"}, "context_policy")
    required = []
    if not isinstance(value["required"], list):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "context_policy.required must be a list")
    for item in value["required"]:
        if isinstance(item, str):
            required.append(item.strip())
        elif isinstance(item, dict):
            _require_keys(item, {"id", "reason"}, {"id", "reason"}, "context_policy.required[]")
            required.append({"id": _non_empty_string(item["id"], "required.id"), "reason": _non_empty_string(item["reason"], "required.reason")})
        else:
            raise ProtocolError("INVALID_CONTRACT_SHAPE", "context required item is invalid")
    jit = []
    if not isinstance(value["jit"], list):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "context_policy.jit must be a list")
    for item in value["jit"]:
        if not isinstance(item, dict):
            raise ProtocolError("INVALID_CONTRACT_SHAPE", "jit item must be an object")
        _require_keys(item, {"id", "retrieval_trigger", "budget"}, {"id", "retrieval_trigger", "budget"}, "context_policy.jit[]")
        if not isinstance(item["budget"], int) or item["budget"] < 1:
            raise ProtocolError("INVALID_CONTRACT_SHAPE", "jit budget must be positive")
        jit.append({"id": _non_empty_string(item["id"], "jit.id"), "retrieval_trigger": _non_empty_string(item["retrieval_trigger"], "jit.retrieval_trigger"), "budget": item["budget"]})
    forbidden_allowed = {"full_conversation", "all_docs", "all_source", "raw_logs", "unrelated_tasks", "absolute_paths", "path_traversal", "glob", "broad_directory_roots"}
    forbidden = _string_list(value["forbidden"], "context_policy.forbidden")
    if len(forbidden) != len(set(forbidden)) or any(item not in forbidden_allowed for item in forbidden):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "context_policy.forbidden contains invalid values")
    budget_raw = value["budget"]
    if not isinstance(budget_raw, dict):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "context_policy.budget must be an object")
    _require_keys(budget_raw, {"total"}, {"total", "by_audience"}, "context_policy.budget")
    if not isinstance(budget_raw["total"], int) or budget_raw["total"] < 1:
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "context budget total must be positive")
    budget = {"total": budget_raw["total"]}
    if "by_audience" in budget_raw:
        if not isinstance(budget_raw["by_audience"], dict):
            raise ProtocolError("INVALID_CONTRACT_SHAPE", "by_audience must be an object")
        audiences = {"contract", "worker", "reviewer", "completion", "finish"}
        by_audience = {}
        for key, amount in budget_raw["by_audience"].items():
            if key not in audiences or not isinstance(amount, int) or amount < 1:
                raise ProtocolError("INVALID_CONTRACT_SHAPE", "invalid audience budget")
            by_audience[key] = amount
        budget["by_audience"] = by_audience
    return {"required": required, "jit": jit, "forbidden": forbidden, "budget": budget}


def _validate_migration(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "migration_or_rollout must be an object")
    fields = {"detection", "preview", "opt_in", "verification", "rollback"}
    _require_keys(value, fields, fields, "migration_or_rollout")
    return {key: _non_empty_string(value[key], f"migration_or_rollout.{key}") for key in sorted(fields)}


def _validate_graph(tasks: list[dict[str, Any]]) -> None:
    seen = set()
    for task in tasks:
        if task["id"] in seen:
            raise ProtocolError("DUPLICATE_TASK_ID", "duplicate task id", {"task_id": task["id"]})
        seen.add(task["id"])
    for task in tasks:
        for dep in task["dependencies"]:
            if dep not in seen:
                raise ProtocolError("DANGLING_DEPENDENCY", "dependency does not name an existing task", {"task_id": task["id"], "dependency": dep})
    visiting: set[str] = set()
    visited: set[str] = set()
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


def _validate_handoffs(tasks: list[dict[str, Any]]) -> None:
    produced: dict[str, str] = {}
    ids = {task["id"] for task in tasks}
    for task in tasks:
        for input_name in task["handoffs"]["inputs"]:
            producer = produced.get(input_name)
            if producer is None:
                raise ProtocolError("DANGLING_HANDOFF", "handoff input has no previous output", {"task_id": task["id"], "input": input_name})
            if producer not in task["dependencies"]:
                raise ProtocolError("DANGLING_HANDOFF", "handoff input producer must be a dependency", {"task_id": task["id"], "input": input_name, "producer": producer})
        for output_name in task["handoffs"]["outputs"]:
            if output_name in produced or output_name in ids:
                raise ProtocolError("DANGLING_HANDOFF", "handoff output must be unique and not task id", {"task_id": task["id"], "output": output_name})
            produced[output_name] = task["id"]


def validate_contract(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not data:
        raise ProtocolError("INVALID_CONTRACT", "contract root must be a non-empty object")
    required = {"schema_version", "change_id", "contract_version", "intent", "acceptance", "constraints", "design", "tasks", "context_policy", "validation"}
    allowed = required | {"migration_or_rollout"}
    _require_keys(data, required, allowed, "contract")
    if not isinstance(data["schema_version"], int) or data["schema_version"] < 1:
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "schema_version must be a positive integer")
    tasks_raw = data["tasks"]
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "tasks must be non-empty")
    tasks = [_validate_task(task) for task in tasks_raw]
    validation_raw = data["validation"]
    if not isinstance(validation_raw, dict):
        raise ProtocolError("INVALID_CONTRACT_SHAPE", "validation must be an object")
    _require_keys(validation_raw, {"focused", "full", "change_wide"}, {"focused", "full", "change_wide"}, "validation")
    normalized = {
        "schema_version": data["schema_version"],
        "change_id": _non_empty_string(data["change_id"], "change_id"),
        "contract_version": _non_empty_string(data["contract_version"], "contract_version"),
        "intent": _validate_intent(data["intent"]),
        "acceptance": _string_list(data["acceptance"], "acceptance", 1),
        "constraints": _string_list(data["constraints"], "constraints", 1),
        "design": _validate_design(data["design"]),
        "tasks": tasks,
        "context_policy": _validate_context_policy(data["context_policy"]),
        "validation": {"focused": _check_list(validation_raw["focused"], "validation.focused"), "full": _check_list(validation_raw["full"], "validation.full"), "change_wide": _check_list(validation_raw["change_wide"], "validation.change_wide")},
    }
    if "migration_or_rollout" in data:
        normalized["migration_or_rollout"] = _validate_migration(data["migration_or_rollout"])
    _validate_graph(tasks)
    _validate_handoffs(tasks)
    derive_ownership(normalized)
    return normalized


def load_contract(path: str | Path) -> dict[str, Any]:
    contract_path = Path(path)
    if not contract_path.exists() or not contract_path.is_file():
        raise ProtocolError("INPUT_NOT_FOUND", "contract path must name an existing file", {"path": str(path)})
    data = parse_yaml_subset(contract_path.read_text(encoding="utf-8"))
    return validate_contract(data)


def _handoff_between(previous: dict[str, Any], current: dict[str, Any]) -> str | None:
    previous_outputs = set(previous["handoffs"]["outputs"])
    current_inputs = set(current["handoffs"]["inputs"])
    overlap = sorted(previous_outputs & current_inputs)
    if previous["id"] in current["dependencies"] and overlap:
        return overlap[0]
    return None


def derive_ownership(contract: dict[str, Any]) -> dict[str, Any]:
    path_entries: dict[str, dict[str, Any]] = {}
    task_by_id = {task["id"]: task for task in contract["tasks"]}
    for task in contract["tasks"]:
        for target in task["mutation_targets"]:
            path = target["path"]
            if path not in path_entries:
                path_entries[path] = {"owner_chain": [task["id"]], "modes": [target["mode"]], "incoming_handoff": None, "outgoing_handoff": None}
                continue
            entry = path_entries[path]
            previous_id = entry["owner_chain"][-1]
            previous = task_by_id[previous_id]
            handoff_name = _handoff_between(previous, task)
            if handoff_name is None:
                raise ProtocolError("OWNERSHIP_OVERLAP", "duplicate mutation target requires explicit linear handoff", {"path": path, "previous_owner": previous_id, "next_owner": task["id"]})
            entry["outgoing_handoff"] = {"from": previous_id, "to": task["id"], "artifact": handoff_name}
            entry["incoming_handoff"] = {"from": previous_id, "to": task["id"], "artifact": handoff_name}
            entry["owner_chain"].append(task["id"])
            entry["modes"].append(target["mode"])
    for path, entry in path_entries.items():
        entry["final_owner"] = entry["owner_chain"][-1]
    return {"paths": dict(sorted(path_entries.items()))}


def build_identity(contract: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_json(contract)
    return {"change_id": contract["change_id"], "contract_version": contract["contract_version"], "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def build_task_graph(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"id": task["id"], "dependencies": list(task["dependencies"])} for task in contract["tasks"]]


def build_summary(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval": False,
        "approval_notice": "summary artifact is not an approval and cannot replace fresh Contract Gate approval",
        "change_id": contract["change_id"],
        "contract_version": contract["contract_version"],
        "goals": contract["intent"]["goals"],
        "non_goals": contract["intent"]["non_goals"],
        "acceptance_count": len(contract["acceptance"]),
        "task_graph": build_task_graph(contract),
        "tasks": [
            {
                "id": task["id"],
                "name": task["name"],
                "targets": task["mutation_targets"],
                "checks": task["checks"],
                "rollback": task["rollback"],
            }
            for task in contract["tasks"]
        ],
        "context_budget": contract["context_policy"]["budget"],
        "validation": contract["validation"],
        "migration_or_rollout": contract.get("migration_or_rollout"),
    }


def _ok(payload: dict[str, Any]) -> int:
    sys.stdout.write(canonical_json({"ok": True, **payload}) + "\n")
    return 0


def _err(error: ProtocolError) -> int:
    sys.stderr.write(canonical_json({"ok": False, "code": error.code, "message": error.message, "details": error.details}) + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and derive Nuclio Next contract authority")
    parser.add_argument("command", choices=["validate", "summary", "identity", "ownership", "task-graph"])
    parser.add_argument("contract")
    args = parser.parse_args(argv)
    try:
        contract = load_contract(args.contract)
        if args.command == "validate":
            return _ok({"code": "VALID_CONTRACT", "change_id": contract["change_id"], "contract_version": contract["contract_version"], "task_count": len(contract["tasks"])})
        if args.command == "summary":
            return _ok({"summary": build_summary(contract)})
        if args.command == "identity":
            return _ok({"identity": build_identity(contract)})
        if args.command == "ownership":
            return _ok({"ownership": derive_ownership(contract)})
        if args.command == "task-graph":
            return _ok({"task_graph": build_task_graph(contract)})
        raise ProtocolError("INVALID_COMMAND", "unknown command")
    except ProtocolError as exc:
        return _err(exc)


if __name__ == "__main__":
    raise SystemExit(main())
