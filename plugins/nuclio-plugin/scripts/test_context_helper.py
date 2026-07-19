"""
Context helper tests.

## Contents

- [Fixture builders](#fixture-builders)
- [Validation and fingerprint tests](#validation-and-fingerprint-tests)
- [CLI envelope tests](#cli-envelope-tests)
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "context-helper.py"
VALID_HASH = "a" * 64
OTHER_HASH = "b" * 64


def load_helper():
    spec = importlib.util.spec_from_file_location("context_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stable_entry(**overrides):
    entry = {
        "id": "contract-ref",
        "audience": "contract",
        "mode": "stable",
        "path": "plugins/nuclio-plugin/references/contract.md",
        "reason": "Contract authority details for this change",
        "sha256": VALID_HASH,
        "line_range": {"start": 1, "end": 20},
    }
    entry.update(overrides)
    return entry


def jit_entry(**overrides):
    entry = {
        "id": "worker-interface",
        "audience": "worker",
        "mode": "jit",
        "path": "plugins/nuclio-plugin/scripts/contract-helper.py",
        "reason": "Need declared helper interface for implementation",
        "retrieval_trigger": "Worker needs function signature",
        "budget": 3,
    }
    entry.update(overrides)
    return entry


class ContextHelperTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()

    def write_jsonl(self, entries):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "context.jsonl"
        path.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n", encoding="utf-8")
        return path

    def load(self, entries, budget=5):
        return self.helper.load_context(self.write_jsonl(entries), budget)

    def test_valid_stable_jit_split_and_fingerprint(self):
        entries = self.load([stable_entry(), jit_entry(), stable_entry(id="review-ref", audience="reviewer", sha256=OTHER_HASH)])
        self.assertEqual([e["id"] for e in self.helper.split_entries(entries)["contract"]], ["contract-ref"])
        self.assertEqual([e["id"] for e in self.helper.split_entries(entries)["worker"]], ["worker-interface"])
        self.assertEqual([e["id"] for e in self.helper.split_entries(entries)["reviewer"]], ["review-ref"])
        fp = self.helper.build_fingerprint(entries)
        self.assertRegex(fp["fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(fp["stable_hashes"], {"contract-ref": VALID_HASH, "review-ref": OTHER_HASH})
        self.assertEqual(fp["jit_budget_total"], 3)

    def test_fingerprint_stable_for_input_order(self):
        first = self.helper.build_fingerprint(self.load([stable_entry(), jit_entry()]))["fingerprint"]
        second = self.helper.build_fingerprint(self.load([jit_entry(), stable_entry()]))["fingerprint"]
        self.assertEqual(first, second)
        changed = self.helper.build_fingerprint(self.load([stable_entry(sha256=OTHER_HASH), jit_entry()]))["fingerprint"]
        self.assertNotEqual(first, changed)

    def assert_context_error(self, entries, code, budget=5):
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.load(entries, budget)
        self.assertEqual(ctx.exception.code, code)

    def test_rejects_duplicate_id(self):
        self.assert_context_error([stable_entry(), stable_entry(audience="worker")], "DUPLICATE_CONTEXT_ID")

    def test_rejects_forbidden_context_concepts(self):
        forbidden = [
            stable_entry(reason="full conversation needed"),
            stable_entry(reason="all docs needed"),
            stable_entry(reason="all source needed"),
            stable_entry(reason="raw logs needed"),
            stable_entry(reason="unrelated tasks needed"),
            stable_entry(path="raw/logs/output.txt"),
        ]
        for entry in forbidden:
            self.assert_context_error([entry], "FORBIDDEN_CONTEXT")

    def test_rejects_missing_or_invalid_stable_hash(self):
        missing = stable_entry()
        missing.pop("sha256")
        self.assert_context_error([missing], "INVALID_STABLE_HASH")
        self.assert_context_error([stable_entry(sha256="A" * 64)], "INVALID_STABLE_HASH")
        self.assert_context_error([stable_entry(sha256="abc")], "INVALID_STABLE_HASH")

    def test_rejects_missing_trigger_non_positive_budget_and_over_budget(self):
        missing = jit_entry()
        missing.pop("retrieval_trigger")
        self.assert_context_error([missing], "INVALID_JIT_ENTRY")
        self.assert_context_error([jit_entry(budget=0)], "INVALID_JIT_ENTRY")
        self.assert_context_error([jit_entry(budget=6)], "JIT_BUDGET_EXCEEDED", budget=5)

    def test_rejects_absolute_traversal_glob_broad_and_directory_paths(self):
        for bad_path in ["/tmp/x", "../x", "plugins/**/*.py", "plugins", ".", "./", ".dev-docs", "src", "docs", "plugins/nuclio-plugin/scripts/", "plugins/nuclio-plugin/scripts"]:
            self.assert_context_error([stable_entry(path=bad_path)], "INVALID_CONTEXT_PATH")

    def test_allows_future_concrete_file_path(self):
        future_path = "plugins/nuclio-plugin/scripts/future-context-helper-output.py"
        self.assertFalse((ROOT / future_path).exists())
        entries = self.load([stable_entry(path=future_path)])
        self.assertEqual(entries[0]["path"], future_path)

    def test_rejects_unknown_fields_invalid_audience_and_mode(self):
        self.assert_context_error([stable_entry(extra="nope")], "UNKNOWN_AUTHORITY_FIELD")
        self.assert_context_error([stable_entry(audience="admin")], "INVALID_AUDIENCE")
        self.assert_context_error([stable_entry(mode="raw")], "INVALID_MODE")

    def test_cli_error_envelope(self):
        path = self.write_jsonl([stable_entry(sha256="abc")])
        proc = subprocess.run([sys.executable, str(HELPER), "validate", str(path)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        envelope = json.loads(proc.stderr)
        self.assertEqual(envelope["ok"], False)
        self.assertEqual(envelope["code"], "INVALID_STABLE_HASH")


if __name__ == "__main__":
    unittest.main()
