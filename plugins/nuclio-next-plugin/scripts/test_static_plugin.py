"""
Nuclio Next static plugin contract tests.

## Contents

- [Helpers](#helpers)
- [Static plugin structure tests](#static-plugin-structure-tests)
- [Coordinator skill contract tests](#coordinator-skill-contract-tests)
- [Packet, agent and baseline tests](#packet-agent-and-baseline-tests)
- [Eval trajectory assertions](#eval-trajectory-assertions)
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional validation dependency
    jsonschema = None

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "plugins" / "nuclio-next-plugin"
SCRIPTS = PLUGIN / "scripts"
SKILLS = PLUGIN / "skills"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
OLD_LIFECYCLE = {"project-init", "brief", "design", "implement", "verify", "fold"}
NEW_LIFECYCLE = {"init", "work", "finish"}
HEX = {
    "a": "a" * 64,
    "b": "b" * 64,
    "c": "c" * 64,
    "d": "d" * 64,
    "e": "e" * 64,
    "f": "f" * 64,
}


def read_text(path):
    return path.read_text(encoding="utf-8")


def split_skill(path):
    text = read_text(path)
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
    if not match:
        raise AssertionError(f"{path} must contain YAML frontmatter")
    frontmatter = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.lower() == "true":
            parsed = True
        elif value.lower() == "false":
            parsed = False
        else:
            parsed = value.strip('"')
        frontmatter[key.strip()] = parsed
    return frontmatter, match.group(2)


def all_plugin_text_files():
    for path in PLUGIN.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".md", ".py", ".json"}:
            yield path


def load_json(path):
    return json.loads(read_text(path))


def load_helper_module(filename):
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_"), SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(ch):
    return HEX[ch]


class StaticPluginTests(unittest.TestCase):
    def skills(self):
        return {path.parent.name: path for path in SKILLS.glob("*/SKILL.md")}

    def test_plugin_metadata_and_skill_directory_are_exact(self):
        metadata = load_json(PLUGIN / ".claude-plugin" / "plugin.json")
        self.assertEqual(metadata["name"], "nuclio-next")
        self.assertRegex(metadata["version"], r"^0\.1\.0$")
        self.assertEqual(set(self.skills()), NEW_LIFECYCLE)
        self.assertEqual({path.name for path in SKILLS.iterdir() if path.is_dir()}, NEW_LIFECYCLE)

    def test_skill_frontmatter_description_and_size_contract(self):
        for name, path in self.skills().items():
            with self.subTest(skill=name):
                frontmatter, body = split_skill(path)
                self.assertEqual(frontmatter["name"], name)
                self.assertTrue(frontmatter["disable-model-invocation"])
                description = frontmatter["description"]
                self.assertLessEqual(len(description), 1024)
                self.assertTrue(description.startswith("Use when"), description)
                self.assertRegex(description, r"^Use when (a|an|the|users?|someone|teams?|projects?)\b")
                self.assertLess(len(body.splitlines()), 500)
                if len(body.splitlines()) > 100:
                    self.assertIn("## Contents", body)
                    headings = re.findall(r"^## (.+)$", body, re.M)
                    anchors = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in headings if h != "Contents"}
                    for anchor in anchors:
                        self.assertIn(f"](#{anchor})", body)

    def test_progressive_disclosure_and_reference_links_are_one_level(self):
        for path in all_plugin_text_files():
            text = read_text(path)
            if path.suffix == ".md" and len(text.splitlines()) > 100:
                self.assertIn("## Contents", text, f"{path} needs Contents")
        for skill_name, path in self.skills().items():
            body = split_skill(path)[1]
            links = re.findall(r"\]\(([^)]+)\)", body)
            reference_links = [link for link in links if link.startswith("../../references/")]
            self.assertTrue(reference_links, f"{skill_name} should use progressive disclosure links")
            for link in reference_links:
                rest = link.removeprefix("../../references/").split("#", 1)[0]
                self.assertNotIn("/", rest, f"nested reference link is forbidden: {link}")
        for ref in (PLUGIN / "references").rglob("*.md"):
            rel = ref.relative_to(PLUGIN / "references")
            self.assertEqual(len(rel.parts), 1, f"nested reference file is forbidden: {rel}")

    def test_json_metadata_and_schemas_are_valid_and_packet_fixtures_conform(self):
        for path in [PLUGIN / ".claude-plugin" / "plugin.json", *sorted((PLUGIN / "schemas").glob("*.json"))]:
            with self.subTest(json=path.name):
                load_json(path)
        if jsonschema is None:
            self.skipTest("jsonschema not installed")
        schema = load_json(PLUGIN / "schemas" / "packet.schema.json")
        validator = jsonschema.Draft202012Validator(schema)
        fixtures = self.packet_fixtures()
        self.assertEqual(set(fixtures), {"worker", "reviewer", "completion", "finish"})
        for role, packet in fixtures.items():
            with self.subTest(role=role):
                errors = sorted(validator.iter_errors(packet), key=lambda error: list(error.absolute_path))
                self.assertEqual(errors, [], [error.message for error in errors])

    def packet_fixtures(self):
        common = {
            "schema_version": 1,
            "change_id": "change-alpha",
            "contract_sha256": sha("a"),
            "context_fingerprint": sha("b"),
            "state_version": 7,
        }
        checks = {"focused": [{"name": "focused", "command": ["python3", "-m", "unittest"]}], "full": [{"name": "full", "command": ["claude", "plugin", "validate", "plugins/nuclio-next-plugin", "--strict"]}]}
        return {
            "worker": {**common, "packet_id": sha("c"), "role": "worker", "task_id": "T1", "ownership": [{"path": "plugins/nuclio-next-plugin/skills/init/SKILL.md", "mode": "create"}], "range": {"base_head": "abcdef1", "expected_dirty_state": "clean"}, "snapshots": [{"path": "handoff.json", "state": "absent"}], "checks": checks},
            "reviewer": {**common, "packet_id": sha("d"), "role": "reviewer", "task_id": "T1", "ownership": [{"path": "plugins/nuclio-next-plugin/skills/init/SKILL.md", "mode": "read"}], "range": {"base_head": "abcdef1", "new_head": "abcdef2", "expected_dirty_state": "clean"}, "snapshots": [{"path": "iface.md", "state": "present", "sha256": sha("a")}], "checks": checks, "review_targets": ["plugins/nuclio-next-plugin/skills/init/SKILL.md"], "mutation_map_sha256": sha("e")},
            "completion": {**common, "packet_id": sha("e"), "role": "completion", "task_heads": {"T1": "abcdef2"}, "implementation_range": {"base": "abcdef1", "head": "abcdef2"}, "acceptance_index_sha256": sha("a"), "task_evidence": {"T1": sha("b")}, "task_evidence_sha256": sha("c"), "range": {"base_head": "abcdef1", "new_head": "abcdef2", "expected_dirty_state": "clean"}, "checks": {**checks, "change_wide": checks["focused"]}, "handoffs": ["task:T1@abcdef2"], "mutation_map_sha256": sha("d")},
            "finish": {**common, "packet_id": sha("f"), "role": "finish", "range": {"base_head": "abcdef1", "new_head": "abcdef2", "expected_dirty_state": "clean"}, "snapshots": [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], "completion_sha256": sha("c"), "decision_sha256": sha("d"), "finish_plan_sha256": sha("e"), "knowledge_proposal": {"summary": "approved finish knowledge only"}, "knowledge_targets": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None}], "archive_targets": [{"path": ".dev-docs/archive/change.json", "before_sha256": sha("a")}], "archive_intent": "archive only after fresh accept"},
        }

    def test_agent_tools_are_exact_and_reviewers_are_read_only(self):
        expected = {
            "nuclio-implementer.md": "Read, Edit, Write, Grep, Glob, Bash",
            "nuclio-fixer.md": "Read, Edit, Write, Grep, Glob, Bash",
            "nuclio-task-reviewer.md": "Read, Grep, Glob, Bash",
            "nuclio-completion-critic.md": "Read, Grep, Glob, Bash",
        }
        for filename, tools in expected.items():
            with self.subTest(agent=filename):
                frontmatter, body = split_skill(PLUGIN / "agents" / filename)
                self.assertEqual(frontmatter["tools"], tools)
                if "reviewer" in filename or "critic" in filename:
                    self.assertNotIn("Edit", frontmatter["tools"])
                    self.assertNotIn("Write", frontmatter["tools"])
                    self.assertIn("read-only", body.lower())

    def test_marketplace_not_registered_and_release_targets_not_declared(self):
        marketplace = load_json(MARKETPLACE)
        registered = {plugin["source"] for plugin in marketplace["plugins"]} | {plugin["name"] for plugin in marketplace["plugins"]}
        self.assertNotIn("./plugins/nuclio-next-plugin", registered)
        self.assertNotIn("nuclio-next", registered)
        forbidden_targets = [".claude-plugin/marketplace.json", "README.md", "CLAUDE.md", "plugins/nuclio-plugin/"]
        mutation_pattern = re.compile(r"(mutation_targets|allowed_writes|write authority|修改|写入|创建|删除)", re.I)
        for path in all_plugin_text_files():
            text = read_text(path)
            for target in forbidden_targets:
                with self.subTest(path=path.name, target=target):
                    for line in text.splitlines():
                        if target in line and mutation_pattern.search(line):
                            self.fail(f"{path} declares forbidden target mutation: {line}")

    def test_old_lifecycle_is_not_canonical_but_legal_as_baseline_or_migration(self):
        skill_dirs = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertTrue(OLD_LIFECYCLE.isdisjoint(skill_dirs))
        allowed_context = re.compile(r"(legacy|baseline|migration|旧|只读)", re.I)
        for path in list(self.skills().values()) + [PLUGIN / "references" / "eval-prompts.md"]:
            text = read_text(path)
            for old in OLD_LIFECYCLE - {"design"}:
                for line in text.splitlines():
                    token = re.search(rf"(?<![A-Za-z0-9_-]){re.escape(old)}(?![A-Za-z0-9_-])", line)
                    if token and not allowed_context.search(line):
                        self.fail(f"{path} mentions old lifecycle without baseline/migration context: {line}")

    def test_runtime_mechanisms_are_not_implemented(self):
        forbidden = ["daemon", "MCP server", "runtime hook", ".nuclio/", ".claude/ installation"]
        for path in all_plugin_text_files():
            text = read_text(path)
            for phrase in forbidden:
                for line in text.splitlines():
                    if phrase.lower() in line.lower():
                        self.assertRegex(line, r"不|no |not |forbid|forbidden|禁止", f"runtime mechanism may be implemented in {path}: {line}")

    def test_coordinator_skills_encode_required_behavior_trajectories(self):
        init = split_skill(SKILLS / "init" / "SKILL.md")[1]
        work = split_skill(SKILLS / "work" / "SKILL.md")[1]
        finish = split_skill(SKILLS / "finish" / "SKILL.md")[1]
        for text, needles in {
            "init": ["inspect", "proposal", "preview", "current turn explicit approval", "STOP", "does not create product code", "does not start work", "legacy migration"],
            "work": ["state-helper.py inspect", "next-action", "multiple active changes", "at most 5", "recommendation-first", "Contract Gate hard STOP", "fresh Contract approval", "fresh implementer", "fresh read-only reviewer", "fresh completion critic", "completion.md", "decision.md", "Completion Verdict", "Remaining Risks", "Knowledge Proposal", "Archive Decision", "STOP", "does not patch product files"],
            "finish": ["decision_pending", "Completion Verdict", "Remaining Risks", "Knowledge Proposal", "Archive Decision", "accept", "request_changes", "defer", "reject", "ambiguous", "fresh accept", "finish-apply.md", "does not modify product code"],
        }.items():
            body = {"init": init, "work": work, "finish": finish}[text]
            for needle in needles:
                with self.subTest(skill=text, needle=needle):
                    self.assertIn(needle, body)
        self.assertRegex(work, r"(?is)Contract Gate hard STOP.*?fresh Contract approval.*?forbid")
        self.assertRegex(finish, r"(?is)exact token.*?accept.*?request_changes.*?defer.*?reject")
        self.assertRegex(finish, r"(?is)fresh accept.*?Knowledge Proposal.*?Archive Decision")

    def test_finish_decision_token_matches_helper_enum(self):
        state_helper = load_helper_module("state-helper.py")
        finish = split_skill(SKILLS / "finish" / "SKILL.md")[1]
        self.assertIn("request_changes", state_helper.FINISH_DECISIONS)
        self.assertIn("`request_changes`", finish)
        self.assertIn("--decision request_changes", finish)
        self.assertNotIn("request changes", finish)
        self.assertRegex(finish, r"(?is)exact token.*?accept.*?request_changes.*?defer.*?reject")

    def test_init_references_only_real_init_and_migration_command_surfaces(self):
        init = split_skill(SKILLS / "init" / "SKILL.md")[1]
        self.assertIn("project fact-source bootstrap/repair path only", init)
        self.assertIn(".dev-docs/index.md", init)
        self.assertIn(".dev-docs/knowledge/product.md", init)
        self.assertIn(".dev-docs/knowledge/architecture.md", init)
        self.assertIn(".dev-docs/knowledge/engineering.md", init)
        self.assertIn(".dev-docs/changes/index.md", init)
        self.assertIn("state-helper.py inspect <state>", init)
        self.assertIn("state-helper.py next-action <state>", init)
        self.assertIn("migration-helper.py detect --legacy-change-path <path> --target-change-path <path>", init)
        self.assertIn("migration-helper.py preview --legacy-change-path <path> --target-change-path <path>", init)
        self.assertIn("migration-helper.py apply --legacy-change-path <path> --target-change-path <path> --apply --preview-identity <sha256> --approval-json <json>", init)
        self.assertIn("contract-helper and context-helper validation are work drafting surfaces only", init)
        self.assertNotRegex(init, r"\.dev-docs/(contract\.yaml|context\.jsonl|state\.json).*bootstrap artifacts through helpers")
        self.assertNotIn("helper apply/validate action", init)

    def test_change_artifacts_are_change_local(self):
        init = split_skill(SKILLS / "init" / "SKILL.md")[1]
        work = split_skill(SKILLS / "work" / "SKILL.md")[1]
        finish = split_skill(SKILLS / "finish" / "SKILL.md")[1]
        required = {
            "init": [".dev-docs/index.md", ".dev-docs/knowledge/product.md", ".dev-docs/changes/index.md", ".dev-docs/changes/<change-id>"],
            "work": ["CHANGE_ROOT", "contract.yaml", "context.jsonl", "state.json", "research/", "evidence/tasks/<task-id>/...", "evidence/completion.md", "evidence/decision.md", "evidence/finish-apply.md"],
            "finish": ["CHANGE_ROOT", "evidence/decision.md", "state.json", "contract.yaml", "context.jsonl", "evidence/completion.md", "evidence/finish-apply.md"],
        }
        for name, needles in required.items():
            body = {"init": init, "work": work, "finish": finish}[name]
            for needle in needles:
                with self.subTest(skill=name, needle=needle):
                    self.assertIn(needle, body)
        project_level_root_artifact = re.compile(r"(?<!changes/<change-id>/)\.dev-docs/(contract\.yaml|context\.jsonl|state\.json|completion\.md|decision\.md|finish-apply\.md)")
        for name, body in {"init": init, "work": work, "finish": finish}.items():
            with self.subTest(skill=name, reject="root change artifact"):
                self.assertNotRegex(body, project_level_root_artifact)
        self.assertIn("Both `<path>` values must be `.dev-docs/changes/<change-id>` directories", init)
        self.assertIn("pass only absolute resolved `CHANGE_ROOT` artifact paths to helpers", work)
        self.assertIn("absolute resolved `CHANGE_ROOT/state.json`", finish)

    def test_finish_accept_apply_uses_controller_sequence_and_real_helper_flags(self):
        finish = split_skill(SKILLS / "finish" / "SKILL.md")[1]
        required_in_order = [
            "state-helper.py finish-decision <state> --expected-version <n> --decision accept --metadata-json <json>",
            "state-helper.py next-action <state>` returns `APPLY_FINISH`",
            "There is no separate finish applier agent or unsupported applier role",
            "state-helper.py inspect <state>",
            "state-helper.py next-action <state>",
            "packet-helper.py finish --repo <repo> --contract-json <contract> --context-json <context> --state-json <state> --base <base> --head <head> --output <packet> --expected-state-version <n> --decision-json <decision> --completion-identity-json <identity> --finish-plan-json <plan> --knowledge-snapshots-json <json>",
            "compare `before_sha256`",
            "`before_sha256: null` as create-only absent",
            "no untracked/out-of-packet targets",
            "Controller Write/Edit is limited to exact approved",
            "Do not write product files",
            "finish-apply.md",
            "evidence-helper.py validate-finish-apply --decision-sha256 <sha256> --finish-plan-json <plan> --journal-json <journal>",
            "Only an ok JSON result permits setting `verified: true` and `journal_sha256`",
            "state-helper.py record-finish-apply <state> --expected-version <n> --journal-json <journal>",
            "partial write failure",
            "do not invent rollback",
        ]
        cursor = -1
        for needle in required_in_order:
            with self.subTest(needle=needle):
                next_cursor = finish.find(needle, cursor + 1)
                self.assertGreater(next_cursor, cursor, needle)
                cursor = next_cursor
        self.assertNotRegex(finish, r"(?i)dispatch .*finish applier")
        self.assertNotRegex(finish, r"(?i)fresh finish applier")
        self.assertNotIn("rollback", finish.lower().replace("do not invent rollback", ""))


if __name__ == "__main__":
    unittest.main()
