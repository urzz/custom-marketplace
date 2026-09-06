"""Focused behavior tests for the Nuclio v3 thin Runtime."""

import json
import re
import shlex
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
        git(self.root, "config", "commit.gpgsign", "false")
        git(self.root, "config", "core.hooksPath", "/dev/null")
        git(self.root, "config", "core.quotePath", "true")
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

    def manual(self, status="PASS", result="观察符合验收结果"):
        return json.dumps({"acceptance": "AC-1", "status": status, "steps": "观察所需行为", "result": result, "executor": "test"})

    def verified_change(self):
        directory = self.create()
        self.approve()
        result = run(self.root, "verify", "--id", "alpha-change", "--manual", self.manual())
        self.assertTrue(output(result)["verified"], result.stderr)
        self.finish_sections(directory)
        return directory

    def test_documented_remote_ref_command_runs_in_bash_and_zsh(self):
        guide = SCRIPT.parents[1] / "skills/work/SKILL.md"
        command = re.search(r"(?m)^\s*(git -C .* for-each-ref .*?)$", guide.read_text()).group(1)
        command = command.replace('"${NUCLIO_PROJECT_DIR}"', shlex.quote(str(self.root)))
        ref = "refs/remotes/team/fix/alpha-change"
        git(self.root, "update-ref", ref, "HEAD")
        for shell in ("bash", "zsh"):
            with self.subTest(shell=shell):
                executable = shutil.which(shell)
                if executable is None:
                    self.skipTest(f"未安装 {shell}")
                result = subprocess.run([executable, "-c", command], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), [ref])

    def test_failed_manual_blocks_completion_even_with_passing_review(self):
        directory = self.create()
        self.approve()
        result = run(self.root, "verify", "--id", "alpha-change", "--manual", self.manual("FAIL", "缺少所需行为"),
                     "--review-status", "PASS", "--review-summary", "其他审查通过", "--review-cover", "AC-1")
        self.assertFalse(output(result)["verified"])
        status = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(status["next_action"], "build")
        self.assertEqual(status["manual_blocker"], ["AC-1"])
        self.finish_sections(directory)
        self.assertEqual(output(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP"))["code"], "VERIFICATION_NOT_CURRENT")
        self.assertFalse(output(run(self.root, "archive", "--id", "alpha-change"))["ok"])
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", self.manual()))["verified"])

    def test_manual_requires_explicit_status_and_legacy_evidence_is_not_passed(self):
        directory = self.verified_change()
        legacy = json.loads(self.manual())
        del legacy["status"]
        rejected = run(self.root, "verify", "--id", "alpha-change", "--manual", json.dumps(legacy))
        self.assertEqual(output(rejected)["code"], "INVALID_MANUAL")
        state = change.load_state(self.root, "alpha-change")
        del state["verification"]["manual"][0]["status"]
        change.write_state(self.root, "alpha-change", state)
        before = (directory / "state.yaml").read_bytes()
        status = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(status["missing_acceptance"], ["AC-1"])
        self.assertEqual(status["next_action"], "build")
        self.assertEqual((directory / "state.yaml").read_bytes(), before)
        self.assertEqual(output(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP"))["code"], "VERIFICATION_NOT_CURRENT")
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", self.manual()))["verified"])

    def test_unicode_knowledge_archives_and_retries_with_default_git_quoting(self):
        self.verified_change()
        path = self.root / ".dev-docs/knowledge/认证.md"
        path.parent.mkdir(parents=True)
        path.write_text("# 认证约束\n", encoding="utf-8")
        completed = run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "APPLIED", "--knowledge-path", path.relative_to(self.root).as_posix())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for _ in range(2):
            archived = run(self.root, "archive", "--id", "alpha-change")
            self.assertEqual(archived.returncode, 0, archived.stderr)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def test_quoted_and_control_character_knowledge_paths_are_preserved(self):
        self.verified_change()
        directory = self.root / ".dev-docs/knowledge"
        directory.mkdir(parents=True)
        args = ["complete", "--id", "alpha-change", "--knowledge-result", "APPLIED"]
        for filename in ('引号".md', "制表\t.md", "换行\n.md", "回车\r.md", "literal[1].md"):
            path = directory / filename
            path.write_text("# 项目事实\n")
            args.extend(["--knowledge-path", path.relative_to(self.root).as_posix()])
        result = run(self.root, *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        for _ in range(2):
            result = run(self.root, "archive", "--id", "alpha-change")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def test_nested_project_completes_reapproves_and_archives(self):
        repository = self.root
        self.root = repository / "packages/app"
        (self.root / ".dev-docs/changes/archive").mkdir(parents=True)
        directory = self.create()
        first = self.approve()
        path = directory / "change.md"
        path.write_text(path.read_text().replace("revision: 1", "revision: 2"))
        second = self.approve()
        self.assertEqual(first["base_head"], second["base_head"])
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", self.manual()))["verified"])
        self.finish_sections(directory)
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        for _ in range(2):
            result = run(self.root, "archive", "--id", "alpha-change")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((repository / ".dev-docs/changes/alpha-change").exists())
        self.assertTrue((self.root / ".dev-docs/changes/archive/alpha-change/state.yaml").is_file())
        self.assertEqual(git(repository, "status", "--porcelain"), "")

    def test_approval_postcommit_interruption_has_readonly_recovery_route(self):
        directory = self.create()
        real_write = change.write_state
        def interrupt_after_commit(root, change_id, state):
            if state["approval_head"] is not None:
                raise change.NuclioError("INTERRUPTED", "模拟批准提交后的中断")
            real_write(root, change_id, state)
        args = change.build_parser().parse_args(["approve", "--id", "alpha-change"])
        with mock.patch.object(change, "write_state", side_effect=interrupt_after_commit):
            with self.assertRaises(change.NuclioError):
                change.cmd_approve(args, self.root)
        approved_head = git(self.root, "rev-parse", "HEAD")
        before = (directory / "state.yaml").read_bytes()
        status = output(run(self.root, "status", "--id", "alpha-change"))
        self.assertEqual(status["next_action"], "recover-approval")
        self.assertEqual((directory / "state.yaml").read_bytes(), before)
        recovered = self.approve()
        self.assertTrue(recovered["recovered"])
        self.assertEqual(recovered["approval_head"], approved_head)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), approved_head)

    def test_archive_commit_failure_can_be_retried_by_explicit_id(self):
        directory = self.verified_change()
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        real_git = change.git
        def fail_commit(root, *args, **kwargs):
            if args[:1] == ("commit",):
                raise change.NuclioError("GIT_ERROR", "模拟归档提交失败")
            return real_git(root, *args, **kwargs)
        args = change.build_parser().parse_args(["archive", "--id", "alpha-change"])
        with mock.patch.object(change, "git", side_effect=fail_commit):
            with self.assertRaises(change.NuclioError) as raised:
                change.cmd_archive(args, self.root)
        self.assertEqual(raised.exception.code, "ARCHIVE_COMMIT_FAILED")
        self.assertFalse(directory.exists())
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")
        recovered = run(self.root, "archive", "--id", "alpha-change")
        self.assertTrue(output(recovered)["recovered"], recovered.stderr)

    def test_reverted_knowledge_is_rejected_before_archive_mutation(self):
        path = self.root / ".dev-docs/knowledge/alpha.md"
        path.parent.mkdir(parents=True)
        path.write_text("# 原有知识\n")
        git(self.root, "add", ".dev-docs/knowledge/alpha.md")
        git(self.root, "commit", "-m", "docs: prior knowledge")
        directory = self.verified_change()
        path.write_text("# 更新知识\n")
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "APPLIED", "--knowledge-path", ".dev-docs/knowledge/alpha.md").returncode, 0)
        path.write_text("# 原有知识\n")
        before = git(self.root, "rev-parse", "HEAD")
        for moved in (False, True):
            if moved:
                directory.rename(self.root / ".dev-docs/changes/archive/alpha-change")
            with self.subTest(moved=moved):
                result = run(self.root, "archive", "--id", "alpha-change")
                self.assertEqual(output(result)["code"], "KNOWLEDGE_PATH_MISMATCH")
                self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
                self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")
                if not moved:
                    self.assertTrue(directory.exists())

    def test_ignored_archive_is_rejected_before_move(self):
        (self.root / ".gitignore").write_text(".dev-docs/changes/archive/\n")
        git(self.root, "add", ".gitignore")
        git(self.root, "commit", "-m", "chore: ignored archive fixture")
        directory = self.verified_change()
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        result = run(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(output(result)["code"], "ARCHIVE_TARGET_IGNORED")
        self.assertTrue(directory.exists())
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")

    def test_partial_archive_add_failure_unstages_only_transition_and_retries(self):
        self.verified_change()
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        real_git = change.git
        def fail_add(root, *args, **kwargs):
            if args[:2] == ("add", "-A"):
                real_git(root, "add", "-u", "--", ".dev-docs/changes/alpha-change")
                raise change.NuclioError("GIT_ERROR", "模拟部分暂存失败")
            return real_git(root, *args, **kwargs)
        args = change.build_parser().parse_args(["archive", "--id", "alpha-change"])
        with mock.patch.object(change, "git", side_effect=fail_add):
            with self.assertRaises(change.NuclioError) as raised:
                change.cmd_archive(args, self.root)
        self.assertEqual(raised.exception.code, "ARCHIVE_COMMIT_FAILED")
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")
        recovered = run(self.root, "archive", "--id", "alpha-change")
        self.assertTrue(output(recovered)["recovered"], recovered.stderr)

    def test_archive_failure_preserves_concurrently_staged_unrelated_file(self):
        self.verified_change()
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        real_git = change.git
        def fail_add(root, *args, **kwargs):
            if args[:2] == ("add", "-A"):
                real_git(root, "add", "-u", "--", ".dev-docs/changes/alpha-change")
                (root / "README.md").write_text("# 用户在检查后暂存的独立改动\n")
                real_git(root, "add", "--", "README.md")
                raise change.NuclioError("GIT_ERROR", "模拟暂存中断")
            return real_git(root, *args, **kwargs)
        args = change.build_parser().parse_args(["archive", "--id", "alpha-change"])
        with mock.patch.object(change, "git", side_effect=fail_add):
            with self.assertRaises(change.NuclioError):
                change.cmd_archive(args, self.root)
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "README.md")

    def test_archive_recovery_add_failure_cleans_partial_index_and_retries(self):
        directory = self.verified_change()
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        directory.rename(self.root / ".dev-docs/changes/archive/alpha-change")
        real_git = change.git
        def fail_add(root, *args, **kwargs):
            if args[:2] == ("add", "-A"):
                real_git(root, "add", "-u", "--", ".dev-docs/changes/alpha-change")
                raise change.NuclioError("GIT_ERROR", "模拟恢复暂存中断")
            return real_git(root, *args, **kwargs)
        args = change.build_parser().parse_args(["archive", "--id", "alpha-change"])
        with mock.patch.object(change, "git", side_effect=fail_add):
            with self.assertRaises(change.NuclioError):
                change.cmd_archive(args, self.root)
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "")
        self.assertEqual(run(self.root, "archive", "--id", "alpha-change").returncode, 0)

    def test_create_rejects_internal_symlink_parent_without_product_writes(self):
        changes = self.root / ".dev-docs/changes"
        (changes / "archive").rmdir()
        changes.rmdir()
        target = self.root / "product-data"
        (target / "archive").mkdir(parents=True)
        changes.symlink_to(target, target_is_directory=True)
        result = run(self.root, "create", "--id", "alpha-change", "--title", "Alpha", "--goal", "Ship alpha")
        self.assertEqual(output(result)["code"], "UNSAFE_SYMLINK")
        self.assertEqual(list(target.iterdir()), [target / "archive"])

    def test_runtime_rejects_state_symlink_without_reading_or_overwriting_target(self):
        directory = self.create()
        path = directory / "state.yaml"
        target = self.root / "user-data.txt"
        original = b"private project data\n"
        target.write_bytes(original)
        path.unlink()
        path.symlink_to(target)
        result = run(self.root, "status", "--id", "alpha-change")
        self.assertEqual(output(result)["code"], "UNSAFE_SYMLINK")
        self.assertEqual(target.read_bytes(), original)

    def test_nested_project_clean_gate_keeps_unrelated_repository_paths(self):
        repository = self.root
        self.root = repository / "packages/app"
        (self.root / ".dev-docs/changes/archive").mkdir(parents=True)
        self.create()
        (repository / "README.md").write_text("# 独立项目改动\n")
        result = run(self.root, "approve", "--id", "alpha-change")
        self.assertEqual(output(result)["code"], "DIRTY_PRODUCT_WORKTREE")
        self.assertEqual(output(result)["details"]["paths"], ["../../README.md"])

    def test_archive_retry_rejects_modified_artifacts_without_touching_them(self):
        self.verified_change()
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        self.assertEqual(run(self.root, "archive", "--id", "alpha-change").returncode, 0)
        target = self.root / ".dev-docs/changes/archive/alpha-change"
        for filename in change.ARTIFACTS:
            with self.subTest(filename=filename):
                path = target / filename
                original = path.read_bytes()
                path.write_bytes(original + b"\n# Edited archive\n")
                edited = path.read_bytes()
                result = run(self.root, "archive", "--id", "alpha-change")
                self.assertEqual(output(result)["code"], "ARCHIVE_CONTENT_DRIFT")
                self.assertEqual(path.read_bytes(), edited)
                path.write_bytes(original)

    def test_archive_is_idempotent_after_later_commits_and_project_check_changes(self):
        self.verified_change()
        self.assertEqual(run(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "NO_OP").returncode, 0)
        archived = output(run(self.root, "archive", "--id", "alpha-change"))
        (self.root / "README.md").write_text("# 后续产品改动\n")
        (self.root / ".dev-docs/nuclio.yaml").write_text("schema_version: 1\nchecks:\n- id: later\n  run: [python3, --version]\n")
        git(self.root, "add", "README.md", ".dev-docs/nuclio.yaml")
        git(self.root, "commit", "-m", "feat: later product change")
        before = git(self.root, "rev-parse", "HEAD")
        result = run(self.root, "archive", "--id", "alpha-change")
        self.assertTrue(output(result)["recovered"], result.stderr)
        self.assertEqual(output(result)["archive_commit"], archived["archive_commit"])
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), before)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

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
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", '{"status":"PASS","acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'))["verified"])
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
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", '{"status":"PASS","acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'))["verified"])
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
        manual = '{"status":"PASS","acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'
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
        manual = '{"status":"PASS","acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'
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
        evidence = '{"status":"PASS","acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'
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
        manual = '{"status":"PASS","acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'
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
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", '{"status":"PASS","acceptance":"AC-1","steps":"check","result":"pass","executor":"test"}'))["verified"])
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
        refreshed = output(run(self.root, "verify", "--id", "alpha-change", "--manual", '{"status":"PASS","acceptance":"AC-1","steps":"recheck","result":"pass","executor":"test"}'))
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
        first = '{"status":"PASS","acceptance":"AC-1","steps":"first","result":"pass","executor":"test"}'
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change", "--manual", first))["verified"])
        self.assertTrue(output(run(self.root, "verify", "--id", "alpha-change"))["verified"])
        replacement = '{"status":"PASS","acceptance":"AC-1","steps":"replacement","result":"pass","executor":"test"}'
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
