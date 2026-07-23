"""
Nuclio v2 static regression tests.

## Contents
- [Helpers](#helpers)
- [Structure tests](#structure-tests)
- [Markdown contract tests](#markdown-contract-tests)
- [Eval contract tests](#eval-contract-tests)
- [Runtime helper tests](#runtime-helper-tests)
- [Composite semantics tests](#composite-semantics-tests)
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "plugins" / "nuclio-plugin"
SKILLS = PLUGIN / "skills"
REFERENCES = PLUGIN / "references"
SCRIPTS = PLUGIN / "scripts"
AGENTS = PLUGIN / "agents"
SCHEMAS = PLUGIN / "schemas"
CHANGE = SCRIPTS / "change.py"

EXPECTED_SKILLS = {"init", "work"}
EXPECTED_REFERENCES = {
    "workflow.md",
    "change-format.md",
    "knowledge.md",
    "context-hygiene.md",
    "eval-prompts.md",
}
EXPECTED_SCRIPTS = {"change.py", "test_change.py", "test_static_plugin.py"}
EXPECTED_CHANGE_COMMANDS = {"create", "list", "show", "set-status", "archive", "legacy-move"}
EVAL_REQUIRED_FIELDS = {
    "User Prompt",
    "Expected Route",
    "Allowed Writes",
    "Forbidden Writes",
    "Key Assertions",
}

REFERENCE_LINK_RE = re.compile(r"\[[^\]]+\]\((../../references/[^)#]+)(#[^)]+)?\)")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
ALLOWED_NON_REFERENCE_LINK_SCHEMES = ("http://", "https://", "mailto:")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
CASE_HEADING_RE = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$", re.M)
FIELD_RE = re.compile(r"^-\s+`([^`]+)`: ?(.*)$", re.M)

# Current-authority scans intentionally operate on declarative guidance, not on
# this test file's explicit negative fixtures. Historical or forbidden-context
# mentions are handled by section/line context instead of brittle global bans.
CURRENT_AUTHORITY_WORDS = r"(?:daily|current|runtime|entry|route|authority|authoritative|required|must|日常|当前|运行时|入口|权威|必须|要求)"
CREATE_REQUIRE_WORDS = r"(?:create|write|require|store|install|enable|run|start|state|runtime|authority|authoritative|must|创建|写入|要求|保存|安装|启用|运行|启动|状态|运行时|权威|必须)"
FORBIDDEN_CURRENT_AUTHORITY_PATTERNS = {
    "/nuclio:finish current authority": re.compile(rf"(?i){CURRENT_AUTHORITY_WORDS}.{{0,80}}/nuclio:finish|/nuclio:finish.{{0,80}}{CURRENT_AUTHORITY_WORDS}"),
    "Contract/State/Packet/Evidence/Finish handoff authority": re.compile(rf"(?i)(?:contract|state machine|state\.json|packet|evidence|finish handoff|five-file handoff|finish-plan\.json).{{0,80}}{CURRENT_AUTHORITY_WORDS}|{CURRENT_AUTHORITY_WORDS}.{{0,80}}(?:contract|state machine|state\.json|packet|evidence|finish handoff|five-file handoff|finish-plan\.json).{{0,80}}{CURRENT_AUTHORITY_WORDS}"),
    "exact approval token": re.compile(r"(?i)(?:exact token|fixed token|approval token|固定 token|固定口令).{0,80}(?:required|must|必须|要求)"),
    "identity/hash/fingerprint gate": re.compile(r"(?i)(?:identity|hash|fingerprint|身份|哈希|指纹).{0,80}(?:approval|gate|authority|批准|授权|权威)"),
    "approval JSON": re.compile(r"(?i)approval json.{0,80}(?:required|must|authority|必须|权威)"),
    "helper next-action routing": re.compile(r"(?i)(?:next-action).{0,80}(?:required|authority|route|dispatch|必须|权威|路由)"),
    "protocol agent pipeline": re.compile(r"(?i)(?:nuclio-(?:implementer|task-reviewer|fixer|completion-critic)|protocol agent).{0,80}(?:required|must|pipeline|authority|必须|流水线|权威)"),
}
FORBIDDEN_RUNTIME_REBUILD_PATTERNS = {
    "hidden persistent JSON": re.compile(rf"(?i)(?:persistent process json|persistent json|持久过程 JSON).{{0,80}}{CREATE_REQUIRE_WORDS}|{CREATE_REQUIRE_WORDS}.{{0,80}}(?:persistent process json|persistent json|持久过程 JSON)"),
    ".nuclio state directory": re.compile(rf"(?i)\.nuclio/?.{{0,80}}{CREATE_REQUIRE_WORDS}|{CREATE_REQUIRE_WORDS}.{{0,80}}\.nuclio/?"),
    "runtime hook": re.compile(rf"(?i)runtime hook.{{0,80}}{CREATE_REQUIRE_WORDS}|{CREATE_REQUIRE_WORDS}.{{0,80}}runtime hook"),
    "daemon": re.compile(rf"(?i)daemon.{{0,80}}{CREATE_REQUIRE_WORDS}|{CREATE_REQUIRE_WORDS}.{{0,80}}daemon"),
    "MCP": re.compile(rf"(?i)MCP.{{0,80}}(?:server|{CREATE_REQUIRE_WORDS})|(?:server|{CREATE_REQUIRE_WORDS}).{{0,80}}MCP"),
    "project-local .claude install": re.compile(rf"(?i)(?:project-local\s+)?\.claude/.{{0,80}}{CREATE_REQUIRE_WORDS}|{CREATE_REQUIRE_WORDS}.{{0,80}}(?:project-local\s+)?\.claude/"),
    "changes index": re.compile(rf"(?i)\.dev-docs/changes/index\.md.{{0,80}}{CREATE_REQUIRE_WORDS}|{CREATE_REQUIRE_WORDS}.{{0,80}}\.dev-docs/changes/index\.md"),
    "packet evidence hash fingerprint": re.compile(r"(?i)(?:packet|evidence).{0,40}(?:hash|fingerprint|identity).{0,80}(?:authority|gate|approval|required|权威|批准|要求)"),
    "approval ledger": re.compile(rf"(?i)approval ledger.{{0,80}}{CREATE_REQUIRE_WORDS}|{CREATE_REQUIRE_WORDS}.{{0,80}}approval ledger"),
    "helper next-action": re.compile(r"(?i)helper.{0,40}next-action.{0,80}(?:route|dispatch|authority|require|路由|调度|权威|要求)"),
}
NEGATIVE_CONTEXT_RE = re.compile(
    r"(?i)(?:do not|don't|does not|not |never|forbid|forbidden|prohibit|without|no |non-goal|禁止|不得|不要|不应|不会|不能|不创建|不写入|非目标|不是|无须|无需|都不是|只在|仅在)"
)
LEGACY_CONTEXT_RE = re.compile(r"(?i)(?:legacy|v1|historical|old|旧|历史|禁止恢复|整体移动|只读)")
NEGATIVE_OR_LEGACY_HEADING_RE = re.compile(r"(?i)(?:禁止|不得|非 Gate|非目标|v1|legacy|旧|历史)")


# Helpers

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def skill_paths() -> dict[str, Path]:
    return {path.parent.name: path for path in SKILLS.glob("*/SKILL.md")}


def split_skill(path: Path) -> tuple[dict[str, object], str]:
    text = read_text(path)
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
    if not match:
        raise AssertionError(f"{path} must contain YAML frontmatter")
    frontmatter: dict[str, object] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.lower() == "true":
            parsed: object = True
        elif value.lower() == "false":
            parsed = False
        else:
            parsed = value.strip('"')
        frontmatter[key.strip()] = parsed
    return frontmatter, match.group(2)


def runtime_markdown_paths() -> list[Path]:
    paths = list(skill_paths().values()) + sorted(REFERENCES.glob("*.md"))
    return sorted(paths, key=lambda path: path.as_posix())


def runtime_files_under(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and "__pycache__" not in candidate.parts
    )


def validate_one_level_reference_link(testcase: unittest.TestCase, link: str, source: Path) -> None:
    if link.startswith("#"):
        return
    testcase.assertFalse(
        link.startswith(ALLOWED_NON_REFERENCE_LINK_SCHEMES),
        f"{source.relative_to(ROOT)} must link only to one-level runtime references, not {link}",
    )
    match = re.fullmatch(r"../../references/([^/#)]+\.md)(#[^)]+)?", link)
    testcase.assertIsNotNone(match, f"{source.relative_to(ROOT)} has non-reference Markdown link {link}")
    if match is None:
        return
    target_name = match.group(1)
    anchor = match.group(2)
    testcase.assertNotIn("/", target_name)
    testcase.assertIn(target_name, EXPECTED_REFERENCES)
    target = REFERENCES / target_name
    testcase.assertTrue(target.is_file())
    if anchor:
        testcase.assertIn(anchor[1:], headings_by_anchor(read_text(target)))


def reference_paths_without_eval() -> list[Path]:
    return [REFERENCES / name for name in sorted(EXPECTED_REFERENCES - {"eval-prompts.md"})]


def markdown_anchor(text: str) -> str:
    anchor = text.strip().lower()
    anchor = re.sub(r"[`*_\\[\\]()]", "", anchor)
    anchor = re.sub(r"[^\w一-鿿 -]", "", anchor)
    anchor = anchor.replace(" ", "-")
    return anchor


def headings_by_anchor(text: str) -> set[str]:
    return {markdown_anchor(match.group(2)) for match in HEADING_RE.finditer(text)}


def contents_block(text: str) -> str:
    match = re.search(r"(?ms)^## Contents\s*$\n(?P<body>.*?)(?=^## \S|\Z)", text)
    return match.group("body") if match else ""


def line_is_allowed_historical_or_negative(line: str) -> bool:
    return bool(NEGATIVE_CONTEXT_RE.search(line) or LEGACY_CONTEXT_RE.search(line))


def assert_no_positive_pattern(testcase: unittest.TestCase, text: str, patterns: dict[str, re.Pattern[str]], source: Path | str) -> None:
    for name, pattern in patterns.items():
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line) and not line_is_allowed_historical_or_negative(line):
                testcase.fail(f"{source}:{number}: positive forbidden {name}: {line}")


def parse_eval_cases(text: str) -> dict[int, dict[str, str]]:
    matches = list(CASE_HEADING_RE.finditer(text))
    cases: dict[int, dict[str, str]] = {}
    for index, match in enumerate(matches):
        case_number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else text.find("\n## 全局断言", start)
        if end == -1:
            end = len(text)
        block = text[start:end]
        fields = {field: value.strip() for field, value in FIELD_RE.findall(block)}
        cases[case_number] = fields
    return cases


def load_change_module():
    spec = importlib.util.spec_from_file_location("nuclio_change_static_under_test", CHANGE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def run_static_suite_in_temp_plugin(mutator: Callable[[Path], None] | None = None) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir) / "repo"
        temp_plugin = temp_root / "plugins" / "nuclio-plugin"
        temp_plugin.parent.mkdir(parents=True)
        shutil.copytree(PLUGIN, temp_plugin)
        if mutator:
            mutator(temp_plugin)
        env = {**dict(os.environ), "NUCLIO_STATIC_MUTANT_CHILD": "1"}
        return subprocess.run(
            [sys.executable, str(temp_plugin / "scripts" / "test_static_plugin.py"), "-q"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=env,
        )


def append_text(path: Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def stdlib_names() -> set[str]:
    names = set(sys.builtin_module_names)
    stdlib = sysconfig.get_paths().get("stdlib")
    if stdlib:
        for path in Path(stdlib).iterdir():
            if path.name.startswith("_"):
                continue
            if path.suffix == ".py":
                names.add(path.stem)
            elif path.is_dir() and (path / "__init__.py").exists():
                names.add(path.name)
    names.update({"__future__"})
    return names


# Structure tests

class StaticPluginStructureTests(unittest.TestCase):
    def test_runtime_file_collections_are_exact_v2(self):
        self.assertEqual(set(skill_paths()), EXPECTED_SKILLS)
        self.assertEqual({path.parent.name for path in SKILLS.glob("*/SKILL.md")}, EXPECTED_SKILLS)
        self.assertEqual({path.name for path in REFERENCES.glob("*.md")}, EXPECTED_REFERENCES)
        script_files = {path.name for path in SCRIPTS.glob("*.py") if "__pycache__" not in path.parts}
        self.assertEqual(script_files, EXPECTED_SCRIPTS)
        for directory in [AGENTS, SCHEMAS]:
            with self.subTest(directory=directory.relative_to(ROOT).as_posix()):
                self.assertEqual(
                    [path.relative_to(directory).as_posix() for path in runtime_files_under(directory)],
                    [],
                )

    def test_deleted_v1_runtime_files_remain_absent(self):
        deleted = [
            AGENTS / "nuclio-implementer.md",
            AGENTS / "nuclio-task-reviewer.md",
            AGENTS / "nuclio-fixer.md",
            AGENTS / "nuclio-completion-critic.md",
            SCHEMAS / "contract.schema.json",
            SCHEMAS / "context.schema.json",
            SCHEMAS / "state.schema.json",
            SCHEMAS / "packet.schema.json",
            SCHEMAS / "evidence.schema.json",
            SCHEMAS / "finish-plan.schema.json",
            SCRIPTS / "contract-helper.py",
            SCRIPTS / "context-helper.py",
            SCRIPTS / "state-helper.py",
            SCRIPTS / "packet-helper.py",
            SCRIPTS / "evidence-helper.py",
            SCRIPTS / "migration-helper.py",
            SCRIPTS / "json-schema-helper.py",
            SCRIPTS / "test_contract_helper.py",
            SCRIPTS / "test_context_helper.py",
            SCRIPTS / "test_state_helper.py",
            SCRIPTS / "test_packet_helper.py",
            SCRIPTS / "test_evidence_helper.py",
            SCRIPTS / "test_migration_helper.py",
            SCRIPTS / "test_json_schema_helper.py",
            SCRIPTS / "test_finish_resume.py",
        ]
        for path in deleted:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertFalse(path.exists())


# Mutant regression evidence tests

@unittest.skipIf(os.environ.get("NUCLIO_STATIC_MUTANT_CHILD") == "1", "avoid recursive temp-copy mutant probes")
class StaticPluginMutantEvidenceTests(unittest.TestCase):
    def assert_mutant_detected(self, name: str, mutator: Callable[[Path], None]) -> None:
        with self.subTest(mutant=name):
            result = run_static_suite_in_temp_plugin(mutator)
            combined_output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, combined_output)

    def test_unmutated_temp_copy_static_suite_passes(self):
        result = run_static_suite_in_temp_plugin()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_temp_copy_mutants_are_detected(self):
        def nested_agent_and_schema_files(plugin: Path) -> None:
            agent = plugin / "agents" / "nested" / "nuclio-implementer.md"
            agent.parent.mkdir(parents=True)
            agent.write_text("# forbidden nested agent\n", encoding="utf-8")
            schema = plugin / "schemas" / "nested" / "state.schema.json"
            schema.parent.mkdir(parents=True)
            schema.write_text("{}\n", encoding="utf-8")

        def bad_skill_markdown_link(plugin: Path) -> None:
            append_text(plugin / "skills" / "work" / "SKILL.md", "\n[bad](../references/workflow.md)\n")

        def positive_finish_plan_authority(plugin: Path) -> None:
            append_text(
                plugin / "references" / "workflow.md",
                "\nCurrent runtime must create finish-plan.json as authority.\n",
            )

        def positive_nuclio_state_directory(plugin: Path) -> None:
            append_text(
                plugin / "references" / "workflow.md",
                "\nCurrent runtime must create .nuclio/ state directory.\n",
            )

        for name, mutator in {
            "nested agents/schemas runtime files": nested_agent_and_schema_files,
            "skill Markdown link outside one-level references": bad_skill_markdown_link,
            "positive finish-plan current authority": positive_finish_plan_authority,
            "positive .nuclio state directory requirement": positive_nuclio_state_directory,
        }.items():
            self.assert_mutant_detected(name, mutator)


# Markdown contract tests

class MarkdownContractTests(unittest.TestCase):
    def test_skill_frontmatter_description_body_and_links(self):
        for name, path in skill_paths().items():
            with self.subTest(skill=name):
                frontmatter, body = split_skill(path)
                self.assertEqual(frontmatter.get("name"), name)
                self.assertIs(frontmatter.get("disable-model-invocation"), True)
                description = frontmatter.get("description")
                self.assertIsInstance(description, str)
                self.assertTrue(description.startswith("Use when"), description)
                self.assertLessEqual(len(description), 1024)
                self.assertLess(len(body.splitlines()), 500)
                links = MARKDOWN_LINK_RE.findall(body)
                self.assertTrue(links)
                for link in links:
                    validate_one_level_reference_link(self, link, path)

    def test_contents_links_match_existing_headings(self):
        for path in runtime_markdown_paths():
            text = read_text(path)
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                if len(text.splitlines()) > 100:
                    self.assertIn("## Contents", text)
                    block = contents_block(text)
                    self.assertTrue(block.strip(), "Contents block must not be empty")
                    anchors = headings_by_anchor(text)
                    for link in MARKDOWN_LINK_RE.findall(block):
                        if not link.startswith("#"):
                            continue
                        self.assertIn(link[1:], anchors, f"missing heading for {link}")

    def test_references_do_not_create_second_layer_read_dependencies(self):
        for path in sorted(REFERENCES.glob("*.md")):
            text = read_text(path)
            with self.subTest(path=path.name):
                reference_links = [link for link in MARKDOWN_LINK_RE.findall(text) if link.endswith(".md") or ".md#" in link]
                self.assertEqual(reference_links, [], "reference Markdown must not require more reference reads")
                for line in text.splitlines():
                    if re.search(r"(?i)(?:read|读取|继续 Read|再读取).{0,40}(?:references/|\.md\)|\.md#)", line):
                        self.fail(f"second-layer Read dependency in {path.name}: {line}")

    def test_current_guidance_does_not_restore_v1_authority(self):
        for path in runtime_markdown_paths():
            text = read_text(path)
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                assert_no_positive_pattern(self, text, FORBIDDEN_CURRENT_AUTHORITY_PATTERNS, path.relative_to(ROOT))

    def test_runtime_guidance_blocks_forbidden_mechanisms_without_implementing_them(self):
        corpus_paths = runtime_markdown_paths() + [CHANGE]
        for path in corpus_paths:
            text = read_text(path)
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                assert_no_positive_pattern(self, text, FORBIDDEN_RUNTIME_REBUILD_PATTERNS, path.relative_to(ROOT))
        corpus = "\n".join(read_text(path) for path in corpus_paths)
        for required_forbidden in [
            ".nuclio/",
            "runtime hook",
            "daemon",
            "外部服务依赖",
            "项目级 `.claude/`",
            ".dev-docs/changes/index.md",
            "approval JSON",
            "状态路由",
        ]:
            with self.subTest(required_forbidden=required_forbidden):
                self.assertIn(required_forbidden, corpus)


# Eval contract tests

class EvalContractTests(unittest.TestCase):
    def test_eval_prompts_define_exactly_eighteen_v2_cases_with_required_fields(self):
        text = read_text(REFERENCES / "eval-prompts.md")
        cases = parse_eval_cases(text)
        self.assertEqual(set(cases), set(range(1, 19)))
        for number, fields in cases.items():
            with self.subTest(case=number):
                self.assertEqual(set(fields), EVAL_REQUIRED_FIELDS)
                for field in EVAL_REQUIRED_FIELDS:
                    self.assertTrue(fields[field], f"{field} must be non-empty")
                self.assertRegex(fields["Expected Route"], r"`(?:init|work)`")

    def test_eval_prompts_do_not_use_v1_routing_or_packet_assertions(self):
        text = read_text(REFERENCES / "eval-prompts.md")
        forbidden = [
            "owner_skill",
            "expected_next_action",
            "packet identity",
            "packet-bound",
            "Contract Gate",
            "Finish Gate",
            "contract_sha256",
            "context_fingerprint",
            "state_version",
            "finish-plan.json",
            "decision_sha256",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, text)
        cases = parse_eval_cases(text)
        self.assertEqual(len(cases), 18)
        combined_assertions = "\n".join(fields["Key Assertions"] for fields in cases.values())
        for needle in [
            "产品 mutation 前必须展示",
            "拒绝不影响已验证产品结果",
            "legacy 只能整体移动",
            "不保留双栈",
            "多候选必须人类选择",
            "100k 是上下文卫生警戒线",
        ]:
            with self.subTest(needle=needle):
                self.assertIn(needle, combined_assertions)


# Runtime helper tests

class RuntimeHelperTests(unittest.TestCase):
    def test_change_help_exposes_exactly_six_subcommands(self):
        result = subprocess.run(
            [sys.executable, str(CHANGE), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        change_module = load_change_module()
        self.assertEqual(set(change_module.COMMANDS), EXPECTED_CHANGE_COMMANDS)
        help_commands = set(re.findall(r"\b(create|list|show|set-status|archive|legacy-move)\b", result.stdout))
        self.assertEqual(help_commands, EXPECTED_CHANGE_COMMANDS)
        for forbidden in [
            "next-action",
            "packet",
            "evidence",
            "finish",
            "approve",
            "validate-schema",
            "state-helper",
            "contract-helper",
        ]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, result.stdout)

    def test_change_py_imports_only_python_standard_library(self):
        tree = ast.parse(read_text(CHANGE), filename=str(CHANGE))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        nonstdlib = sorted(imported - stdlib_names())
        self.assertEqual(nonstdlib, [])

    def test_change_py_source_has_no_v1_protocol_router_or_hidden_state_mechanism(self):
        text = read_text(CHANGE)
        forbidden_tokens = [
            "approval_json",
            "approval-ledger",
            "next-action",
            "packet-helper",
            "evidence-helper",
            "state-helper",
            "finish-plan",
            ".nuclio/",
            "runtime hook",
            "daemon",
            "MCP server",
            ".dev-docs/changes/index.md",
            "context_fingerprint",
            "packet_id",
        ]
        for token in forbidden_tokens:
            with self.subTest(token=token):
                self.assertNotIn(token, text)
        self.assertEqual(text.count("def cmd_"), 6)


# Composite semantics tests

class CompositeSemanticsTests(unittest.TestCase):
    def test_skills_and_topic_references_cover_composite_pattern_semantics(self):
        paths = list(skill_paths().values()) + reference_paths_without_eval()
        corpus = "\n".join(read_text(path) for path in paths)
        semantic_groups = {
            "Sequential lifecycle": ["standard sequence", "标准顺序", "生命周期", "Locate", "create", "archive"],
            "plan approval": ["implementation Gate", "计划批准", "自然语言批准", "Approved on YYYY-MM-DD"],
            "knowledge candidate confirmation": ["知识候选", "五问", "用户确认", "拒绝不影响"],
            "risk-based review": ["Risk guidance", "风险矩阵", "independent reviewer", "审查深度"],
            "generic subagent": ["generic subagents", "通用 subagent", "不强制固定 agent 流水线"],
            "change.md checkpoint": ["change.md", "checkpoint", "压缩恢复状态", "Plan"],
            "legacy/v1": ["legacy/v1", "clear v1", "整体移动", "不保留 v1/v2 双栈"],
        }
        for group, alternatives in semantic_groups.items():
            with self.subTest(group=group):
                self.assertTrue(any(needle in corpus for needle in alternatives), f"missing semantic anchors for {group}")
        self.assertRegex(corpus, r"(?s)产品 mutation 前.*?(?:计划|Plan).*?(?:批准|approval)")
        self.assertRegex(corpus, r"(?s)(?:风险|Risk).*?(?:reviewer|审查)")
        self.assertRegex(corpus, r"(?s)(?:知识|knowledge).*?(?:候选|candidate).*?(?:确认|confirm|用户)")


if __name__ == "__main__":
    unittest.main()
