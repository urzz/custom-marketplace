"""
Nuclio v2 change Plan/State helper behavior tests.

## Contents
- [Test harness](#test-harness)
- [Create/list/show coverage](#createlistshow-coverage)
- [Plan and YAML safety coverage](#plan-and-yaml-safety-coverage)
- [State checkpoint and repair coverage](#state-checkpoint-and-repair-coverage)
- [Completion archive and legacy coverage](#completion-archive-and-legacy-coverage)
"""

import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).with_name("change.py")
SKELETON_EXPECTED = {
    ".dev-docs/index.md": (
        "# Project Knowledge Index\n"
        "\n"
        "Nuclio v2 文档库用于保存可恢复的 change 摘要和经确认的长期项目知识；代码、配置、测试、CI 和 Git working tree 仍是执行事实。\n"
        "\n"
        "## Knowledge\n"
        "\n"
        "- `knowledge/project.md`: 产品目标、用户、术语和跨领域事实。\n"
        "- `knowledge/architecture.md`: 架构约束、系统边界和重要设计关系。\n"
        "- `knowledge/engineering.md`: 构建、测试、发布、协作和代码实践。\n"
        "\n"
        "## Changes\n"
        "\n"
        "Active changes live in `.dev-docs/changes/<change-id>/` with `change.md`, `plan.yaml`, and `state.yaml`.\n"
        "\n"
        "Completed changes move to `.dev-docs/changes/archive/<change-id>/`.\n"
        "\n"
        "Do not create `.dev-docs/changes/index.md`; root index does not enumerate active or archived changes.\n"
        "\n"
        "## Legacy\n"
        "\n"
        "Legacy material lives under `.dev-docs/legacy/` and is not read by default.\n"
    ),
    ".dev-docs/knowledge/project.md": (
        "# Project Knowledge\n"
        "\n"
        "This file records confirmed product goals, users, terminology, and cross-domain facts that remain useful across changes.\n"
        "\n"
        "## Confirmed Knowledge\n"
        "\n"
        "No confirmed project knowledge has been recorded yet.\n"
    ),
    ".dev-docs/knowledge/architecture.md": (
        "# Architecture Knowledge\n"
        "\n"
        "This file records confirmed architecture constraints, system boundaries, and important design relationships that remain useful across changes.\n"
        "\n"
        "## Confirmed Knowledge\n"
        "\n"
        "No confirmed architecture knowledge has been recorded yet.\n"
    ),
    ".dev-docs/knowledge/engineering.md": (
        "# Engineering Knowledge\n"
        "\n"
        "This file records confirmed build, test, release, collaboration, and code practice knowledge that remain useful across changes.\n"
        "\n"
        "## Confirmed Knowledge\n"
        "\n"
        "No confirmed engineering knowledge has been recorded yet.\n"
    ),
}


def load_change_module():
    spec = importlib.util.spec_from_file_location("nuclio_change_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def run_change(project_root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(project_root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def stdout_json(result):
    return json.loads(result.stdout)


def stderr_json(result):
    return json.loads(result.stderr)


def git(root, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr)
    return result


class ChangeHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make_v2_skeleton(self):
        docs = self.root / ".dev-docs"
        (docs / "knowledge").mkdir(parents=True)
        (docs / "changes" / "archive").mkdir(parents=True)
        (docs / "legacy").mkdir(parents=True)
        (docs / "index.md").write_text("# Index\n", encoding="utf-8")
        for name in ("project", "architecture", "engineering"):
            (docs / "knowledge" / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
        return docs

    def init_git(self):
        if (self.root / ".git").exists():
            shutil.rmtree(self.root / ".git")
        for child in list(self.root.iterdir()):
            if child.name != ".git":
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        git(self.root, "init")
        git(self.root, "config", "user.email", "nuclio@example.invalid")
        git(self.root, "config", "user.name", "Nuclio Test")
        (self.root / "README.md").write_text("# Test\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "chore: initial")

    def create_change(self, change_id="alpha-change", title="Alpha Change", goal="Ship alpha"):
        self.make_v2_skeleton()
        result = run_change(self.root, "create", "--id", change_id, "--title", title, "--goal", goal)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.root / ".dev-docs" / "changes" / change_id

    def write_plan(self, change_id="alpha-change", risk="medium", review="task-and-final", allowed_paths=None, tasks=None):
        if allowed_paths is None:
            allowed_paths = ["src/", "README.md"]
        if tasks is None:
            tasks = [
                {
                    "id": 1,
                    "name": "Implement alpha",
                    "steps": ["Edit source"],
                    "acceptance": ["Source is present"],
                    "validation": ["python -m pytest"],
                    "delegate": "main",
                    "review": "task-and-final",
                    "checkpoint_subject": "feat(alpha): implement task 1",
                }
            ]
        plan = self.root / ".dev-docs" / "changes" / change_id / "plan.yaml"
        plan.write_text(
            "schema_version: 1\n"
            f"change_id: {change_id}\n"
            "revision: 1\n"
            f"risk_level: {risk}\n"
            f"review_policy: {review}\n"
            "repair_policy: in-scope\n"
            "summary: Implement alpha safely\n"
            "allowed_paths:\n"
            + "".join(f"  - {path}\n" for path in allowed_paths)
            + "tasks:\n"
            + "".join(
                (
                    f"  - id: {task['id']}\n"
                    f"    name: {task['name']}\n"
                    "    steps:\n"
                    + "".join(f"      - {step}\n" for step in task["steps"])
                    + "    acceptance:\n"
                    + "".join(f"      - {item}\n" for item in task["acceptance"])
                    + "    validation:\n"
                    + "".join(f"      - {command}\n" for command in task["validation"])
                    + f"    delegate: {task['delegate']}\n"
                    + f"    review: {task['review']}\n"
                    + f"    checkpoint_subject: '{task['checkpoint_subject']}'\n"
                )
                for task in tasks
            ),
            encoding="utf-8",
        )
        return plan

    def prepare_plan_state_repo(self, review="task-and-final"):
        self.init_git()
        change_dir = self.create_change()
        tasks = None
        if review == "self":
            tasks = [
                {
                    "id": 1,
                    "name": "Implement alpha",
                    "steps": ["Edit source"],
                    "acceptance": ["Source is present"],
                    "validation": ["python -m pytest"],
                    "delegate": "main",
                    "review": "self",
                    "checkpoint_subject": "feat(alpha): implement task 1",
                }
            ]
        self.write_plan(review=review, tasks=tasks)
        git(self.root, "add", ".dev-docs/changes/alpha-change/change.md", ".dev-docs/changes/alpha-change/plan.yaml")
        git(self.root, "commit", "-m", "docs: approve alpha plan")
        result = run_change(self.root, "init-state", "--id", "alpha-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        return change_dir

    def test_main_and_subcommand_help_expose_plan_state_commands_and_no_set_status(self):
        main = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(main.returncode, 0, main.stderr)
        expected = (
            "create", "list", "show", "validate-plan", "init-state", "status", "next-action",
            "start-task", "record-task", "record-review", "start-repair", "record-repair",
            "record-validation", "complete", "archive", "legacy-move",
        )
        for command in expected:
            self.assertIn(command, main.stdout)
            sub = subprocess.run(
                [sys.executable, str(SCRIPT), command, "--help"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(sub.returncode, 0, sub.stderr)
        self.assertNotIn("set-status", main.stdout)

    def test_create_writes_spec_only_with_json_stdout_and_no_plan_or_state(self):
        self.make_v2_skeleton()
        result = run_change(
            self.root,
            "create",
            "--id", "alpha-change",
            "--title", "Alpha Change",
            "--goal", "Ship alpha",
            "--related-change", "prior-change",
            "--date", "2026-07-23",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = stdout_json(result)
        self.assertTrue(payload["ok"])
        docs = self.root / ".dev-docs"
        change_dir = docs / "changes" / "alpha-change"
        change = change_dir / "change.md"
        self.assertTrue(change.exists())
        text = change.read_text(encoding="utf-8")
        self.assertIn("id: alpha-change", text)
        self.assertIn("title: Alpha Change", text)
        self.assertIn("status: active", text)
        self.assertIn("created: 2026-07-23", text)
        self.assertIn('related_changes: ["prior-change"]', text)
        self.assertIn("## Acceptance Criteria", text)
        self.assertFalse((change_dir / "plan.yaml").exists())
        self.assertFalse((change_dir / "state.yaml").exists())
        self.assertFalse((docs / "changes" / "index.md").exists())

    def test_errors_use_stable_json_stderr_and_no_side_effect_for_bad_id(self):
        self.make_v2_skeleton()
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        result = run_change(self.root, "create", "--id", "../bad", "--title", "Bad", "--goal", "Bad")
        self.assertNotEqual(result.returncode, 0)
        payload = stderr_json(result)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "INVALID_CHANGE_ID")
        after = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        self.assertEqual(after, before)

    def test_list_and_show_return_compact_json(self):
        change_dir = self.create_change("alpha-change", "Alpha Change", "Ship alpha")
        result = run_change(self.root, "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = stdout_json(result)
        self.assertEqual(payload["changes"][0]["change_id"], "alpha-change")
        self.assertEqual(payload["changes"][0]["title"], "Alpha Change")
        show = run_change(self.root, "show", "--id", "alpha-change")
        self.assertEqual(show.returncode, 0, show.stderr)
        self.assertEqual(stdout_json(show)["content"], (change_dir / "change.md").read_text(encoding="utf-8"))

    def test_validate_plan_accepts_native_yaml_multiline_and_rejects_duplicate_keys(self):
        self.create_change()
        plan = self.write_plan()
        text = plan.read_text(encoding="utf-8").replace("summary: Implement alpha safely", "summary: |\n  Implement alpha safely\n  with block scalar")
        plan.write_text(text, encoding="utf-8")
        ok = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        duplicate = text.replace("revision: 1\n", "revision: 1\nrevision: 2\n")
        plan.write_text(duplicate, encoding="utf-8")
        bad = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(stderr_json(bad)["code"], "DUPLICATE_YAML_KEY")

    def test_validate_plan_rejects_unsafe_tag_missing_dependency_placeholder_and_high_final(self):
        self.create_change()
        plan = self.write_plan()
        plan.write_text("!!python/object/apply:os.system ['echo bad']\n", encoding="utf-8")
        unsafe = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertNotEqual(unsafe.returncode, 0)
        self.assertEqual(stderr_json(unsafe)["code"], "INVALID_YAML")
        self.write_plan(risk="high", review="final")
        mismatch = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertEqual(stderr_json(mismatch)["code"], "RISK_REVIEW_MISMATCH")
        self.write_plan()
        plan.write_text(plan.read_text(encoding="utf-8").replace("Implement alpha safely", "TODO"), encoding="utf-8")
        placeholder = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertNotEqual(placeholder.returncode, 0)
        self.assertEqual(stderr_json(placeholder)["code"], "PLACEHOLDER_VALUE")
        change_module = load_change_module()
        original_yaml = change_module.yaml
        change_module.yaml = None
        try:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = change_module.main(["--project-root", str(self.root), "validate-plan", "--id", "alpha-change"])
            self.assertNotEqual(result, 0)
            self.assertEqual(json.loads(stderr.getvalue())["code"], "DEPENDENCY_MISSING")
        finally:
            change_module.yaml = original_yaml

    def test_validate_plan_rejects_illegal_allowed_paths_and_task_schema(self):
        self.create_change()
        bad_paths = ["/abs", "./rel", "../up", "src\\bad", "src/*.py", "white space", "src//bad", ".", ""]
        for bad_path in bad_paths:
            with self.subTest(bad_path=bad_path):
                self.write_plan(allowed_paths=[bad_path])
                result = run_change(self.root, "validate-plan", "--id", "alpha-change")
                self.assertNotEqual(result.returncode, 0)
        self.write_plan(allowed_paths=["src/", "src/"])
        duplicate = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertEqual(stderr_json(duplicate)["code"], "DUPLICATE_ALLOWED_PATH")
        self.write_plan(tasks=[
            {
                "id": 2,
                "name": "Late",
                "steps": ["Step"],
                "acceptance": ["Accept"],
                "validation": ["Check"],
                "delegate": "main",
                "review": "self",
                "checkpoint_subject": "feat(alpha): late",
            },
            {
                "id": 1,
                "name": "Early",
                "steps": ["Step"],
                "acceptance": ["Accept"],
                "validation": ["Check"],
                "delegate": "main",
                "review": "self",
                "checkpoint_subject": "feat(alpha): early",
            },
        ])
        unordered = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertNotEqual(unordered.returncode, 0)

    def test_init_state_atomic_write_and_identity_drift_guard(self):
        self.init_git()
        change_dir = self.create_change()
        self.write_plan()
        git(self.root, "add", ".dev-docs/changes/alpha-change/change.md", ".dev-docs/changes/alpha-change/plan.yaml")
        git(self.root, "commit", "-m", "docs: approve alpha plan")
        result = run_change(self.root, "init-state", "--id", "alpha-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = change_dir / "state.yaml"
        self.assertTrue(state.exists())
        self.assertFalse(list(change_dir.glob(".state.yaml.*.tmp")))
        state_before = state.read_text(encoding="utf-8")
        change_module = load_change_module()

        def fail_replace(source, target):
            raise OSError("simulated replace failure")

        with mock.patch.object(change_module.os, "replace", fail_replace):
            with contextlib.redirect_stderr(io.StringIO()):
                failed = change_module.main(["--project-root", str(self.root), "init-state", "--id", "beta-change"])
        self.assertNotEqual(failed, 0)
        self.assertEqual(state.read_text(encoding="utf-8"), state_before)
        (change_dir / "change.md").write_text((change_dir / "change.md").read_text(encoding="utf-8") + "\nDrift\n", encoding="utf-8")
        drift = run_change(self.root, "status", "--id", "alpha-change")
        self.assertNotEqual(drift.returncode, 0)
        self.assertEqual(stderr_json(drift)["code"], "IDENTITY_DRIFT")

    def test_start_task_allows_unrelated_dirty_but_rejects_index_and_allowed_dirty(self):
        self.prepare_plan_state_repo()
        (self.root / "notes.txt").write_text("outside allowed\n", encoding="utf-8")
        ok = run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1", "--executor", "main")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(stdout_json(ok)["checkpoint_subject"], "feat(alpha): implement task 1")

        self.prepare_plan_state_repo()
        (self.root / "README.md").write_text("dirty allowed\n", encoding="utf-8")
        allowed_dirty = run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        self.assertNotEqual(allowed_dirty.returncode, 0)
        self.assertEqual(stderr_json(allowed_dirty)["code"], "DIRTY_ALLOWED_PATH")

    def test_start_task_rejects_non_empty_index(self):
        self.prepare_plan_state_repo()
        (self.root / "notes.txt").write_text("outside allowed\n", encoding="utf-8")
        git(self.root, "add", "notes.txt")
        indexed = run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        self.assertNotEqual(indexed.returncode, 0)
        self.assertEqual(stderr_json(indexed)["code"], "DIRTY_INDEX")

    def test_record_task_validates_parent_subject_allowed_paths_index_and_validation(self):
        self.prepare_plan_state_repo()
        start = run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        self.assertEqual(start.returncode, 0, start.stderr)
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha.txt").write_text("alpha\n", encoding="utf-8")
        git(self.root, "add", "src/alpha.txt")
        git(self.root, "commit", "-m", "feat(alpha): implement task 1")
        fail_validation = run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "FAIL", "--validation-summary", "no")
        self.assertNotEqual(fail_validation.returncode, 0)
        ok = run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "PASS", "--validation-summary", "unit ok")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(stdout_json(ok)["next_action"], "RUN_TASK_REVIEW")

        self.prepare_plan_state_repo()
        run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        (self.root / "outside.txt").write_text("bad\n", encoding="utf-8")
        git(self.root, "add", "outside.txt")
        git(self.root, "commit", "-m", "feat(alpha): implement task 1")
        outside = run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "PASS", "--validation-summary", "unit ok")
        self.assertNotEqual(outside.returncode, 0)
        self.assertEqual(stderr_json(outside)["code"], "ALLOWED_PATH_VIOLATION")

        self.prepare_plan_state_repo()
        run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha.txt").write_text("alpha\n", encoding="utf-8")
        git(self.root, "add", "src/alpha.txt")
        git(self.root, "commit", "-m", "wrong subject")
        wrong_subject = run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "PASS", "--validation-summary", "unit ok")
        self.assertNotEqual(wrong_subject.returncode, 0)
        self.assertEqual(stderr_json(wrong_subject)["code"], "CHECKPOINT_SUBJECT_MISMATCH")

    def test_task_review_failure_repair_checkpoint_returns_original_gate(self):
        self.prepare_plan_state_repo()
        run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha.txt").write_text("alpha\n", encoding="utf-8")
        git(self.root, "add", "src/alpha.txt")
        git(self.root, "commit", "-m", "feat(alpha): implement task 1")
        record = run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "PASS", "--validation-summary", "unit ok")
        self.assertEqual(record.returncode, 0, record.stderr)
        review = run_change(
            self.root,
            "record-review",
            "--id", "alpha-change",
            "--scope", "task",
            "--task-id", "1",
            "--status", "FAIL",
            "--contract", "acceptance",
            "--path", "src/alpha.txt",
            "--evidence", "missing edge",
        )
        self.assertEqual(review.returncode, 0, review.stderr)
        self.assertEqual(stdout_json(review)["next_action"], "REQUEST_REPAIR_DECISION")
        bad_repair = run_change(
            self.root,
            "start-repair",
            "--id", "alpha-change",
            "--source-gate", "RUN_TASK_REVIEW",
            "--path", "outside.txt",
            "--decision", "in scope",
            "--evidence", "review finding",
            "--contract-unchanged",
        )
        self.assertNotEqual(bad_repair.returncode, 0)
        start_repair = run_change(
            self.root,
            "start-repair",
            "--id", "alpha-change",
            "--source-gate", "RUN_TASK_REVIEW",
            "--path", "src/alpha.txt",
            "--decision", "in scope",
            "--evidence", "review finding",
            "--contract-unchanged",
        )
        self.assertEqual(start_repair.returncode, 0, start_repair.stderr)
        subject = stdout_json(start_repair)["checkpoint_subject"]
        self.assertEqual(subject, "repair(alpha-change): run_task_review repair 1")
        (self.root / "src" / "alpha.txt").write_text("alpha fixed\n", encoding="utf-8")
        git(self.root, "add", "src/alpha.txt")
        git(self.root, "commit", "-m", subject)
        record_repair = run_change(self.root, "record-repair", "--id", "alpha-change", "--repair-id", "1", "--validation-status", "PASS", "--validation-summary", "closure ok")
        self.assertEqual(record_repair.returncode, 0, record_repair.stderr)
        self.assertEqual(stdout_json(record_repair)["next_action"], "RUN_TASK_REVIEW")

    def test_completion_and_archive_require_reviews_validation_and_preserve_artifacts(self):
        change_dir = self.prepare_plan_state_repo()
        run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha.txt").write_text("alpha\n", encoding="utf-8")
        git(self.root, "add", "src/alpha.txt")
        git(self.root, "commit", "-m", "feat(alpha): implement task 1")
        self.assertEqual(run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "PASS", "--validation-summary", "unit ok").returncode, 0)
        self.assertEqual(run_change(self.root, "record-review", "--id", "alpha-change", "--scope", "task", "--task-id", "1", "--status", "PASS", "--contract", "ok", "--evidence", "review ok").returncode, 0)
        self.assertEqual(run_change(self.root, "record-review", "--id", "alpha-change", "--scope", "final", "--status", "PASS", "--contract", "ok", "--evidence", "final ok").returncode, 0)
        validation = run_change(self.root, "record-validation", "--id", "alpha-change", "--status", "PASS", "--summary", "all ok", "--command", "python -m unittest")
        self.assertEqual(validation.returncode, 0, validation.stderr)
        complete = run_change(self.root, "complete", "--id", "alpha-change")
        self.assertEqual(complete.returncode, 0, complete.stderr)
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(archive.returncode, 0, archive.stderr)
        archived_dir = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        self.assertFalse(change_dir.exists())
        self.assertTrue((archived_dir / "change.md").exists())
        self.assertTrue((archived_dir / "plan.yaml").exists())
        self.assertTrue((archived_dir / "state.yaml").exists())

    def test_validation_fail_requests_repair_decision(self):
        self.prepare_plan_state_repo(review="self")
        run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha.txt").write_text("alpha\n", encoding="utf-8")
        git(self.root, "add", "src/alpha.txt")
        git(self.root, "commit", "-m", "feat(alpha): implement task 1")
        record = run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "PASS", "--validation-summary", "unit ok")
        self.assertEqual(stdout_json(record)["next_action"], "RUN_VALIDATION")
        validation = run_change(self.root, "record-validation", "--id", "alpha-change", "--status", "FAIL", "--summary", "integration failed", "--path", "src/alpha.txt", "--evidence", "trace")
        self.assertEqual(validation.returncode, 0, validation.stderr)
        self.assertEqual(stdout_json(validation)["next_action"], "REQUEST_REPAIR_DECISION")

    def test_legacy_move_preserves_clear_v1_tree_verbatim(self):
        docs = self.root / ".dev-docs"
        v1_change = docs / "changes" / "old-change"
        (v1_change / "packets").mkdir(parents=True)
        (v1_change / "evidence" / "nested").mkdir(parents=True)
        (v1_change / "contract.yaml").write_text("name: old\n", encoding="utf-8")
        (v1_change / "context.jsonl").write_text("{}\n", encoding="utf-8")
        (v1_change / "state.json").write_text("{}\n", encoding="utf-8")
        (v1_change / "packets" / "packet.json").write_text("packet\n", encoding="utf-8")
        (v1_change / "evidence" / "nested" / "raw.bin").write_bytes(b"\x00legacy")
        result = run_change(self.root, "legacy-move")
        self.assertEqual(result.returncode, 0, result.stderr)
        legacy = self.root / ".dev-docs" / "legacy" / "v1" / "changes" / "old-change"
        self.assertEqual((legacy / "contract.yaml").read_text(encoding="utf-8"), "name: old\n")
        self.assertEqual((legacy / "context.jsonl").read_text(encoding="utf-8"), "{}\n")
        self.assertEqual((legacy / "state.json").read_text(encoding="utf-8"), "{}\n")
        self.assertEqual((legacy / "packets" / "packet.json").read_text(encoding="utf-8"), "packet\n")
        self.assertEqual((legacy / "evidence" / "nested" / "raw.bin").read_bytes(), b"\x00legacy")
        for relative_path, expected in SKELETON_EXPECTED.items():
            self.assertEqual((self.root / relative_path).read_text(encoding="utf-8"), expected)
        self.assertTrue((self.root / ".dev-docs" / "changes" / "archive").is_dir())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "index.md").exists())

    def test_legacy_move_fails_closed_for_v2_unknown_conflict_and_targets(self):
        self.make_v2_skeleton()
        v2_result = run_change(self.root, "legacy-move")
        self.assertNotEqual(v2_result.returncode, 0)
        self.assertEqual(stderr_json(v2_result)["code"], "ALREADY_V2")
        shutil.rmtree(self.root / ".dev-docs")
        (self.root / ".dev-docs" / "changes" / "mystery").mkdir(parents=True)
        unknown = run_change(self.root, "legacy-move")
        self.assertNotEqual(unknown.returncode, 0)
        self.assertEqual(stderr_json(unknown)["code"], "NOT_CLEAR_V1")
        shutil.rmtree(self.root / ".dev-docs")
        (self.root / ".dev-docs" / "changes" / "old-change").mkdir(parents=True)
        (self.root / ".dev-docs" / "changes" / "old-change" / "contract.yaml").write_text("x\n", encoding="utf-8")
        (self.root / ".dev-docs" / "index.md").write_text("# v2-ish\n", encoding="utf-8")
        (self.root / ".dev-docs" / "knowledge").mkdir()
        for name in ("project", "architecture", "engineering"):
            (self.root / ".dev-docs" / "knowledge" / f"{name}.md").write_text("# k\n", encoding="utf-8")
        (self.root / ".dev-docs" / "changes" / "archive").mkdir()
        (self.root / ".dev-docs" / "legacy").mkdir()
        conflict = run_change(self.root, "legacy-move")
        self.assertNotEqual(conflict.returncode, 0)
        self.assertEqual(stderr_json(conflict)["code"], "LEGACY_CONFLICT")

    def test_legacy_move_mid_failure_restores_or_reports_precise_residue(self):
        docs = self.root / ".dev-docs"
        (docs / "changes" / "old-change").mkdir(parents=True)
        (docs / "changes" / "old-change" / "state.json").write_text("{}\n", encoding="utf-8")
        change_module = load_change_module()
        real_rename = change_module.Path.rename

        def fail_final_rename(path, target):
            if path == self.root / ".dev-docs-v1-legacy-tmp" and Path(target) == self.root / ".dev-docs" / "legacy" / "v1":
                raise OSError("simulated final move failure")
            return real_rename(path, target)

        stderr = io.StringIO()
        with mock.patch.object(change_module.Path, "rename", fail_final_rename):
            with contextlib.redirect_stderr(stderr):
                result = change_module.main(["--project-root", str(self.root), "legacy-move"])

        self.assertNotEqual(result, 0)
        self.assertTrue((self.root / ".dev-docs").exists())
        self.assertFalse((self.root / ".dev-docs-v1-legacy-tmp").exists())
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["code"], "LEGACY_MOVE_FAILED")
        self.assertIn(".dev-docs exists=", payload["message"])
        self.assertIn(".dev-docs-v1-legacy-tmp exists=", payload["message"])
        self.assertIn(".dev-docs/legacy/v1 exists=", payload["message"])


if __name__ == "__main__":
    unittest.main()
