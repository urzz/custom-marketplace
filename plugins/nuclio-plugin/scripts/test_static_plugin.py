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
IMPLEMENTER = PLUGIN / "agents" / "task-implementer.md"
REVIEWER = PLUGIN / "agents" / "readonly-reviewer.md"
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
            {"schema_version", "change_id", "revision", "risk_level", "review_policy", "execution", "summary", "allowed_paths", "tasks"},
        )
        self.assertEqual(assignment_literal(self.tree, "EXECUTION_KEYS"), {"mode", "rationale"})
        self.assertEqual(
            assignment_literal(self.tree, "TASK_REQUIRED_KEYS"),
            {"id", "name", "steps", "acceptance", "validation"},
        )
        self.assertEqual(assignment_literal(self.tree, "TASK_OPTIONAL_KEYS"), {"review"})
        for forbidden in ("owner", "owners", "depends_on", "requirements", "fix_budget", "behavioral_eval_owner"):
            self.assertNotIn(f'"{forbidden}"', self.source)
        self.assertNotIn('start_task.add_argument("--executor"', self.source)

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
            "direct_execution_requires",
            "derive_required_executor",
            "verified_task_handoff_facts",
            "v1_plan_defaults_pending_task_to_subagent",
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
        self.assertIn("execution.mode", combined)
        self.assertIn("不得静默回退", combined)

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

    def test_knowledge_closeout_uses_one_result_oriented_decision(self):
        work = read(WORK)
        knowledge = read(REFERENCES / "knowledge.md")
        workflow = read(REFERENCES / "workflow.md")
        combined = "\n".join((work, knowledge, workflow))
        for required in (
            "AskUserQuestion",
            "如何处理以上知识候选并完成本次 change？",
            "写入并归档（推荐）",
            "跳过并归档",
            "不得要求固定口令",
            "不得再次请求归档确认",
        ):
            self.assertIn(required, combined)
        self.assertIn("无合格候选时不要显示这些选项", knowledge)
        self.assertNotIn("接受知识更新", combined)
        self.assertNotIn("不写知识，直接归档", combined)

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

    def test_eval_prompts_keep_twenty_named_cases(self):
        text = read(REFERENCES / "eval-prompts.md")
        cases = re.findall(r"^###\s+(\d+)\.\s+", text, flags=re.M)
        self.assertEqual(cases, [str(index) for index in range(1, 21)])


class AgentContractTests(unittest.TestCase):
    def test_named_agents_have_exact_tool_allowlists(self):
        implementer_frontmatter = read(IMPLEMENTER).split("---\n", 2)[1]
        reviewer_frontmatter = read(REVIEWER).split("---\n", 2)[1]
        implementer_tools = re.search(r"^tools:\s*(.+)$", implementer_frontmatter, flags=re.M)
        reviewer_tools = re.search(r"^tools:\s*(.+)$", reviewer_frontmatter, flags=re.M)
        self.assertIsNotNone(implementer_tools)
        self.assertIsNotNone(reviewer_tools)
        self.assertIn("name: task-implementer", implementer_frontmatter)
        self.assertIn("name: readonly-reviewer", reviewer_frontmatter)
        self.assertEqual(
            [item.strip() for item in implementer_tools.group(1).split(",")],
            ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        )
        self.assertEqual(
            [item.strip() for item in reviewer_tools.group(1).split(",")],
            ["Read", "Grep", "Glob", "Bash"],
        )

    def test_named_agents_block_recursive_composition_and_worktrees(self):
        for source in (read(IMPLEMENTER), read(REVIEWER)):
            for required in (
                "不调用 Agent、Skill、Workflow、Task",
                "`/code-review`",
                "Claude/Codex CLI",
                "MCP",
                "worktree",
            ):
                self.assertIn(required, source)
        self.assertIn("创建恰好一个", read(IMPLEMENTER))
        self.assertIn("不调用 `change.py`", read(IMPLEMENTER))
        self.assertIn("不得修改产品、Git 或 Nuclio State", read(REVIEWER))

    def test_named_agents_constrain_bash_usage(self):
        implementer = read(IMPLEMENTER)
        reviewer = read(REVIEWER)
        self.assertIn("## Bash Allowlist", implementer)
        self.assertIn("git add -- <exact approved paths>", implementer)
        self.assertIn("git commit -m <expected subject>", implementer)
        self.assertIn("rm -- <exact approved file paths>", implementer)
        self.assertIn("不使用递归选项、目录目标或 glob", implementer)
        self.assertIn("## Bash Allowlist", reviewer)
        self.assertIn("Bash 只允许", reviewer)
        self.assertIn("不使用 shell 重定向、管道、命令替换", reviewer)

    def test_named_agent_dispatch_distinguishes_task_and_repair(self):
        implementer = read(IMPLEMENTER)
        reviewer = read(REVIEWER)
        self.assertIn("`TASK` 提供 Task id，`REPAIR` 提供 repair id 与 source gate", implementer)
        self.assertIn("精确 closure validation commands", implementer)
        self.assertIn("`TASK` 的 validation commands 以 Plan 为准", implementer)
        self.assertIn("Task id 与 helper 派生的 expected checkpoint subject", reviewer)

    def test_implementer_supports_only_verified_bounded_handoff(self):
        implementer = read(IMPLEMENTER)
        self.assertIn("DONE | HANDOFF | BLOCKED | NEEDS_CONTEXT", implementer)
        self.assertIn("`NEEDS_CONTEXT` 只能在首次产品写入前返回", implementer)
        self.assertIn("validation FAIL 是当前实施动作的反馈", implementer)
        self.assertIn("HEAD 等于 base", implementer)
        self.assertIn("index 为空", implementer)
        self.assertIn("continuation: HANDOFF", implementer)
        self.assertIn("dirty_allowed_paths", implementer)

    def test_work_routes_only_to_named_agents_with_bounded_handoff(self):
        work = read(WORK)
        workflow = read(REFERENCES / "workflow.md")
        context = read(REFERENCES / "context-hygiene.md")
        combined = "\n".join((work, workflow, context))
        for required in (
            "nuclio:task-implementer",
            "nuclio:readonly-reviewer",
            "只允许一次 agent dispatch",
            "不自动重试",
            "不改由 generic subagent",
            "一次 fresh `nuclio:task-implementer`",
            "不再次调用 `start-task`/`start-repair`",
            "不要求用户重复批准",
            "错误返回 `NEEDS_CONTEXT`",
            "agent 状态文本不能覆盖 Git 事实",
            "再次未完成",
            "失败或中断的 review",
        ):
            self.assertIn(required, combined)


class PackageSyncTests(unittest.TestCase):
    def test_manifest_marketplace_and_repository_docs_are_synced(self):
        plugin = json.loads(read(PLUGIN / ".claude-plugin" / "plugin.json"))
        marketplace = json.loads(read(ROOT / ".claude-plugin" / "marketplace.json"))
        entry = next(item for item in marketplace["plugins"] if item["name"] == "nuclio")
        self.assertEqual(plugin["name"], "nuclio")
        self.assertEqual(plugin["version"], "4.2.3")
        self.assertEqual(entry["source"], "./plugins/nuclio-plugin")
        for text in (plugin["description"], entry["description"], read(ROOT / "README.md"), read(ROOT / "CLAUDE.md")):
            self.assertIn("4.2.3", text)
            self.assertIn("plan.yaml", text)
            self.assertIn("state.yaml", text)


if __name__ == "__main__":
    unittest.main()
