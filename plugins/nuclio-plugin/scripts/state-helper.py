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
import sys


MISSING_FILES_FOR_CHANGE = ("state.json", "plan.yaml", "context/implement.jsonl")


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


def write_json_file(path, data):
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise StateHelperError("failed to write state file", detail=str(exc)) from exc


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
    gates = state.get("gates", {})
    if isinstance(gates, dict):
        gate_summary = copy.deepcopy(gates)
    else:
        gate_summary = {}

    artifacts = state.get("artifacts", {})
    if isinstance(artifacts, dict):
        artifact_summary = copy.deepcopy(artifacts)
    else:
        artifact_summary = {}

    print_json(
        {
            "ok": True,
            "state_path": path_text(state_path),
            "change_path": path_text(change_path),
            "phase": state.get("phase"),
            "status": state.get("status"),
            "current_task": copy.deepcopy(state.get("current_task")),
            "gates": gate_summary,
            "artifacts": artifact_summary,
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
