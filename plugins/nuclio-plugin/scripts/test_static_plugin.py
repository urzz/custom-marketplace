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
OPEN_DESIGN_HANDOFF = REFERENCES / "open-design-handoff.md"
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
    OPEN_DESIGN_HANDOFF,
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

    def test_nuclio_never_enters_or_exits_claude_plan_mode(self):
        for path in (INIT, WORK):
            skill = read(path)
            self.assertIn("始终在当前模式执行", skill)
            self.assertIn("`EnterPlanMode` 或 `ExitPlanMode`", skill)
            self.assertIn("已处于 Claude Code Plan Mode", skill)
            self.assertIn("立即 fail closed", skill)
            self.assertIn("不自行调用 `ExitPlanMode`", skill)
        init = read(INIT)
        self.assertIn("不创建或恢复 change", init)
        self.assertIn("不写入知识骨架", init)
        self.assertIn("不调用 Runtime", init)
        work = read(WORK)
        self.assertIn("不创建或恢复 change", work)
        self.assertIn("不调用 Runtime", work)
        workflow = read(REFERENCES / "workflow.md")
        self.assertIn("Nuclio 生命周期始终在调用开始时的当前模式内运行", workflow)
        self.assertIn("不调用 Claude Code 的 `EnterPlanMode` 或 `ExitPlanMode`", workflow)
        self.assertIn("delivery milestone 是 Nuclio 的交付跟踪，不等于也不触发 Claude Code Plan Mode", workflow)
        eval_prompts = read(REFERENCES / "eval-prompts.md")
        self.assertIn("已处于 Plan Mode", eval_prompts)
        self.assertIn("不调用 `EnterPlanMode` 或 `ExitPlanMode`", eval_prompts)

    def test_reviewer_is_the_only_agent_and_is_exactly_read_only(self):
        self.assertFalse((PLUGIN / "agents" / "task-implementer.md").exists())
        metadata = frontmatter(REVIEWER)
        tools = re.search(r"^tools:\s*(.+)$", metadata, flags=re.M)
        self.assertIsNotNone(tools)
        self.assertEqual([item.strip() for item in tools.group(1).split(",")], ["Read", "Grep", "Glob"])
        reviewer = read(REVIEWER)
        for boundary in ("不运行 shell", "不创建、编辑、删除", "不调用 Skill、Agent、Task、Workflow", "只返回 findings"):
            self.assertIn(boundary, reviewer)

    def test_build_agent_dispatch_is_context_aware_and_bounded(self):
        build_guides = (
            read(WORK),
            read(REFERENCES / "workflow.md"),
            read(REFERENCES / "context-hygiene.md"),
        )
        for guide in build_guides:
            self.assertRegex(guide, r"主会话(?:仍)?是唯一控制器")
            for required in (
                "保护主会话上下文是优先使用一个有界 Claude Code Agent 的判断条件",
                "读取广度",
                "预期实现/诊断迭代",
                "原始命令输出体量",
                "必要范围能否清楚界定",
                "已确认结果合同是否保持不变",
                "不使用 token 或 ctx 数值硬阈值",
                "阅读或诊断密集、合同稳定、范围清晰且可由预期检查验证",
                "极小、单一且实现路径明确",
                "仍由主会话直接处理",
                "不为形式而派发",
                "短回传改动、检查和未完成项",
            ):
                self.assertIn(required, guide)
            self.assertRegex(guide, r"(?:不得|不)复制完整知识正文")
            for required in (
                "先保留或读取紧凑控制信息",
                "`status --id <change-id> --json` 工作包",
                "当前合同",
                "milestone/handoff",
                "相关知识",
                "先作出派发判断",
                "仅将当前控制信息、相关知识路径及读取理由和必要范围交给 Agent",
                "主会话不预读该委派范围的局部代码、测试、配置或测试诊断",
                "Agent 在必要范围内读取代码、测试和配置",
                "吸收局部探索、测试诊断和原始输出",
                "主会话只处理短回传、milestone/handoff、Runtime 和 Verify",
                "主会话才读取相关代码、测试和配置",
            ):
                self.assertIn(required, guide)
        self.assertIn("不新增专用 implementer、固定任务流水线", build_guides[2])
        self.assertIn("固定实现流水线", build_guides[0])

    def test_fresh_session_eval_prompts_cover_dispatch_reading_roles(self):
        eval_prompts = read(REFERENCES / "eval-prompts.md")
        for required in (
            "多文件阅读与测试诊断的 Build 派发",
            "多个回调、服务、配置和测试文件",
            "主会话不预读委派范围的局部材料",
            "agent 在支付子系统必要范围内吸收局部探索、测试诊断和原始输出",
            "不以 token 或 ctx 数值硬阈值决定派发",
            "单文件确定性 Build 不机械派发",
            "不因进入 Build 或存在 Agent 能力而机械委派",
            "主会话直接完成改动和检查",
            "直接实施时主会话才读取相关代码、测试和配置",
        ):
            self.assertIn(required, eval_prompts)

    def test_authority_has_no_v2_execution_protocol(self):
        combined = "\n".join(read(path) for path in AUTHORITY)
        for forbidden in ("allowed_paths", "execution.mode", "task-implementer", "validate-plan", "init-state", "record-task", "supersede"):
            self.assertNotIn(forbidden, combined)

    def test_active_change_discovery_routes_before_status(self):
        work = read(WORK)
        workflow = read(REFERENCES / "workflow.md")
        context = read(REFERENCES / "context-hygiene.md")
        eval_prompts = read(REFERENCES / "eval-prompts.md")
        authority = "\n".join((work, workflow, context, eval_prompts))
        for text in (work, workflow, context):
            self.assertIn("archive", text)
            self.assertIn("无候选", text)
            self.assertIn("恰有一个候选", text)
            self.assertIn("多个候选", text)
            self.assertIn("status --id <change-id> --json", text)
        self.assertIn("不调用 `status`", work)
        self.assertIn("不猜测", work)
        self.assertIn("不调用 Runtime", work)
        self.assertNotRegex(authority, r"(?m)^python3 .*?\bstatus --json(?:\s|$)")
        for heading in ("无 active change 的 Shape", "恢复与失败修复", "多个 active change"):
            self.assertIn(heading, eval_prompts)
        source = read(RUNTIME)
        self.assertIn('status.add_argument("--id", required=True)', source)

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

    def test_open_design_handoff_is_conditional_read_only_intake(self):
        work = read(WORK)
        handoff = read(OPEN_DESIGN_HANDOFF)
        eval_prompts = read(REFERENCES / "eval-prompts.md")
        self.assertIn("[Open Design handoff]", work)
        self.assertNotIn("CLAUDE.md", work)
        self.assertNotIn("AGENTS.md", work)
        for required in ('`project-id`', '`get_project`', '`get_artifact`', '`include="all"`'):
            self.assertIn(required, handoff)
        for boundary in (
            "合同批准前不得把设计文件写入产品仓库",
            "不得调用 `get_active_context`",
            "跳过 `*.artifact.json`",
            "固定目录 `.dev-docs/artifacts/open-design/`",
            "不得把完整 HTML/CSS 交付写入 `.dev-docs/knowledge/`",
            "通过 `verify --manual` 绑定到当前 HEAD",
        ):
            self.assertIn(boundary, handoff)
        self.assertIn("已加载的项目上下文", handoff)
        self.assertNotIn("项目根目录", handoff)
        self.assertNotIn("open-design/<project-id>", handoff)
        self.assertNotIn("docs/design/open-design/", handoff)
        self.assertNotIn(".dev-docs/knowledge/project.md", handoff)
        self.assertIn("Open Design 绑定交付", eval_prompts)
        self.assertIn("Open Design 输入不可用", eval_prompts)
        self.assertFalse((PLUGIN / "skills" / "open-design-handoff").exists())


class PackageSyncContracts(unittest.TestCase):
    def test_v3_metadata_and_repository_docs_are_synced(self):
        plugin = json.loads(read(PLUGIN / ".claude-plugin" / "plugin.json"))
        marketplace = json.loads(read(ROOT / ".claude-plugin" / "marketplace.json"))
        entry = next(item for item in marketplace["plugins"] if item["name"] == "nuclio")
        self.assertEqual(plugin["name"], "nuclio")
        self.assertEqual(plugin["version"], "5.1.5")
        self.assertEqual(entry["source"], "./plugins/nuclio-plugin")
        self.assertEqual(entry["description"], plugin["description"])
        self.assertIn("without entering or exiting Claude Code Plan Mode", plugin["description"])
        self.assertIn("context-aware bounded Agent dispatch", plugin["description"])
        readme = read(ROOT / "README.md")
        nuclio_rules = read(ROOT / "CLAUDE.md").split("## Nuclio v3 5.1.5 约束", 1)[1].split("## 验证命令", 1)[0]
        self.assertIn("Nuclio v3 5.1.5", readme)
        self.assertIn("Nuclio v3 5.1.5", read(ROOT / "CLAUDE.md"))
        self.assertIn("主会话基于上下文负担按需有界委派 Agent", readme)
        self.assertIn("主会话基于上下文负担按需有界委派 Agent", nuclio_rules)
        for text in (readme, nuclio_rules):
            self.assertIn("Claude Code Plan Mode", text)
            self.assertIn("delivery.yaml", text)
            self.assertIn("state.yaml", text)
            self.assertNotIn("plan.yaml", text)
            self.assertNotIn("task-implementer", text)
            self.assertIn("docs/research/", text)
            self.assertIn("Open Design", text)


if __name__ == "__main__":
    unittest.main()
