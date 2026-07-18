#!/usr/bin/env python3
"""
Nuclio Next deterministic context helper.

## Contents

- [Protocol errors](#protocol-errors)
- [Path and entry validation](#path-and-entry-validation)
- [Fingerprint and split derivation](#fingerprint-and-split-derivation)
- [CLI](#cli)
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


AUDIENCES = ("contract", "worker", "reviewer", "completion", "finish")
ALLOWED_FIELDS = {"id", "audience", "mode", "path", "reason", "sha256", "line_range", "retrieval_trigger", "budget"}
FORBIDDEN_PHRASES = (
    "full conversation",
    "chat history",
    "raw transcript",
    "all docs",
    "all documentation",
    "all source",
    "entire repository",
    "whole repository",
    "raw logs",
    "terminal scrollback",
    "unrelated tasks",
)
BROAD_PATHS = {".", "./", "", "docs", "src", "plugins", ".dev-docs", "references", "scripts", "raw/logs"}
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class ProtocolError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _non_empty_string(value: Any, where: str, code: str = "INVALID_CONTEXT_ENTRY") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(code, f"{where} must be a non-empty string")
    return value.strip()


def normalize_context_path(value: Any) -> str:
    raw = _non_empty_string(value, "path", "INVALID_CONTEXT_PATH")
    lowered = raw.lower()
    if raw.startswith(("/", "~")) or raw in BROAD_PATHS:
        raise ProtocolError("INVALID_CONTEXT_PATH", "context path must be bounded and repo-relative", {"path": raw})
    if any(char in raw for char in "*?[]{}"):
        raise ProtocolError("INVALID_CONTEXT_PATH", "context path must not contain glob characters", {"path": raw})
    parts = PurePosixPath(raw).parts
    if ".." in parts or raw.endswith("/"):
        raise ProtocolError("INVALID_CONTEXT_PATH", "context path must not traverse or name a broad directory", {"path": raw})
    normalized = posixpath.normpath(raw)
    if normalized != raw or normalized in BROAD_PATHS:
        raise ProtocolError("INVALID_CONTEXT_PATH", "context path must be normalized and concrete", {"path": raw})
    if lowered in {"all docs", "all source", "full conversation", "raw logs", "unrelated tasks"} or lowered.startswith("raw/logs/"):
        raise ProtocolError("FORBIDDEN_CONTEXT", "context path names a forbidden concept", {"path": raw})
    return normalized


def _reject_forbidden_text(*values: Any) -> None:
    for value in values:
        if not isinstance(value, str):
            continue
        lowered = value.lower().replace("_", " ").replace("-", " ")
        for phrase in FORBIDDEN_PHRASES:
            if phrase in lowered:
                raise ProtocolError("FORBIDDEN_CONTEXT", "context entry includes a forbidden reason/path concept", {"phrase": phrase})


def _validate_line_range(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_CONTEXT_ENTRY", "line_range must be an object")
    unknown = sorted(set(value) - {"start", "end"})
    if unknown:
        raise ProtocolError("UNKNOWN_AUTHORITY_FIELD", "unknown line_range fields", {"fields": unknown})
    if set(value) != {"start", "end"}:
        raise ProtocolError("INVALID_CONTEXT_ENTRY", "line_range requires start and end")
    start = value["start"]
    end = value["end"]
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < 1 or end < start:
        raise ProtocolError("INVALID_CONTEXT_ENTRY", "line_range must use positive ordered integers")
    return {"start": start, "end": end}


def validate_entry(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        raise ProtocolError("INVALID_CONTEXT_ENTRY", "context line must be a non-empty object")
    unknown = sorted(set(raw) - ALLOWED_FIELDS)
    if unknown:
        raise ProtocolError("UNKNOWN_AUTHORITY_FIELD", "unknown context authority fields", {"fields": unknown})
    required = {"id", "audience", "mode", "path", "reason"}
    missing = sorted(required - set(raw))
    if missing:
        raise ProtocolError("INVALID_CONTEXT_ENTRY", "missing context fields", {"fields": missing})
    entry_id = _non_empty_string(raw["id"], "id")
    audience = raw["audience"]
    if audience not in AUDIENCES:
        raise ProtocolError("INVALID_AUDIENCE", "invalid context audience", {"audience": audience})
    mode = raw["mode"]
    if mode not in {"stable", "jit"}:
        raise ProtocolError("INVALID_MODE", "invalid context mode", {"mode": mode})
    path = normalize_context_path(raw["path"])
    reason = _non_empty_string(raw["reason"], "reason")
    _reject_forbidden_text(entry_id, path, reason)
    normalized: dict[str, Any] = {"id": entry_id, "audience": audience, "mode": mode, "path": path, "reason": reason}
    if "line_range" in raw:
        normalized["line_range"] = _validate_line_range(raw["line_range"])
    if mode == "stable":
        if "retrieval_trigger" in raw or "budget" in raw:
            raise ProtocolError("INVALID_STABLE_HASH", "stable entries must not carry jit fields")
        sha = raw.get("sha256")
        if not isinstance(sha, str) or not HASH_RE.fullmatch(sha):
            raise ProtocolError("INVALID_STABLE_HASH", "stable entries require a 64-character lowercase sha256")
        normalized["sha256"] = sha
    if mode == "jit":
        if "sha256" in raw:
            raise ProtocolError("INVALID_JIT_ENTRY", "jit entries must not carry stable sha256")
        trigger = _non_empty_string(raw.get("retrieval_trigger"), "retrieval_trigger", "INVALID_JIT_ENTRY")
        budget = raw.get("budget")
        if not isinstance(budget, int) or budget < 1:
            raise ProtocolError("INVALID_JIT_ENTRY", "jit entries require a positive integer budget")
        _reject_forbidden_text(trigger)
        normalized["retrieval_trigger"] = trigger
        normalized["budget"] = budget
    return normalized


def validate_entries(entries: list[Any], jit_budget_limit: int = 1000000) -> list[dict[str, Any]]:
    if not isinstance(jit_budget_limit, int) or jit_budget_limit < 1:
        raise ProtocolError("INVALID_BUDGET_LIMIT", "jit budget limit must be a positive integer")
    normalized = []
    seen = set()
    jit_total = 0
    for raw in entries:
        entry = validate_entry(raw)
        if entry["id"] in seen:
            raise ProtocolError("DUPLICATE_CONTEXT_ID", "duplicate context id", {"id": entry["id"]})
        seen.add(entry["id"])
        if entry["mode"] == "jit":
            jit_total += entry["budget"]
        normalized.append(entry)
    if jit_total > jit_budget_limit:
        raise ProtocolError("JIT_BUDGET_EXCEEDED", "total jit budget exceeds context policy limit", {"total": jit_total, "limit": jit_budget_limit})
    return normalized


def load_context(path: str | Path, jit_budget_limit: int = 1000000) -> list[dict[str, Any]]:
    context_path = Path(path)
    if not context_path.exists() or not context_path.is_file():
        raise ProtocolError("INPUT_NOT_FOUND", "context path must name an existing file", {"path": str(path)})
    entries = []
    for line_number, line in enumerate(context_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ProtocolError("INVALID_JSONL", "context line is not valid JSON", {"line": line_number}) from exc
    return validate_entries(entries, jit_budget_limit)


def sorted_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=lambda item: (item["audience"], item["id"], item["path"], item["mode"]))


def build_fingerprint(entries: list[dict[str, Any]]) -> dict[str, Any]:
    canonical_entries = sorted_entries(entries)
    canonical = canonical_json(canonical_entries)
    stable_hashes = {entry["id"]: entry["sha256"] for entry in canonical_entries if entry["mode"] == "stable"}
    jit_total = sum(entry["budget"] for entry in canonical_entries if entry["mode"] == "jit")
    return {
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "entry_count": len(canonical_entries),
        "stable_hashes": dict(sorted(stable_hashes.items())),
        "jit_budget_total": jit_total,
    }


def split_entries(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    split = {audience: [] for audience in AUDIENCES}
    for entry in sorted_entries(entries):
        split[entry["audience"]].append(entry)
    return split


def _ok(payload: dict[str, Any]) -> int:
    sys.stdout.write(canonical_json({"ok": True, **payload}) + "\n")
    return 0


def _err(error: ProtocolError) -> int:
    sys.stderr.write(canonical_json({"ok": False, "code": error.code, "message": error.message, "details": error.details}) + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and fingerprint Nuclio Next context JSONL")
    parser.add_argument("command", choices=["validate", "fingerprint", "split"])
    parser.add_argument("context")
    parser.add_argument("--jit-budget-limit", type=int, default=1000000)
    args = parser.parse_args(argv)
    try:
        entries = load_context(args.context, args.jit_budget_limit)
        if args.command == "validate":
            fp = build_fingerprint(entries)
            return _ok({"code": "VALID_CONTEXT", "entry_count": len(entries), "jit_budget_total": fp["jit_budget_total"]})
        if args.command == "fingerprint":
            return _ok({"context": build_fingerprint(entries)})
        if args.command == "split":
            return _ok({"split": split_entries(entries)})
        raise ProtocolError("INVALID_COMMAND", "unknown command")
    except ProtocolError as exc:
        return _err(exc)


if __name__ == "__main__":
    raise SystemExit(main())
