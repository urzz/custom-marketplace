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
REFERENCES = PLUGIN / "references"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
OLD_LIFECYCLE = {"project-init", "brief", "design", "implement", "verify", "fold"}
NEW_LIFECYCLE = {"init", "work", "finish"}
CHANGE_AUTHORITY_REFERENCES = ["authority.md", "lifecycle.md", "execution.md", "finish.md", "grill-protocol.md", "migration.md", "eval-prompts.md"]
ACTIVE_ROOT_ARTIFACT_RE = re.compile(
    r"(?<!changes/<change-id>/)\.dev-docs/"
    r"(contract\.yaml|context\.jsonl|state\.json|completion\.md|decision\.md|finish-apply\.md)"
)
ACTIVE_AUTHORITY_TERMS_RE = re.compile(
    r"\b(authority|authoritative|artifact|state|contract|context|evidence|completion|decision|finish|Gate|fresh|helper|allowed_writes|mutation_targets|writes?|writer|read|validate|identity|path|fixture)\b|"
    r"事实源|授权|写入|读取|校验|验证|状态|合约|证据|新鲜|路径|夹具"
)
EXPLICIT_NEGATIVE_OR_LEGACY_RE = re.compile(
    r"#\s*explicit negative fixture:|self\.assertNot(?:In|Regex)\(",
    re.I,
)
LEGACY_SOURCE_PATH_RE = re.compile(r"\blegacy source path\b|\blegacy artifact path\b", re.I)
LEGAL_PROJECT_LEVEL_RE = re.compile(r"\.dev-docs/(index\.md|changes/index\.md|knowledge/|archive/)")
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

    def test_finish_apply_journal_uses_evidence_path(self):
        finish = split_skill(SKILLS / "finish" / "SKILL.md")[1]
        work = split_skill(SKILLS / "work" / "SKILL.md")[1]
        canonical = "CHANGE_ROOT/evidence/finish-apply.md"
        full_change_local = ".dev-docs/changes/<change-id>/evidence/finish-apply.md"
        forbidden = [
            "CHANGE_ROOT/finish-apply.md",
            ".dev-docs/changes/<change-id>/finish-apply.md",
            ".dev-docs/finish-apply.md",  # explicit negative fixture: forbidden project-root finish apply evidence
        ]

        entry_guard = re.search(r"(?is)## Entry guard(?P<section>.*?)(?:\n## |\Z)", finish).group("section")
        accept_sequence = re.search(r"(?is)## Accept apply sequence(?P<section>.*?)(?:\n## |\Z)", finish).group("section")
        work_handoff_surface = "\n".join(
            re.search(rf"(?is)## {heading}(?P<section>.*?)(?:\n## |\Z)", work).group("section")
            for heading in ["Helper next-action loop", "Completion and decision handoff"]
        )

        for label, section in {
            "finish entry guard": entry_guard,
            "finish accept sequence": accept_sequence,
        }.items():
            with self.subTest(section=label):
                self.assertTrue(canonical in section or full_change_local in section, section)
        with self.subTest(section="work completion handoff surface"):
            self.assertTrue(
                canonical in work_handoff_surface
                or full_change_local in work_handoff_surface
                or ("CHANGE_ROOT" in work_handoff_surface and "evidence/finish-apply.md" in work_handoff_surface),
                work_handoff_surface,
            )

        for needle in [
            "create or append the target entry to the change-local `CHANGE_ROOT/evidence/finish-apply.md` journal evidence",
            "read back `CHANGE_ROOT/evidence/finish-apply.md`",
            "evidence-helper.py validate-finish-apply --decision-sha256 <sha256> --finish-plan-json <plan> --journal-json CHANGE_ROOT/evidence/finish-apply.md",
            "verified `CHANGE_ROOT/evidence/finish-apply.md` identity",
            "state-helper.py record-finish-apply <state> --expected-version <n> --journal-json CHANGE_ROOT/evidence/finish-apply.md",
        ]:
            with self.subTest(needle=needle):
                self.assertIn(needle, accept_sequence)

        for label, text in {"finish": finish, "work": work}.items():
            for bad_path in forbidden:
                with self.subTest(text=label, forbidden=bad_path):
                    self.assertNotIn(bad_path, text)

    def test_whole_plugin_contract_surfaces_use_change_local_authority_paths(self):
        required_paths = [
            "CHANGE_ROOT=.dev-docs/changes/<change-id>",
            "CHANGE_ROOT/contract.yaml",
            "CHANGE_ROOT/context.jsonl",
            "CHANGE_ROOT/state.json",
            "CHANGE_ROOT/research/",
            "CHANGE_ROOT/evidence/completion.md",
            "CHANGE_ROOT/evidence/decision.md",
            "CHANGE_ROOT/evidence/finish-apply.md",
        ]
        authority_corpus = "\n".join(read_text(REFERENCES / filename) for filename in CHANGE_AUTHORITY_REFERENCES)
        for needle in required_paths:
            with self.subTest(surface="reference corpus", needle=needle):
                self.assertIn(needle, authority_corpus)
        for filename in CHANGE_AUTHORITY_REFERENCES:
            text = read_text(REFERENCES / filename)
            with self.subTest(reference=filename, needle="CHANGE_ROOT declaration"):
                self.assertIn(required_paths[0], text)

        schema_text = "\n".join(
            json.dumps(load_json(path), ensure_ascii=False)
            for path in sorted((PLUGIN / "schemas").glob("*.json"))
        )
        for needle in [
            ".dev-docs/changes/<change-id>/contract.yaml",
            ".dev-docs/changes/<change-id>/context.jsonl",
            ".dev-docs/changes/<change-id>/state.json",
        ]:
            with self.subTest(surface="schemas", needle=needle):
                self.assertIn(needle, schema_text)

        state_helper = read_text(SCRIPTS / "state-helper.py")
        self.assertIn(".dev-docs/changes/<change-id>/state.json", state_helper)
        helper_fixture_text = read_text(SCRIPTS / "test_packet_helper.py") + "\n" + read_text(SCRIPTS / "test_state_helper.py")
        for needle in [
            ".dev-docs/changes/change-alpha/contract.yaml",
            ".dev-docs/changes/change-alpha/context.jsonl",
        ]:
            with self.subTest(surface="helper fixtures", needle=needle):
                self.assertIn(needle, helper_fixture_text)

        violations = []
        for path in all_plugin_text_files():
            text = read_text(path)
            for number, line in enumerate(text.splitlines(), 1):
                if not ACTIVE_ROOT_ARTIFACT_RE.search(line):
                    continue
                if LEGAL_PROJECT_LEVEL_RE.search(line):
                    continue
                if EXPLICIT_NEGATIVE_OR_LEGACY_RE.search(line):
                    continue
                if path == REFERENCES / "migration.md" and LEGACY_SOURCE_PATH_RE.search(line):
                    continue
                if ACTIVE_AUTHORITY_TERMS_RE.search(line):
                    violations.append(f"{path.relative_to(PLUGIN)}:{number}:{line.strip()}")
        self.assertEqual(violations, [], "positive project-root active authority paths found")

    def test_authority_scan_exemptions_do_not_hide_positive_project_root_authority(self):
        root = ".dev-docs/"
        positive_lines = [
            f"Positive authority, not a negative fixture: helper reads `{root}state.json` as fresh Contract authority.",
            f"Positive authority in migration discussion: helper validates `{root}contract.yaml` as active contract artifact.",
            f"Positive authority, legacy mention only: `{root}context.jsonl` is the active context path.",
            f"Positive authority with invalid wording: helper treats `{root}completion.md` as fresh completion evidence.",
            f"Positive authority with rejection wording: helper writes `{root}decision.md` after Gate accept.",
        ]
        for line in positive_lines:
            with self.subTest(line=line):
                active = bool(ACTIVE_ROOT_ARTIFACT_RE.search(line))
                exempt = bool(EXPLICIT_NEGATIVE_OR_LEGACY_RE.search(line))
                legacy_source = bool(LEGACY_SOURCE_PATH_RE.search(line))
                authority = bool(ACTIVE_AUTHORITY_TERMS_RE.search(line))
                self.assertTrue(active)
                self.assertTrue(authority)
                self.assertFalse(exempt)
                self.assertFalse(legacy_source)
                self.assertTrue(active and not exempt and not legacy_source and authority)

    def test_authority_scan_allows_structural_negative_fixture_and_legal_project_level_cases(self):
        root = ".dev-docs/"
        negative_fixture_lines = [
            'forbidden = [".dev-docs/finish-apply.md"]  # explicit negative fixture: forbidden project-root finish apply evidence',
            'self.assertNotIn(".dev-docs/state.json", rows[case_id]["allowed_writes"])',
        ]
        for line in negative_fixture_lines:
            with self.subTest(kind="negative fixture", line=line):
                self.assertTrue(ACTIVE_ROOT_ARTIFACT_RE.search(line))
                self.assertTrue(EXPLICIT_NEGATIVE_OR_LEGACY_RE.search(line))

        legal_project_level_lines = [
            "Project index authority remains `.dev-docs/index.md` for fact-source bootstrap.",
            "Knowledge writes may target `.dev-docs/knowledge/product.md` after fresh Finish approval.",
            "The active change index is `.dev-docs/changes/index.md`.",
            "Approved archive target `.dev-docs/archive/change.json` is legal after Finish accept.",
        ]
        for line in legal_project_level_lines:
            with self.subTest(kind="legal project level", line=line):
                self.assertTrue(LEGAL_PROJECT_LEVEL_RE.search(line))
                self.assertFalse(ACTIVE_ROOT_ARTIFACT_RE.search(line))

        legacy_source_line = f"Migration may read a user-selected legacy source path `{root}state.json` only to produce CHANGE_ROOT/state.json."
        self.assertTrue(ACTIVE_ROOT_ARTIFACT_RE.search(legacy_source_line))
        self.assertTrue(LEGACY_SOURCE_PATH_RE.search(legacy_source_line))
        self.assertTrue(ACTIVE_AUTHORITY_TERMS_RE.search(legacy_source_line))

    def test_eval_owner_routing_keeps_contract_work_out_of_init(self):
        eval_prompts = read_text(REFERENCES / "eval-prompts.md")
        rows = {}
        for line in eval_prompts.splitlines():
            match = re.match(r"\| `([^`]+)` \| (.*?) \| `(init|work|finish)` \| (.*?) \| (.*?) \| (.*?) \| (.*?) \|$", line)
            if match:
                case_id, case_input, owner, next_action, allowed_writes, forbidden_writes, assertions = match.groups()
                rows[case_id] = {
                    "input": case_input,
                    "owner_skill": owner,
                    "expected_next_action": next_action,
                    "allowed_writes": allowed_writes,
                    "forbidden_writes": forbidden_writes,
                    "assertions": assertions,
                }

        contract_work_case_pattern = re.compile(
            r"contract-draft|contract-repair|contract-approval|contract-revise|contract-reject|resume-deferred-contract"
        )
        expected_work_cases = {
            "work-contract-draft-new-change",
            "work-contract-draft-safe-defaults",
            "work-contract-draft-five-questions",
            "work-contract-repair-missing-context-fingerprint",
            "work-contract-approval-exact",
            "work-contract-revise",
            "work-contract-reject",
            "work-resume-deferred-contract-stale",
        }
        actual_contract_work_cases = {case_id for case_id in rows if contract_work_case_pattern.search(case_id)}
        self.assertEqual(actual_contract_work_cases, expected_work_cases)
        for case_id in sorted(expected_work_cases):
            with self.subTest(case=case_id, field="owner_skill"):
                self.assertEqual(rows[case_id]["owner_skill"], "work")
            with self.subTest(case=case_id, field="allowed_writes"):
                self.assertNotIn(".dev-docs/contract.yaml", rows[case_id]["allowed_writes"])
                self.assertNotIn(".dev-docs/context.jsonl", rows[case_id]["allowed_writes"])
                self.assertNotIn(".dev-docs/state.json", rows[case_id]["allowed_writes"])
                self.assertIn("CHANGE_ROOT", rows[case_id]["allowed_writes"])

        init_cases = {case_id: row for case_id, row in rows.items() if row["owner_skill"] == "init"}
        self.assertTrue(init_cases)
        for case_id, row in init_cases.items():
            with self.subTest(init_case=case_id):
                self.assertRegex(case_id, r"^(init-bootstrap|init-repair|migration-|multi-active-change-refuse-guess|baseline-)")
                self.assertNotRegex(case_id, r"contract-(approval|revise|reject)|resume-deferred")
                if not case_id.startswith("migration-apply"):
                    self.assertNotRegex(row["allowed_writes"], r"(?<!TARGET_)CHANGE_ROOT/(contract\.yaml|context\.jsonl|state\.json)")
                self.assertNotRegex(row["expected_next_action"], r"生成可审 .*contract|批准 Contract Gate|返回 drafting_contract")
        self.assertIn("`init` 只负责 project fact-source bootstrap/repair/legacy migration", eval_prompts)
        self.assertIn("STOP before work", eval_prompts)

    def test_reference_eval_finish_tokens_match_helper_enum_without_spaced_machine_token(self):
        state_helper = load_helper_module("state-helper.py")
        expected = {"accept", "request_changes", "defer", "reject"}
        self.assertEqual(state_helper.FINISH_DECISIONS, expected)
        machine_context = "\n".join(read_text(REFERENCES / filename) for filename in ["finish.md", "eval-prompts.md"])
        for token in expected:
            with self.subTest(token=token):
                self.assertIn(f"`{token}`", machine_context)
        self.assertIn("--decision request_changes", split_skill(SKILLS / "finish" / "SKILL.md")[1])
        self.assertNotIn("`request changes`", machine_context)
        self.assertNotRegex(machine_context, r"exact token `[^`]*request changes[^`]*`")
        self.assertNotRegex(machine_context, r"用户输入 exact token `request changes`")
        self.assertNotRegex(machine_context, r"--decision request changes")
        self.assertRegex(machine_context, r"(?is)`accept`.*?`request_changes`.*?`defer`.*?`reject`")

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
            "CHANGE_ROOT/evidence/finish-apply.md",
            "evidence-helper.py validate-finish-apply --decision-sha256 <sha256> --finish-plan-json <plan> --journal-json CHANGE_ROOT/evidence/finish-apply.md",
            "Only an ok JSON result for the verified `CHANGE_ROOT/evidence/finish-apply.md` identity permits setting `verified: true` and `journal_sha256`",
            "state-helper.py record-finish-apply <state> --expected-version <n> --journal-json CHANGE_ROOT/evidence/finish-apply.md",
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
