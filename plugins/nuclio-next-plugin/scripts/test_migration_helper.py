"""
Migration helper tests.

## Contents

- [Fixture builders](#fixture-builders)
- [Detect and preview tests](#detect-and-preview-tests)
- [Apply and atomicity tests](#apply-and-atomicity-tests)
- [CLI tests](#cli-tests)
"""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "plugins" / "nuclio-next-plugin" / "scripts" / "migration-helper.py"
VALID_HASH = "a" * 64
OTHER_HASH = "b" * 64
THIRD_HASH = "c" * 64
APPROVAL = {"approval_id": "migration-approval-1", "approved_at": "2026-07-18T00:00:00Z", "approved_by": "user", "token": "explicit-migration-opt-in"}


def load_helper():
    spec = importlib.util.spec_from_file_location("migration_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_tree_bytes(path):
    result = {}
    for item in sorted(path.rglob("*")):
        if item.is_file():
            result[str(item.relative_to(path))] = item.read_bytes()
    return result


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def context_entry(entry_id="worker-impl", audience="worker", mode="jit", path="plugins/nuclio-next-plugin/scripts/context-helper.py", **overrides):
    entry = {"id": entry_id, "audience": audience, "mode": mode, "path": path, "reason": "Bounded legacy context retained for migration"}
    if mode == "stable":
        entry["sha256"] = overrides.pop("sha256", VALID_HASH)
    else:
        entry["retrieval_trigger"] = overrides.pop("retrieval_trigger", "Need bounded interface details")
        entry["budget"] = overrides.pop("budget", 2)
    entry.update(overrides)
    return {"legacy_version": 1, "entry": entry}


def make_change_root(tempdir):
    root = Path(tempdir) / "repo"
    changes = root / ".dev-docs" / "changes"
    changes.mkdir(parents=True)
    return root, changes / "legacy-alpha", changes / "target-alpha"


def write_complete_legacy(change):
    if change.exists():
        shutil.rmtree(change)
    change.mkdir(parents=True)
    (change / "brief.md").write_text(textwrap.dedent("""
    ---
    legacy_version: 1
    change_id: change-alpha
    contract_version: v1
    ---
    # Goals
    - Ship migrated authority
    - Preserve explicit approvals
    # Non-Goals
    - Do not approve new gates from old files
    # Confirmed Answers
    - Q: Which paths are read? A: Only explicit .dev-docs/changes paths.
    """).strip() + "\n", encoding="utf-8")
    (change / "spec.md").write_text(textwrap.dedent("""
    ---
    legacy_version: 1
    ---
    # Acceptance
    - Contract authority validates after migration
    - Context manifests keep audience and mode
    # Constraints
    - Migration is previewed before apply
    - Legacy bytes remain unchanged
    """).strip() + "\n", encoding="utf-8")
    (change / "design.md").write_text(textwrap.dedent("""
    ---
    legacy_version: 1
    ---
    # Boundaries
    The helper reads only declared legacy change artifacts and writes only target authority on apply.
    # Data Flow
    Legacy Markdown, YAML, JSONL and JSON map into contract, context and state authority.
    # Contracts
    New deterministic helpers validate every generated artifact before publish.
    # Tradeoffs
    Unsupported legacy versions fail closed instead of using defaults.
    """).strip() + "\n", encoding="utf-8")
    (change / "plan.yaml").write_text(textwrap.dedent("""
    legacy_version: 1
    tasks:
      - id: T1
        name: Migrate helper
        owner: worker-a
        dependencies: []
        mutation_targets:
          - path: plugins/nuclio-next-plugin/scripts/generated.py
            mode: create
            reason: Legacy task-owned output
        handoffs:
          inputs: []
          outputs:
            - migrated-helper
          report: .dev-docs/changes/target-alpha/reports/t1.md
          evidence:
            - .dev-docs/changes/target-alpha/evidence/t1.json
        checks:
          focused:
            - name: focused migration
              command:
                - python3
                - -m
                - unittest
          full:
            - name: full migration
              command:
                - python3
                - -m
                - unittest
        rollback: Delete generated.py if migration-created task fails.
    context_policy:
      required:
        - worker-impl
      jit:
        - id: worker-impl-jit
          retrieval_trigger: Need helper interface while migrating
          budget: 2
      forbidden:
        - full_conversation
        - all_docs
      budget:
        total: 10
        by_audience:
          worker: 5
          reviewer: 5
    validation:
      focused:
        - name: focused change
          command:
            - python3
            - -m
            - unittest
      full:
        - name: full change
          command:
            - python3
            - -m
            - unittest
      change_wide:
        - name: change-wide
          command:
            - python3
            - -m
            - unittest
    migration_or_rollout:
      detection: Detect explicit legacy layout.
      preview: Preview field-level conversion.
      opt_in: Require explicit apply metadata.
      verification: Validate with new deterministic helpers.
      rollback: Remove unpublished staging on failure.
    """).strip() + "\n", encoding="utf-8")
    write_jsonl(change / "context" / "implement.jsonl", [context_entry(), context_entry("contract-ref", "contract", "stable", "plugins/nuclio-next-plugin/references/lifecycle.md", sha256=VALID_HASH)])
    write_jsonl(change / "context" / "verify.jsonl", [context_entry("review-ref", "reviewer", "stable", "plugins/nuclio-next-plugin/references/state-protocol.md", sha256=OTHER_HASH)])
    (change / "state.json").write_text(json.dumps({"legacy_version": 1, "status": "contract_pending", "gates": {"contract": {"status": "pending"}, "finish": {"status": "none"}}, "evidence": {"task": ["evidence/task-T1.json"], "review": ["evidence/review-T1.json"], "fold": ["evidence/fold.json"]}}, sort_keys=True) + "\n", encoding="utf-8")
    evidence = change / "evidence"
    evidence.mkdir()
    (evidence / "task-T1.json").write_text(json.dumps({"legacy_version": 1, "kind": "task", "task_id": "T1", "head": "head-1", "evidence_sha256": THIRD_HASH}, sort_keys=True) + "\n", encoding="utf-8")
    (evidence / "review-T1.json").write_text(json.dumps({"legacy_version": 1, "kind": "review", "task_id": "T1", "verdict": "PASS", "review_sha256": OTHER_HASH}, sort_keys=True) + "\n", encoding="utf-8")
    (evidence / "fold.json").write_text(json.dumps({"legacy_version": 1, "kind": "fold", "decision": "defer", "decision_sha256": VALID_HASH}, sort_keys=True) + "\n", encoding="utf-8")


class MigrationHelperTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root, self.legacy, self.target = make_change_root(self.temp.name)
        write_complete_legacy(self.legacy)

    def test_detect_lists_supported_missing_and_evidence_without_writing(self):
        before = read_tree_bytes(self.legacy)
        result = self.helper.detect_legacy(self.legacy, self.target)
        self.assertTrue(result["detected"])
        self.assertEqual(result["versions"]["brief.md"], 1)
        self.assertIn("context/implement.jsonl", result["detected"])
        self.assertIn("evidence/task-T1.json", result["detected"])
        self.assertIn("context/finish.jsonl", result["missing"])
        self.assertEqual(result["unsupported"], [])
        self.assertFalse(self.target.exists())
        self.assertEqual(before, read_tree_bytes(self.legacy))

    def test_preview_maps_fields_validates_new_helpers_and_does_not_write(self):
        before = read_tree_bytes(self.legacy)
        preview = self.helper.preview_migration(self.legacy, self.target)
        self.assertTrue(preview["ready_to_apply"], preview["blockers"])
        self.assertRegex(preview["preview_identity"], r"^[0-9a-f]{64}$")
        fields = {item["target_field"]: item for item in preview["field_mappings"]}
        for field in ["contract.intent.goals", "contract.acceptance", "contract.tasks", "contract.validation", "context.entries", "state.gates.contract", "state.evidence_retained"]:
            self.assertIn(field, fields)
            self.assertEqual(fields[field]["blocker"], None)
            self.assertIn("source_path", fields[field])
            self.assertIn("locator", fields[field])
            self.assertIn("confidence", fields[field])
        self.assertEqual(preview["validation"]["contract"]["code"], "VALID_CONTRACT")
        self.assertEqual(preview["validation"]["context"]["code"], "VALID_CONTEXT")
        self.assertEqual(preview["validation"]["state"]["code"], "VALID_STATE")
        self.assertFalse(self.target.exists())
        self.assertEqual(before, read_tree_bytes(self.legacy))

    def test_missing_ownership_validation_and_context_conflict_block_without_partial_authority(self):
        (self.legacy / "plan.yaml").write_text((self.legacy / "plan.yaml").read_text(encoding="utf-8").replace("    owner: worker-a\n", ""), encoding="utf-8")
        preview = self.helper.preview_migration(self.legacy, self.target)
        self.assertFalse(preview["ready_to_apply"])
        self.assertTrue(any(blocker["code"] == "FIELD_BLOCKED" and blocker["target_field"] == "contract.tasks[].owner" for blocker in preview["blockers"]))
        self.assertFalse(self.target.exists())

        write_complete_legacy(self.legacy)
        text = (self.legacy / "plan.yaml").read_text(encoding="utf-8")
        (self.legacy / "plan.yaml").write_text(text.replace("  change_wide:\n    - name: change-wide\n      command:\n        - python3\n        - -m\n        - unittest\n", ""), encoding="utf-8")
        preview = self.helper.preview_migration(self.legacy, self.target)
        self.assertFalse(preview["ready_to_apply"])
        self.assertTrue(any(blocker["target_field"] == "contract.validation" for blocker in preview["blockers"]))
        self.assertFalse(self.target.exists())

        write_complete_legacy(self.legacy)
        write_jsonl(self.legacy / "context" / "verify.jsonl", [context_entry("worker-impl", "reviewer", "stable", "plugins/nuclio-next-plugin/references/state-protocol.md", sha256=OTHER_HASH)])
        preview = self.helper.preview_migration(self.legacy, self.target)
        self.assertFalse(preview["ready_to_apply"])
        self.assertTrue(any(blocker["target_field"] == "context.entries" and blocker["code"] == "FIELD_BLOCKED" for blocker in preview["blockers"]))
        self.assertFalse(self.target.exists())

    def test_missing_required_authority_returns_field_blockers_without_target_files(self):
        (self.legacy / "spec.md").unlink()
        preview = self.helper.preview_migration(self.legacy, self.target)
        self.assertFalse(preview["ready_to_apply"])
        blockers = [blocker for blocker in preview["blockers"] if blocker["code"] == "FIELD_BLOCKED"]
        self.assertTrue(any(blocker["target"] == "contract.acceptance" and blocker["source"].endswith("/spec.md") and blocker["confidence"] == "none" for blocker in blockers))
        self.assertTrue(any(blocker["target"] == "contract.constraints" and blocker["source"].endswith("/spec.md") and blocker["reason"] for blocker in blockers))
        self.assertEqual(preview["validation"]["state"]["code"], "SKIPPED")
        cli = subprocess.run([sys.executable, str(HELPER), "preview", "--legacy-change-path", str(self.legacy), "--target-change-path", str(self.target)], text=True, capture_output=True)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        cli_preview = json.loads(cli.stdout)["preview"]
        self.assertFalse(cli_preview["ready_to_apply"])
        self.assertTrue(any(blocker["code"] == "FIELD_BLOCKED" and blocker["target"] == "contract.acceptance" for blocker in cli_preview["blockers"]))
        self.assertFalse((self.target / "contract.yaml").exists())
        self.assertFalse((self.target / "context.jsonl").exists())
        self.assertFalse((self.target / "state.json").exists())

    def test_unsupported_version_fails_closed(self):
        (self.legacy / "plan.yaml").write_text((self.legacy / "plan.yaml").read_text(encoding="utf-8").replace("legacy_version: 1", "legacy_version: 9"), encoding="utf-8")
        detect = self.helper.detect_legacy(self.legacy, self.target)
        self.assertIn({"path": "plan.yaml", "version": 9, "reason": "unsupported legacy_version"}, detect["unsupported"])
        preview = self.helper.preview_migration(self.legacy, self.target)
        self.assertFalse(preview["ready_to_apply"])
        self.assertTrue(any(blocker["code"] == "UNSUPPORTED_LEGACY_VERSION" for blocker in preview["blockers"]))
        self.assertFalse(self.target.exists())

    def test_apply_requires_opt_in_identity_metadata_and_preserves_legacy_bytes(self):
        source_before = read_tree_bytes(self.legacy)
        preview = self.helper.preview_migration(self.legacy, self.target)
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.apply_migration(self.legacy, self.target, apply=False, preview_identity=preview["preview_identity"], approval=APPROVAL)
        self.assertEqual(ctx.exception.code, "APPLY_NOT_CONFIRMED")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.apply_migration(self.legacy, self.target, apply=True, preview_identity="0" * 64, approval=APPROVAL)
        self.assertEqual(ctx.exception.code, "STALE_PREVIEW")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.apply_migration(self.legacy, self.target, apply=True, preview_identity=preview["preview_identity"], approval={"approval_id": "x"})
        self.assertEqual(ctx.exception.code, "MISSING_APPROVAL_METADATA")

        applied = self.helper.apply_migration(self.legacy, self.target, apply=True, preview_identity=preview["preview_identity"], approval=APPROVAL)
        self.assertTrue(applied["applied"])
        self.assertEqual(applied["preview_identity"], preview["preview_identity"])
        self.assertEqual(source_before, read_tree_bytes(self.legacy))
        self.assertTrue((self.target / "contract.yaml").is_file())
        self.assertTrue((self.target / "context.jsonl").is_file())
        self.assertTrue((self.target / "state.json").is_file())
        report = json.loads((self.target / "migration-report.json").read_text(encoding="utf-8"))
        self.assertTrue(report["legacy_retained"])
        self.assertEqual(report["apply_identity"], applied["apply_identity"])
        state = json.loads((self.target / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["gates"]["contract"]["status"], "pending")
        self.assertEqual(state["gates"]["finish"]["status"], "none")
        self.assertNotIn("approval_id", state["gates"]["contract"])
        for staging in self.target.parent.glob(".migration-staging-*"):
            self.fail(f"staging path was not cleaned: {staging}")

    def test_target_exists_preview_stale_and_publish_failure_leave_no_partial_authority(self):
        preview = self.helper.preview_migration(self.legacy, self.target)
        self.target.mkdir()
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.apply_migration(self.legacy, self.target, apply=True, preview_identity=preview["preview_identity"], approval=APPROVAL)
        self.assertEqual(ctx.exception.code, "TARGET_EXISTS")
        self.assertEqual(list(self.target.iterdir()), [])
        self.target.rmdir()

        preview = self.helper.preview_migration(self.legacy, self.target)
        (self.legacy / "brief.md").write_text((self.legacy / "brief.md").read_text(encoding="utf-8") + "# Extra\n- Changed after preview\n", encoding="utf-8")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.apply_migration(self.legacy, self.target, apply=True, preview_identity=preview["preview_identity"], approval=APPROVAL)
        self.assertEqual(ctx.exception.code, "STALE_PREVIEW")
        self.assertFalse(self.target.exists())

        write_complete_legacy(self.legacy)
        preview = self.helper.preview_migration(self.legacy, self.target)
        original_write = self.helper._write_staged_files
        def race_empty_target(staging, preview_data, approval, apply_identity):
            original_write(staging, preview_data, approval, apply_identity)
            self.target.mkdir()
        self.helper._write_staged_files = race_empty_target
        try:
            with self.assertRaises(self.helper.ProtocolError) as ctx:
                self.helper.apply_migration(self.legacy, self.target, apply=True, preview_identity=preview["preview_identity"], approval=APPROVAL)
            self.assertEqual(ctx.exception.code, "TARGET_EXISTS")
        finally:
            self.helper._write_staged_files = original_write
        self.assertTrue(self.target.exists())
        self.assertEqual(list(self.target.iterdir()), [])
        self.target.rmdir()
        self.assertEqual([], list(self.target.parent.glob(".migration-staging-*")))

        preview = self.helper.preview_migration(self.legacy, self.target)
        def race_nonempty_target(staging, preview_data, approval, apply_identity):
            original_write(staging, preview_data, approval, apply_identity)
            self.target.mkdir()
            (self.target / "race-owned.txt").write_text("preserve me\n", encoding="utf-8")
        self.helper._write_staged_files = race_nonempty_target
        try:
            with self.assertRaises(self.helper.ProtocolError) as ctx:
                self.helper.apply_migration(self.legacy, self.target, apply=True, preview_identity=preview["preview_identity"], approval=APPROVAL)
            self.assertEqual(ctx.exception.code, "TARGET_EXISTS")
        finally:
            self.helper._write_staged_files = original_write
        self.assertEqual((self.target / "race-owned.txt").read_text(encoding="utf-8"), "preserve me\n")
        shutil.rmtree(self.target)
        self.assertEqual([], list(self.target.parent.glob(".migration-staging-*")))

        preview = self.helper.preview_migration(self.legacy, self.target)
        original_move = self.helper.shutil.move
        def fail_after_first_move(src, dst):
            result = original_move(src, dst)
            if Path(dst).name == "contract.yaml":
                raise OSError("simulated publish failure")
            return result
        self.helper.shutil.move = fail_after_first_move
        try:
            with self.assertRaises(self.helper.ProtocolError) as ctx:
                self.helper.apply_migration(self.legacy, self.target, apply=True, preview_identity=preview["preview_identity"], approval=APPROVAL)
            self.assertEqual(ctx.exception.code, "PUBLISH_FAILED")
        finally:
            self.helper.shutil.move = original_move
        self.assertFalse(self.target.exists())
        self.assertEqual([], list(self.target.parent.glob(".migration-staging-*")))

    def test_cli_detect_preview_apply_and_blocked_preview(self):
        detect = subprocess.run([sys.executable, str(HELPER), "detect", "--legacy-change-path", str(self.legacy), "--target-change-path", str(self.target)], text=True, capture_output=True)
        self.assertEqual(detect.returncode, 0, detect.stderr)
        self.assertTrue(json.loads(detect.stdout)["ok"])
        preview_proc = subprocess.run([sys.executable, str(HELPER), "preview", "--legacy-change-path", str(self.legacy), "--target-change-path", str(self.target)], text=True, capture_output=True)
        self.assertEqual(preview_proc.returncode, 0, preview_proc.stderr)
        preview = json.loads(preview_proc.stdout)["preview"]
        apply_proc = subprocess.run([sys.executable, str(HELPER), "apply", "--legacy-change-path", str(self.legacy), "--target-change-path", str(self.target), "--apply", "--preview-identity", preview["preview_identity"], "--approval-json", json.dumps(APPROVAL)], text=True, capture_output=True)
        self.assertEqual(apply_proc.returncode, 0, apply_proc.stderr)
        self.assertTrue(json.loads(apply_proc.stdout)["result"]["applied"])

        _, incomplete, blocked_target = make_change_root(self.temp.name + "-blocked")
        write_complete_legacy(incomplete)
        (incomplete / "plan.yaml").write_text((incomplete / "plan.yaml").read_text(encoding="utf-8").replace("    owner: worker-a\n", ""), encoding="utf-8")
        blocked = subprocess.run([sys.executable, str(HELPER), "preview", "--legacy-change-path", str(incomplete), "--target-change-path", str(blocked_target)], text=True, capture_output=True)
        self.assertEqual(blocked.returncode, 0, blocked.stderr)
        self.assertFalse(json.loads(blocked.stdout)["preview"]["ready_to_apply"])
        self.assertFalse(blocked_target.exists())


if __name__ == "__main__":
    unittest.main()
