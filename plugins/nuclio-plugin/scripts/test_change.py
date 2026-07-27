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
import hashlib
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
        "Completed changes move to `.dev-docs/changes/archive/<change-id>/` as a concise one-file `change.md` record; active `plan.yaml` and `state.yaml` are not retained in long-term archive.\n"
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

    def complete_alpha_change(self):
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
        return change_dir

    def create_successor_change(self, successor_id="beta-change", predecessor_id="alpha-change", *, archived=False, bidirectional=True):
        successor_dir = self.root / ".dev-docs" / "changes" / successor_id
        successor_dir.mkdir(parents=True)
        related = [predecessor_id] if bidirectional else []
        successor_dir.joinpath("change.md").write_text(
            "---\n"
            f"id: {successor_id}\n"
            "title: Beta Change\n"
            f"status: {'completed' if archived else 'active'}\n"
            "created: 2026-07-23\n"
            "updated: 2026-07-23\n"
            f"related_changes: {json.dumps(related)}\n"
            "---\n\n"
            "# Beta Change\n\n"
            "## Goal\n\nTake over alpha.\n\n"
            "## Outcome\n\nBeta shipped.\n\n"
            "## Validation\n\nvalidated.\n\n"
            "## Knowledge Updates\n\nNO_OP\n",
            encoding="utf-8",
        )
        if archived:
            archive_dir = self.root / ".dev-docs" / "changes" / "archive" / successor_id
            archive_dir.parent.mkdir(parents=True, exist_ok=True)
            successor_dir.rename(archive_dir)
            return archive_dir
        self.write_plan(change_id=successor_id, allowed_paths=["src/"], tasks=[
            {
                "id": 1,
                "name": "Implement beta",
                "steps": ["Edit beta"],
                "acceptance": ["Beta exists"],
                "validation": ["python -m pytest"],
                "delegate": "main",
                "review": "self",
                "checkpoint_subject": "feat(beta): implement task 1",
            }
        ])
        return successor_dir

    def prepare_supersede_fixture(self, *, successor_archived=False, successor_bidirectional=True):
        change_dir = self.prepare_plan_state_repo()
        self.create_successor_change(archived=successor_archived, bidirectional=successor_bidirectional)
        return change_dir

    def write_distilled_alpha_record(self, *, goal="Ship alpha", outcome="Alpha shipped.", validation="python -m unittest exited 0.", knowledge="NO_OP", related_changes=None):
        if related_changes is None:
            related_changes = []
        change = self.root / ".dev-docs" / "changes" / "alpha-change" / "change.md"
        change.write_text(
            "---\n"
            "id: alpha-change\n"
            "title: Alpha Change\n"
            "status: completed\n"
            "created: 2026-07-23\n"
            "updated: 2026-07-23\n"
            f"related_changes: {json.dumps(related_changes)}\n"
            "---\n\n"
            "# Alpha Change\n\n"
            f"## Goal\n\n{goal}\n\n"
            f"## Outcome\n\n{outcome}\n\n"
            f"## Validation\n\n{validation}\n\n"
            f"## Knowledge Updates\n\n{knowledge}\n",
            encoding="utf-8",
        )
        return change

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
            "record-validation", "complete", "supersede", "archive", "legacy-move",
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

    def test_pre_complete_status_rejects_current_spec_hash_drift(self):
        change_dir = self.prepare_plan_state_repo()
        change = change_dir / "change.md"
        change.write_text(change.read_text(encoding="utf-8") + "\nPre-complete drift\n", encoding="utf-8")

        drift = run_change(self.root, "status", "--id", "alpha-change")

        self.assertNotEqual(drift.returncode, 0)
        self.assertEqual(stderr_json(drift)["code"], "IDENTITY_DRIFT")
        self.assertTrue(change_dir.exists())

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

    def test_supersede_success_active_successor_status_next_action_and_archive(self):
        change_dir = self.prepare_supersede_fixture()
        change = change_dir / "change.md"
        frozen_change_text = change.read_text(encoding="utf-8")
        frozen_change_hash = hashlib.sha256(change.read_bytes()).hexdigest()
        before_tasks = (change_dir / "state.yaml").read_text(encoding="utf-8")
        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change", "--decision", "approved successor takeover")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = stdout_json(result)
        self.assertEqual(payload["next_action"], "ARCHIVE_SUPERSEDED")
        self.assertEqual(payload["superseded_by"]["successor_location"], "active")
        state = load_change_module().read_yaml_file(change_dir / "state.yaml")
        self.assertEqual(state["status"], "SUPERSEDED")
        self.assertEqual(state["phase"], "SUPERSEDED")
        self.assertEqual(state["next_action"], "ARCHIVE_SUPERSEDED")
        self.assertEqual(state["spec_sha256"], frozen_change_hash)
        self.assertEqual(change.read_text(encoding="utf-8"), frozen_change_text)
        self.assertEqual(hashlib.sha256(change.read_bytes()).hexdigest(), frozen_change_hash)
        self.assertEqual(state["tasks"][0]["status"], "PENDING")
        self.assertIn("status: PENDING", before_tasks)
        status = run_change(self.root, "status", "--id", "alpha-change")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(stdout_json(status)["state"]["next_action"], "ARCHIVE_SUPERSEDED")
        next_action = run_change(self.root, "next-action", "--id", "alpha-change")
        self.assertEqual(next_action.returncode, 0, next_action.stderr)
        self.assertEqual(stdout_json(next_action)["next_action"], "ARCHIVE_SUPERSEDED")
        self.write_distilled_alpha_record(
            outcome="Alpha was superseded and 接管 by beta-change; unfinished scope remains with successor.",
            validation="Not a full alpha acceptance PASS; only supersession facts were verified.",
            related_changes=["beta-change"],
        )
        status = run_change(self.root, "status", "--id", "alpha-change")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(stdout_json(status)["state"]["next_action"], "ARCHIVE_SUPERSEDED")
        next_action = run_change(self.root, "next-action", "--id", "alpha-change")
        self.assertEqual(next_action.returncode, 0, next_action.stderr)
        self.assertEqual(stdout_json(next_action)["next_action"], "ARCHIVE_SUPERSEDED")
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(archive.returncode, 0, archive.stderr)
        archived_dir = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        self.assertFalse(change_dir.exists())
        self.assertEqual([path.name for path in archived_dir.iterdir()], ["change.md"])

    def test_supersede_accepts_archived_successor(self):
        self.prepare_supersede_fixture(successor_archived=True)
        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stdout_json(result)["superseded_by"]["successor_location"], "archive")

    def test_superseded_predecessor_and_archived_successor_keep_final_bidirectional_relation(self):
        change_dir = self.prepare_supersede_fixture(successor_archived=True)
        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write_distilled_alpha_record(
            outcome="Alpha was superseded and taken over by beta-change; unfinished scope remains with successor.",
            validation="Not a full alpha acceptance PASS; only supersession facts were verified.",
            related_changes=["beta-change"],
        )

        archive = run_change(self.root, "archive", "--id", "alpha-change")

        self.assertEqual(archive.returncode, 0, archive.stderr)
        archived_alpha = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        archived_beta = self.root / ".dev-docs" / "changes" / "archive" / "beta-change"
        change_module = load_change_module()
        alpha_frontmatter = change_module.read_change_frontmatter(archived_alpha / "change.md", label="alpha archive")
        beta_frontmatter = change_module.read_change_frontmatter(archived_beta / "change.md", label="beta archive")
        self.assertIn("beta-change", alpha_frontmatter["related_changes"])
        self.assertIn("alpha-change", beta_frontmatter["related_changes"])
        self.assertFalse(change_dir.exists())
        self.assertEqual([path.name for path in archived_alpha.iterdir()], ["change.md"])

    def test_supersede_rejects_missing_one_way_unknown_and_self_without_side_effect(self):
        cases = [
            ({"successor_bidirectional": False}, ["--id", "alpha-change", "--successor-id", "beta-change"], "RELATED_CHANGE_MISSING"),
            ({}, ["--id", "alpha-change", "--successor-id", "missing-change"], "UNKNOWN_SUCCESSOR"),
            ({}, ["--id", "alpha-change", "--successor-id", "alpha-change"], "SELF_SUPERSEDE"),
        ]
        for fixture_kwargs, args, code in cases:
            with self.subTest(code=code):
                change_dir = self.prepare_supersede_fixture(**fixture_kwargs)
                before = (change_dir / "state.yaml").read_text(encoding="utf-8")
                result = run_change(self.root, "supersede", *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(stderr_json(result)["code"], code)
                self.assertEqual((change_dir / "state.yaml").read_text(encoding="utf-8"), before)

    def test_supersede_rejects_active_predecessor_change_drift_without_side_effect(self):
        change_dir = self.prepare_supersede_fixture()
        before = (change_dir / "state.yaml").read_text(encoding="utf-8")
        change = change_dir / "change.md"
        change.write_text(change.read_text(encoding="utf-8") + "\nArbitrary drift\n", encoding="utf-8")

        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(stderr_json(result)["code"], "IDENTITY_DRIFT")
        self.assertEqual((change_dir / "state.yaml").read_text(encoding="utf-8"), before)

    def test_supersede_head_drift_only_accepts_exact_unrecorded_checkpoint(self):
        change_dir = self.prepare_supersede_fixture()
        start = run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        self.assertEqual(start.returncode, 0, start.stderr)
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha.txt").write_text("alpha\n", encoding="utf-8")
        git(self.root, "add", "src/alpha.txt")
        git(self.root, "commit", "-m", "feat(alpha): implement task 1")
        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = load_change_module().read_yaml_file(change_dir / "state.yaml")
        self.assertEqual(state["tasks"][0]["status"], "IN_PROGRESS")
        self.assertIsNone(state["tasks"][0]["checkpoint_commit"])
        self.assertEqual(state["superseded_by"]["unrecorded_checkpoint"]["changed_paths"], ["src/alpha.txt"])

        change_dir = self.prepare_supersede_fixture()
        run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha.txt").write_text("alpha\n", encoding="utf-8")
        git(self.root, "add", "src/alpha.txt")
        git(self.root, "commit", "-m", "wrong subject")
        before = (change_dir / "state.yaml").read_text(encoding="utf-8")
        bad = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(stderr_json(bad)["code"], "IDENTITY_DRIFT")
        self.assertEqual((change_dir / "state.yaml").read_text(encoding="utf-8"), before)

    def test_supersede_rejects_terminal_conflict_and_archive_requires_successor_outcome(self):
        change_dir = self.complete_alpha_change()
        self.create_successor_change()
        terminal = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertNotEqual(terminal.returncode, 0)
        self.assertEqual(stderr_json(terminal)["code"], "TERMINAL_CHANGE")

        change_dir = self.prepare_supersede_fixture()
        self.assertEqual(run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change").returncode, 0)
        self.write_distilled_alpha_record(outcome="Alpha stopped with unfinished scope.", related_changes=["beta-change"])
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(archive.returncode, 0)
        self.assertEqual(stderr_json(archive)["code"], "UNDISTILLED_RECORD")
        self.assertTrue(change_dir.exists())

    def test_superseded_archive_rejects_relation_mismatch_without_side_effect(self):
        change_dir = self.prepare_supersede_fixture()
        self.assertEqual(run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change").returncode, 0)
        before = sorted(path.name for path in change_dir.iterdir())
        self.write_distilled_alpha_record(
            outcome="Alpha was superseded and taken over by beta-change; unfinished scope remains with successor.",
            validation="Not a full alpha acceptance PASS; only supersession facts were verified.",
            related_changes=[],
        )

        archive = run_change(self.root, "archive", "--id", "alpha-change")

        self.assertNotEqual(archive.returncode, 0)
        self.assertEqual(stderr_json(archive)["code"], "UNDISTILLED_RECORD")
        self.assertTrue(change_dir.exists())
        self.assertEqual(sorted(path.name for path in change_dir.iterdir()), before)
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())

    def test_superseded_archive_rejects_wrong_relation_without_side_effect(self):
        change_dir = self.prepare_supersede_fixture()
        self.assertEqual(run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change").returncode, 0)
        before = sorted(path.name for path in change_dir.iterdir())
        self.write_distilled_alpha_record(
            outcome="Alpha was superseded and taken over by beta-change; unfinished scope remains with successor.",
            validation="Not a full alpha acceptance PASS; only supersession facts were verified.",
            related_changes=["gamma-change"],
        )

        archive = run_change(self.root, "archive", "--id", "alpha-change")

        self.assertNotEqual(archive.returncode, 0)
        self.assertEqual(stderr_json(archive)["code"], "UNDISTILLED_RECORD")
        self.assertTrue(change_dir.exists())
        self.assertEqual(sorted(path.name for path in change_dir.iterdir()), before)
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())

    def test_superseded_archive_rejects_misleading_validation_pass_without_side_effect(self):
        change_dir = self.prepare_supersede_fixture()
        self.assertEqual(run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change").returncode, 0)
        before = sorted(path.name for path in change_dir.iterdir())
        self.write_distilled_alpha_record(
            outcome="Alpha was superseded and taken over by beta-change; unfinished scope remains with successor.",
            validation="All original alpha acceptance criteria passed successfully.",
            related_changes=["beta-change"],
        )
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(archive.returncode, 0)
        self.assertEqual(stderr_json(archive)["code"], "UNDISTILLED_RECORD")
        self.assertTrue(change_dir.exists())
        self.assertEqual(sorted(path.name for path in change_dir.iterdir()), before)
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())

    def test_superseded_archive_rejects_validation_without_non_success_distinction(self):
        change_dir = self.prepare_supersede_fixture()
        self.assertEqual(run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change").returncode, 0)
        self.write_distilled_alpha_record(
            outcome="Alpha was superseded and taken over by beta-change; unfinished scope remains with successor.",
            validation="Supersession facts were verified.",
            related_changes=["beta-change"],
        )
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(archive.returncode, 0)
        self.assertEqual(stderr_json(archive)["code"], "UNDISTILLED_RECORD")
        self.assertTrue(change_dir.exists())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())

    def test_supersede_rejects_dirty_index_allowed_dirty_and_keeps_state(self):
        change_dir = self.prepare_supersede_fixture()
        before = (change_dir / "state.yaml").read_text(encoding="utf-8")
        (self.root / "notes.txt").write_text("indexed\n", encoding="utf-8")
        git(self.root, "add", "notes.txt")
        indexed = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertNotEqual(indexed.returncode, 0)
        self.assertEqual(stderr_json(indexed)["code"], "DIRTY_INDEX")
        self.assertEqual((change_dir / "state.yaml").read_text(encoding="utf-8"), before)

        change_dir = self.prepare_supersede_fixture()
        before = (change_dir / "state.yaml").read_text(encoding="utf-8")
        (self.root / "README.md").write_text("dirty allowed\n", encoding="utf-8")
        dirty = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertNotEqual(dirty.returncode, 0)
        self.assertEqual(stderr_json(dirty)["code"], "DIRTY_ALLOWED_PATH")
        self.assertEqual((change_dir / "state.yaml").read_text(encoding="utf-8"), before)

    def test_completion_and_archive_require_reviews_validation_and_retain_only_distilled_change(self):
        change_dir = self.complete_alpha_change()
        original_change = self.write_distilled_alpha_record()
        original_text = original_change.read_text(encoding="utf-8")
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(archive.returncode, 0, archive.stderr)
        payload = stdout_json(archive)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["retained_artifacts"], ["change.md"])
        archived_dir = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        self.assertFalse(change_dir.exists())
        self.assertEqual((archived_dir / "change.md").read_text(encoding="utf-8"), original_text)
        self.assertFalse((archived_dir / "plan.yaml").exists())
        self.assertFalse((archived_dir / "state.yaml").exists())
        self.assertEqual([path.name for path in archived_dir.iterdir()], ["change.md"])

    def test_archive_rejects_symlink_artifact_before_move(self):
        change_dir = self.complete_alpha_change()
        original_change = change_dir / "change.md"
        external_record = self.root / "external-distilled-record.md"
        external_record.write_text(original_change.read_text(encoding="utf-8"), encoding="utf-8")
        original_change.unlink()
        original_change.symlink_to(external_record)
        before = sorted(path.name for path in change_dir.iterdir())
        change_link_target = original_change.readlink()
        change_module = load_change_module()

        def fail_if_rename_called(path, target):
            raise AssertionError(f"archive must reject symlink artifacts before rename: {path} -> {target}")

        stderr = io.StringIO()
        with mock.patch.object(change_module.Path, "rename", fail_if_rename_called):
            with contextlib.redirect_stderr(stderr):
                result = change_module.main(["--project-root", str(self.root), "archive", "--id", "alpha-change"])

        self.assertNotEqual(result, 0)
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["code"], "UNEXPECTED_ARCHIVE_ARTIFACTS")
        self.assertEqual(payload["details"]["symlink_artifacts"], ["change.md"])
        self.assertTrue(change_dir.exists())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())
        self.assertEqual(sorted(path.name for path in change_dir.iterdir()), before)
        self.assertTrue(original_change.is_symlink())
        self.assertEqual(original_change.readlink(), change_link_target)
        self.assertTrue((change_dir / "plan.yaml").is_file())
        self.assertTrue((change_dir / "state.yaml").is_file())

    def test_archive_rejects_undistilled_record_before_move(self):
        change_dir = self.complete_alpha_change()
        before = sorted(path.name for path in change_dir.iterdir())
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(archive.returncode, 0)
        payload = stderr_json(archive)
        self.assertEqual(payload["code"], "UNDISTILLED_RECORD")
        self.assertTrue(change_dir.exists())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())
        self.assertEqual(sorted(path.name for path in change_dir.iterdir()), before)

    def test_archive_allows_distilled_record_with_different_hash_from_frozen_spec(self):
        change_dir = self.complete_alpha_change()
        change_module = load_change_module()
        state = change_module.read_yaml_file(change_dir / "state.yaml")
        frozen_spec_hash = state["spec_sha256"]
        distilled_change = self.write_distilled_alpha_record(
            outcome="Alpha shipped with a concise archive record that intentionally differs from the active Spec.",
            validation="python -m unittest exited 0 after complete.",
        )
        distilled_hash = hashlib.sha256(distilled_change.read_bytes()).hexdigest()

        self.assertNotEqual(distilled_hash, frozen_spec_hash)
        archive = run_change(self.root, "archive", "--id", "alpha-change")

        self.assertEqual(archive.returncode, 0, archive.stderr)
        payload = stdout_json(archive)
        self.assertEqual(payload["retained_artifacts"], ["change.md"])
        archived_dir = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        self.assertFalse(change_dir.exists())
        self.assertEqual([path.name for path in archived_dir.iterdir()], ["change.md"])

    def test_archive_requires_frozen_pre_complete_spec_identity(self):
        change_dir = self.complete_alpha_change()
        self.write_distilled_alpha_record()
        change_module = load_change_module()
        state = change_module.read_yaml_file(change_dir / "state.yaml")
        state.pop("spec_sha256")
        change_module.dump_yaml_atomic(change_dir / "state.yaml", state)

        archive = run_change(self.root, "archive", "--id", "alpha-change")

        self.assertNotEqual(archive.returncode, 0)
        payload = stderr_json(archive)
        self.assertEqual(payload["code"], "IDENTITY_DRIFT")
        self.assertIn("spec_sha256", payload["message"])
        self.assertTrue(change_dir.exists())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())

    def test_archive_rejects_empty_required_heading_before_move(self):
        change_dir = self.complete_alpha_change()
        self.write_distilled_alpha_record(validation="   ")
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(archive.returncode, 0)
        payload = stderr_json(archive)
        self.assertEqual(payload["code"], "UNDISTILLED_RECORD")
        self.assertEqual(payload["details"]["empty_headings"], ["Validation"])
        self.assertTrue(change_dir.exists())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())

    def test_archive_rejects_active_frontmatter_status_before_move(self):
        change_dir = self.complete_alpha_change()
        change = self.write_distilled_alpha_record()
        change.write_text(change.read_text(encoding="utf-8").replace("status: completed", "status: active"), encoding="utf-8")
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(archive.returncode, 0)
        payload = stderr_json(archive)
        self.assertEqual(payload["code"], "UNDISTILLED_RECORD")
        self.assertEqual(payload["details"]["frontmatter"].get("status"), "active")
        self.assertTrue(change_dir.exists())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())

    def test_archive_rejects_unexpected_artifact_before_move(self):
        change_dir = self.complete_alpha_change()
        self.write_distilled_alpha_record()
        (change_dir / "notes.md").write_text("extra\n", encoding="utf-8")
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(archive.returncode, 0)
        payload = stderr_json(archive)
        self.assertEqual(payload["code"], "UNEXPECTED_ARCHIVE_ARTIFACTS")
        self.assertEqual(payload["details"]["unexpected"], ["notes.md"])
        self.assertTrue((change_dir / "notes.md").exists())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())

    def test_archive_still_rejects_uncompleted_or_identity_drift_before_move(self):
        active_change = self.prepare_plan_state_repo()
        self.write_distilled_alpha_record()
        active = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(active.returncode, 0)
        self.assertEqual(stderr_json(active)["code"], "CHANGE_NOT_COMPLETE")
        self.assertTrue(active_change.exists())

        change_dir = self.complete_alpha_change()
        self.write_distilled_alpha_record()
        (change_dir / "plan.yaml").write_text((change_dir / "plan.yaml").read_text(encoding="utf-8").replace("revision: 1", "revision: 2"), encoding="utf-8")
        drift = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(drift.returncode, 0)
        self.assertEqual(stderr_json(drift)["code"], "IDENTITY_DRIFT")
        self.assertTrue(change_dir.exists())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change").exists())

    def test_archive_rejects_target_conflict_before_move(self):
        change_dir = self.complete_alpha_change()
        self.write_distilled_alpha_record()
        target = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        target.mkdir()
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(archive.returncode, 0)
        self.assertEqual(stderr_json(archive)["code"], "ARCHIVE_EXISTS")
        self.assertTrue(change_dir.exists())
        self.assertEqual(list(target.iterdir()), [])

    def test_archive_pruning_failure_reports_archive_path_and_remaining_artifacts(self):
        change_dir = self.complete_alpha_change()
        self.write_distilled_alpha_record()
        change_module = load_change_module()
        real_unlink = change_module.Path.unlink

        def fail_state_unlink(path, *args, **kwargs):
            if path == self.root / ".dev-docs" / "changes" / "archive" / "alpha-change" / "state.yaml":
                raise OSError("simulated prune failure")
            return real_unlink(path, *args, **kwargs)

        stderr = io.StringIO()
        with mock.patch.object(change_module.Path, "unlink", fail_state_unlink):
            with contextlib.redirect_stderr(stderr):
                result = change_module.main(["--project-root", str(self.root), "archive", "--id", "alpha-change"])

        self.assertNotEqual(result, 0)
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["code"], "ARCHIVE_PRUNE_FAILED")
        self.assertEqual(payload["details"]["archive_path"], ".dev-docs/changes/archive/alpha-change")
        self.assertEqual(payload["details"]["remaining_artifacts"], ["change.md", "state.yaml"])
        self.assertFalse(change_dir.exists())
        archived_dir = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        self.assertTrue((archived_dir / "change.md").exists())
        self.assertFalse((archived_dir / "plan.yaml").exists())
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

    def test_task_review_binding_and_completion_follow_task_level_review_requirements(self):
        self.init_git()
        change_dir = self.create_change()
        tasks = [
            {
                "id": 1,
                "name": "Implement first task",
                "steps": ["Edit first source"],
                "acceptance": ["First source is present"],
                "validation": ["python -m pytest"],
                "delegate": "main",
                "review": "task-and-final",
                "checkpoint_subject": "feat(alpha): implement task 1",
            },
            {
                "id": 2,
                "name": "Implement second task",
                "steps": ["Edit second source"],
                "acceptance": ["Second source is present"],
                "validation": ["python -m pytest"],
                "delegate": "main",
                "review": "task-and-final",
                "checkpoint_subject": "feat(alpha): implement task 2",
            },
        ]
        self.write_plan(review="final", tasks=tasks)
        git(self.root, "add", ".dev-docs/changes/alpha-change/change.md", ".dev-docs/changes/alpha-change/plan.yaml")
        git(self.root, "commit", "-m", "docs: approve alpha plan")
        self.assertEqual(run_change(self.root, "init-state", "--id", "alpha-change").returncode, 0)

        self.assertEqual(run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1").returncode, 0)
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha-1.txt").write_text("alpha 1\n", encoding="utf-8")
        git(self.root, "add", "src/alpha-1.txt")
        git(self.root, "commit", "-m", "feat(alpha): implement task 1")
        record = run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "PASS", "--validation-summary", "task 1 ok")
        self.assertEqual(record.returncode, 0, record.stderr)
        self.assertEqual(stdout_json(record)["next_action"], "RUN_TASK_REVIEW")

        wrong_task_review = run_change(
            self.root,
            "record-review",
            "--id",
            "alpha-change",
            "--scope",
            "task",
            "--task-id",
            "2",
            "--status",
            "PASS",
            "--contract",
            "wrong task",
            "--evidence",
            "wrong task should fail closed",
        )
        self.assertNotEqual(wrong_task_review.returncode, 0)
        self.assertEqual(stderr_json(wrong_task_review)["code"], "INVALID_TRANSITION")

        change_module = load_change_module()
        state_path = change_dir / "state.yaml"
        state = change_module.read_yaml_file(state_path)
        state["tasks"][1].update({"status": "DONE", "task_base": git(self.root, "rev-parse", "HEAD").stdout.strip(), "task_head": git(self.root, "rev-parse", "HEAD").stdout.strip(), "checkpoint_commit": git(self.root, "rev-parse", "HEAD").stdout.strip(), "validation": {"status": "PASS", "summary": "task 2 ok"}})
        state["review"]["task_reviews"]["2"] = {"status": "PASS", "contract": "ok", "evidence": "review ok"}
        state["review"]["final"] = {"status": "PASS", "contract": "ok", "evidence": "final ok"}
        state["validation"] = {"status": "PASS", "commands": ["python -m unittest"], "summary": "all ok"}
        state.update({"phase": "COMPLETE", "next_action": "COMPLETE", "current_task_id": None, "blocker": None})
        change_module.dump_yaml_atomic(state_path, state)

        complete = run_change(self.root, "complete", "--id", "alpha-change")
        self.assertNotEqual(complete.returncode, 0)
        payload = stderr_json(complete)
        self.assertEqual(payload["code"], "REVIEW_NOT_PASSED")
        self.assertEqual(payload["details"]["tasks"], [1])

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
