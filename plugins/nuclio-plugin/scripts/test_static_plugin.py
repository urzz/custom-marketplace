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
EXPECTED_CHANGE_COMMANDS = {
    "create",
    "list",
    "show",
    "validate-plan",
    "init-state",
    "status",
    "next-action",
    "start-task",
    "record-task",
    "record-review",
    "start-repair",
    "record-repair",
    "record-validation",
    "complete",
    "archive",
    "legacy-move",
}
ALLOWED_CHANGE_IMPORTS = {"yaml"}
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
    "legacy helper next-action routing": re.compile(r"(?i)(?:旧式|legacy|v1).{0,40}(?:next-action).{0,80}(?:authority|route|dispatch|权威|路由)"),
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
    "runtime owner routing": re.compile(r"(?i)(?:must|require|use|route|assign|create|必须|要求|使用|分配|调度).{0,80}(?:owner routing|finding owner routing|owner mapping|owner fixer)|(?:owner routing|finding owner routing|owner mapping|owner fixer).{0,80}(?:must|required|use|route|assign|create|必须|要求|使用|分配|调度)"),
    "unapproved init-state or mutation": re.compile(r"(?i)(?:init-state|product mutation).{0,80}(?:before|without).{0,40}(?:approval|natural-language approval|批准).{0,80}(?:allow|allowed|permitted|可|允许)|(?:allow|allowed|permitted|可|允许).{0,80}(?:init-state|product mutation).{0,80}(?:before|without).{0,40}(?:approval|批准)"),
    "bad checkpoint or repair acceptance": re.compile(r"(?i)(?:record-task|checkpoint|record-repair|repair).{0,80}(?:multiple checkpoint|wrong checkpoint_subject|outside allowed_paths|多个 checkpoint|错误 checkpoint|超出 allowed_paths).{0,80}(?:may accept|allowed|allow|可接受|允许)"),
    "legacy helper next-action authority": re.compile(r"(?i)(?:旧式|legacy|v1).{0,40}helper.{0,40}next-action.{0,80}(?:route|dispatch|authority|require|路由|调度|权威|要求)"),
}
NEGATIVE_CONTEXT_RE = re.compile(
    r"(?i)(?:do not|don't|does not|not |never|forbid|forbidden|prohibit|no |non-goal|禁止|不得|不要|不应|不会|不能|不创建|不写入|非目标|不是|无须|无需|都不是|只在|仅在)"
)
HISTORICAL_CONTEXT_RE = re.compile(r"(?i)(?:historical|old|旧|历史|整体移动|只读)")
CURRENT_RUNTIME_INSTRUCTION_RE = re.compile(r"(?i)(?:current|runtime|daily|entry|required|require|requires|must|use|uses|using|当前|运行时|日常|入口|必须|要求|使用)")
NEGATIVE_OR_LEGACY_HEADING_RE = re.compile(r"(?i)(?:禁止|不得|非 Gate|非目标|v1|legacy|旧|历史)")
STATE_LIGHTWEIGHT_FORBIDDEN_KEYS = {
    "history",
    "transition_history",
    "events",
    "event_log",
    "diff",
    "diffs",
    "transcript",
    "transcripts",
    "messages",
    "agent_messages",
    "logs",
    "test_logs",
    "file_snapshot",
    "content_snapshot",
    "snapshots",
}
PLAN_OWNER_FORBIDDEN_KEYS = {
    "files",
    "owner",
    "owners",
    "owner_map",
    "owner_mapping",
    "owner_routing",
    "finding_owner",
    "finding_owners",
    "finding_routes",
    "behavioral_eval_owner",
}


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


def markdown_section(text: str, heading: str) -> str:
    pattern = rf"(?ms)^## {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^## \S|\Z)"
    match = re.search(pattern, text)
    if not match:
        raise AssertionError(f"missing markdown section: {heading}")
    return match.group("body")


def line_is_allowed_historical_or_negative(line: str) -> bool:
    explicit_negative = any(token in line for token in ("不新增", "不恢复", "不使用", "不用于", "不创建", "不做", "不得新增", "不得使用"))
    if NEGATIVE_CONTEXT_RE.search(line) or explicit_negative:
        return True
    if HISTORICAL_CONTEXT_RE.search(line) and not CURRENT_RUNTIME_INSTRUCTION_RE.search(line):
        return True
    return False


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

        def positive_legacy_helper_next_action_authority(plugin: Path) -> None:
            append_text(
                plugin / "references" / "workflow.md",
                "\nCurrent runtime must use legacy helper next-action as authority for routing.\n",
            )

        def second_runtime_helper(plugin: Path) -> None:
            (plugin / "scripts" / "workflow.py").write_text("# forbidden second helper\n", encoding="utf-8")

        def state_history_storage(plugin: Path) -> None:
            append_text(
                plugin / "scripts" / "change.py",
                "\nSTATE_HISTORY = {'transition_history': [], 'diffs': [], 'test_logs': []}\n",
            )

        def runtime_task_owner_schema(plugin: Path) -> None:
            append_text(
                plugin / "scripts" / "change.py",
                "\nPLAN_TOP_KEYS.add('owner_mapping')\nTASK_KEYS.add('files')\n",
            )

        def owner_routing_guidance(plugin: Path) -> None:
            append_text(
                plugin / "references" / "workflow.md",
                "\nRuntime must use owner routing and finding owner routing for repair dispatch.\n",
            )

        def skip_approval_guidance(plugin: Path) -> None:
            append_text(
                plugin / "references" / "workflow.md",
                "\nFor urgent changes, init-state before approval and product mutation before natural-language approval are allowed.\n",
            )

        def skip_approval_without_guidance(plugin: Path) -> None:
            append_text(
                plugin / "references" / "workflow.md",
                "\nFor urgent changes, product mutation without approval is allowed.\n",
            )

        def bad_checkpoint_repair_guidance(plugin: Path) -> None:
            append_text(
                plugin / "references" / "change-format.md",
                "\nrecord-task may accept multiple checkpoint commits, wrong checkpoint_subject, or repair paths outside allowed_paths.\n",
            )

        def remove_taskstop_lifecycle_guard(plugin: Path) -> None:
            for rel in [
                "skills/work/SKILL.md",
                "references/workflow.md",
                "references/context-hygiene.md",
                "references/eval-prompts.md",
            ]:
                path = plugin / rel
                text = path.read_text(encoding="utf-8")
                text = text.replace("TaskStop/Stop Task", "task lifecycle helper")
                text = text.replace("Controller/task-tracking", "Controller coordination")
                text = re.sub(r"(?is)when complete, blocked, timed out, or needing a decision.*?do not stop any task;", "when finished, provide a brief note;", text)
                text = re.sub(r"完成、阻塞、超时或需要决策时.*?(?:不得尝试停止任何任务|停止任何自身、父级、兄弟、后台、Controller/task-tracking 任务。)", "完成时可以自行结束。", text)
                path.write_text(text, encoding="utf-8")

        def missing_large_delegation_contract(plugin: Path) -> None:
            work = plugin / "skills" / "work" / "SKILL.md"
            text = work.read_text(encoding="utf-8")
            text = text.replace("Larger changes default to at least one bounded generic subagent unit", "Larger changes may remain entirely in the main session")
            text = text.replace("compact return: checkpoint SHA, changed paths, commands with exit codes, risks, and blockers", "compact return: short confidence summary")
            work.write_text(text, encoding="utf-8")

        def whole_directory_archive_retention(plugin: Path) -> None:
            change = plugin / "scripts" / "change.py"
            text = change.read_text(encoding="utf-8")
            text = text.replace("if remaining != [\"change.md\"]:", "if False:")
            text = text.replace("for name in (\"plan.yaml\", \"state.yaml\"):", "for name in ():")
            text = text.replace("\"retained_artifacts\": retained", "\"retained_artifacts\": archive_artifacts(target)")
            change.write_text(text, encoding="utf-8")

        def skip_archive_distilled_record_check(plugin: Path) -> None:
            change = plugin / "scripts" / "change.py"
            text = change.read_text(encoding="utf-8")
            text = text.replace("require_distilled_change_record(paths, change_id)", "# skipped distilled record validation")
            change.write_text(text, encoding="utf-8")

        for name, mutator in {
            "nested agents/schemas runtime files": nested_agent_and_schema_files,
            "skill Markdown link outside one-level references": bad_skill_markdown_link,
            "positive finish-plan current authority": positive_finish_plan_authority,
            "positive .nuclio state directory requirement": positive_nuclio_state_directory,
            "positive legacy helper next-action authority": positive_legacy_helper_next_action_authority,
            "second runtime helper": second_runtime_helper,
            "State history storage": state_history_storage,
            "runtime per-Task owner schema": runtime_task_owner_schema,
            "owner routing guidance": owner_routing_guidance,
            "skip approval guidance": skip_approval_guidance,
            "skip approval without guidance": skip_approval_without_guidance,
            "bad checkpoint/repair guidance": bad_checkpoint_repair_guidance,
            "remove TaskStop lifecycle guard": remove_taskstop_lifecycle_guard,
            "missing large delegation contract": missing_large_delegation_contract,
            "whole-directory archive retention": whole_directory_archive_retention,
            "skip archive distilled record check": skip_archive_distilled_record_check,
        }.items():
            self.assert_mutant_detected(name, mutator)


# Markdown contract tests

class MarkdownContractTests(unittest.TestCase):
    def test_historical_negative_allowlist_does_not_exempt_current_runtime_legacy_authority(self):
        allowed_lines = [
            "Use `change.py status` and `change.py next-action` as the current lightweight state.yaml helper.",
            "Do not restore legacy helper next-action routing authority.",
            "Historical v1 helper next-action routing is read-only legacy context.",
        ]
        for line in allowed_lines:
            with self.subTest(line=line):
                self.assertTrue(line_is_allowed_historical_or_negative(line) or not any(pattern.search(line) for pattern in FORBIDDEN_RUNTIME_REBUILD_PATTERNS.values()))
        self.assertFalse(
            line_is_allowed_historical_or_negative("Current runtime must use legacy helper next-action as authority for routing.")
        )

    def test_negative_allowlist_does_not_exempt_positive_without_approval_bypass(self):
        allowed_lines = [
            "Product mutation without approval is forbidden.",
            "Product mutation without approval is not allowed.",
        ]
        for line in allowed_lines:
            with self.subTest(line=line):
                self.assertTrue(line_is_allowed_historical_or_negative(line))
        self.assertFalse(
            line_is_allowed_historical_or_negative("For urgent changes, product mutation without approval is allowed.")
        )

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
            "旧式状态路由",
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
                self.assertNotIn("Owner Task", "\n".join(fields.values()))
                self.assertNotIn("owner_skill", "\n".join(fields.values()))

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
        combined_case_text = "\n".join("\n".join(fields.values()) for fields in cases.values())
        combined_assertions = "\n".join(fields["Key Assertions"] for fields in cases.values())
        for needle in [
            "file-first Gate",
            "每个实施 Task 恰好一个 checkpoint commit",
            "Plan 不创建 runtime owner routing",
            "大型变更默认委派有界单元",
            "查看片段不等于批准",
            "未批准不得初始化 State",
            "Spec/Plan hash、revision、HEAD 或 checkpoint drift",
            "Git index 非空",
            "预存 allowed-path dirty",
            "parent、subject、count、range、index 和 validation",
            "超出边界必须重新批准",
            "State 不复制历史",
            "agent claim",
            "REQUEST_REPAIR_DECISION",
            "deterministic-first",
            "拒绝不影响已验证产品结果",
            "legacy 只能整体移动",
            "多候选必须人类选择",
        ]:
            with self.subTest(needle=needle):
                self.assertIn(needle, combined_case_text)
        self.assertIn("简单任务", combined_case_text)
        self.assertIn("主会话直做", combined_case_text)


# Runtime helper tests

class RuntimeHelperTests(unittest.TestCase):
    def test_change_help_exposes_plan_state_commands_and_no_set_status(self):
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
        for command in EXPECTED_CHANGE_COMMANDS:
            with self.subTest(command=command):
                self.assertRegex(result.stdout, rf"\b{re.escape(command)}\b")
                sub = subprocess.run(
                    [sys.executable, str(CHANGE), command, "--help"],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(sub.returncode, 0, sub.stderr)
        for forbidden in [
            "set-status",
            "packet-helper",
            "evidence-helper",
            "finish-plan",
            "validate-schema",
            "state-helper",
            "contract-helper",
        ]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, result.stdout)

    def test_change_py_imports_only_python_standard_library_plus_pyyaml(self):
        tree = ast.parse(read_text(CHANGE), filename=str(CHANGE))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        nonstdlib = sorted(imported - stdlib_names() - ALLOWED_CHANGE_IMPORTS)
        self.assertEqual(nonstdlib, [])
        self.assertIn("yaml", imported)

    def test_change_py_source_has_single_helper_plan_state_and_no_v1_hidden_runtime(self):
        text = read_text(CHANGE)
        forbidden_tokens = [
            "approval_json",
            "approval-ledger",
            "set-status",
            "packet-helper",
            "evidence-helper",
            "state-helper",
            "finish-plan",
            ".nuclio/",
            "runtime hook",
            "daemon",
            "MCP server",
            "context_fingerprint",
            "packet_id",
        ]
        for token in forbidden_tokens:
            with self.subTest(token=token):
                self.assertNotIn(token, text)
        self.assertEqual(text.count("def cmd_"), len(EXPECTED_CHANGE_COMMANDS))
        for command in ["validate-plan", "init-state", "status", "next-action", "start-task", "record-task", "start-repair", "record-repair", "complete"]:
            with self.subTest(command=command):
                self.assertIn(command, text)

    def test_change_py_plan_schema_rejects_owner_routing_and_second_state_model(self):
        change_module = load_change_module()
        self.assertEqual(set(change_module.COMMANDS), EXPECTED_CHANGE_COMMANDS)
        self.assertEqual(set(change_module.PLAN_TOP_KEYS), {
            "schema_version",
            "change_id",
            "revision",
            "risk_level",
            "review_policy",
            "repair_policy",
            "summary",
            "allowed_paths",
            "tasks",
        })
        self.assertEqual(set(change_module.TASK_KEYS), {
            "id",
            "name",
            "steps",
            "acceptance",
            "validation",
            "delegate",
            "review",
            "checkpoint_subject",
        })
        self.assertTrue(PLAN_OWNER_FORBIDDEN_KEYS.isdisjoint(change_module.PLAN_TOP_KEYS))
        self.assertTrue(PLAN_OWNER_FORBIDDEN_KEYS.isdisjoint(change_module.TASK_KEYS))
        self.assertEqual(set(change_module.DELEGATES), {"main", "subagent", "auto"})
        self.assertEqual(set(change_module.REVIEW_POLICIES), {"self", "final", "task-and-final"})
        self.assertIn("in-scope", read_text(CHANGE))

    def test_archive_hash_transition_contract_is_two_phase(self):
        workflow_archive = markdown_section(read_text(REFERENCES / "workflow.md"), "完成与 archive")
        format_archive = markdown_section(read_text(REFERENCES / "change-format.md"), "Archive 路径")
        archive_docs = workflow_archive + "\n" + format_archive
        change_text = read_text(CHANGE)
        archive_helper = change_text[change_text.index("def load_archive_verified_state_and_plan") : change_text.index("def prune_archive_execution_artifacts")]

        for required in [
            "complete 前",
            "current Spec hash equality",
            "frozen pre-complete `spec_sha256`",
            "distilled record",
            "不得要求当前蒸馏后的 `change.md` hash 等于冻结的 pre-complete `state.spec_sha256`",
        ]:
            with self.subTest(required=required):
                self.assertIn(required, archive_docs)
        for stale in [
            "Plan/Spec/HEAD identity",
            "State/Spec/Plan identity",
            "HEAD/State/Spec/Plan identity",
            "验证 completed State、Plan/Spec/HEAD identity",
        ]:
            with self.subTest(stale=stale):
                self.assertNotIn(stale, archive_docs)
        self.assertIn("load_archive_verified_state_and_plan", change_text)
        self.assertIn("state.get(\"plan_sha256\") != sha256_file(plan_path)", archive_helper)
        self.assertIn("state.get(\"current_head\") != current", archive_helper)
        self.assertIn("not isinstance(state.get(\"spec_sha256\"), str)", archive_helper)
        self.assertIn("require_distilled_change_record(paths, change_id)", archive_helper)
        self.assertNotIn("spec_path_for", archive_helper)
        self.assertNotIn("state.get(\"spec_sha256\") != sha256_file(spec_path)", archive_helper)

    def test_change_py_archive_is_fail_closed_one_file_retention(self):
        change_module = load_change_module()
        self.assertEqual(tuple(change_module.ARCHIVE_ACTIVE_ARTIFACTS), ("change.md", "plan.yaml", "state.yaml"))
        self.assertEqual(tuple(change_module.ARCHIVE_REQUIRED_HEADINGS), ("Goal", "Outcome", "Validation", "Knowledge Updates"))
        text = read_text(CHANGE)
        for required in [
            "require_exact_archive_artifacts",
            "require_distilled_change_record",
            "load_archive_verified_state_and_plan",
            "ARCHIVE_PRUNE_FAILED",
            "UNEXPECTED_ARCHIVE_ARTIFACTS",
            "UNDISTILLED_RECORD",
            "retained_artifacts",
            "remaining_artifacts",
            "archive_path",
            "symlink_artifacts",
            ".is_symlink()",
        ]:
            with self.subTest(required=required):
                self.assertIn(required, text)
        self.assertIn("require_distilled_change_record(paths, change_id)", text)
        self.assertIn("source.rename(target)", text)
        self.assertIn("artifact.unlink()", text)
        self.assertNotIn("copytree", text)
        self.assertNotIn("manifest", text.lower())
        self.assertNotRegex(text, r"retained_artifacts[\"']\s*:\s*archive_artifacts")

    def test_change_py_initial_state_is_lightweight_and_helper_only(self):
        change_module = load_change_module()
        plan = {
            "tasks": [
                {
                    "id": 1,
                    "checkpoint_subject": "feat(example): one",
                }
            ]
        }
        state_tasks = change_module.initial_task_states(plan)
        self.assertEqual(set(state_tasks[0]), {"id", "status", "task_base", "task_head", "checkpoint_commit", "checkpoint_subject", "executor", "validation"})
        self.assertTrue(STATE_LIGHTWEIGHT_FORBIDDEN_KEYS.isdisjoint(state_tasks[0]))
        corpus = read_text(CHANGE)
        for required in ["dump_yaml_atomic", "os.replace", "load_verified_state_and_plan", "plan_sha256", "spec_sha256", "current_head"]:
            with self.subTest(required=required):
                self.assertIn(required, corpus)
        for forbidden in STATE_LIGHTWEIGHT_FORBIDDEN_KEYS:
            with self.subTest(forbidden=forbidden):
                self.assertNotRegex(corpus, rf"[\"']{re.escape(forbidden)}[\"']\s*:")


# Composite semantics tests

class CompositeSemanticsTests(unittest.TestCase):
    def test_skills_and_topic_references_cover_composite_pattern_semantics(self):
        paths = list(skill_paths().values()) + reference_paths_without_eval()
        corpus = "\n".join(read_text(path) for path in paths)
        semantic_groups = {
            "Sequential lifecycle": ["标准顺序", "生命周期", "Locate", "create", "complete", "archive"],
            "file-first approval": ["file-first", "完整 Spec", "完整 Plan", "自然语言批准", "validate-plan", "init-state"],
            "three-layer authority": ["change.md", "plan.yaml", "state.yaml", "Spec 权威", "批准合同权威", "动态恢复状态权威"],
            "single helper": ["唯一 runtime helper", "change.py", "status", "next-action"],
            "change-level allowed paths": ["change-level `allowed_paths`", "不分配给具体 Task", "finding owner routing"],
            "checkpoint and repair": ["checkpoint commit", "record-task", "REQUEST_REPAIR_DECISION", "record-repair", "in-scope"],
            "lightweight State": ["State 只保存当前恢复状态", "不保存完整 transition history", "完整 diff", "完整日志"],
            "delegation sizing": ["小型", "主会话直接", "大型", "默认委派", "bounded generic subagent"],
            "sequential writes": ["产品写入按 Task/repair 顺序执行", "不得新增 DAG scheduler", "并行产品写入"],
            "compact terminal": ["compact", "1–3 行", "默认不回显完整"],
            "deterministic-first": ["deterministic validation", "Review 不能替代失败的确定性校验", "exit code"],
            "knowledge candidate confirmation": ["知识候选", "五问", "用户确认", "拒绝不影响"],
            "legacy/v1": ["legacy/v1", "clear v1", "整体移动", "v1/v2 双栈"],
        }
        for group, alternatives in semantic_groups.items():
            with self.subTest(group=group):
                missing = [needle for needle in alternatives if needle not in corpus]
                self.assertFalse(missing, f"missing semantic anchors for {group}: {missing}")
        self.assertRegex(corpus, r"(?s)产品 mutation 前.*?(?:Spec|Plan|计划).*?(?:批准|approval)")
        self.assertRegex(corpus, r"(?s)(?:风险|Risk).*?(?:review|审查)")
        self.assertRegex(corpus, r"(?s)(?:知识|knowledge).*?(?:候选|candidate).*?(?:确认|confirm|用户)")

    def test_runtime_guidance_forbids_owner_routing_and_unapproved_mutation(self):
        paths = list(skill_paths().values()) + reference_paths_without_eval()
        corpus = "\n".join(read_text(path) for path in paths)
        work = read_text(SKILLS / "work" / "SKILL.md")
        lifecycle_guard_corpus = "\n".join(
            read_text(path)
            for path in [
                SKILLS / "work" / "SKILL.md",
                REFERENCES / "workflow.md",
                REFERENCES / "context-hygiene.md",
                REFERENCES / "eval-prompts.md",
            ]
        )
        for required in [
            "不做 owner mapping",
            "finding owner routing",
            "per-Task files ownership",
            "产品 mutation 前",
            "批准后才运行 `change.py init-state`",
            "不以 subagent claim 推进",
            "Helper 不自动 reset、rebase、squash、stash 或改写历史",
            "每个实施 Task 和每个 repair 单元恰好一个 checkpoint commit",
        ]:
            with self.subTest(required=required):
                self.assertIn(required, corpus)
        for required in [
            "Larger changes default to at least one bounded generic subagent unit",
            "change-level `allowed_paths`",
            "task base from `start-task`",
            "expected checkpoint subject",
            "compact return: checkpoint SHA, changed paths, commands with exit codes, risks, and blockers",
        ]:
            with self.subTest(work_required=required):
                self.assertIn(required, work)
        for required in [
            "TaskStop/Stop Task",
            "不得调用 TaskStop/Stop Task",
            "Controller/task-tracking",
            "不得创建、更新、停止或接管 Controller/task-tracking",
            "不得尝试停止自身、父任务、兄弟任务或后台任务",
            "完成、阻塞、超时或需要决策时",
            "只能返回 compact result 给主会话",
        ]:
            with self.subTest(lifecycle_guard_required=required):
                self.assertIn(required, lifecycle_guard_corpus)
        self.assertRegex(
            lifecycle_guard_corpus,
            r"(?s)(?:blocked|阻塞).*?(?:return only a compact result to the main session|只能返回 compact result 给主会话)",
        )
        self.assertRegex(corpus, r"(?s)超出.*?allowed_paths.*?(?:重新批准|Plan revision)")


if __name__ == "__main__":
    unittest.main()
