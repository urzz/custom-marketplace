#!/usr/bin/env python3
"""
Nuclio fail-closed legacy migration helper.

## Contents

- [Protocol errors and helper loading](#protocol-errors-and-helper-loading)
- [Stable JSON, hashes and path validation](#stable-json-hashes-and-path-validation)
- [Legacy parsing](#legacy-parsing)
- [Authority builders](#authority-builders)
- [Detect, preview and apply](#detect-preview-and-apply)
- [CLI](#cli)

The helper provides explicit detect, preview and apply commands for legacy
`.dev-docs/changes/*` authority. Detect and preview are read-only. Apply requires
an explicit `--apply` flag, a fresh preview identity and user approval metadata;
it stages every generated authority artifact, validates the staged contract,
context and state with the new deterministic helpers, then atomically publishes
without overwriting legacy bytes or synthesizing Gate approval.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

SUPPORTED_LEGACY_VERSION = 1
KNOWN_LEGACY_FILES = (
    "brief.md",
    "spec.md",
    "design.md",
    "plan.yaml",
    "context/implement.jsonl",
    "context/verify.jsonl",
    "context/finish.jsonl",
    "state.json",
)
REQUIRED_PREVIEW_FILES = ("brief.md", "spec.md", "design.md", "plan.yaml", "context/implement.jsonl", "context/verify.jsonl", "state.json")
REQUIRED_PREVIEW_FIELD_TARGETS = {
    "brief.md": ("contract.output_language", "contract.intent.goals", "contract.intent.confirmed_answers"),
    "spec.md": ("contract.acceptance", "contract.constraints"),
    "design.md": ("contract.design",),
    "plan.yaml": ("contract.tasks", "contract.validation", "contract.migration_or_rollout"),
    "context/implement.jsonl": ("context.entries",),
    "context/verify.jsonl": ("context.entries",),
    "state.json": ("state.gates.contract", "state.gates.finish"),
}
HASH_CHARS = set("0123456789abcdef")


class ProtocolError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _load_helper(filename: str, module_name: str) -> Any:
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ProtocolError("HELPER_LOAD_FAILED", "helper module could not be loaded", {"path": str(path)})
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract_helper = _load_helper("contract-helper.py", "nuclio_next_contract_helper")
context_helper = _load_helper("context-helper.py", "nuclio_next_context_helper")
state_helper = _load_helper("state-helper.py", "nuclio_next_state_helper")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in HASH_CHARS for ch in value)


def _repo_relative_change_path(path: Path) -> str:
    parts = path.resolve().parts
    for index in range(len(parts) - 2):
        if parts[index] == ".dev-docs" and parts[index + 1] == "changes":
            rel = "/".join(parts[index:])
            if len(parts) > index + 2:
                return rel
    raise ProtocolError("INVALID_CHANGE_PATH", "path must be inside .dev-docs/changes", {"path": str(path)})


def _validate_change_paths(legacy_change_path: str | Path, target_change_path: str | Path) -> tuple[Path, Path]:
    legacy = Path(legacy_change_path).resolve()
    target = Path(target_change_path).resolve()
    _repo_relative_change_path(legacy)
    _repo_relative_change_path(target)
    if not legacy.exists() or not legacy.is_dir():
        raise ProtocolError("INPUT_NOT_FOUND", "legacy change path must name an existing directory", {"legacy_change_path": str(legacy)})
    try:
        target.relative_to(legacy)
        overlaps = True
    except ValueError:
        overlaps = False
    try:
        legacy.relative_to(target)
        overlaps = True
    except ValueError:
        pass
    if overlaps:
        raise ProtocolError("OVERLAPPING_CHANGE_PATHS", "target change path must not overlap legacy source", {"legacy_change_path": str(legacy), "target_change_path": str(target)})
    return legacy, target


def _source_path(legacy: Path, relpath: str) -> str:
    return f"{_repo_relative_change_path(legacy)}/{relpath}"


def _target_path(target: Path, relpath: str) -> str:
    return f"{_repo_relative_change_path(target)}/{relpath}"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError("INVALID_LEGACY_ENCODING", "legacy file must be UTF-8 text", {"path": str(path)}) from exc


def _load_json(path: Path) -> Any:
    try:
        return json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise ProtocolError("INVALID_LEGACY_JSON", "legacy JSON file is invalid", {"path": str(path)}) from exc


def _load_jsonl(path: Path) -> list[Any]:
    rows = []
    for line_number, line in enumerate(_read_text(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ProtocolError("INVALID_LEGACY_JSONL", "legacy JSONL line is invalid", {"path": str(path), "line": line_number}) from exc
    return rows


def _coerce_legacy_version(value: Any, relpath: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("UNSUPPORTED_LEGACY_VERSION", "legacy_version must be an integer", {"path": relpath, "value": value}) from exc


def _frontmatter_and_body(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        raise ProtocolError("INVALID_LEGACY_MARKDOWN", "frontmatter is not closed")
    raw = text[4:end].strip()
    body = text[text.find("\n", end + 1) + 1 :]
    if not raw:
        return {}, body
    try:
        parsed = contract_helper.parse_yaml_subset(raw)
    except Exception as exc:
        code = getattr(exc, "code", "INVALID_LEGACY_MARKDOWN")
        raise ProtocolError(code, "legacy Markdown frontmatter is invalid", {"message": str(exc)}) from exc
    return parsed, body


def _markdown_sections(path: Path) -> tuple[dict[str, Any], dict[str, list[str]]]:
    frontmatter, body = _frontmatter_and_body(_read_text(path))
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            current = stripped.lstrip("#").strip().lower().replace("-", "_").replace(" ", "_")
            sections.setdefault(current, [])
            continue
        if current is None or not stripped:
            continue
        if stripped.startswith("- "):
            sections.setdefault(current, []).append(stripped[2:].strip())
        else:
            sections.setdefault(current, []).append(stripped)
    return frontmatter, sections


def _legacy_version_for(path: Path, relpath: str) -> int | None:
    if not path.exists():
        return None
    if relpath.endswith(".md"):
        frontmatter, _ = _frontmatter_and_body(_read_text(path))
        return _coerce_legacy_version(frontmatter.get("legacy_version", SUPPORTED_LEGACY_VERSION), relpath)
    if relpath.endswith(".yaml"):
        data = contract_helper.parse_yaml_subset(_read_text(path))
        return _coerce_legacy_version(data.get("legacy_version", SUPPORTED_LEGACY_VERSION), relpath)
    if relpath.endswith(".jsonl"):
        rows = _load_jsonl(path)
        versions = {_coerce_legacy_version(row.get("legacy_version", SUPPORTED_LEGACY_VERSION), relpath) for row in rows if isinstance(row, dict)}
        if len(versions) > 1:
            raise ProtocolError("UNSUPPORTED_LEGACY_VERSION", "legacy JSONL contains mixed versions", {"path": relpath, "versions": sorted(versions)})
        return next(iter(versions), SUPPORTED_LEGACY_VERSION)
    if relpath.endswith(".json"):
        data = _load_json(path)
        return _coerce_legacy_version(data.get("legacy_version", SUPPORTED_LEGACY_VERSION), relpath) if isinstance(data, dict) else SUPPORTED_LEGACY_VERSION
    return SUPPORTED_LEGACY_VERSION


def _field_mapping(legacy: Path, relpath: str, locator: str, target_field: str, confidence: str = "high", blocker: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"source_path": _source_path(legacy, relpath), "locator": locator, "target_field": target_field, "confidence": confidence, "blocker": blocker}


def _blocker(target_field: str, source_path: str, locator: str, reason: str, code: str = "FIELD_BLOCKED", confidence: str = "none") -> dict[str, Any]:
    return {"code": code, "target_field": target_field, "target": target_field, "source_path": source_path, "source": source_path, "locator": locator, "confidence": confidence, "reason": reason}


def _missing_required_blockers(legacy: Path, relpath: str) -> list[dict[str, Any]]:
    targets = REQUIRED_PREVIEW_FIELD_TARGETS.get(relpath, (relpath,))
    return [_blocker(target, _source_path(legacy, relpath), "exists", "required legacy authority file is missing") for target in targets]


def _string_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def _parse_confirmed_answers(items: list[str]) -> list[dict[str, str]]:
    answers = []
    for item in items:
        text = item.strip()
        if text.startswith("Q:") and " A:" in text:
            question, answer = text[2:].split(" A:", 1)
            answers.append({"question": question.strip(), "answer": answer.strip()})
        elif "?" in text:
            question, answer = text.split("?", 1)
            answers.append({"question": question.strip() + "?", "answer": answer.strip()})
        else:
            answers.append({"question": "legacy confirmed answer", "answer": text})
    return answers


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _yaml_dump(value: Any, indent: int = 0) -> str:
    space = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                if item == []:
                    lines.append(f"{space}{key}: []")
                elif item == {}:
                    lines.append(f"{space}{key}: {{}}")
                else:
                    lines.append(f"{space}{key}:")
                    lines.append(_yaml_dump(item, indent + 2))
            else:
                lines.append(f"{space}{key}: {_yaml_dump(item, 0).strip()}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return f"{space}[]"
        lines = []
        for item in value:
            if isinstance(item, dict):
                keys = list(item.keys())
                first = keys[0]
                first_value = item[first]
                if isinstance(first_value, (dict, list)) and first_value not in ([], {}):
                    lines.append(f"{space}- {first}:")
                    lines.append(_yaml_dump(first_value, indent + 4))
                else:
                    lines.append(f"{space}- {first}: {_yaml_dump(first_value, 0).strip()}")
                for key in keys[1:]:
                    sub = item[key]
                    if isinstance(sub, (dict, list)) and sub not in ([], {}):
                        lines.append(f"{space}  {key}:")
                        lines.append(_yaml_dump(sub, indent + 4))
                    else:
                        lines.append(f"{space}  {key}: {_yaml_dump(sub, 0).strip()}")
            elif isinstance(item, list):
                lines.append(f"{space}-")
                lines.append(_yaml_dump(item, indent + 2))
            else:
                lines.append(f"{space}- {_yaml_dump(item, 0).strip()}")
        return "\n".join(lines)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    return _yaml_quote(str(value))


def _contract_to_yaml(contract: dict[str, Any]) -> str:
    return _yaml_dump(contract) + "\n"


def _source_hashes(legacy: Path) -> dict[str, str]:
    hashes = {}
    for item in sorted(legacy.rglob("*")):
        if item.is_file():
            rel = str(item.relative_to(legacy)).replace(os.sep, "/")
            hashes[rel] = sha256_bytes(item.read_bytes())
    return hashes


def _empty_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "change_id": "",
        "contract_version": "",
        "output_language": "",
        "intent": {"goals": [], "non_goals": [], "confirmed_answers": []},
        "acceptance": [],
        "constraints": [],
        "design": {"boundaries": "", "data_flow": "", "contracts": "", "tradeoffs": ""},
        "tasks": [],
        "context_policy": {},
        "validation": {},
        "migration_or_rollout": {},
    }


def _section_data_or_blocked(legacy: Path, relpath: str, blockers: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, list[str]]]:
    path = legacy / relpath
    if not path.exists():
        return {}, {}
    try:
        return _markdown_sections(path)
    except ProtocolError as exc:
        blockers.append(_blocker(REQUIRED_PREVIEW_FIELD_TARGETS.get(relpath, (relpath,))[0], _source_path(legacy, relpath), "parse", exc.message, exc.code))
    return {}, {}


def _plan_data_or_blocked(legacy: Path, blockers: list[dict[str, Any]]) -> dict[str, Any]:
    path = legacy / "plan.yaml"
    if not path.exists():
        return {}
    try:
        plan = contract_helper.parse_yaml_subset(_read_text(path))
    except ProtocolError as exc:
        blockers.append(_blocker("contract.tasks", _source_path(legacy, "plan.yaml"), "parse", exc.message, exc.code))
        return {}
    except Exception as exc:
        blockers.append(_blocker("contract.tasks", _source_path(legacy, "plan.yaml"), "parse", str(exc)))
        return {}
    if not isinstance(plan, dict):
        blockers.append(_blocker("contract.tasks", _source_path(legacy, "plan.yaml"), "parse", "plan must be an object"))
        return {}
    return plan


def _normalize_context_rows(legacy: Path, relpaths: list[str], mappings: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = []
    seen: dict[str, dict[str, Any]] = {}
    for relpath in relpaths:
        path = legacy / relpath
        if not path.exists():
            continue
        try:
            rows = _load_jsonl(path)
        except ProtocolError as exc:
            blockers.append(_blocker("context.entries", _source_path(legacy, relpath), "jsonl", exc.message, exc.code))
            continue
        for line_number, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                blockers.append(_blocker("context.entries", _source_path(legacy, relpath), f"line:{line_number}", "context row must be an object"))
                continue
            try:
                version = _coerce_legacy_version(row.get("legacy_version", SUPPORTED_LEGACY_VERSION), relpath)
            except ProtocolError as exc:
                blockers.append(_blocker("context.entries", _source_path(legacy, relpath), f"line:{line_number}.legacy_version", exc.message, exc.code))
                continue
            if version != SUPPORTED_LEGACY_VERSION:
                blockers.append(_blocker("context.entries", _source_path(legacy, relpath), f"line:{line_number}", "unsupported legacy_version", "UNSUPPORTED_LEGACY_VERSION"))
                continue
            entry = copy.deepcopy(row.get("entry", row))
            entry.pop("legacy_version", None)
            if not isinstance(entry, dict):
                blockers.append(_blocker("context.entries", _source_path(legacy, relpath), f"line:{line_number}", "context entry must be an object"))
                continue
            entry_id = str(entry.get("id", ""))
            if entry_id in seen and seen[entry_id] != entry:
                blockers.append(_blocker("context.entries", _source_path(legacy, relpath), f"line:{line_number}", "context identity conflicts with another manifest"))
                continue
            if entry_id not in seen:
                seen[entry_id] = entry
                entries.append(entry)
    mappings.append(_field_mapping(legacy, "context/implement.jsonl", "jsonl:entry", "context.entries", "high"))
    return entries


def _task_graph_for_state(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    graph = []
    for task in tasks:
        ownership = [target["path"] for target in task.get("mutation_targets", [])]
        graph.append({"id": str(task.get("id")), "owner": task.get("owner", ""), "dependencies": list(task.get("dependencies", [])), "ownership": ownership, "packet_sha256": sha256_value({"migration_packet_placeholder": str(task.get("id")), "ownership": ownership})})
    return graph


def _state_from_identities(change_id: str, contract_id: dict[str, Any], context_id: dict[str, Any], task_graph: list[dict[str, Any]], facts: dict[str, Any]) -> dict[str, Any]:
    tasks = []
    budgets: dict[str, dict[str, int]] = {}
    for index, task in enumerate(task_graph):
        tasks.append({"id": task["id"], "status": "ready" if index == 0 and not task["dependencies"] else "pending", "ownership": task["ownership"], "packet_sha256": task["packet_sha256"]})
        budgets.setdefault(task["owner"], {"maximum": 2, "used": 0, "remaining": 2})
    metadata = {"tasks": task_graph, "context_fingerprint": context_id["fingerprint"], "contract_sha256": contract_id["sha256"], "legacy_migration": {"legacy_retained": True, "facts": facts}}
    state = {
        "schema_version": 1,
        "state_version": 1,
        "change_id": change_id,
        "status": "contract_pending",
        "contract": contract_id,
        "context": context_id,
        "gates": {"contract": {"status": "pending", "artifact_sha256": contract_id["sha256"], "context_fingerprint": context_id["fingerprint"], "state_version": 1}, "finish": {"status": "none"}},
        "tasks": tasks,
        "blockers": [],
        "fix_budgets": dict(sorted(budgets.items())),
        "history": [{"event": "INITIALIZED", "from": None, "to": "contract_pending", "state_version": 1, "artifact_sha256": contract_id["sha256"], "reason": canonical_json(metadata)}],
        "legacy_evidence": {"retained": True, "facts": facts},
    }
    state_helper.validate_state_shape(state)
    return state


def _load_evidence_facts(legacy: Path) -> tuple[dict[str, Any], list[str]]:
    facts = {"tasks": [], "reviews": [], "fold_decisions": []}
    unmigrated = []
    evidence_dir = legacy / "evidence"
    if not evidence_dir.exists():
        return facts, unmigrated
    for path in sorted(evidence_dir.glob("*.json")):
        rel = str(path.relative_to(legacy)).replace(os.sep, "/")
        data = _load_json(path)
        if not isinstance(data, dict):
            unmigrated.append(rel)
            continue
        kind = data.get("kind")
        if kind == "task":
            facts["tasks"].append({key: data[key] for key in ("task_id", "head", "evidence_sha256") if key in data})
        elif kind == "review":
            facts["reviews"].append({key: data[key] for key in ("task_id", "verdict", "review_sha256") if key in data})
        elif kind == "fold":
            facts["fold_decisions"].append({key: data[key] for key in ("decision", "decision_sha256") if key in data})
        else:
            unmigrated.append(rel)
    return facts, unmigrated


def _build_preview(legacy: Path, target: Path) -> dict[str, Any]:
    mappings: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    detect = detect_legacy(legacy, target)
    for item in detect["unsupported"]:
        for target_field in REQUIRED_PREVIEW_FIELD_TARGETS.get(item["path"], (item["path"],)):
            blockers.append(_blocker(target_field, _source_path(legacy, item["path"]), "legacy_version", item["reason"], "UNSUPPORTED_LEGACY_VERSION"))
    for relpath in REQUIRED_PREVIEW_FILES:
        if relpath in detect["missing"]:
            blockers.extend(_missing_required_blockers(legacy, relpath))

    brief_front, brief = _section_data_or_blocked(legacy, "brief.md", blockers)
    spec_front, spec = _section_data_or_blocked(legacy, "spec.md", blockers)
    _, design_sections = _section_data_or_blocked(legacy, "design.md", blockers)
    plan = _plan_data_or_blocked(legacy, blockers)

    try:
        unsupported_frontmatter = _coerce_legacy_version(brief_front.get("legacy_version", SUPPORTED_LEGACY_VERSION), "brief.md") != SUPPORTED_LEGACY_VERSION or _coerce_legacy_version(spec_front.get("legacy_version", SUPPORTED_LEGACY_VERSION), "spec.md") != SUPPORTED_LEGACY_VERSION
    except ProtocolError as exc:
        unsupported_frontmatter = True
        blockers.append(_blocker("contract.schema_version", _source_path(legacy, exc.details.get("path", "brief.md")), "frontmatter.legacy_version", exc.message, exc.code))
    if unsupported_frontmatter:
        blockers.append(_blocker("contract.schema_version", _source_path(legacy, "brief.md"), "frontmatter.legacy_version", "unsupported legacy_version", "UNSUPPORTED_LEGACY_VERSION"))

    output_language_sources = []
    for relpath, frontmatter in (("brief.md", brief_front), ("spec.md", spec_front)):
        if "output_language" not in frontmatter:
            continue
        candidate = frontmatter.get("output_language")
        if not isinstance(candidate, str) or not candidate:
            blockers.append(_blocker("contract.output_language", _source_path(legacy, relpath), "frontmatter.output_language", "required explicit legacy output_language authority is empty"))
            continue
        if candidate != candidate.strip():
            blockers.append(_blocker("contract.output_language", _source_path(legacy, relpath), "frontmatter.output_language", "output_language must not contain leading or trailing whitespace", "INVALID_OUTPUT_LANGUAGE"))
            continue
        try:
            output_language_sources.append((relpath, contract_helper._output_language(candidate)))
        except Exception as exc:
            blockers.append(_blocker("contract.output_language", _source_path(legacy, relpath), "frontmatter.output_language", getattr(exc, "message", str(exc)), getattr(exc, "code", "INVALID_OUTPUT_LANGUAGE")))
    output_language_values = {value for _, value in output_language_sources}
    if not output_language_sources:
        blockers.append(_blocker("contract.output_language", _source_path(legacy, "brief.md"), "frontmatter.output_language", "required explicit legacy output_language authority is missing"))
        output_language = ""
    elif len(output_language_values) > 1:
        blockers.append(_blocker("contract.output_language", _source_path(legacy, "brief.md"), "frontmatter.output_language", "conflicting explicit legacy output_language authorities", "FIELD_BLOCKED", "conflict"))
        output_language = ""
    else:
        output_language = next(iter(output_language_values))
    mappings.append(_field_mapping(legacy, output_language_sources[0][0] if output_language_sources else "brief.md", "frontmatter.output_language", "contract.output_language"))

    goals = _string_list(brief.get("goals", []))
    non_goals = _string_list(brief.get("non_goals", []))
    answers = _parse_confirmed_answers(_string_list(brief.get("confirmed_answers", [])))
    acceptance = _string_list(spec.get("acceptance", []))
    constraints = _string_list(spec.get("constraints", []))
    for field, value, relpath, locator in (
        ("contract.intent.goals", goals, "brief.md", "# Goals"),
        ("contract.acceptance", acceptance, "spec.md", "# Acceptance"),
        ("contract.constraints", constraints, "spec.md", "# Constraints"),
    ):
        if not value:
            blockers.append(_blocker(field, _source_path(legacy, relpath), locator, "required field cannot be determined"))
    mappings.extend([
        _field_mapping(legacy, "brief.md", "# Goals", "contract.intent.goals"),
        _field_mapping(legacy, "brief.md", "# Non-Goals", "contract.intent.non_goals"),
        _field_mapping(legacy, "brief.md", "# Confirmed Answers", "contract.intent.confirmed_answers"),
        _field_mapping(legacy, "spec.md", "# Acceptance", "contract.acceptance"),
        _field_mapping(legacy, "spec.md", "# Constraints", "contract.constraints"),
    ])

    design = {
        "boundaries": "\n".join(_string_list(design_sections.get("boundaries", []))),
        "data_flow": "\n".join(_string_list(design_sections.get("data_flow", []))),
        "contracts": "\n".join(_string_list(design_sections.get("contracts", []))),
        "tradeoffs": "\n".join(_string_list(design_sections.get("tradeoffs", []))),
    }
    for key, value in design.items():
        if not value:
            blockers.append(_blocker(f"contract.design.{key}", _source_path(legacy, "design.md"), f"# {key.replace('_', ' ').title()}", "design field cannot be determined"))
    mappings.append(_field_mapping(legacy, "design.md", "# Boundaries/# Data Flow/# Contracts/# Tradeoffs", "contract.design"))

    tasks = plan.get("tasks") if isinstance(plan, dict) else None
    if not isinstance(tasks, list) or not tasks:
        blockers.append(_blocker("contract.tasks", _source_path(legacy, "plan.yaml"), "tasks", "tasks cannot be determined"))
        tasks = []
    else:
        for task in tasks:
            if not isinstance(task, dict):
                blockers.append(_blocker("contract.tasks", _source_path(legacy, "plan.yaml"), "tasks[]", "task must be an object"))
                continue
            if not task.get("owner"):
                blockers.append(_blocker("contract.tasks[].owner", _source_path(legacy, "plan.yaml"), f"tasks[{task.get('id', '?')}].owner", "task owner cannot be determined"))
            if not task.get("mutation_targets"):
                blockers.append(_blocker("contract.tasks[].mutation_targets", _source_path(legacy, "plan.yaml"), f"tasks[{task.get('id', '?')}].mutation_targets", "mutation targets cannot be determined"))
            if not task.get("rollback"):
                blockers.append(_blocker("contract.tasks[].rollback", _source_path(legacy, "plan.yaml"), f"tasks[{task.get('id', '?')}].rollback", "rollback cannot be determined"))
    mappings.extend([
        _field_mapping(legacy, "plan.yaml", "tasks", "contract.tasks"),
        _field_mapping(legacy, "plan.yaml", "tasks[].dependencies", "contract.tasks[].dependencies"),
        _field_mapping(legacy, "plan.yaml", "tasks[].mutation_targets", "contract.tasks[].mutation_targets"),
        _field_mapping(legacy, "plan.yaml", "tasks[].handoffs", "contract.tasks[].handoffs"),
        _field_mapping(legacy, "plan.yaml", "tasks[].checks", "contract.tasks[].checks"),
        _field_mapping(legacy, "plan.yaml", "tasks[].rollback", "contract.tasks[].rollback"),
    ])

    validation = plan.get("validation") if isinstance(plan, dict) else None
    if not isinstance(validation, dict) or not all(key in validation for key in ("focused", "full", "change_wide")):
        blockers.append(_blocker("contract.validation", _source_path(legacy, "plan.yaml"), "validation", "focused/full/change_wide validation cannot be determined"))
    mappings.append(_field_mapping(legacy, "plan.yaml", "validation", "contract.validation"))

    context_policy = plan.get("context_policy", {}) if isinstance(plan, dict) else {}
    migration_or_rollout = plan.get("migration_or_rollout", {}) if isinstance(plan, dict) else {}
    contract = _empty_contract()
    contract.update({
        "change_id": str(brief_front.get("change_id", legacy.name)),
        "contract_version": str(brief_front.get("contract_version", "v1")),
        "output_language": output_language if isinstance(output_language, str) else "",
        "intent": {"goals": goals, "non_goals": non_goals, "confirmed_answers": answers},
        "acceptance": acceptance,
        "constraints": constraints,
        "design": design,
        "tasks": tasks,
        "context_policy": context_policy,
        "validation": validation or {},
        "migration_or_rollout": migration_or_rollout,
    })

    context_entries = _normalize_context_rows(legacy, ["context/implement.jsonl", "context/verify.jsonl", "context/finish.jsonl"], mappings, blockers)
    evidence_facts, unmigrated = _load_evidence_facts(legacy)
    mappings.extend([
        _field_mapping(legacy, "state.json", "gates.contract/status", "state.gates.contract"),
        _field_mapping(legacy, "state.json", "gates.finish/status", "state.gates.finish"),
        _field_mapping(legacy, "evidence", "*.json", "state.evidence_retained", "medium"),
    ])

    validation_result: dict[str, Any] = {}
    normalized_contract = None
    normalized_context = None
    proposed_state = None
    contract_yaml = _contract_to_yaml(contract)
    try:
        normalized_contract = contract_helper.validate_contract(contract_helper.parse_yaml_subset(contract_yaml))
        contract_identity = contract_helper.build_identity(normalized_contract)
        validation_result["contract"] = {"code": "VALID_CONTRACT", "sha256": contract_identity["sha256"]}
    except Exception as exc:
        blockers.append(_blocker("contract", _source_path(legacy, "plan.yaml"), "contract", getattr(exc, "message", str(exc)), getattr(exc, "code", "FIELD_BLOCKED")))
        validation_result["contract"] = {"code": getattr(exc, "code", "INVALID_CONTRACT"), "message": getattr(exc, "message", str(exc))}

    try:
        normalized_context = context_helper.validate_entries(context_entries, int(context_policy.get("budget", {}).get("total", 1000000)) if isinstance(context_policy, dict) else 1000000)
        context_fp = context_helper.build_fingerprint(normalized_context)
        validation_result["context"] = {"code": "VALID_CONTEXT", "fingerprint": context_fp["fingerprint"], "entry_count": context_fp["entry_count"]}
    except Exception as exc:
        blockers.append(_blocker("context.entries", _source_path(legacy, "context/implement.jsonl"), "jsonl", getattr(exc, "message", str(exc)), getattr(exc, "code", "FIELD_BLOCKED")))
        validation_result["context"] = {"code": getattr(exc, "code", "INVALID_CONTEXT"), "message": getattr(exc, "message", str(exc))}

    if normalized_contract is not None and normalized_context is not None:
        contract_id = {"path": _target_path(target, "contract.yaml"), "sha256": contract_helper.build_identity(normalized_contract)["sha256"], "version": normalized_contract["contract_version"], "change_id": normalized_contract["change_id"]}
        context_fingerprint = context_helper.build_fingerprint(normalized_context)
        context_id = {"path": _target_path(target, "context.jsonl"), "fingerprint": context_fingerprint["fingerprint"], "entries": [entry["id"] for entry in context_helper.sorted_entries(normalized_context)]}
        try:
            proposed_state = _state_from_identities(normalized_contract["change_id"], contract_id, context_id, _task_graph_for_state(normalized_contract["tasks"]), evidence_facts)
            validation_result["state"] = {"code": "VALID_STATE", "state_version": proposed_state["state_version"]}
        except Exception as exc:
            blockers.append(_blocker("state", _source_path(legacy, "state.json"), "state", getattr(exc, "message", str(exc)), getattr(exc, "code", "FIELD_BLOCKED")))
            validation_result["state"] = {"code": getattr(exc, "code", "INVALID_STATE"), "message": getattr(exc, "message", str(exc))}
    else:
        validation_result.setdefault("state", {"code": "SKIPPED", "message": "contract/context validation did not pass"})

    artifacts = {"contract_yaml": contract_yaml, "context_jsonl": "".join(canonical_json(entry) + "\n" for entry in context_helper.sorted_entries(normalized_context or context_entries)), "state_json": canonical_json(proposed_state) + "\n" if proposed_state is not None else ""}
    source_hashes = _source_hashes(legacy)
    identity_body = {"schema_version": 1, "source_hashes": source_hashes, "target_path": _repo_relative_change_path(target), "artifacts": artifacts, "blockers": blockers}
    preview_identity = sha256_value(identity_body)
    return {
        "schema_version": 1,
        "legacy_change_path": _repo_relative_change_path(legacy),
        "target_change_path": _repo_relative_change_path(target),
        "ready_to_apply": not blockers and proposed_state is not None,
        "preview_identity": preview_identity,
        "source_hashes": source_hashes,
        "target_paths": {"contract": _target_path(target, "contract.yaml"), "context": _target_path(target, "context.jsonl"), "state": _target_path(target, "state.json"), "migration_report": _target_path(target, "migration-report.json")},
        "field_mappings": mappings,
        "blockers": blockers,
        "validation": validation_result,
        "unmigrated_items": sorted(unmigrated),
        "evidence_facts": evidence_facts,
        "artifacts": artifacts,
    }


def detect_legacy(legacy_change_path: str | Path, target_change_path: str | Path) -> dict[str, Any]:
    legacy, target = _validate_change_paths(legacy_change_path, target_change_path)
    detected = []
    missing = []
    versions: dict[str, int] = {}
    unsupported = []
    for relpath in KNOWN_LEGACY_FILES:
        path = legacy / relpath
        if not path.exists():
            missing.append(relpath)
            continue
        detected.append(relpath)
        try:
            version = _legacy_version_for(path, relpath)
        except ProtocolError as exc:
            unsupported.append({"path": relpath, "version": None, "reason": exc.message})
            continue
        versions[relpath] = version or SUPPORTED_LEGACY_VERSION
        if versions[relpath] != SUPPORTED_LEGACY_VERSION:
            unsupported.append({"path": relpath, "version": versions[relpath], "reason": "unsupported legacy_version"})
    evidence_dir = legacy / "evidence"
    if evidence_dir.exists():
        for path in sorted(evidence_dir.glob("*.json")):
            relpath = str(path.relative_to(legacy)).replace(os.sep, "/")
            detected.append(relpath)
            try:
                version = _legacy_version_for(path, relpath)
            except ProtocolError as exc:
                unsupported.append({"path": relpath, "version": None, "reason": exc.message})
                continue
            versions[relpath] = version or SUPPORTED_LEGACY_VERSION
            if versions[relpath] != SUPPORTED_LEGACY_VERSION:
                unsupported.append({"path": relpath, "version": versions[relpath], "reason": "unsupported legacy_version"})
    else:
        missing.append("evidence/")
    return {"schema_version": 1, "legacy_change_path": _repo_relative_change_path(legacy), "target_change_path": _repo_relative_change_path(target), "detected": detected, "missing": missing, "unsupported": unsupported, "versions": versions}


def preview_migration(legacy_change_path: str | Path, target_change_path: str | Path) -> dict[str, Any]:
    legacy, target = _validate_change_paths(legacy_change_path, target_change_path)
    preview = _build_preview(legacy, target)
    public = dict(preview)
    public.pop("artifacts", None)
    return public


def _require_approval(approval: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(approval, dict):
        raise ProtocolError("MISSING_APPROVAL_METADATA", "approval metadata must be a JSON object")
    required = {"approval_id", "approved_at", "approved_by", "token"}
    missing = sorted(key for key in required if not isinstance(approval.get(key), str) or not approval.get(key, "").strip())
    if missing:
        raise ProtocolError("MISSING_APPROVAL_METADATA", "approval metadata is incomplete", {"fields": missing})
    return {key: approval[key].strip() if isinstance(approval[key], str) else approval[key] for key in approval}


def _copy_file_no_replace(source: Path, destination: Path, helper_owned: list[Path]) -> None:
    try:
        with source.open("rb") as src:
            try:
                with destination.open("xb") as dst:
                    shutil.copyfileobj(src, dst)
                    dst.flush()
                    os.fsync(dst.fileno())
            except FileExistsError as exc:
                raise ProtocolError("TARGET_EXISTS", "target artifact already exists; refusing to overwrite", {"target_path": str(destination)}) from exc
            except Exception as exc:
                if destination.exists() and destination.is_file():
                    try:
                        destination.unlink()
                    except OSError:
                        pass
                raise ProtocolError("PUBLISH_FAILED", "target artifact publish failed", {"target_path": str(destination), "message": str(exc)}) from exc
        helper_owned.append(destination)
        source.unlink()
    except ProtocolError:
        raise
    except Exception as exc:
        raise ProtocolError("PUBLISH_FAILED", "target artifact publish failed", {"target_path": str(destination), "message": str(exc)}) from exc


def _publish_staging_without_replace(staging: Path, target: Path) -> None:
    try:
        target.mkdir()
    except FileExistsError as exc:
        raise ProtocolError("TARGET_EXISTS", "target change path already exists; refusing to overwrite", {"target_change_path": str(target)}) from exc
    except Exception as exc:
        raise ProtocolError("PUBLISH_FAILED", "target reservation failed", {"message": str(exc)}) from exc
    helper_owned: list[Path] = []
    try:
        for item in sorted(staging.iterdir()):
            if not item.is_file():
                raise ProtocolError("PUBLISH_FAILED", "staging contains a non-file artifact", {"path": str(item)})
            _copy_file_no_replace(item, target / item.name, helper_owned)
        staging.rmdir()
    except ProtocolError:
        for item in reversed(helper_owned):
            if item.exists():
                item.unlink()
        try:
            target.rmdir()
        except OSError:
            pass
        raise
    except Exception as exc:
        for item in reversed(helper_owned):
            if item.exists():
                item.unlink()
        try:
            target.rmdir()
        except OSError:
            pass
        raise ProtocolError("PUBLISH_FAILED", "atomic migration publish failed", {"message": str(exc)}) from exc


def _write_staged_files(staging: Path, preview: dict[str, Any], approval: dict[str, Any], apply_identity: str) -> None:
    staging.mkdir(parents=True, exist_ok=False)
    artifacts = preview["artifacts"]
    (staging / "contract.yaml").write_text(artifacts["contract_yaml"], encoding="utf-8")
    (staging / "context.jsonl").write_text(artifacts["context_jsonl"], encoding="utf-8")
    (staging / "state.json").write_text(artifacts["state_json"], encoding="utf-8")
    contract = contract_helper.load_contract(staging / "contract.yaml")
    context = context_helper.load_context(staging / "context.jsonl")
    state = state_helper.load_state(staging / "state.json")
    state_helper.validate_state_shape(state)
    report = {
        "schema_version": 1,
        "legacy_change_path": preview["legacy_change_path"],
        "target_change_path": preview["target_change_path"],
        "preview_identity": preview["preview_identity"],
        "apply_identity": apply_identity,
        "approval_metadata": approval,
        "source_hashes": preview["source_hashes"],
        "target_hashes": {
            "contract.yaml": sha256_bytes((staging / "contract.yaml").read_bytes()),
            "context.jsonl": sha256_bytes((staging / "context.jsonl").read_bytes()),
            "state.json": sha256_bytes((staging / "state.json").read_bytes()),
        },
        "field_mappings": preview["field_mappings"],
        "blockers": preview["blockers"],
        "unmigrated_items": preview["unmigrated_items"],
        "evidence_facts": preview["evidence_facts"],
        "legacy_retained": True,
        "validated": {"contract_sha256": contract_helper.build_identity(contract)["sha256"], "context_fingerprint": context_helper.build_fingerprint(context)["fingerprint"], "state_version": state["state_version"]},
        "notice": "migration approval authorizes this explicit conversion only; it is not Contract Gate or Finish Gate approval",
    }
    (staging / "migration-report.json").write_text(canonical_json(report) + "\n", encoding="utf-8")


def apply_migration(legacy_change_path: str | Path, target_change_path: str | Path, apply: bool, preview_identity: str, approval: dict[str, Any]) -> dict[str, Any]:
    legacy, target = _validate_change_paths(legacy_change_path, target_change_path)
    if not apply:
        raise ProtocolError("APPLY_NOT_CONFIRMED", "apply requires explicit --apply")
    if not _is_sha(preview_identity):
        raise ProtocolError("STALE_PREVIEW", "preview identity must be a lowercase sha256")
    approval = _require_approval(approval)
    if target.exists():
        raise ProtocolError("TARGET_EXISTS", "target change path already exists; refusing to overwrite", {"target_change_path": str(target)})
    preview = _build_preview(legacy, target)
    if preview["preview_identity"] != preview_identity:
        raise ProtocolError("STALE_PREVIEW", "preview identity does not match current legacy source", {"expected": preview["preview_identity"], "actual": preview_identity})
    if not preview["ready_to_apply"]:
        raise ProtocolError("PREVIEW_BLOCKED", "preview has blockers and cannot be applied", {"blockers": preview["blockers"]})
    apply_identity = sha256_value({"preview_identity": preview_identity, "approval_metadata": approval, "target_change_path": _repo_relative_change_path(target)})
    staging = target.parent / f".migration-staging-{apply_identity}"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        _write_staged_files(staging, preview, approval, apply_identity)
        _publish_staging_without_replace(staging, target)
    except ProtocolError:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging)
        raise ProtocolError("PUBLISH_FAILED", "atomic migration publish failed", {"message": str(exc)}) from exc
    report = json.loads((target / "migration-report.json").read_text(encoding="utf-8"))
    return {"schema_version": 1, "applied": True, "legacy_change_path": _repo_relative_change_path(legacy), "target_change_path": _repo_relative_change_path(target), "preview_identity": preview_identity, "apply_identity": apply_identity, "target_hashes": report["target_hashes"], "legacy_retained": True}


def _json_arg(value: str, where: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProtocolError("INVALID_JSON_ARGUMENT", f"{where} is not valid JSON") from exc


def _ok(payload: dict[str, Any]) -> int:
    sys.stdout.write(canonical_json({"ok": True, **payload}) + "\n")
    return 0


def _err(error: ProtocolError) -> int:
    sys.stderr.write(canonical_json({"ok": False, "code": error.code, "message": error.message, "details": error.details}) + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect, preview and explicitly apply Nuclio legacy change migrations")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("detect", "preview", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--legacy-change-path", required=True)
        p.add_argument("--target-change-path", required=True)
        if name == "apply":
            p.add_argument("--apply", action="store_true")
            p.add_argument("--preview-identity", required=True)
            p.add_argument("--approval-json", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "detect":
            return _ok({"detect": detect_legacy(args.legacy_change_path, args.target_change_path)})
        if args.command == "preview":
            return _ok({"preview": preview_migration(args.legacy_change_path, args.target_change_path)})
        if args.command == "apply":
            return _ok({"result": apply_migration(args.legacy_change_path, args.target_change_path, args.apply, args.preview_identity, _json_arg(args.approval_json, "approval"))})
        raise ProtocolError("INVALID_COMMAND", "unknown command")
    except ProtocolError as exc:
        return _err(exc)


if __name__ == "__main__":
    raise SystemExit(main())
