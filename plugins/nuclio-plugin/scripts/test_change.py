"""Focused behavior tests for the Nuclio v3 thin Runtime."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).with_name("change.py")
sys.path.insert(0, str(SCRIPT.parent))
import change  # noqa: E402


def run(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--project-root", str(root), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def output(result):
    return json.loads(result.stdout if result.stdout else result.stderr)


class ChangeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        git(self.root, "init")
        git(self.root, "config", "user.email", "nuclio@example.invalid")
        git(self.root, "config", "user.name", "Nuclio Test")
        (self.root / "README.md").write_text("# Test\n", encoding="utf-8")
        (self.root / ".dev-docs" / "changes" / "archive").mkdir(parents=True)
        git(self.root, "add", "README.md", ".dev-docs")
        git(self.root, "commit", "-m", "chore: initial")

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        result = run(self.root, "create", "--id", "alpha-change", "--title", "Alpha", "--goal", "Ship alpha", "--acceptance", "Alpha is observable")
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.root / ".dev-docs" / "changes" / "alpha-change"

    def approve(self):
        result = run(self.root, "approve", "--id", "alpha-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        return output(result)

    def finish_sections(self, directory):
        change = directory / "change.md"
        change.write_text(change.read_text(encoding="utf-8") + "\n## Outcome\n\nAlpha shipped.\n\n## Validation\n\nFocused check passed.\n\n## Knowledge Updates\n\nNO_OP\n\n## Residual Risks\n\nNone.\n", encoding="utf-8")

    def test_help_exposes_exactly_seven_commands(self):
        result = run(self.root, "--help")
        self.assertEqual(result.returncode, 0)
        for command in ("create", "approve", "status", "record-check", "verify", "complete", "archive"):
            self.assertIn(command, result.stdout)
        for removed in ("plan", "task", "repair", "supersede", "legacy-move"):
            self.assertNotIn(removed, result.stdout)

    def test_record_check_never_executes_argv_and_current_evidence_completes(self):
        directory = self.create()
        self.approve()
        marker = self.root / "executed"
        current = git(self.root, "rev-parse", "HEAD")
        # Define a check after approval; delivery changes are Agent-owned and do not need a new approval.
        delivery = directory / "delivery.yaml"
        delivery.write_text("""schema_version: 1
change_id: alpha-change
milestones:
  - id: M1
    kind: delivery
    outcome: Ship alpha
    covers: [AC-1]
    status: done
    handoff: null
verification:
  checks:
    - id: focused
      run: [python3, -c, \"open('executed', 'w')\"]
      covers: [AC-1]
""", encoding="utf-8")
        self.assertEqual(output(run(self.root, "status", "--id", "alpha-change"))["next_action"], "run-required-checks")
        record = run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "host reported pass", "--", "python3", "-c", "open('executed', 'w')")
        self.assertEqual(record.returncode, 0, record.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(output(run(self.root, "status", "--id", "alpha-change"))["next_action"], "verify")
        verified = run(self.root, "verify", "--id", "alpha-change")
        self.assertTrue(output(verified)["verified"], verified.stderr)
        self.finish_sections(directory)
        complete = run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP")
        self.assertEqual(complete.returncode, 0, complete.stderr)
        state_path = directory / "state.yaml"
        terminal_state = state_path.read_bytes()
        repeated = run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "repeat", "--", "python3", "-c", "open('executed', 'w')")
        self.assertEqual(output(repeated)["code"], "CHANGE_COMPLETE")
        self.assertEqual(state_path.read_bytes(), terminal_state)
        change_path = directory / "change.md"
        change_path.write_text(change_path.read_text(encoding="utf-8").replace("Ship alpha", "Forged alpha"), encoding="utf-8")
        self.assertEqual(output(run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "repeat", "--", "python3", "-c", "open('executed', 'w')"))["code"], "CONTRACT_DRIFT")
        self.assertEqual(output(run(self.root, "verify", "--id", "alpha-change"))["code"], "CONTRACT_DRIFT")

    def test_head_and_definition_drift_invalidate_evidence(self):
        directory = self.create()
        self.approve()
        current = git(self.root, "rev-parse", "HEAD")
        delivery = directory / "delivery.yaml"
        delivery.write_text("""schema_version: 1
change_id: alpha-change
milestones:
  - id: M1
    kind: delivery
    outcome: Ship alpha
    covers: [AC-1]
    status: done
    handoff: null
verification:
  checks:
    - id: focused
      run: [python3, -m, unittest]
      covers: [AC-1]
""", encoding="utf-8")
        self.assertEqual(run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "pass", "--", "python3", "-m", "unittest").returncode, 0)
        delivery.write_text(delivery.read_text(encoding="utf-8").replace("unittest]", "unittest, discover]"), encoding="utf-8")
        verified = run(self.root, "verify", "--id", "alpha-change")
        self.assertFalse(output(verified)["verified"])
        self.assertEqual(output(verified)["missing_checks"], ["focused"])

    def test_complete_rejects_delivery_definition_drift_after_verify(self):
        directory = self.create()
        self.approve()
        current = git(self.root, "rev-parse", "HEAD")
        delivery = directory / "delivery.yaml"
        delivery.write_text("""schema_version: 1
change_id: alpha-change
milestones:
  - id: M1
    kind: delivery
    outcome: Ship alpha
    covers: [AC-1]
    status: done
    handoff: null
verification:
  checks:
    - id: focused
      run: [python3, -m, unittest]
      covers: [AC-1]
""", encoding="utf-8")
        self.assertEqual(run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "pass", "--", "python3", "-m", "unittest").returncode, 0)
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change"))["verified"])
        delivery.write_text(delivery.read_text(encoding="utf-8").replace("unittest]", "unittest, discover]"), encoding="utf-8")
        self.finish_sections(directory)
        complete = run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP")
        self.assertNotEqual(complete.returncode, 0)
        self.assertEqual(output(complete)["code"], "VERIFICATION_NOT_CURRENT")

    def test_archive_rejects_forged_knowledge_path_without_staging_readme(self):
        directory = self.create()
        state = directory / "state.yaml"
        data = state.read_text(encoding="utf-8").replace("  paths: []", "  paths:\n  - README.md")
        state.write_text(data, encoding="utf-8")
        (self.root / "README.md").write_text("unrelated\n", encoding="utf-8")
        archive = run(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(archive.returncode, 0)
        self.assertEqual(output(archive)["code"], "INVALID_KNOWLEDGE_PATH")
        self.assertNotIn("README.md", git(self.root, "diff", "--cached", "--name-only"))

    def test_revision_only_reapproval_preserves_base_head(self):
        directory = self.create()
        first = self.approve()
        base = first["base_head"]
        change_path = directory / "change.md"
        change_path.write_text(change_path.read_text(encoding="utf-8").replace("revision: 1", "revision: 2"), encoding="utf-8")
        second = self.approve()
        self.assertEqual(second["base_head"], base)
        self.assertNotEqual(second["approval_head"], first["approval_head"])
        state = change.load_state(self.root, "alpha-change")
        self.assertEqual(state["verification"], {"checks": [], "acceptance": {"AC-1": "missing"}, "manual": [], "review": None})
        self.assertEqual(set(git(self.root, "show", "--format=", "--name-only", "HEAD").splitlines()), {".dev-docs/changes/alpha-change/change.md", ".dev-docs/changes/alpha-change/state.yaml"})

    def test_approval_commit_failure_restores_state(self):
        self.create()
        state_path = self.root / ".dev-docs" / "changes" / "alpha-change" / "state.yaml"
        original = state_path.read_bytes()
        real_git = change.git
        def fail_commit(root, *args, **kwargs):
            if args[:1] == ("commit",):
                raise change.NuclioError("GIT_ERROR", "simulated commit failure")
            return real_git(root, *args, **kwargs)
        args = change.build_parser().parse_args(["approve", "--id", "alpha-change"])
        with mock.patch.object(change, "git", side_effect=fail_commit), mock.patch.object(change, "write_state", wraps=change.write_state) as write_state:
            with self.assertRaises(change.NuclioError):
                change.cmd_approve(args, self.root)
        self.assertGreaterEqual(write_state.call_count, 2)
        self.assertEqual(state_path.read_bytes(), original)
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")

    def test_v2_active_is_rejected_and_old_archive_is_not_parsed(self):
        directory = self.root / ".dev-docs" / "changes" / "old-change"
        directory.mkdir()
        (directory / "plan.yaml").write_text("schema_version: 2\n", encoding="utf-8")
        result = run(self.root, "status", "--id", "old-change")
        self.assertEqual(output(result)["code"], "V2_ACTIVE_UNSUPPORTED")
        old_archive = self.root / ".dev-docs" / "changes" / "archive" / "old-change"
        old_archive.mkdir()
        (old_archive / "change.md").write_text("old record\n", encoding="utf-8")
        archive = run(self.root, "archive", "--id", "old-change")
        self.assertNotEqual(archive.returncode, 0)
        self.assertEqual((old_archive / "change.md").read_text(encoding="utf-8"), "old record\n")

    def test_archive_succeeds_from_active_complete_change(self):
        directory = self.create()
        self.approve()
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", '{"acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'))["verified"])
        self.finish_sections(directory)
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        archived = output(run(self.root, "archive", "--id", "alpha-change"))
        target = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        self.assertFalse(directory.exists())
        self.assertEqual(sorted(path.name for path in target.iterdir()), ["change.md", "delivery.yaml", "state.yaml"])
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "archive(alpha-change): retain complete change record")
        self.assertEqual(archived["path"], ".dev-docs/changes/archive/alpha-change")

    def test_archive_recovers_after_move_and_is_idempotent(self):
        directory = self.create()
        self.approve()
        current = git(self.root, "rev-parse", "HEAD")
        delivery = directory / "delivery.yaml"
        delivery.write_text("""schema_version: 1
change_id: alpha-change
milestones:
  - id: M1
    kind: delivery
    outcome: Ship alpha
    covers: [AC-1]
    status: done
    handoff: null
verification:
  checks:
    - id: focused
      run: [python3, -m, unittest]
      covers: [AC-1]
""", encoding="utf-8")
        self.assertEqual(run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "pass", "--", "python3", "-m", "unittest").returncode, 0)
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change"))["verified"])
        self.finish_sections(directory)
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        target = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        shutil.move(directory, target)
        recovered = run(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertTrue(output(recovered)["recovered"])
        second = run(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(output(second)["recovered"])

    def test_archive_recovery_rejects_contract_and_delivery_tampering(self):
        directory = self.create()
        self.approve()
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", '{"acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'))["verified"])
        self.finish_sections(directory)
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        target = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        shutil.move(directory, target)
        change_path = target / "change.md"
        original_change = change_path.read_text(encoding="utf-8")
        change_path.write_text(original_change.replace("Ship alpha", "Forged alpha"), encoding="utf-8")
        contract = run(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(output(contract)["code"], "CONTRACT_DRIFT")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "approve(alpha-change): confirm revision 1")
        change_path.write_text(original_change, encoding="utf-8")
        delivery = target / "delivery.yaml"
        delivery.write_text(delivery.read_text(encoding="utf-8").replace("AC-1", "AC-2"), encoding="utf-8")
        malformed = run(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(malformed.returncode, 0)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "approve(alpha-change): confirm revision 1")

    def test_applied_complete_allows_only_recorded_knowledge_during_reverify(self):
        directory = self.create()
        self.approve()
        delivery = directory / "delivery.yaml"
        delivery.write_text("""schema_version: 1
change_id: alpha-change
milestones:
  - id: M1
    kind: delivery
    outcome: Ship alpha
    covers: [AC-1]
    status: done
    handoff: null
verification:
  checks:
    - id: focused
      run: [python3, -m, unittest]
      covers: [AC-1]
""", encoding="utf-8")
        current = git(self.root, "rev-parse", "HEAD")
        self.assertEqual(run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "pass", "--", "python3", "-m", "unittest").returncode, 0)
        manual = '{"acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", manual))["verified"])
        self.finish_sections(directory)
        knowledge = self.root / ".dev-docs" / "knowledge" / "alpha.md"
        knowledge.parent.mkdir(parents=True, exist_ok=True)
        knowledge.write_text("# Alpha\n", encoding="utf-8")
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "APPLIED", "--knowledge-path", ".dev-docs/knowledge/alpha.md").returncode, 0)
        (self.root / "README.md").write_text("# New head\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "feat: move head")
        current = git(self.root, "rev-parse", "HEAD")
        recorded = run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "pass", "--", "python3", "-m", "unittest")
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.assertEqual(change.load_state(self.root, "alpha-change")["phase"], "build")
        verified = run(self.root, "verify", "--id", "alpha-change", "--manual", manual)
        self.assertTrue(output(verified)["verified"], verified.stderr)
        extra = self.root / "unrelated.txt"
        extra.write_text("dirty\n", encoding="utf-8")
        blocked = run(self.root, "verify", "--id", "alpha-change", "--manual", manual)
        self.assertEqual(output(blocked)["code"], "DIRTY_PRODUCT_WORKTREE")
        self.assertEqual(output(blocked)["details"]["paths"], ["unrelated.txt"])

    def test_complete_rejects_removed_check_until_verify_cleans_stale_record(self):
        directory = self.create()
        self.approve()
        current = git(self.root, "rev-parse", "HEAD")
        delivery = directory / "delivery.yaml"
        delivery.write_text("""schema_version: 1
change_id: alpha-change
milestones:
  - id: M1
    kind: delivery
    outcome: Ship alpha
    covers: [AC-1]
    status: done
    handoff: null
verification:
  checks:
    - id: focused
      run: [python3, -m, unittest]
      covers: [AC-1]
""", encoding="utf-8")
        self.assertEqual(run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "pass", "--", "python3", "-m", "unittest").returncode, 0)
        manual = '{"acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", manual))["verified"])
        self.finish_sections(directory)
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        delivery.write_text(delivery.read_text(encoding="utf-8").replace("  checks:\n    - id: focused\n      run: [python3, -m, unittest]\n      covers: [AC-1]", "  checks: []"), encoding="utf-8")
        (self.root / "README.md").write_text("# New head\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "feat: move head after check removal")
        status = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(status["stale_checks"], ["focused"])
        self.assertEqual(status["next_action"], "verify")
        state_path = directory / "state.yaml"
        stale_state = state_path.read_bytes()
        self.assertEqual(output(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP"))["code"], "VERIFICATION_NOT_CURRENT")
        self.assertEqual(state_path.read_bytes(), stale_state)
        self.assertEqual(output(run(self.root, "archive", "--id", "alpha-change"))["code"], "CHANGE_NOT_COMPLETE")
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", manual))["verified"])
        self.assertEqual(change.load_state(self.root, "alpha-change")["verification"]["checks"], [])
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)

    def test_archive_recovery_rejects_changed_check_definition(self):
        self._assert_archive_rejects_changed_check_definition(moved=True)

    def test_archive_rejects_changed_check_definition_before_move(self):
        self._assert_archive_rejects_changed_check_definition(moved=False)

    def _assert_archive_rejects_changed_check_definition(self, *, moved):
        directory = self.create()
        self.approve()
        current = git(self.root, "rev-parse", "HEAD")
        delivery = directory / "delivery.yaml"
        delivery.write_text("""schema_version: 1
change_id: alpha-change
milestones:
  - id: M1
    kind: delivery
    outcome: Ship alpha
    covers: [AC-1]
    status: done
    handoff: null
verification:
  checks:
    - id: focused
      run: [python3, -m, unittest]
      covers: [AC-1]
""", encoding="utf-8")
        self.assertEqual(run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "pass", "--", "python3", "-m", "unittest").returncode, 0)
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change"))["verified"])
        self.finish_sections(directory)
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        if moved:
            target = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
            shutil.move(directory, target)
            delivery = target / "delivery.yaml"
        delivery.write_text(delivery.read_text(encoding="utf-8").replace("[python3, -m, unittest]", "[python3, -m, unittest, discover]"), encoding="utf-8")
        archived = run(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(output(archived)["code"], "VERIFICATION_NOT_CURRENT")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "approve(alpha-change): confirm revision 1")

    def test_reviewer_fail_blocks_and_pass_unblocks(self):
        self.create()
        self.approve()
        evidence = '{"acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'
        failed = run(self.root, "verify", "--id", "alpha-change", "--manual", evidence, "--review-status", "FAIL", "--review-summary", "found issue", "--review-cover", "AC-1")
        self.assertFalse(output(failed)["verified"])
        self.assertEqual(change.load_state(self.root, "alpha-change")["phase"], "build")
        status = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(status["next_action"], "build")
        self.assertEqual(status["review_blocker"]["status"], "FAIL")
        self.assertEqual(output(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP"))["code"], "VERIFICATION_NOT_CURRENT")
        passed = run(self.root, "verify", "--id", "alpha-change", "--review-status", "PASS", "--review-summary", "resolved", "--review-cover", "AC-1")
        self.assertTrue(output(passed)["verified"])

    def test_status_clean_gate_routes_and_allows_expected_knowledge(self):
        directory = self.create()
        self.approve()
        manual = '{"acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", manual))["verified"])
        readme = self.root / "README.md"
        original = readme.read_text(encoding="utf-8")
        readme.write_text("# Dirty\n", encoding="utf-8")
        dirty = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(dirty["next_action"], "build")
        self.assertEqual(dirty["clean_gate"]["dirty_product"], ["README.md"])
        git(self.root, "add", "README.md")
        staged = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(staged["next_action"], "build")
        self.assertFalse(staged["clean_gate"]["index_clean"])
        git(self.root, "restore", "--staged", "README.md")
        readme.write_text(original, encoding="utf-8")
        knowledge = self.root / ".dev-docs" / "knowledge" / "alpha.md"
        knowledge.parent.mkdir(parents=True, exist_ok=True)
        knowledge.write_text("# Alpha\n", encoding="utf-8")
        candidate = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(candidate["next_action"], "finish")
        self.assertEqual(candidate["clean_gate"]["allowed_dirty"], [".dev-docs/knowledge/alpha.md"])
        self.finish_sections(directory)
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "APPLIED", "--knowledge-path", ".dev-docs/knowledge/alpha.md").returncode, 0)
        self.assertEqual(output(run(self.root, "status", "--id", "alpha-change"))["next_action"], "archive")
        readme.write_text("# Dirty after complete\n", encoding="utf-8")
        blocked = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(blocked["next_action"], "build")
        self.assertEqual(blocked["clean_gate"]["dirty_product"], ["README.md"])

    def test_status_actions_and_complete_verify_guard(self):
        directory = self.create()
        self.assertEqual(output(run(self.root, "status", "--id", "alpha-change"))["next_action"], "confirm-contract")
        self.approve()
        self.assertEqual(output(run(self.root, "status", "--id", "alpha-change"))["next_action"], "verify")
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", '{"acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'))["verified"])
        self.assertEqual(output(run(self.root, "status", "--id", "alpha-change"))["next_action"], "finish")
        (self.root / "README.md").write_text("# Changed\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "feat: move product head")
        drifted = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(drifted["next_action"], "build")
        self.assertEqual(drifted["missing_acceptance"], ["AC-1"])
        git(self.root, "reset", "--soft", "HEAD^")
        git(self.root, "restore", "--staged", "README.md")
        git(self.root, "restore", "README.md")
        self.finish_sections(directory)
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        self.assertEqual(output(run(self.root, "status", "--id", "alpha-change"))["next_action"], "archive")
        change_path = directory / "change.md"
        complete_change = change_path.read_text(encoding="utf-8")
        change_path.write_text(complete_change.replace("\n## Outcome\n\nAlpha shipped.\n", ""), encoding="utf-8")
        self.assertEqual(output(run(self.root, "status", "--id", "alpha-change"))["next_action"], "finish")
        change_path.write_text(complete_change, encoding="utf-8")
        delivery = directory / "delivery.yaml"
        original_delivery = delivery.read_text(encoding="utf-8")
        delivery.write_text(original_delivery.replace("  checks: []", "  checks:\n  - id: focused\n    run: [python3, -m, unittest]\n    covers: [AC-1]"), encoding="utf-8")
        check_drift = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(check_drift["failed_checks"], ["focused"])
        self.assertEqual(check_drift["next_action"], "run-required-checks")
        current = git(self.root, "rev-parse", "HEAD")
        recorded = run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "pass", "--", "python3", "-m", "unittest")
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.assertEqual(change.load_state(self.root, "alpha-change")["phase"], "build")
        delivery.write_text(original_delivery, encoding="utf-8")
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change"))["verified"])
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        (self.root / "README.md").write_text("# Changed after complete\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "feat: drift after complete")
        head_drift = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertNotEqual(head_drift["git"]["verified_head"], head_drift["git"]["current_head"])
        self.assertEqual(head_drift["next_action"], "build")
        refreshed = output(run(self.root, "verify", "--id", "alpha-change", "--manual", '{"acceptance":"AC-1","steps":"recheck","result":"pass","executor":"test"}'))
        self.assertTrue(refreshed["verified"])
        self.assertEqual(change.load_state(self.root, "alpha-change")["phase"], "verified")
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        repeated = run(self.root, "verify", "--id", "alpha-change")
        self.assertEqual(output(repeated)["code"], "CHANGE_COMPLETE")
        self.assertEqual(change.load_state(self.root, "alpha-change")["phase"], "complete")

    def test_cli_errors_and_manual_validation_are_json(self):
        missing = run(self.root, "status")
        self.assertEqual(output(missing)["code"], "INVALID_ARGUMENTS")
        self.create()
        self.approve()
        manual = run(self.root, "verify", "--id", "alpha-change", "--manual", '{"acceptance":[],"steps":"x","result":"x","executor":"x"}')
        self.assertEqual(output(manual)["code"], "INVALID_MANUAL")
        args = change.build_parser().parse_args(["verify", "--id", "alpha-change"])
        args.review_status, args.review_summary, args.review_cover = "PASS", "pass", [[]]
        with self.assertRaises(change.NuclioError) as raised:
            change.cmd_verify(args, self.root)
        self.assertEqual(raised.exception.code, "INVALID_REVIEW")
        delivery = self.root / ".dev-docs" / "changes" / "alpha-change" / "delivery.yaml"
        delivery.write_text("""schema_version: 1
change_id: alpha-change
milestones:
  - id: M1
    kind: delivery
    outcome: Ship alpha
    covers: [[AC-1]]
    status: pending
    handoff: null
verification:
  checks: []
""", encoding="utf-8")
        nested = run(self.root, "status", "--id", "alpha-change")
        self.assertEqual(output(nested)["code"], "INVALID_DELIVERY")
        delivery.write_text(delivery.read_text(encoding="utf-8").replace("kind: delivery", "kind: []").replace("covers: [[AC-1]]", "covers: [AC-1]"), encoding="utf-8")
        container = run(self.root, "status", "--id", "alpha-change")
        self.assertEqual(output(container)["code"], "INVALID_DELIVERY")
        delivery.write_text(delivery.read_text(encoding="utf-8").replace("kind: []", "kind: delivery"), encoding="utf-8")
        state_path = self.root / ".dev-docs" / "changes" / "alpha-change" / "state.yaml"
        state_path.write_text(state_path.read_text(encoding="utf-8").replace("phase: build", "phase: []"), encoding="utf-8")
        invalid_state = run(self.root, "status", "--id", "alpha-change")
        self.assertEqual(output(invalid_state)["code"], "INVALID_STATE")

    def test_manual_evidence_preserves_or_replaces_current_batch(self):
        self.create()
        self.approve()
        first = '{"acceptance":"AC-1","steps":"first","result":"pass","executor":"test"}'
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", first))["verified"])
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change"))["verified"])
        replacement = '{"acceptance":"AC-1","steps":"replacement","result":"pass","executor":"test"}'
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", replacement))["verified"])
        records = change.load_state(self.root, "alpha-change")["verification"]["manual"]
        self.assertEqual([record["steps"] for record in records], ["replacement"])

    def test_create_rejects_multiline_acceptance_before_artifacts(self):
        for value in ("line one\nline two", "line one\rline two"):
            result = run(self.root, "create", "--id", "alpha-change", "--title", "Alpha", "--goal", "Ship alpha", "--acceptance", value)
            self.assertEqual(output(result)["code"], "INVALID_INPUT")
            self.assertFalse((self.root / ".dev-docs" / "changes" / "alpha-change").exists())


if __name__ == "__main__":
    unittest.main()
