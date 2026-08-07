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
        record = run(self.root, "record-check", "--id", "alpha-change", "--check-id", "focused", "--head", current, "--exit-code", "0", "--summary", "host reported pass", "--", "python3", "-c", "open('executed', 'w')")
        self.assertEqual(record.returncode, 0, record.stderr)
        self.assertFalse(marker.exists())
        verified = run(self.root, "verify", "--id", "alpha-change")
        self.assertTrue(output(verified)["verified"], verified.stderr)
        self.finish_sections(directory)
        complete = run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP")
        self.assertEqual(complete.returncode, 0, complete.stderr)

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
        with mock.patch.object(change, "git", side_effect=fail_commit):
            with self.assertRaises(change.NuclioError):
                change.cmd_approve(args, self.root)
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


if __name__ == "__main__":
    unittest.main()
