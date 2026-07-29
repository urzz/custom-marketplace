"""Focused static contracts for the Nuclio plugin package."""

import ast
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
ROOT = PLUGIN.parents[1]
CHANGE = PLUGIN / "scripts" / "change.py"
BEHAVIOR_TESTS = PLUGIN / "scripts" / "test_change.py"
WORK = PLUGIN / "skills" / "work" / "SKILL.md"
INIT = PLUGIN / "skills" / "init" / "SKILL.md"
REFERENCES = PLUGIN / "references"
RUNTIME_DOCS = [
    WORK,
    INIT,
    REFERENCES / "workflow.md",
    REFERENCES / "change-format.md",
    REFERENCES / "knowledge.md",
    REFERENCES / "context-hygiene.md",
    REFERENCES / "eval-prompts.md",
]


def read(path):
    return path.read_text(encoding="utf-8")


def assignment_literal(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"missing assignment: {name}")


class RuntimeHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = read(CHANGE)
        cls.tree = ast.parse(cls.source)

    def test_helper_exposes_one_plan_state_lifecycle(self):
        result = subprocess.run(
            [sys.executable, str(CHANGE), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("create", "validate-plan", "init-state", "status", "next-action", "record-task", "complete", "supersede", "archive"):
            self.assertIn(command, result.stdout)
        self.assertNotIn("set-status", result.stdout)

    def test_canonical_plan_schema_is_minimal(self):
        self.assertEqual(
            assignment_literal(self.tree, "PLAN_TOP_KEYS"),
            {"schema_version", "change_id", "revision", "risk_level", "review_policy", "summary", "allowed_paths", "tasks"},
        )
        self.assertEqual(
            assignment_literal(self.tree, "TASK_REQUIRED_KEYS"),
            {"id", "name", "steps", "acceptance", "validation"},
        )
        self.assertEqual(assignment_literal(self.tree, "TASK_OPTIONAL_KEYS"), {"review"})
        for forbidden in ("owner", "owners", "depends_on", "requirements", "fix_budget", "behavioral_eval_owner"):
            self.assertNotIn(f'"{forbidden}"', self.source)

    def test_archive_retains_complete_record_without_pruning(self):
        self.assertIn('ARCHIVE_ACTIVE_ARTIFACTS = ("change.md", "plan.yaml", "state.yaml")', self.source)
        self.assertIn("ARCHIVE_RETAINED_ARTIFACTS = ARCHIVE_ACTIVE_ARTIFACTS", self.source)
        self.assertIn("retain complete change record", self.source)
        for removed in (
            "def write_archive_pending_state",
            "def prune_archive_execution_artifacts",
            "ARCHIVE_PRUNE_FAILED",
            "ARCHIVE_FINAL_PRUNE_FAILED",
        ):
            self.assertNotIn(removed, self.source)

    def test_helper_mechanically_binds_identity_and_evidence(self):
        for required in (
            "approval_checkpoint",
            "VALIDATION_COMMAND_MISMATCH",
            "VALIDATION_EVIDENCE_STALE",
            "REVIEW_EVIDENCE_STALE",
            "knowledge_result",
            "NEXT_ARCHIVE",
            "SPEC_HISTORY_DRIFT",
            "SUCCESSOR_NOT_ARCHIVED",
            "merge-base",
        ):
            self.assertIn(required, self.source)
        self.assertNotIn('"repo_root"', self.source)

    def test_helper_uses_only_standard_library_and_pyyaml(self):
        imports = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        allowed = {
            "__future__",
            "argparse",
            "datetime",
            "hashlib",
            "json",
            "os",
            "re",
            "shutil",
            "subprocess",
            "sys",
            "tempfile",
            "dataclasses",
            "pathlib",
            "typing",
            "yaml",
        }
        self.assertEqual(imports - allowed, set())

    def test_behavior_suite_covers_real_workflows(self):
        source = read(BEHAVIOR_TESTS)
        tests = re.findall(r"^    def (test_[a-z0-9_]+)\(", source, flags=re.M)
        self.assertGreaterEqual(len(tests), 25)
        for behavior in (
            "without_precommit",
            "commands_exit_codes",
            "invalidate_final_evidence",
            "knowledge_paths",
            "retains_complete_record",
            "recovers_by_rerunning",
            "rejects_active_successor",
        ):
            self.assertTrue(any(behavior in test for test in tests), behavior)


class MarkdownContractTests(unittest.TestCase):
    def test_skill_frontmatter_and_one_level_references(self):
        for path, name in ((WORK, "work"), (INIT, "init")):
            text = read(path)
            self.assertTrue(text.startswith("---\n"))
            frontmatter = text.split("---\n", 2)[1]
            self.assertIn(f"name: {name}", frontmatter)
            self.assertIn("disable-model-invocation: true", frontmatter)
        work = read(WORK)
        for name in ("workflow", "change-format", "knowledge", "context-hygiene"):
            self.assertRegex(work, rf"\.\./\.\./references/{name}\.md")
        for reference in REFERENCES.glob("*.md"):
            self.assertNotRegex(read(reference), r"\]\([^)]*/references/[^)]+\.md\)")

    def test_runtime_docs_describe_the_canonical_complete_archive(self):
        combined = "\n".join(read(path) for path in RUNTIME_DOCS)
        for required in (
            "approval checkpoint",
            "knowledge.result",
            "next_action: ARCHIVE",
            "Residual Risks",
            "plan.yaml",
            "state.yaml",
            "完整",
        ):
            self.assertIn(required, combined)
        self.assertIn("successor", combined)
        self.assertIn("archive", combined)

    def test_current_docs_do_not_promise_one_file_pruning(self):
        combined = "\n".join(read(path) for path in RUNTIME_DOCS)
        forbidden = (
            "archive 后只保留 `change.md`",
            "archive 目录只保留 `change.md`",
            "pruning active execution artifacts",
            "retain distilled change record",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, combined)

    def test_runtime_docs_keep_forbidden_architecture_out(self):
        combined = "\n".join(read(path) for path in RUNTIME_DOCS)
        for forbidden in (
            "workflow.py",
            "DAG scheduler",
            "parallel product write",
            "owner routing",
            "automatic fixer",
            "archive manifest",
            "hidden archive backup",
        ):
            self.assertIn(forbidden, combined)

    def test_eval_prompts_keep_eighteen_named_cases(self):
        text = read(REFERENCES / "eval-prompts.md")
        cases = re.findall(r"^###\s+(\d+)\.\s+", text, flags=re.M)
        self.assertEqual(cases, [str(index) for index in range(1, 19)])


class PackageSyncTests(unittest.TestCase):
    def test_manifest_marketplace_and_repository_docs_are_synced(self):
        plugin = json.loads(read(PLUGIN / ".claude-plugin" / "plugin.json"))
        marketplace = json.loads(read(ROOT / ".claude-plugin" / "marketplace.json"))
        entry = next(item for item in marketplace["plugins"] if item["name"] == "nuclio")
        self.assertEqual(plugin["name"], "nuclio")
        self.assertEqual(plugin["version"], "4.1.0")
        self.assertEqual(entry["source"], "./plugins/nuclio-plugin")
        for text in (plugin["description"], entry["description"], read(ROOT / "README.md"), read(ROOT / "CLAUDE.md")):
            self.assertIn("4.1.0", text)
            self.assertIn("plan.yaml", text)
            self.assertIn("state.yaml", text)


if __name__ == "__main__":
    unittest.main()
