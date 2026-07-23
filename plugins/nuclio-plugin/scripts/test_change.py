"""
Nuclio v2 change helper behavior tests.

## Contents
- [Test harness](#test-harness)
- [Create/list/show/status/archive coverage](#createlistshowstatusarchive-coverage)
- [Legacy move coverage](#legacy-move-coverage)
"""

import contextlib
import importlib.util
import io
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
        "Active changes live in `.dev-docs/changes/<change-id>/change.md`.\n"
        "\n"
        "Completed changes move to `.dev-docs/changes/archive/<change-id>/change.md`.\n"
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
        "This file records confirmed build, test, release, collaboration, and code practice knowledge that remains useful across changes.\n"
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

    def create_change(self, change_id="alpha-change", title="Alpha Change", goal="Ship alpha"):
        self.make_v2_skeleton()
        result = run_change(self.root, "create", "--id", change_id, "--title", title, "--goal", goal)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.root / ".dev-docs" / "changes" / change_id / "change.md"

    def test_main_and_subcommand_help_expose_exact_six_commands(self):
        main = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(main.returncode, 0, main.stderr)
        for command in ("create", "list", "show", "set-status", "archive", "legacy-move"):
            self.assertIn(command, main.stdout)
            sub = subprocess.run(
                [sys.executable, str(SCRIPT), command, "--help"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(sub.returncode, 0, sub.stderr)
        for forbidden in (
            "next-action", "approve", "packet", "evidence", "validate-schema",
            "finish", "dispatch", "import-review", "authorize-fix",
        ):
            self.assertNotIn(forbidden, main.stdout)

    def test_create_writes_only_change_markdown_and_no_json(self):
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
        docs = self.root / ".dev-docs"
        change = docs / "changes" / "alpha-change" / "change.md"
        self.assertTrue(change.exists())
        text = change.read_text(encoding="utf-8")
        self.assertIn("id: alpha-change", text)
        self.assertIn("status: active", text)
        self.assertIn("created: 2026-07-23", text)
        self.assertIn("updated: 2026-07-23", text)
        self.assertIn("related_changes: prior-change", text)
        self.assertIn("# Alpha Change", text)
        self.assertIn("## Goal\n\nShip alpha", text)
        self.assertIn("## Current State", text)
        self.assertEqual([p.relative_to(docs) for p in docs.rglob("*.json")], [])
        self.assertFalse((docs / "changes" / "index.md").exists())
        self.assertEqual([p.name for p in (docs / "changes" / "alpha-change").iterdir()], ["change.md"])

    def test_create_rejects_all_illegal_ids(self):
        self.make_v2_skeleton()
        illegal_ids = [
            "", "Alpha", "alpha_change", "alpha change", "alpha/change", "alpha\\change",
            "/alpha", "../alpha", "alpha..beta", "alpha*beta", "alpha?beta", "alpha[beta",
            "-alpha", "alpha-", "alpha--beta", ".", "..",
        ]
        for bad_id in illegal_ids:
            with self.subTest(bad_id=bad_id):
                before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
                result = run_change(self.root, "create", "--id", bad_id, "--title", "Bad", "--goal", "Bad")
                self.assertNotEqual(result.returncode, 0)
                after = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
                self.assertEqual(after, before)

    def test_create_rejects_active_or_archive_duplicate(self):
        self.make_v2_skeleton()
        active = self.root / ".dev-docs" / "changes" / "alpha-change"
        active.mkdir()
        first = run_change(self.root, "create", "--id", "alpha-change", "--title", "A", "--goal", "A")
        self.assertNotEqual(first.returncode, 0)
        shutil.rmtree(active)
        archived = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        archived.mkdir()
        second = run_change(self.root, "create", "--id", "alpha-change", "--title", "A", "--goal", "A")
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(list((self.root / ".dev-docs" / "changes").glob("alpha-change*")), [])

    def test_list_excludes_archive_and_tolerates_malformed(self):
        self.create_change("alpha-change", "Alpha Change", "Ship alpha")
        malformed_dir = self.root / ".dev-docs" / "changes" / "broken-change"
        malformed_dir.mkdir()
        (malformed_dir / "change.md").write_text("---\nid: broken-change\nstatus: active\n# missing close\n", encoding="utf-8")
        archive_dir = self.root / ".dev-docs" / "changes" / "archive" / "old-change"
        archive_dir.mkdir(parents=True)
        (archive_dir / "change.md").write_text("# Old\n", encoding="utf-8")
        result = run_change(self.root, "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("alpha-change\tactive\tAlpha Change\t.dev-docs/changes/alpha-change/change.md", result.stdout)
        self.assertIn("broken-change\tunknown\tunknown\t.dev-docs/changes/broken-change/change.md", result.stdout)
        self.assertNotIn("old-change", result.stdout)

    def test_list_omits_active_symlink_escaping_project_root(self):
        self.make_v2_skeleton()
        with tempfile.TemporaryDirectory() as external_tmp:
            external = Path(external_tmp) / "linked-change"
            external.mkdir()
            (external / "change.md").write_text(
                "---\nid: linked-change\nstatus: active\n---\n\n# Outside Title\n",
                encoding="utf-8",
            )
            (self.root / ".dev-docs" / "changes" / "linked-change").symlink_to(external, target_is_directory=True)
            result = run_change(self.root, "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("linked-change", result.stdout)
        self.assertNotIn("Outside Title", result.stdout)

    def test_show_active_and_archived(self):
        change = self.create_change("alpha-change", "Alpha Change", "Ship alpha")
        active = run_change(self.root, "show", "--id", "alpha-change")
        self.assertEqual(active.returncode, 0, active.stderr)
        self.assertEqual(active.stdout, change.read_text(encoding="utf-8"))
        archive_dir = self.root / ".dev-docs" / "changes" / "archive" / "old-change"
        archive_dir.mkdir(parents=True)
        archived_change = archive_dir / "change.md"
        archived_change.write_text("# Old\n", encoding="utf-8")
        missing_active = run_change(self.root, "show", "--id", "old-change")
        self.assertNotEqual(missing_active.returncode, 0)
        archived = run_change(self.root, "show", "--id", "old-change", "--archived")
        self.assertEqual(archived.returncode, 0, archived.stderr)
        self.assertEqual(archived.stdout, "# Old\n")

    def test_set_status_preserves_body_and_extra_frontmatter(self):
        change = self.create_change("alpha-change", "Alpha Change", "Ship alpha")
        original = change.read_text(encoding="utf-8")
        change.write_text(original.replace("updated: ", "owner: human\nupdated: ") + "\nTail text\n", encoding="utf-8")
        result = run_change(self.root, "set-status", "--id", "alpha-change", "--status", "completed", "--date", "2026-07-23")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = change.read_text(encoding="utf-8")
        self.assertIn("status: completed", text)
        self.assertIn("updated: 2026-07-23", text)
        self.assertIn("owner: human", text)
        self.assertIn("Tail text\n", text)
        self.assertNotIn("status: active", text)

    def test_set_status_malformed_has_no_side_effect(self):
        change = self.create_change("alpha-change", "Alpha Change", "Ship alpha")
        change.write_text("---\nid: alpha-change\nstatus: active\nstatus: completed\n---\n# Bad\n", encoding="utf-8")
        before = change.read_text(encoding="utf-8")
        result = run_change(self.root, "set-status", "--id", "alpha-change", "--status", "completed")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(change.read_text(encoding="utf-8"), before)

    def test_archive_only_accepts_completed_and_conflict_has_no_side_effect(self):
        change = self.create_change("alpha-change", "Alpha Change", "Ship alpha")
        active_result = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(active_result.returncode, 0)
        self.assertTrue(change.exists())
        run_change(self.root, "set-status", "--id", "alpha-change", "--status", "completed")
        conflict = self.root / ".dev-docs" / "changes" / "archive" / "alpha-change"
        conflict.mkdir(parents=True)
        conflict_result = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertNotEqual(conflict_result.returncode, 0)
        self.assertTrue(change.exists())
        shutil.rmtree(conflict)
        ok = run_change(self.root, "archive", "--id", "alpha-change")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertFalse((self.root / ".dev-docs" / "changes" / "alpha-change").exists())
        self.assertTrue((self.root / ".dev-docs" / "changes" / "archive" / "alpha-change" / "change.md").exists())
        self.assertFalse((self.root / ".dev-docs" / "changes" / "index.md").exists())

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
        v2_json = [
            p.relative_to(self.root / ".dev-docs")
            for p in (self.root / ".dev-docs").rglob("*.json")
            if "legacy/v1" not in p.relative_to(self.root / ".dev-docs").as_posix()
        ]
        self.assertEqual(v2_json, [])

    def test_legacy_move_fails_closed_for_v2_unknown_conflict_and_targets(self):
        self.make_v2_skeleton()
        v2_result = run_change(self.root, "legacy-move")
        self.assertNotEqual(v2_result.returncode, 0)
        shutil.rmtree(self.root / ".dev-docs")
        (self.root / ".dev-docs" / "changes" / "mystery").mkdir(parents=True)
        unknown = run_change(self.root, "legacy-move")
        self.assertNotEqual(unknown.returncode, 0)
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
        shutil.rmtree(self.root / ".dev-docs")
        (self.root / ".dev-docs" / "changes" / "old-change").mkdir(parents=True)
        (self.root / ".dev-docs" / "changes" / "old-change" / "state.json").write_text("{}\n", encoding="utf-8")
        (self.root / ".dev-docs-v1-legacy-tmp").mkdir()
        tmp_conflict = run_change(self.root, "legacy-move")
        self.assertNotEqual(tmp_conflict.returncode, 0)
        shutil.rmtree(self.root / ".dev-docs-v1-legacy-tmp")
        (self.root / ".dev-docs" / "legacy" / "v1").mkdir(parents=True)
        legacy_conflict = run_change(self.root, "legacy-move")
        self.assertNotEqual(legacy_conflict.returncode, 0)

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
        self.assertIn(".dev-docs exists=", stderr.getvalue())
        self.assertIn(".dev-docs-v1-legacy-tmp exists=", stderr.getvalue())
        self.assertIn(".dev-docs/legacy/v1 exists=", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
