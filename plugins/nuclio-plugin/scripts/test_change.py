"""Behavior tests for the Nuclio v2 Plan/State helper."""

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


def stdout_json(result):
    return json.loads(result.stdout)


def stderr_json(result):
    return json.loads(result.stderr)


class ChangeHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def init_git(self):
        git(self.root, "init")
        git(self.root, "config", "user.email", "nuclio@example.invalid")
        git(self.root, "config", "user.name", "Nuclio Test")
        (self.root / "README.md").write_text("# Test\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "chore: initial")

    def make_skeleton(self, *, commit=True):
        docs = self.root / ".dev-docs"
        (docs / "knowledge").mkdir(parents=True)
        (docs / "changes" / "archive").mkdir(parents=True)
        (docs / "legacy").mkdir(parents=True)
        (docs / "index.md").write_text("# Project Knowledge Index\n", encoding="utf-8")
        for name in ("project", "architecture", "engineering"):
            (docs / "knowledge" / f"{name}.md").write_text(f"# {name.title()} Knowledge\n", encoding="utf-8")
        if commit:
            git(self.root, "add", ".dev-docs/index.md", ".dev-docs/knowledge")
            git(self.root, "commit", "-m", "docs: initialize nuclio skeleton")
        return docs

    def create_change(self, change_id="alpha-change", title="Alpha Change", goal="Ship alpha"):
        result = run_change(self.root, "create", "--id", change_id, "--title", title, "--goal", goal, "--date", "2026-07-29")
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.root / ".dev-docs" / "changes" / change_id

    def approve_spec(self, change_dir):
        change = change_dir / "change.md"
        text = change.read_text(encoding="utf-8")
        text = text.replace("待补充必要背景。", "Alpha is required by the current product flow.")
        text = text.replace("待在计划批准前确认。", "Keep implementation inside approved paths.", 1)
        text = text.replace("待在计划批准前确认。", "Do not change public APIs.", 1)
        text = text.replace("待在计划批准前确认。", "- Alpha behavior is present and validated.", 1)
        change.write_text(text, encoding="utf-8")
        return change

    def write_plan(
        self,
        *,
        change_id="alpha-change",
        risk="medium",
        review="final",
        execution_mode="delegated",
        execution_rationale="Use bounded subagents for product work.",
        allowed_paths=None,
        tasks=None,
        legacy=False,
        v1=False,
    ):
        allowed_paths = allowed_paths or ["src/", "README.md"]
        tasks = tasks or [
            {
                "id": 1,
                "name": "Implement alpha",
                "steps": ["Edit source"],
                "acceptance": ["Source is present"],
                "validation": ["python -m pytest"],
            }
        ]
        lines = [
            f"schema_version: {1 if legacy or v1 else 2}",
            f"change_id: {change_id}",
            "revision: 1",
            f"risk_level: {risk}",
            f"review_policy: {review}",
        ]
        if not legacy and not v1:
            lines.extend(
                [
                    "execution:",
                    f"  mode: {execution_mode}",
                    f"  rationale: {execution_rationale}",
                ]
            )
        if legacy:
            lines.append("repair_policy: in-scope")
        lines.extend(["summary: Implement alpha safely", "allowed_paths:"])
        lines.extend(f"  - {path}" for path in allowed_paths)
        lines.append("tasks:")
        for task in tasks:
            lines.extend(
                [
                    f"  - id: {task['id']}",
                    f"    name: {task['name']}",
                    "    steps:",
                    *(f"      - {step}" for step in task["steps"]),
                    "    acceptance:",
                    *(f"      - {item}" for item in task["acceptance"]),
                    "    validation:",
                    *(f"      - {command}" for command in task["validation"]),
                ]
            )
            if legacy:
                lines.extend(
                    [
                        f"    delegate: {task.get('delegate', 'main')}",
                        f"    review: {task.get('review', review)}",
                        f"    checkpoint_subject: '{task.get('checkpoint_subject', f'legacy({change_id}): task {task['id']}')}'",
                    ]
                )
            elif task.get("review"):
                lines.append(f"    review: {task['review']}")
        path = self.root / ".dev-docs" / "changes" / change_id / "plan.yaml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def prepare_change(self, *, review="final", risk="medium", execution_mode="delegated", allowed_paths=None, tasks=None):
        self.init_git()
        self.make_skeleton()
        change_dir = self.create_change()
        self.approve_spec(change_dir)
        self.write_plan(review=review, risk=risk, execution_mode=execution_mode, allowed_paths=allowed_paths, tasks=tasks)
        result = run_change(self.root, "init-state", "--id", "alpha-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        return change_dir

    def task_subject(self, task_id=1, change_id="alpha-change"):
        return f"task({change_id}): complete task {task_id}"

    def implement_task(self, task_id=1, *, command="python -m pytest", filename=None, change_id="alpha-change"):
        start = run_change(self.root, "start-task", "--id", change_id, "--task-id", str(task_id))
        self.assertEqual(start.returncode, 0, start.stderr)
        self.assertEqual(stdout_json(start)["checkpoint_subject"], self.task_subject(task_id, change_id))
        src = self.root / "src"
        src.mkdir(exist_ok=True)
        target = src / (filename or f"{change_id}-task-{task_id}.txt")
        target.write_text(f"task {task_id}\n", encoding="utf-8")
        git(self.root, "add", target.relative_to(self.root).as_posix())
        git(self.root, "commit", "-m", self.task_subject(task_id, change_id))
        record = run_change(
            self.root,
            "record-task",
            "--id",
            change_id,
            "--task-id",
            str(task_id),
            "--validation-status",
            "PASS",
            "--validation-summary",
            "task validation passed",
            "--validation-command",
            command,
            "--validation-exit-code",
            "0",
        )
        self.assertEqual(record.returncode, 0, record.stderr)
        return stdout_json(record)

    def finish_product_gates(self, *, review="final", change_id="alpha-change"):
        if review == "task-and-final":
            task_review = run_change(
                self.root,
                "record-review",
                "--id",
                change_id,
                "--scope",
                "task",
                "--task-id",
                "1",
                "--status",
                "PASS",
                "--summary",
                "task review passed",
            )
            self.assertEqual(task_review.returncode, 0, task_review.stderr)
        if review in {"final", "task-and-final"}:
            final = run_change(
                self.root,
                "record-review",
                "--id",
                change_id,
                "--scope",
                "final",
                "--status",
                "PASS",
                "--summary",
                "final review passed",
            )
            self.assertEqual(final.returncode, 0, final.stderr)
        validation = run_change(
            self.root,
            "record-validation",
            "--id",
            change_id,
            "--status",
            "PASS",
            "--summary",
            "whole-change validation passed",
            "--command",
            "python -m unittest",
            "--exit-code",
            "0",
        )
        self.assertEqual(validation.returncode, 0, validation.stderr)

    def complete_change(self, *, knowledge_result="NO_OP", knowledge_paths=None, change_id="alpha-change"):
        args = ["complete", "--id", change_id, "--knowledge-result", knowledge_result]
        for path in knowledge_paths or []:
            args.extend(["--knowledge-path", path])
        result = run_change(self.root, *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stdout_json(result)["next_action"], "ARCHIVE")
        return result

    def append_completion(self, *, outcome="Alpha shipped.", validation="python -m unittest exited 0.", knowledge="NO_OP", residual="No known residual risks.", related_changes=None, change_id="alpha-change"):
        change = self.root / ".dev-docs" / "changes" / change_id / "change.md"
        module = load_change_module()
        frontmatter, body = module.parse_markdown_frontmatter(change.read_text(encoding="utf-8"))
        frontmatter["status"] = "completed"
        if related_changes is not None:
            frontmatter["related_changes"] = related_changes
        text = (
            f"---\n{module.yaml_frontmatter(frontmatter)}\n---\n"
            f"{body.rstrip()}\n\n"
            f"## Outcome\n\n{outcome}\n\n"
            f"## Validation\n\n{validation}\n\n"
            f"## Knowledge Updates\n\n{knowledge}\n\n"
            f"## Residual Risks\n\n{residual}\n"
        )
        change.write_text(text, encoding="utf-8")
        return change

    def prepare_completed_change(self, *, review="final"):
        change_dir = self.prepare_change(review=review)
        self.implement_task()
        self.finish_product_gates(review=review)
        self.complete_change()
        self.append_completion()
        return change_dir

    def state(self, directory=None):
        module = load_change_module()
        directory = directory or self.root / ".dev-docs" / "changes" / "alpha-change"
        return module.read_yaml_file(directory / "state.yaml")

    def assert_archive_commit(self, *, extra_paths=None):
        subject = git(self.root, "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(subject, "archive(alpha-change): retain complete change record")
        changed = set(
            git(self.root, "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-r", "HEAD").stdout.splitlines()
        )
        expected = {
            ".dev-docs/changes/alpha-change/change.md",
            ".dev-docs/changes/alpha-change/plan.yaml",
            ".dev-docs/changes/alpha-change/state.yaml",
            ".dev-docs/changes/archive/alpha-change/change.md",
            ".dev-docs/changes/archive/alpha-change/plan.yaml",
            ".dev-docs/changes/archive/alpha-change/state.yaml",
        }
        expected.update(extra_paths or [])
        self.assertEqual(changed, expected)
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only").stdout, "")

    def create_legacy_archived_successor(self, *, backlink=True):
        successor_id = "beta-change"
        archive_dir = self.root / ".dev-docs" / "changes" / "archive" / successor_id
        archive_dir.mkdir(parents=True)
        related = ["alpha-change"] if backlink else []
        archive_dir.joinpath("change.md").write_text(
            "---\n"
            f"id: {successor_id}\n"
            "title: Beta Change\n"
            "status: completed\n"
            "created: 2026-07-29\n"
            "updated: 2026-07-29\n"
            f"related_changes: {json.dumps(related)}\n"
            "---\n\n"
            "# Beta Change\n\n"
            "## Goal\n\nTake over alpha.\n\n"
            "## Outcome\n\nBeta shipped.\n\n"
            "## Validation\n\nValidation passed.\n\n"
            "## Knowledge Updates\n\nNO_OP\n",
            encoding="utf-8",
        )
        git(self.root, "add", f".dev-docs/changes/archive/{successor_id}/change.md")
        git(self.root, "commit", "-m", f"archive({successor_id}): retain distilled change record")
        return archive_dir

    def create_complete_archived_successor(self):
        successor_id = "beta-change"
        change_dir = self.create_change(change_id=successor_id, title="Beta Change", goal="Take over alpha")
        self.approve_spec(change_dir)
        change = change_dir / "change.md"
        change.write_text(
            change.read_text(encoding="utf-8").replace("related_changes: []", "related_changes:\n- alpha-change"),
            encoding="utf-8",
        )
        self.write_plan(change_id=successor_id)
        init = run_change(self.root, "init-state", "--id", successor_id)
        self.assertEqual(init.returncode, 0, init.stderr)
        self.implement_task(change_id=successor_id)
        self.finish_product_gates(change_id=successor_id)
        self.complete_change(change_id=successor_id)
        self.append_completion(
            change_id=successor_id,
            outcome="Beta took over alpha-change and shipped.",
        )
        archive = run_change(self.root, "archive", "--id", successor_id)
        self.assertEqual(archive.returncode, 0, archive.stderr)
        return self.root / ".dev-docs" / "changes" / "archive" / successor_id

    def test_help_exposes_single_helper_lifecycle(self):
        result = run_change(self.root, "--help")
        self.assertEqual(result.returncode, 0)
        for command in ("create", "validate-plan", "init-state", "record-task", "complete", "supersede", "archive"):
            self.assertIn(command, result.stdout)
        self.assertNotIn("set-status", result.stdout)

    def test_create_uses_safe_yaml_and_rejects_multiline_title(self):
        self.init_git()
        self.make_skeleton()
        change_dir = self.create_change(title="Fix: auth #1")
        module = load_change_module()
        frontmatter, _body = module.parse_markdown_frontmatter((change_dir / "change.md").read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["title"], "Fix: auth #1")
        self.assertFalse((change_dir / "plan.yaml").exists())
        bad = run_change(self.root, "create", "--id", "bad-change", "--title", "Bad\ntitle", "--goal", "x")
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(stderr_json(bad)["code"], "INVALID_INPUT")

    def test_validate_plan_checks_spec_identity_content_and_placeholders(self):
        self.init_git()
        self.make_skeleton()
        change_dir = self.create_change()
        self.write_plan()
        placeholder = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertEqual(stderr_json(placeholder)["code"], "INVALID_SPEC")
        self.approve_spec(change_dir)
        ok = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        (change_dir / "change.md").write_text((change_dir / "change.md").read_text(encoding="utf-8").replace("id: alpha-change", "id: other-change"), encoding="utf-8")
        drift = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertEqual(stderr_json(drift)["code"], "IDENTITY_DRIFT")

    def test_plan_schema_is_minimal_and_legacy_is_recovery_only(self):
        module = load_change_module()
        canonical = {
            "schema_version": 2,
            "change_id": "alpha-change",
            "revision": 1,
            "risk_level": "medium",
            "review_policy": "final",
            "execution": {"mode": "delegated", "rationale": "Use a bounded subagent."},
            "summary": "Implement alpha",
            "allowed_paths": ["src/"],
            "tasks": [{"id": 1, "name": "Alpha", "steps": ["Edit"], "acceptance": ["Works"], "validation": ["pytest"]}],
        }
        normalized = module.validate_plan_data(canonical)
        self.assertFalse(normalized["_legacy"])
        self.assertEqual(normalized["_variant"], "v2")
        self.assertEqual(normalized["execution"]["mode"], "delegated")
        self.assertEqual(normalized["tasks"][0]["checkpoint_subject"], self.task_subject())
        v1 = dict(canonical)
        v1["schema_version"] = 1
        del v1["execution"]
        with self.assertRaises(module.NuclioError):
            module.validate_plan_data(v1)
        recovered = module.validate_plan_data(v1, allow_legacy=True)
        self.assertEqual(recovered["_variant"], "v1-4.1")
        self.assertEqual(recovered["execution"]["mode"], "delegated")
        legacy = dict(v1)
        legacy["repair_policy"] = "in-scope"
        legacy["tasks"] = [dict(v1["tasks"][0], delegate="main", review="final", checkpoint_subject="legacy subject")]
        with self.assertRaises(module.NuclioError):
            module.validate_plan_data(legacy)
        recovered_legacy = module.validate_plan_data(legacy, allow_legacy=True)
        self.assertTrue(recovered_legacy["_legacy"])
        self.assertEqual(recovered_legacy["_variant"], "v1-4.0")
        self.assertEqual(recovered_legacy["execution"]["mode"], "legacy-task-delegate")
        self.assertEqual(module.required_task_executor(recovered_legacy, recovered_legacy["tasks"][0]), "main")
        self.assertEqual(module.required_repair_executor(recovered_legacy), "main")

    def test_direct_execution_requires_all_structural_eligibility_rules(self):
        module = load_change_module()
        direct = {
            "schema_version": 2,
            "change_id": "alpha-change",
            "revision": 1,
            "risk_level": "low",
            "review_policy": "self",
            "execution": {"mode": "direct", "rationale": "Localized fix in one source file and its test."},
            "summary": "Fix alpha",
            "allowed_paths": ["src/alpha.py", "tests/test_alpha.py"],
            "tasks": [{"id": 1, "name": "Fix alpha", "steps": ["Edit"], "acceptance": ["Works"], "validation": ["pytest"]}],
        }
        normalized = module.validate_plan_data(direct)
        self.assertEqual(module.required_task_executor(normalized, normalized["tasks"][0]), "main")
        invalid_variants = (
            dict(direct, risk_level="medium"),
            dict(direct, review_policy="final"),
            dict(direct, allowed_paths=["src/"]),
            dict(direct, allowed_paths=["a.py", "b.py", "c.py", "d.py"]),
            dict(
                direct,
                tasks=direct["tasks"]
                + [{"id": 2, "name": "Second", "steps": ["Edit"], "acceptance": ["Works"], "validation": ["pytest"]}],
            ),
        )
        for invalid in invalid_variants:
            with self.subTest(invalid=invalid):
                with self.assertRaises(module.NuclioError) as raised:
                    module.validate_plan_data(invalid)
                self.assertEqual(raised.exception.code, "DIRECT_EXECUTION_INELIGIBLE")

    def test_plan_rejects_duplicate_yaml_unsafe_paths_and_invalid_review_override(self):
        self.init_git()
        self.make_skeleton()
        change_dir = self.create_change()
        self.approve_spec(change_dir)
        plan = self.write_plan()
        plan.write_text(plan.read_text(encoding="utf-8") + "summary: duplicate\n", encoding="utf-8")
        duplicate = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertEqual(stderr_json(duplicate)["code"], "DUPLICATE_YAML_KEY")
        self.write_plan(allowed_paths=["../escape"])
        unsafe = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertEqual(stderr_json(unsafe)["code"], "INVALID_ALLOWED_PATH")
        self.write_plan(review="self", tasks=[{"id": 1, "name": "Alpha", "steps": ["Edit"], "acceptance": ["Works"], "validation": ["pytest"], "review": "task-and-final"}])
        override = run_change(self.root, "validate-plan", "--id", "alpha-change")
        self.assertEqual(stderr_json(override)["code"], "INVALID_SCHEMA")

    def test_init_state_tracks_spec_plan_and_state_without_precommit(self):
        change_dir = self.prepare_change()
        state = self.state(change_dir)
        self.assertNotIn("repo_root", state)
        self.assertEqual(state["approval_checkpoint"], git(self.root, "rev-parse", "HEAD").stdout.strip())
        changed = set(git(self.root, "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-r", "HEAD").stdout.splitlines())
        self.assertEqual(
            changed,
            {
                ".dev-docs/changes/alpha-change/change.md",
                ".dev-docs/changes/alpha-change/plan.yaml",
                ".dev-docs/changes/alpha-change/state.yaml",
            },
        )
        for name in ("change.md", "plan.yaml", "state.yaml"):
            self.assertEqual(git(self.root, "ls-files", f".dev-docs/changes/alpha-change/{name}").stdout.strip(), f".dev-docs/changes/alpha-change/{name}")

    def test_init_state_rejects_detached_head_and_dirty_index_without_state(self):
        self.init_git()
        self.make_skeleton()
        change_dir = self.create_change()
        self.approve_spec(change_dir)
        self.write_plan()
        git(self.root, "checkout", "--detach", "HEAD")
        detached = run_change(self.root, "init-state", "--id", "alpha-change")
        self.assertEqual(stderr_json(detached)["code"], "DETACHED_HEAD")
        self.assertFalse((change_dir / "state.yaml").exists())

        git(self.root, "switch", "-")
        (self.root / "README.md").write_text("dirty\n", encoding="utf-8")
        git(self.root, "add", "README.md")
        dirty = run_change(self.root, "init-state", "--id", "alpha-change")
        self.assertEqual(stderr_json(dirty)["code"], "DIRTY_INDEX")
        self.assertFalse((change_dir / "state.yaml").exists())

    def test_state_commands_fail_closed_on_branch_drift(self):
        change_dir = self.prepare_change()
        before = (change_dir / "state.yaml").read_text(encoding="utf-8")
        git(self.root, "switch", "-c", "drift")
        result = run_change(self.root, "status", "--id", "alpha-change")
        self.assertEqual(stderr_json(result)["code"], "BRANCH_DRIFT")
        self.assertEqual((change_dir / "state.yaml").read_text(encoding="utf-8"), before)

    def test_record_task_binds_commands_exit_codes_and_checkpoint_head(self):
        self.prepare_change()
        result = self.implement_task()
        state = self.state()
        self.assertEqual(state["tasks"][0]["executor"], "subagent")
        evidence = state["tasks"][0]["validation"]
        self.assertEqual(evidence["head"], result["checkpoint_commit"])
        self.assertEqual(evidence["commands"], [{"command": "python -m pytest", "exit_code": 0}])

    def test_next_action_and_start_task_derive_required_executor_from_plan(self):
        self.prepare_change()
        next_action = run_change(self.root, "next-action", "--id", "alpha-change")
        self.assertEqual(stdout_json(next_action)["required_executor"], "subagent")
        start = run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        self.assertEqual(stdout_json(start)["required_executor"], "subagent")
        self.assertEqual(self.state()["tasks"][0]["executor"], "subagent")

    def test_next_action_exposes_verified_task_handoff_facts(self):
        self.prepare_change()
        start = run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        start_payload = stdout_json(start)
        source = self.root / "src"
        source.mkdir()
        (source / "handoff.txt").write_text("unfinished\n", encoding="utf-8")

        result = run_change(self.root, "next-action", "--id", "alpha-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = stdout_json(result)
        self.assertEqual(payload["next_action"], "HALT")
        self.assertEqual(payload["in_progress_action"], "TASK")
        self.assertEqual(payload["task_id"], 1)
        self.assertEqual(payload["base"], start_payload["task_base"])
        self.assertEqual(payload["head"], start_payload["task_base"])
        self.assertEqual(payload["checkpoint_subject"], self.task_subject())
        self.assertEqual(payload["required_executor"], "subagent")
        self.assertTrue(payload["index_clean"])
        self.assertEqual(payload["dirty_allowed_paths"], ["src/handoff.txt"])

    def test_next_action_exposes_verified_repair_handoff_facts(self):
        self.prepare_change()
        self.implement_task()
        run_change(
            self.root,
            "record-review",
            "--id",
            "alpha-change",
            "--scope",
            "final",
            "--status",
            "FAIL",
            "--summary",
            "review failed",
            "--contract",
            "Acceptance Criteria",
            "--path",
            "src/alpha-change-task-1.txt",
            "--evidence",
            "missing behavior",
        )
        start = run_change(
            self.root,
            "start-repair",
            "--id",
            "alpha-change",
            "--source-gate",
            "RUN_FINAL_REVIEW",
            "--path",
            "src/alpha-change-task-1.txt",
            "--decision",
            "repair the reviewed defect",
            "--evidence",
            "missing behavior",
            "--contract-unchanged",
        )
        start_payload = stdout_json(start)
        (self.root / "src" / "alpha-change-task-1.txt").write_text("unfinished repair\n", encoding="utf-8")

        result = run_change(self.root, "next-action", "--id", "alpha-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = stdout_json(result)
        self.assertEqual(payload["next_action"], "HALT")
        self.assertEqual(payload["in_progress_action"], "REPAIR")
        self.assertEqual(payload["repair_id"], start_payload["repair_id"])
        self.assertEqual(payload["source_gate"], "RUN_FINAL_REVIEW")
        self.assertEqual(payload["base"], start_payload["repair_base"])
        self.assertEqual(payload["head"], start_payload["repair_base"])
        self.assertEqual(payload["checkpoint_subject"], start_payload["checkpoint_subject"])
        self.assertEqual(payload["required_executor"], "subagent")
        self.assertTrue(payload["index_clean"])
        self.assertEqual(payload["dirty_allowed_paths"], ["src/alpha-change-task-1.txt"])

    def test_direct_plan_records_main_executor_only_after_hard_gate(self):
        self.prepare_change(review="self", risk="low", execution_mode="direct", allowed_paths=["src/alpha-change-task-1.txt"])
        next_action = run_change(self.root, "next-action", "--id", "alpha-change")
        self.assertEqual(stdout_json(next_action)["required_executor"], "main")
        start = run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        self.assertEqual(stdout_json(start)["required_executor"], "main")
        self.assertEqual(self.state()["tasks"][0]["executor"], "main")

    def test_direct_repair_inherits_main_executor(self):
        self.prepare_change(review="self", risk="low", execution_mode="direct", allowed_paths=["src/alpha-change-task-1.txt"])
        self.implement_task()
        failed = run_change(
            self.root,
            "record-validation",
            "--id",
            "alpha-change",
            "--status",
            "FAIL",
            "--summary",
            "focused validation failed",
            "--command",
            "python -m unittest",
            "--exit-code",
            "1",
            "--path",
            "src/alpha-change-task-1.txt",
        )
        self.assertEqual(failed.returncode, 0, failed.stderr)
        repair = run_change(
            self.root,
            "start-repair",
            "--id",
            "alpha-change",
            "--source-gate",
            "RUN_VALIDATION",
            "--path",
            "src/alpha-change-task-1.txt",
            "--decision",
            "repair the localized defect",
            "--evidence",
            "focused validation failure",
            "--contract-unchanged",
        )
        self.assertEqual(repair.returncode, 0, repair.stderr)
        self.assertEqual(stdout_json(repair)["required_executor"], "main")
        self.assertEqual(self.state()["repair"]["executor"], "main")

    def test_state_backed_v1_plan_defaults_pending_task_to_subagent(self):
        self.init_git()
        self.make_skeleton()
        change_dir = self.create_change()
        self.approve_spec(change_dir)
        self.write_plan(v1=True)
        module = load_change_module()
        plan_path = change_dir / "plan.yaml"
        plan = module.validate_plan_file(plan_path, allow_legacy=True)
        state = {
            "schema_version": 1,
            "change_id": "alpha-change",
            "plan_revision": 1,
            "plan_sha256": module.sha256_file(plan_path),
            "spec_sha256": module.sha256_file(change_dir / "change.md"),
            "git_branch": git(self.root, "branch", "--show-current").stdout.strip(),
            "initial_head": git(self.root, "rev-parse", "HEAD").stdout.strip(),
            "approval_checkpoint": git(self.root, "rev-parse", "HEAD").stdout.strip(),
            "current_head": git(self.root, "rev-parse", "HEAD").stdout.strip(),
            "status": "ACTIVE",
            "phase": "READY",
            "current_task_id": None,
            "next_action": "DISPATCH_TASK",
            "tasks": module.initial_task_states(plan),
            "review": {"task_reviews": {}, "final": {"status": "PENDING"}},
            "validation": {"status": "PENDING", "head": None, "commands": [], "summary": None},
            "repair": None,
            "blocker": None,
        }
        module.dump_yaml_atomic(change_dir / "state.yaml", state)
        next_action = run_change(self.root, "next-action", "--id", "alpha-change")
        self.assertEqual(next_action.returncode, 0, next_action.stderr)
        self.assertEqual(stdout_json(next_action)["required_executor"], "subagent")

    def test_record_task_rejects_command_mismatch_and_nonzero_pass(self):
        self.prepare_change()
        run_change(self.root, "start-task", "--id", "alpha-change", "--task-id", "1")
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha.txt").write_text("alpha\n", encoding="utf-8")
        git(self.root, "add", "src/alpha.txt")
        git(self.root, "commit", "-m", self.task_subject())
        mismatch = run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "PASS", "--validation-summary", "ok", "--validation-command", "other", "--validation-exit-code", "0")
        self.assertEqual(stderr_json(mismatch)["code"], "VALIDATION_COMMAND_MISMATCH")
        nonzero = run_change(self.root, "record-task", "--id", "alpha-change", "--task-id", "1", "--validation-status", "PASS", "--validation-summary", "ok", "--validation-command", "python -m pytest", "--validation-exit-code", "1")
        self.assertEqual(stderr_json(nonzero)["code"], "INVALID_EVIDENCE")

    def test_task_and_final_reviews_bind_exact_ranges(self):
        self.prepare_change(review="task-and-final", risk="high")
        checkpoint = self.implement_task()["checkpoint_commit"]
        self.finish_product_gates(review="task-and-final")
        state = self.state()
        task_review = state["review"]["task_reviews"]["1"]
        self.assertEqual(task_review["reviewer"], "subagent")
        self.assertEqual(task_review["base"], state["tasks"][0]["task_base"])
        self.assertEqual(task_review["head"], checkpoint)
        self.assertEqual(state["review"]["final"]["base"], state["approval_checkpoint"])
        self.assertEqual(state["review"]["final"]["head"], state["current_head"])
        self.assertEqual(state["validation"]["head"], state["current_head"])

    def test_pass_review_requires_summary_or_evidence(self):
        self.prepare_change()
        self.implement_task()
        result = run_change(self.root, "record-review", "--id", "alpha-change", "--scope", "final", "--status", "PASS")
        self.assertEqual(stderr_json(result)["code"], "INVALID_EVIDENCE")

    def test_validation_fail_and_repair_invalidate_final_evidence(self):
        self.prepare_change()
        self.implement_task()
        final = run_change(self.root, "record-review", "--id", "alpha-change", "--scope", "final", "--status", "PASS", "--summary", "review passed")
        self.assertEqual(final.returncode, 0, final.stderr)
        failed = run_change(self.root, "record-validation", "--id", "alpha-change", "--status", "FAIL", "--summary", "integration failed", "--command", "python -m unittest", "--exit-code", "1", "--path", "src/task-1.txt", "--evidence", "trace")
        self.assertEqual(stdout_json(failed)["next_action"], "REQUEST_REPAIR_DECISION")
        start = run_change(self.root, "start-repair", "--id", "alpha-change", "--source-gate", "RUN_VALIDATION", "--path", "src/task-1.txt", "--decision", "fix integration", "--evidence", "trace", "--contract-unchanged")
        self.assertEqual(start.returncode, 0, start.stderr)
        payload = stdout_json(start)
        self.assertEqual(payload["required_executor"], "subagent")
        self.assertEqual(self.state()["repair"]["executor"], "subagent")
        (self.root / "src" / "task-1.txt").write_text("repaired\n", encoding="utf-8")
        git(self.root, "add", "src/task-1.txt")
        git(self.root, "commit", "-m", payload["checkpoint_subject"])
        record = run_change(self.root, "record-repair", "--id", "alpha-change", "--repair-id", "1", "--validation-status", "PASS", "--validation-summary", "closure passed", "--validation-command", "python -m unittest", "--validation-exit-code", "0")
        self.assertEqual(stdout_json(record)["next_action"], "RUN_FINAL_REVIEW")
        state = self.state()
        self.assertEqual(state["review"]["final"]["status"], "PENDING")
        self.assertEqual(state["validation"]["status"], "PENDING")

    def test_complete_requires_fresh_validation_and_knowledge_result(self):
        self.prepare_change(review="self")
        self.implement_task()
        self.finish_product_gates(review="self")
        missing = run_change(self.root, "complete", "--id", "alpha-change")
        self.assertNotEqual(missing.returncode, 0)
        applied_without_path = run_change(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "APPLIED")
        self.assertEqual(stderr_json(applied_without_path)["code"], "INVALID_KNOWLEDGE_RESULT")
        complete = self.complete_change()
        self.assertEqual(stdout_json(complete)["knowledge"], {"result": "NO_OP", "paths": []})
        self.assertEqual(self.state()["next_action"], "ARCHIVE")

    def test_complete_records_exact_confirmed_knowledge_paths(self):
        self.prepare_change(review="self")
        self.implement_task()
        self.finish_product_gates(review="self")
        knowledge_path = self.root / ".dev-docs" / "knowledge" / "engineering.md"
        knowledge_path.write_text("# Engineering Knowledge\n\nConfirmed alpha practice.\n", encoding="utf-8")
        wrong = run_change(self.root, "complete", "--id", "alpha-change", "--knowledge-result", "APPLIED", "--knowledge-path", "README.md")
        self.assertEqual(stderr_json(wrong)["code"], "INVALID_KNOWLEDGE_PATH")
        self.complete_change(knowledge_result="APPLIED", knowledge_paths=[".dev-docs/knowledge/engineering.md"])
        self.append_completion(knowledge="APPLIED: .dev-docs/knowledge/engineering.md")
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(archive.returncode, 0, archive.stderr)
        self.assert_archive_commit(extra_paths={".dev-docs/knowledge/engineering.md"})

    def test_archive_retains_complete_record_and_single_verified_commit(self):
        self.prepare_completed_change()
        before = git(self.root, "rev-parse", "HEAD").stdout.strip()
        result = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = stdout_json(result)
        self.assertEqual(payload["retained_artifacts"], ["change.md", "plan.yaml", "state.yaml"])
        archive_dir = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        self.assertFalse((self.root / ".dev-docs" / "changes" / "alpha-change").exists())
        self.assertEqual(sorted(path.name for path in archive_dir.iterdir()), ["change.md", "plan.yaml", "state.yaml"])
        self.assertEqual(git(self.root, "rev-parse", "HEAD^").stdout.strip(), before)
        self.assert_archive_commit()

    def test_archive_rejects_destructive_spec_rewrite_before_move(self):
        change_dir = self.prepare_completed_change()
        change = change_dir / "change.md"
        change.write_text(change.read_text(encoding="utf-8").replace("Alpha is required by the current product flow.", "Context was erased."), encoding="utf-8")
        result = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(stderr_json(result)["code"], "SPEC_HISTORY_DRIFT")
        self.assertTrue(change_dir.exists())

    def test_archive_rejects_missing_completion_section_and_unexpected_artifact(self):
        change_dir = self.prepare_completed_change()
        change = change_dir / "change.md"
        change.write_text(change.read_text(encoding="utf-8").replace("## Residual Risks\n\nNo known residual risks.\n", ""), encoding="utf-8")
        missing = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(stderr_json(missing)["code"], "INCOMPLETE_CHANGE_RECORD")
        self.append_completion()
        (change_dir / "notes.md").write_text("unexpected\n", encoding="utf-8")
        unexpected = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(stderr_json(unexpected)["code"], "UNEXPECTED_ARCHIVE_ARTIFACTS")

    def test_archive_rejects_symlink_artifact(self):
        change_dir = self.prepare_completed_change()
        state = change_dir / "state.yaml"
        external = self.root / "external-state.yaml"
        external.write_text(state.read_text(encoding="utf-8"), encoding="utf-8")
        state.unlink()
        state.symlink_to(external)
        result = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(stderr_json(result)["code"], "UNEXPECTED_ARCHIVE_ARTIFACTS")
        self.assertTrue(change_dir.exists())

    def test_archive_commit_failure_recovers_by_rerunning_same_command(self):
        self.prepare_completed_change()
        module = load_change_module()
        stderr = io.StringIO()
        with mock.patch.object(module, "git_commit", side_effect=module.NuclioError("GIT_ERROR", "simulated commit failure")):
            with contextlib.redirect_stderr(stderr):
                code = module.main(["--project-root", str(self.root), "archive", "--id", "alpha-change"])
        self.assertNotEqual(code, 0)
        target = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        self.assertEqual(sorted(path.name for path in target.iterdir()), ["change.md", "plan.yaml", "state.yaml"])
        recovered = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertTrue(stdout_json(recovered)["recovered"])
        self.assert_archive_commit()

    def test_archive_rerun_after_success_is_idempotent(self):
        self.prepare_completed_change()
        first = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(first.returncode, 0, first.stderr)
        head = git(self.root, "rev-parse", "HEAD").stdout.strip()
        second = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(stdout_json(second)["recovered"])
        self.assertEqual(git(self.root, "rev-parse", "HEAD").stdout.strip(), head)

    def test_archive_leaves_unrelated_dirty_files_unstaged(self):
        self.prepare_completed_change()
        (self.root / "unrelated.txt").write_text("user change\n", encoding="utf-8")
        result = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("?? unrelated.txt", git(self.root, "status", "--porcelain=v1").stdout)

    def test_archive_recovery_fails_closed_on_branch_drift(self):
        self.prepare_completed_change()
        module = load_change_module()
        with mock.patch.object(module, "git_commit", side_effect=module.NuclioError("GIT_ERROR", "stop after move")):
            with contextlib.redirect_stderr(io.StringIO()):
                module.main(["--project-root", str(self.root), "archive", "--id", "alpha-change"])
        git(self.root, "switch", "-c", "drift")
        result = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(stderr_json(result)["code"], "BRANCH_DRIFT")

    def test_supersede_rejects_active_successor(self):
        self.prepare_change()
        successor = self.root / ".dev-docs" / "changes" / "beta-change"
        successor.mkdir()
        successor.joinpath("change.md").write_text("---\nid: beta-change\n---\n", encoding="utf-8")
        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertEqual(stderr_json(result)["code"], "SUCCESSOR_NOT_ARCHIVED")

    def test_supersede_accepts_committed_legacy_archive_with_backlink(self):
        self.prepare_change()
        self.create_legacy_archived_successor()
        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.state()
        self.assertEqual(state["next_action"], "ARCHIVE_SUPERSEDED")
        self.assertEqual(state["superseded_by"]["successor_location"], "archive")

    def test_supersede_accepts_complete_archived_successor_with_verified_commit(self):
        self.prepare_change()
        self.create_complete_archived_successor()
        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state()["superseded_by"]["successor_id"], "beta-change")

    def test_supersede_rejects_complete_successor_with_forged_archive_commit(self):
        change_dir = self.prepare_change()
        archive_dir = self.create_complete_archived_successor()
        state_path = archive_dir / "state.yaml"
        state_path.write_text(state_path.read_text(encoding="utf-8") + "tampered_after_archive: true\n", encoding="utf-8")
        git(self.root, "add", state_path.relative_to(self.root).as_posix())
        git(self.root, "commit", "-m", "archive(beta-change): retain complete change record")
        before = (change_dir / "state.yaml").read_text(encoding="utf-8")
        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertEqual(stderr_json(result)["code"], "SUCCESSOR_INCOMPLETE")
        self.assertEqual((change_dir / "state.yaml").read_text(encoding="utf-8"), before)

    def test_supersede_rejects_missing_backlink_without_state_change(self):
        change_dir = self.prepare_change()
        self.create_legacy_archived_successor(backlink=False)
        before = (change_dir / "state.yaml").read_text(encoding="utf-8")
        result = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertEqual(stderr_json(result)["code"], "RELATED_CHANGE_MISSING")
        self.assertEqual((change_dir / "state.yaml").read_text(encoding="utf-8"), before)

    def test_superseded_record_preserves_spec_and_archives_complete_directory(self):
        self.prepare_change()
        self.create_legacy_archived_successor()
        supersede = run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.assertEqual(supersede.returncode, 0, supersede.stderr)
        self.append_completion(
            outcome="Alpha was superseded and taken over by beta-change; unfinished scope moved to the successor.",
            validation="Original acceptance was not fully validated and was not a complete success.",
            related_changes=["beta-change"],
        )
        archive = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(archive.returncode, 0, archive.stderr)
        self.assertEqual(stdout_json(archive)["retained_artifacts"], ["change.md", "plan.yaml", "state.yaml"])
        self.assert_archive_commit()

    def test_superseded_record_cannot_claim_full_old_acceptance(self):
        change_dir = self.prepare_change()
        self.create_legacy_archived_successor()
        run_change(self.root, "supersede", "--id", "alpha-change", "--successor-id", "beta-change")
        self.append_completion(
            outcome="Alpha was superseded and taken over by beta-change; unfinished scope moved to the successor.",
            validation="All original acceptance criteria fully passed successfully.",
            related_changes=["beta-change"],
        )
        result = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(stderr_json(result)["code"], "UNDISTILLED_RECORD")
        self.assertTrue(change_dir.exists())

    def test_show_supports_new_archive_and_reports_missing_legacy_artifact(self):
        self.prepare_completed_change()
        run_change(self.root, "archive", "--id", "alpha-change")
        state = run_change(self.root, "show", "--id", "alpha-change", "--archived", "--artifact", "state")
        self.assertEqual(state.returncode, 0, state.stderr)

        legacy = self.root / ".dev-docs" / "changes" / "archive" / "legacy-change"
        legacy.mkdir()
        legacy.joinpath("change.md").write_text("# Legacy\n", encoding="utf-8")
        missing = run_change(self.root, "show", "--id", "legacy-change", "--archived", "--artifact", "plan")
        self.assertEqual(stderr_json(missing)["code"], "MISSING_ARTIFACT")

    def test_legacy_move_preserves_clear_v1_tree(self):
        self.init_git()
        old = self.root / ".dev-docs"
        (old / "changes" / "old-change").mkdir(parents=True)
        (old / "changes" / "old-change" / "state.json").write_text('{"phase":"old"}\n', encoding="utf-8")
        result = run_change(self.root, "legacy-move")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / ".dev-docs" / "legacy" / "v1" / "changes" / "old-change" / "state.json").read_text(encoding="utf-8"), '{"phase":"old"}\n')
        self.assertTrue((self.root / ".dev-docs" / "changes" / "archive").is_dir())


if __name__ == "__main__":
    unittest.main()
