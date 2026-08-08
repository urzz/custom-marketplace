"""High-value static contracts for the Nuclio v3 Claude Code plugin."""

import ast
import json
import re
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
ROOT = PLUGIN.parents[1]
RUNTIME = PLUGIN / "scripts" / "change.py"
WORK = PLUGIN / "skills" / "work" / "SKILL.md"
INIT = PLUGIN / "skills" / "init" / "SKILL.md"
REVIEWER = PLUGIN / "agents" / "readonly-reviewer.md"
REFERENCES = PLUGIN / "references"
AUTHORITY = (
    RUNTIME,
    WORK,
    INIT,
    REVIEWER,
    REFERENCES / "workflow.md",
    REFERENCES / "change-format.md",
    REFERENCES / "knowledge.md",
    REFERENCES / "context-hygiene.md",
    REFERENCES / "eval-prompts.md",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def literal(source: str, name: str):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"missing assignment: {name}")


def frontmatter(path: Path) -> str:
    text = read(path)
    if not text.startswith("---\n"):
        raise AssertionError(f"missing frontmatter: {path}")
    return text.split("---\n", 2)[1]


class V3RuntimeContracts(unittest.TestCase):
    def test_runtime_has_only_v3_commands_and_artifacts(self):
        source = read(RUNTIME)
        self.assertEqual(
            literal(source, "COMMANDS"),
            ("create", "approve", "status", "record-check", "verify", "complete", "archive"),
        )
        self.assertEqual(literal(source, "ARTIFACTS"), ("change.md", "delivery.yaml", "state.yaml"))
        for legacy_command in ("validate-plan", "init-state", "next-action", "record-task", "supersede"):
            self.assertNotIn(f'"{legacy_command}"', source)

    def test_v2_active_input_is_rejected_without_archive_compatibility(self):
        source = read(RUNTIME)
        self.assertIn('if (directory / "plan.yaml").exists()', source)
        self.assertIn('NuclioError("V2_ACTIVE_UNSUPPORTED"', source)
        self.assertNotIn("legacy compatibility", source.lower())

    def test_knowledge_result_paths_have_exact_contract(self):
        change_format = read(REFERENCES / "change-format.md")
        self.assertIn("`NO_OP|REJECTED` 不带路径", change_format)
        self.assertIn("`APPLIED|PARTIAL` 必须给出与当前 dirty knowledge 路径精确一致", change_format)
        self.assertNotIn("前两种无路径", change_format)
        source = read(RUNTIME)
        self.assertIn('args.knowledge_result in {"NO_OP", "REJECTED"} and knowledge', source)
        self.assertIn('args.knowledge_result in {"APPLIED", "PARTIAL"} and not knowledge', source)


class ClaudeCodeContracts(unittest.TestCase):
    def test_skills_are_explicit_and_work_uses_portable_paths(self):
        for path, name in ((INIT, "init"), (WORK, "work")):
            metadata = frontmatter(path)
            self.assertIn(f"name: {name}", metadata)
            self.assertIn("disable-model-invocation: true", metadata)
            self.assertIn("只能由用户显式调用", read(path))
        work = read(WORK)
        self.assertIn('"${CLAUDE_SKILL_DIR}/../../scripts/change.py"', work)
        self.assertIn('"${CLAUDE_PROJECT_DIR}"', work)
        self.assertIn("Marketplace cache 始终只读", work)

    def test_reviewer_is_the_only_agent_and_is_exactly_read_only(self):
        self.assertFalse((PLUGIN / "agents" / "task-implementer.md").exists())
        metadata = frontmatter(REVIEWER)
        tools = re.search(r"^tools:\s*(.+)$", metadata, flags=re.M)
        self.assertIsNotNone(tools)
        self.assertEqual([item.strip() for item in tools.group(1).split(",")], ["Read", "Grep", "Glob"])
        reviewer = read(REVIEWER)
        for boundary in ("不运行 shell", "不创建、编辑、删除", "不调用 Skill、Agent、Task、Workflow", "只返回 findings"):
            self.assertIn(boundary, reviewer)

    def test_authority_has_no_v2_execution_protocol(self):
        combined = "\n".join(read(path) for path in AUTHORITY)
        for forbidden in ("allowed_paths", "execution.mode", "task-implementer", "validate-plan", "init-state", "record-task", "supersede"):
            self.assertNotIn(forbidden, combined)

    def test_knowledge_is_index_first_in_each_lifecycle_phase(self):
        for path in (WORK, REFERENCES / "workflow.md", REFERENCES / "knowledge.md", REFERENCES / "context-hygiene.md"):
            self.assertIn(".dev-docs/index.md", read(path))
        context = read(REFERENCES / "context-hygiene.md")
        for phase in ("Shape", "Build / recovery", "Verify", "Finish"):
            self.assertIn(phase, context)

    def test_change_contract_is_concise_but_information_complete(self):
        work = read(WORK)
        change_format = read(REFERENCES / "change-format.md")
        eval_prompts = read(REFERENCES / "eval-prompts.md")
        self.assertIn("`create` 的单行参数只是种子", work)
        self.assertIn("精简不等于单句", work)
        self.assertIn("精简不等于单句", change_format)
        self.assertIn("验证所绑定的 HEAD", change_format)
        self.assertIn("不直接批准只有单句概括的草稿", eval_prompts)


class PackageSyncContracts(unittest.TestCase):
    def test_v3_metadata_and_repository_docs_are_synced(self):
        plugin = json.loads(read(PLUGIN / ".claude-plugin" / "plugin.json"))
        marketplace = json.loads(read(ROOT / ".claude-plugin" / "marketplace.json"))
        entry = next(item for item in marketplace["plugins"] if item["name"] == "nuclio")
        self.assertEqual(plugin["name"], "nuclio")
        self.assertEqual(plugin["version"], "5.0.0")
        self.assertEqual(entry["source"], "./plugins/nuclio-plugin")
        self.assertEqual(entry["description"], plugin["description"])
        readme = read(ROOT / "README.md")
        nuclio_rules = read(ROOT / "CLAUDE.md").split("## Nuclio v3 5.0.0 约束", 1)[1].split("## 验证命令", 1)[0]
        self.assertIn("Nuclio v3 5.0.0", readme)
        self.assertIn("Nuclio v3 5.0.0", read(ROOT / "CLAUDE.md"))
        for text in (readme, nuclio_rules):
            self.assertIn("delivery.yaml", text)
            self.assertIn("state.yaml", text)
            self.assertNotIn("plan.yaml", text)
            self.assertNotIn("task-implementer", text)
            self.assertIn("docs/research/", text)


if __name__ == "__main__":
    unittest.main()
