"""
Packet helper tests.

## Contents

- [Fixture builders](#fixture-builders)
- [Role packet contracts](#role-packet-contracts)
- [Freshness and CLI tests](#freshness-and-cli-tests)
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional validation dependency
    jsonschema = None

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "packet-helper.py"
STATE_HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "state-helper.py"
CONTRACT_HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "contract-helper.py"
JSON_SCHEMA_HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "json-schema-helper.py"
SCHEMA = ROOT / "plugins" / "nuclio-plugin" / "schemas" / "packet.schema.json"
A_HASH = "a" * 64
B_HASH = "b" * 64
C_HASH = "c" * 64
D_HASH = "d" * 64
E_HASH = "e" * 64
F_HASH = "f" * 64


def load_helper():
    spec = importlib.util.spec_from_file_location("packet_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_state_helper():
    spec = importlib.util.spec_from_file_location("state_helper", STATE_HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_contract_helper():
    spec = importlib.util.spec_from_file_location("contract_helper", CONTRACT_HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json_schema_helper():
    spec = importlib.util.spec_from_file_location("json_schema_helper", JSON_SCHEMA_HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract(output_language="en"):
    return {
        "schema_version": 1,
        "change_id": "change-alpha",
        "contract_version": "v1",
        "output_language": output_language,
        "sha256": A_HASH,
        "acceptance": [{"id": "AC-object", "text": "object id acceptance"}, "string acceptance", {"text": "object without id"}],
        "tasks": [
            {
                "id": "T1",
                "name": "Task one",
                "owner": "owner-a",
                "dependencies": [],
                "mutation_targets": [{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "create"}],
                "handoffs": {"inputs": [], "outputs": ["artifact-a"]},
                "checks": {"focused": [{"name": "focused", "command": ["python3", "test.py"]}], "full": [{"name": "full", "command": ["python3", "all.py"]}]},
                "rollback": "delete a.py",
            },
            {
                "id": "T2",
                "name": "Task two",
                "owner": "owner-a",
                "dependencies": ["T1"],
                "mutation_targets": [{"path": "plugins/nuclio-plugin/scripts/b.py", "mode": "modify"}],
                "handoffs": {"inputs": ["artifact-a"], "outputs": ["artifact-b"]},
                "checks": {"focused": [{"name": "focused2", "command": ["python3", "test2.py"]}], "full": [{"name": "full2", "command": ["python3", "all2.py"]}]},
                "rollback": "restore b.py",
            },
        ],
        "validation": {"focused": [{"name": "vf", "command": ["python3"]}], "full": [{"name": "vfull", "command": ["python3"]}], "change_wide": [{"name": "cw", "command": ["python3"]}]},
    }


def context():
    return {
        "fingerprint": B_HASH,
        "entries": ["all-context"],
        "split": {
            "worker": [{"id": "worker-ref", "path": "plugins/nuclio-plugin/references/execution.md"}],
            "reviewer": [{"id": "review-ref", "path": "plugins/nuclio-plugin/references/authority.md"}],
            "completion": [{"id": "completion-ref", "path": "plugins/nuclio-plugin/references/execution.md"}],
            "finish": [{"id": "plugins/nuclio-plugin/references/finish.md", "path": "plugins/nuclio-plugin/references/finish.md"}],
        },
    }


def state(all_completed=False):
    tasks = [
        {"id": "T1", "status": "completed" if all_completed else "ready", "ownership": ["plugins/nuclio-plugin/scripts/a.py"], "packet_sha256": C_HASH},
        {"id": "T2", "status": "completed" if all_completed else "pending", "ownership": ["plugins/nuclio-plugin/scripts/b.py"], "packet_sha256": D_HASH},
    ]
    return {
        "schema_version": 1,
        "state_version": 7,
        "change_id": "change-alpha",
        "status": "executing",
        "contract": {"path": ".dev-docs/changes/change-alpha/contract.yaml", "sha256": A_HASH, "version": "v1", "output_language": "en"},
        "context": {"path": ".dev-docs/changes/change-alpha/context.jsonl", "fingerprint": B_HASH, "entries": ["all-context"]},
        "tasks": tasks,
        "gates": {"contract": {"status": "approved"}, "finish": {"status": "none"}},
        "history": [{"event": "INITIALIZED", "reason": json.dumps({"heads": {"T1": "1111111", "T2": "2222222"}})}],
    }


def mutation_map():
    return {"mutation_map": {"sha256": E_HASH, "changed_paths": ["plugins/nuclio-plugin/scripts/a.py"], "blockers": []}}


def completed_tasks():
    return [{"task_id": "T1", "head": "1111111", "evidence_sha256": A_HASH}, {"task_id": "T2", "head": "2222222", "evidence_sha256": B_HASH}]


def acceptance_index():
    return [{"id": "AC-object", "accepted": True, "evidence": "tests"}, {"id": "A2", "accepted": True, "evidence": "review"}, {"id": "A3", "accepted": True, "evidence": "contract"}]


def normalized_contract_for_state():
    doc = contract("zh-CN")
    doc.pop("sha256")
    doc["intent"] = {"goals": ["Bind real packets"], "non_goals": [], "confirmed_answers": []}
    doc["acceptance"] = ["worker evidence records after packet bind"]
    doc["constraints"] = ["no placeholder packet sha"]
    doc["design"] = {"boundaries": "helpers only", "data_flow": "contract context state packet", "contracts": "stable JSON", "tradeoffs": "fail closed"}
    doc["context_policy"] = {"required": [], "jit": [], "forbidden": ["full_conversation"], "budget": {"total": 10}}
    doc["validation"] = {"focused": [{"name": "focused", "command": ["python3"]}], "full": [{"name": "full", "command": ["python3"]}], "change_wide": [{"name": "wide", "command": ["python3"]}]}
    doc["tasks"] = doc["tasks"][:1]
    return doc


def self_hash(value, self_field):
    body = {key: value[key] for key in sorted(value) if key != self_field}
    return load_helper().sha256_value(body)


def finish_target(path, before_sha256, proposed_after_summary, reason, source_evidence, target_language, language_source):
    return {
        "path": path,
        "before_sha256": before_sha256,
        "proposed_after_summary": proposed_after_summary,
        "reason": reason,
        "source_evidence": source_evidence,
        "target_language": target_language,
        "language_source": language_source,
    }


def finish_plan(new_language="en", existing_language="en", existing_source="existing_target", include_index=True):
    plan = {
        "schema_version": 1,
        "contract_sha256": A_HASH,
        "context_fingerprint": B_HASH,
        "completion_sha256": C_HASH,
        "decision_sha256": F_HASH,
        "mutation_map_sha256": E_HASH,
        "acceptance_index_sha256": B_HASH,
        "implementation_range": {"base": "abcdef1", "head": "abcdef9"},
        "task_heads": {"T1": "1111111", "T2": "2222222"},
        "decision_state_version": 8,
        "knowledge_proposal": {"summary": "retain validated decisions"},
        "knowledge_targets": [
            finish_target(".dev-docs/knowledge/notes.md", None, "Knowledge summary exactly", "Keep validated decisions exactly", F_HASH, new_language, "contract_output_language")
        ],
        "archive_targets": [
            finish_target(".dev-docs/archive/change.json", A_HASH, "Archive summary exactly", "Archive validated handoff exactly", F_HASH, existing_language, existing_source)
        ],
        "index_targets": [],
        "archive_intent": "archive change-local evidence after finish approval",
    }
    if include_index:
        plan["index_targets"].append(finish_target(".dev-docs/changes/index.md", None, "Index summary exactly", "Index archived change exactly", F_HASH, new_language, "contract_output_language"))
    plan["finish_plan_sha256"] = self_hash(plan, "finish_plan_sha256")
    return plan


def completion_identity_doc():
    return {
        "completion_identity": {
            "contract_sha256": A_HASH,
            "context_fingerprint": B_HASH,
            "completion_sha256": C_HASH,
            "mutation_map_sha256": E_HASH,
            "acceptance_index_sha256": B_HASH,
            "implementation_range": {"base": "abcdef1", "head": "abcdef9"},
            "task_heads": {"T1": "1111111", "T2": "2222222"},
            "state_version": 7,
        }
    }


def decision_doc():
    return {
        "contract_sha256": A_HASH,
        "context_fingerprint": B_HASH,
        "decision": {"decision_sha256": F_HASH, "completion_sha256": C_HASH, "decision_state_version": 8},
    }


def finish_gate_notes(plan):
    return {
        "change_root": "/tmp/change-alpha",
        "decision": "accept",
        "decision_sha256": F_HASH,
        "finish_plan_sha256": plan["finish_plan_sha256"],
        "expected_decision_state_version": 8,
        "readiness": {"decision_sha256": F_HASH, "finish_plan_sha256": plan["finish_plan_sha256"], "decision_state_version": 8},
    }


def finish_state(plan=None):
    plan = plan or finish_plan()
    doc = state(all_completed=True)
    doc["completion"] = dict(completion_identity_doc()["completion_identity"])
    doc["decision"] = {**dict(completion_identity_doc()["completion_identity"]), "decision_sha256": F_HASH, "finish_plan_sha256": plan["finish_plan_sha256"], "decision_state_version": 8, "state_version": 7, "approved": True}
    doc["gates"]["finish"] = {"status": "approved", "decision_sha256": F_HASH, "artifact_sha256": F_HASH, "state_version": 7, "notes": json.dumps(finish_gate_notes(plan))}
    return doc


class PacketHelperTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()
        self.schema_helper = load_json_schema_helper()
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.validator = jsonschema.Draft202012Validator(self.schema) if jsonschema is not None else None
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)

    def schema_errors(self, packet):
        if self.validator is not None:
            return sorted(self.validator.iter_errors(packet), key=lambda error: list(error.absolute_path))
        try:
            self.schema_helper.validate_instance(SCHEMA, packet)
        except self.schema_helper.SchemaValidationError as exc:
            return [exc]
        return []

    def assert_schema_valid(self, packet):
        errors = self.schema_errors(packet)
        self.assertEqual(errors, [], [getattr(error, "message", getattr(error, "reason", str(error))) for error in errors])

    def assert_schema_invalid(self, packet):
        errors = self.schema_errors(packet)
        self.assertNotEqual(errors, [], packet)

    def generated_role_packets(self):
        return {
            "worker": self.helper.worker_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef1", [{"path": "handoff.json", "state": "absent"}], 7),
            "reviewer": self.helper.reviewer_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef2", mutation_map(), {"evidence_paths": ["evidence/t1.json"]}, [{"path": "iface.py", "state": "present", "sha256": A_HASH}], 7),
            "completion": self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), completed_tasks(), acceptance_index(), {"evidence_paths": ["validation.json"]}, ["risk-1"], 7),
            "finish": self.helper.finish_packet(self.repo, contract(), context(), finish_state(), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), finish_plan(), [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7),
        }

    def assert_role_fields_forbidden(self, base_packet, forbidden_fields):
        for field, value in forbidden_fields.items():
            with self.subTest(role=base_packet["role"], forbidden_field=field):
                self.assertNotIn(field, base_packet)
                bad = dict(base_packet)
                bad[field] = value
                self.assert_schema_invalid(bad)

    def test_packet_schema_rejects_cross_role_authority(self):
        packets = self.generated_role_packets()
        for packet in packets.values():
            with self.subTest(role=packet["role"], legitimate=True):
                self.assert_schema_valid(packet)

        self.assert_role_fields_forbidden(
            packets["worker"],
            {
                "completion_sha256": C_HASH,
                "decision_sha256": F_HASH,
                "finish_plan_sha256": D_HASH,
                "knowledge_proposal": {"summary": "not worker authority"},
                "knowledge_targets": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None}],
                "archive_targets": [{"path": ".dev-docs/archive/change.json", "before_sha256": A_HASH}],
                "archive_intent": "not worker authority",
            },
        )
        self.assert_role_fields_forbidden(
            packets["reviewer"],
            {
                "task_heads": {"T1": "1111111", "T2": "2222222"},
                "implementation_range": {"base": "abcdef1", "head": "abcdef9"},
                "acceptance_index_sha256": A_HASH,
                "task_evidence": {"T1": A_HASH, "T2": B_HASH},
                "task_evidence_sha256": B_HASH,
                "completion_sha256": C_HASH,
                "decision_sha256": F_HASH,
                "finish_plan_sha256": D_HASH,
                "knowledge_proposal": {"summary": "not reviewer authority"},
                "knowledge_targets": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None}],
                "archive_targets": [{"path": ".dev-docs/archive/change.json", "before_sha256": A_HASH}],
                "archive_intent": "not reviewer authority",
            },
        )
        self.assert_role_fields_forbidden(
            packets["completion"],
            {
                "completion_sha256": C_HASH,
                "decision_sha256": F_HASH,
                "finish_plan_sha256": D_HASH,
                "knowledge_proposal": {"summary": "not completion authority"},
                "knowledge_targets": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None}],
                "archive_targets": [{"path": ".dev-docs/archive/change.json", "before_sha256": A_HASH}],
                "archive_intent": "not completion authority",
            },
        )
        self.assert_role_fields_forbidden(
            packets["finish"],
            {
                "task_id": "T1",
                "ownership": [{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "modify"}],
                "checks": {"focused": [], "full": []},
                "handoffs": ["artifact-a"],
                "review_targets": ["plugins/nuclio-plugin/scripts/a.py"],
                "task_heads": {"T1": "1111111", "T2": "2222222"},
                "implementation_range": {"base": "abcdef1", "head": "abcdef9"},
                "acceptance_index_sha256": A_HASH,
                "task_evidence": {"T1": A_HASH, "T2": B_HASH},
                "task_evidence_sha256": B_HASH,
                "mutation_map_sha256": E_HASH,
            },
        )

    def test_all_four_generated_packet_roles_conform_to_authoritative_schema(self):
        packets = [
            self.helper.worker_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef1", [{"path": "handoff.json", "state": "absent"}], 7),
            self.helper.reviewer_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef2", mutation_map(), {"evidence_paths": ["evidence/t1.json"]}, [{"path": "iface.py", "state": "present", "sha256": A_HASH}], 7),
            self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), completed_tasks(), acceptance_index(), {"evidence_paths": ["validation.json"]}, ["risk-1"], 7),
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), finish_plan(), [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7),
        ]
        for packet in packets:
            with self.subTest(role=packet["role"]):
                self.assert_schema_valid(packet)
                self.assertEqual(packet["output_language"], "en")

    def test_output_language_propagates_to_all_roles_and_binds_packet_id(self):
        zh_contract = contract("zh-CN")
        zh_plan = finish_plan(new_language="zh-CN", existing_language="zh-CN", existing_source="user_confirmed")
        packets = [
            self.helper.worker_packet(self.repo, zh_contract, context(), state(), "T1", "abcdef1", "abcdef1", [{"path": "handoff.json", "state": "absent"}], 7),
            self.helper.reviewer_packet(self.repo, zh_contract, context(), state(), "T1", "abcdef1", "abcdef2", mutation_map(), {"evidence_paths": ["evidence/t1.json"]}, [{"path": "iface.py", "state": "present", "sha256": A_HASH}], 7),
            self.helper.completion_packet(self.repo, zh_contract, context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), completed_tasks(), acceptance_index(), {"evidence_paths": ["validation.json"]}, ["risk-1"], 7),
            self.helper.finish_packet(self.repo, zh_contract, context(), finish_state(zh_plan), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), zh_plan, [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7),
        ]
        for packet in packets:
            with self.subTest(role=packet["role"]):
                self.assertEqual(packet["output_language"], "zh-CN")
                self.assert_schema_valid(packet)
        en_packet = self.helper.worker_packet(self.repo, contract("en"), context(), state(), "T1", "abcdef1", "abcdef1", [{"path": "handoff.json", "state": "absent"}], 7)
        self.assertNotEqual(packets[0]["packet_id"], en_packet["packet_id"])

    def test_packet_schema_requires_language_and_rejects_invalid_language_tag(self):
        packet = self.helper.worker_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef1", [{"path": "handoff.json", "state": "absent"}], 7)
        missing = dict(packet)
        missing.pop("output_language")
        self.assert_schema_invalid(missing)
        invalid = dict(packet)
        invalid["output_language"] = "中文"
        self.assert_schema_invalid(invalid)

    def test_finish_targets_enforce_language_source_rules(self):
        zh_contract = contract("zh-CN")
        user_confirmed = finish_plan(new_language="zh-CN", existing_language="fr", existing_source="user_confirmed")
        packet = self.helper.finish_packet(self.repo, zh_contract, context(), finish_state(user_confirmed), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), user_confirmed, [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7)
        self.assertEqual(packet["knowledge_targets"][0]["target_language"], "zh-CN")
        self.assertEqual(packet["knowledge_targets"][0]["language_source"], "contract_output_language")
        self.assertEqual(packet["archive_targets"][0]["target_language"], "fr")
        self.assertEqual(packet["archive_targets"][0]["language_source"], "user_confirmed")

        wrong_new = finish_plan(new_language="en")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, zh_contract, context(), finish_state(wrong_new), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), wrong_new, [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7)
        self.assertEqual(ctx.exception.code, "INVALID_TARGET_LANGUAGE")

        wrong_existing = finish_plan(new_language="zh-CN", existing_language="zh-CN", existing_source="contract_output_language")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, zh_contract, context(), finish_state(wrong_existing), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), wrong_existing, [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7)
        self.assertEqual(ctx.exception.code, "INVALID_TARGET_LANGUAGE")

    def test_finish_packet_fails_closed_for_missing_or_unknown_existing_target_language(self):
        missing_language = finish_plan(new_language="en")
        missing_language["archive_targets"][0].pop("target_language")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(missing_language), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), missing_language, [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7)
        self.assertEqual(ctx.exception.code, "UNKNOWN_TARGET_LANGUAGE")
        unknown_source = finish_plan(new_language="en", existing_language="en", existing_source="unknown")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(unknown_source), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), unknown_source, [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7)
        self.assertEqual(ctx.exception.code, "UNKNOWN_TARGET_LANGUAGE")

    def test_worker_packet_is_minimal_and_binds_current_task_only(self):
        packet = self.helper.worker_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef1", [{"path": "handoff.json", "state": "absent"}], 7)
        self.assert_schema_valid(packet)
        self.assertEqual(packet["role"], "worker")
        self.assertEqual(packet["contract_sha256"], A_HASH)
        self.assertEqual(packet["context_fingerprint"], B_HASH)
        self.assertEqual(packet["state_version"], 7)
        self.assertEqual(packet["ownership"], [{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "create"}])
        self.assertIn("worker-ref", packet["handoffs"])
        self.assertNotIn("review-ref", packet["handoffs"])
        self.assertNotIn("tasks", packet)
        self.assertNotIn("source", packet)
        self.assertRegex(packet["packet_id"], r"^[0-9a-f]{64}$")

    def test_reviewer_packet_is_read_only_and_has_no_fix_or_gate_authority(self):
        packet = self.helper.reviewer_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef2", mutation_map(), {"evidence_paths": ["evidence/t1.json"]}, [{"path": "iface.py", "state": "present", "sha256": A_HASH}], 7)
        self.assert_schema_valid(packet)
        self.assertEqual(packet["role"], "reviewer")
        self.assertEqual(packet["ownership"], [{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "read"}])
        self.assertIn("review-ref", packet["review_targets"])
        self.assertEqual(packet["mutation_map_sha256"], E_HASH)
        self.assertNotIn("fixer_authorization", packet)
        self.assertNotIn("gate_approval", packet)
        self.assertNotIn("approval", json.dumps(packet))

    def test_completion_packet_requires_full_range_all_tasks_and_acceptance(self):
        packet = self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), completed_tasks(), acceptance_index(), {"evidence_paths": ["validation.json"]}, ["risk-1"], 7)
        self.assert_schema_valid(packet)
        self.assertEqual(packet["role"], "completion")
        self.assertEqual(packet["range"], {"base_head": "abcdef1", "expected_dirty_state": "clean", "new_head": "abcdef9"})
        self.assertEqual(packet["task_heads"], {"T1": "1111111", "T2": "2222222"})
        self.assertEqual(packet["implementation_range"], {"base": "abcdef1", "head": "abcdef9"})
        self.assertRegex(packet["acceptance_index_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(packet["task_evidence"], {"T1": A_HASH, "T2": B_HASH})
        self.assertEqual(packet["mutation_map_sha256"], E_HASH)
        self.assertIn("change_wide", packet["checks"])
        self.assertIn("task:T1@1111111", packet["handoffs"])
        self.assertIn("task:T2@2222222", packet["handoffs"])
        self.assertNotIn("raw_transcript", packet)
        bad_acceptance = acceptance_index()
        bad_acceptance[1]["accepted"] = False
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), completed_tasks(), bad_acceptance, {}, [], 7)
        self.assertEqual(ctx.exception.code, "INCOMPLETE_ACCEPTANCE")
        for label, bad in {
            "missing": acceptance_index()[:2],
            "duplicate": acceptance_index() + [acceptance_index()[0]],
            "extra": acceptance_index() + [{"id": "AX", "accepted": True}],
        }.items():
            with self.subTest(label=label), self.assertRaises(self.helper.ProtocolError) as ctx:
                self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), completed_tasks(), bad, {}, [], 7)
            self.assertEqual(ctx.exception.code, "INCOMPLETE_ACCEPTANCE")
        missing_evidence = completed_tasks()
        missing_evidence[1].pop("evidence_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), missing_evidence, acceptance_index(), {}, [], 7)
        self.assertIn(ctx.exception.code, {"TASKS_INCOMPLETE", "INVALID_IDENTITY"})
        stale_tasks = completed_tasks(); stale_tasks[1]["head"] = "3333333"
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), stale_tasks, acceptance_index(), {}, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_HEAD")
        drift_state = state(all_completed=True); drift_state["history"][0]["reason"] = json.dumps({"heads": {"T1": "1111111", "T2": "3333333"}})
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.completion_packet(self.repo, contract(), context(), drift_state, "abcdef1", "abcdef9", mutation_map(), completed_tasks(), acceptance_index(), {}, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_HEAD")

    def test_real_worker_packet_binds_state_and_records_matching_implementation(self):
        state_helper = load_state_helper()
        contract_helper = load_contract_helper()
        normalized = contract_helper.validate_contract(normalized_contract_for_state())
        identity = contract_helper.build_identity(normalized)
        contract_id = {"path": ".dev-docs/changes/change-alpha/contract.yaml", "sha256": identity["sha256"], "version": identity["contract_version"], "change_id": identity["change_id"], "output_language": identity["output_language"]}
        context_id = {"path": ".dev-docs/changes/change-alpha/context.jsonl", "fingerprint": B_HASH, "entries": ["all-context"]}
        state_path = self.repo / "real-state.json"
        initialized = state_helper.init_state(state_path, contract_id, context_id, contract_helper.build_task_graph(normalized))
        self.assertNotIn("packet_sha256", initialized["tasks"][0])
        approved = state_helper.approve_contract(state_path, 1, contract_id, context_id, {"approval_id": "A1", "approved_at": "2026-07-18T00:00:00Z", "token": "approve"})
        packet_contract = {**normalized, "sha256": identity["sha256"]}
        packet = self.helper.worker_packet(self.repo, packet_contract, context_id, approved, "T1", "abcdef1", "abcdef1", [], 2)
        packet_path = self.repo / "worker.json"
        packet_identity = self.helper.write_packet(packet_path, packet)
        written_packet = json.loads(packet_path.read_text(encoding="utf-8"))
        started = state_helper.start_task(state_path, 2, "T1", written_packet)
        self.assertEqual(started["tasks"][0]["status"], "implementing")
        self.assertEqual(started["tasks"][0]["packet_sha256"], packet_identity["packet_sha256"])
        evidence = {"task_id": "T1", "packet_sha256": packet_identity["packet_sha256"], "base_head": "abcdef1", "new_head": "head-1", "implementation_sha256": C_HASH, "changed_paths": ["plugins/nuclio-plugin/scripts/a.py"]}
        recorded = state_helper.record_implementation(state_path, 3, evidence)
        self.assertEqual(recorded["tasks"][0]["status"], "reviewing")

    def test_worker_packet_schema_differential_matrix_matches_start_task_acceptance(self):
        state_helper = load_state_helper()
        contract_helper = load_contract_helper()
        normalized = contract_helper.validate_contract(normalized_contract_for_state())
        identity = contract_helper.build_identity(normalized)
        contract_id = {"path": ".dev-docs/changes/change-alpha/contract.yaml", "sha256": identity["sha256"], "version": identity["contract_version"], "change_id": identity["change_id"], "output_language": identity["output_language"]}
        context_id = {"path": ".dev-docs/changes/change-alpha/context.jsonl", "fingerprint": B_HASH, "entries": ["all-context"]}
        packet_contract = {**normalized, "sha256": identity["sha256"]}

        def fresh_state_and_packet():
            state_path = self.repo / f"state-{len(list(self.repo.glob('state-*.json')))}.json"
            initialized = state_helper.init_state(state_path, contract_id, context_id, contract_helper.build_task_graph(normalized))
            approved = state_helper.approve_contract(state_path, 1, contract_id, context_id, {"approval_id": "A1", "approved_at": "2026-07-18T00:00:00Z", "token": "approve"})
            packet = self.helper.worker_packet(self.repo, packet_contract, context_id, approved, "T1", "abcdef1", "abcdef1", [], 2)
            return state_path, packet

        def recompute(packet):
            packet["packet_id"] = self.helper._packet_id(packet)
            return packet

        matrix = [
            ("valid", lambda p: p, True),
            ("boolean schema_version", lambda p: recompute({**p, "schema_version": True}), False),
            ("boolean state_version", lambda p: recompute({**p, "state_version": True}), False),
            ("missing checks", lambda p: (p.pop("checks"), recompute(p))[1], False),
            ("extra field", lambda p: recompute({**p, "unexpected": "extra"}), False),
            ("wrong role", lambda p: recompute({**p, "role": "reviewer"}), False),
            ("cross-role field", lambda p: recompute({**p, "completion_sha256": C_HASH}), False),
            ("invalid ownership entry", lambda p: recompute({**p, "ownership": [{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "invalid"}]}), False),
            ("invalid range", lambda p: recompute({**p, "range": {"base_head": "bad-ref", "expected_dirty_state": "clean"}}), False),
            ("invalid snapshot", lambda p: recompute({**p, "snapshots": [{"path": "../escape", "state": "present"}]}), False),
            ("invalid checks", lambda p: recompute({**p, "checks": {"focused": [{"name": "unit", "command": []}], "full": []}}), False),
            ("invalid handoffs", lambda p: recompute({**p, "handoffs": [""]}), False),
        ]
        for label, mutate, expected_valid in matrix:
            with self.subTest(label=label):
                state_path, base_packet = fresh_state_and_packet()
                packet = mutate(json.loads(json.dumps(base_packet)))
                schema_valid = not self.schema_errors(packet)
                self.assertEqual(schema_valid, expected_valid)
                before = state_path.read_bytes()
                if expected_valid:
                    started = state_helper.start_task(state_path, 2, "T1", packet)
                    self.assertEqual(started["tasks"][0]["status"], "implementing")
                else:
                    with self.assertRaises(state_helper.ProtocolError) as ctx:
                        state_helper.start_task(state_path, 2, "T1", packet)
                    self.assertEqual(ctx.exception.code, "INVALID_PACKET_SCHEMA")
                    self.assertEqual(before, state_path.read_bytes())

    def test_generated_completion_packet_starts_state_helper_completion(self):
        state_helper = load_state_helper()
        packet = self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), completed_tasks(), acceptance_index(), {"evidence_paths": ["validation.json"]}, [], 7)
        state_doc = {
            "schema_version": 1,
            "state_version": 7,
            "change_id": "change-alpha",
            "status": "executing",
            "contract": {"path": ".dev-docs/changes/change-alpha/contract.yaml", "sha256": A_HASH, "version": "v1", "output_language": "en"},
            "context": {"path": ".dev-docs/changes/change-alpha/context.jsonl", "fingerprint": B_HASH, "entries": ["all-context"]},
            "gates": {"contract": {"status": "approved", "artifact_sha256": A_HASH, "context_fingerprint": B_HASH, "state_version": 1}, "finish": {"status": "none"}},
            "tasks": [{"id": "T1", "status": "completed", "ownership": ["plugins/nuclio-plugin/scripts/a.py"], "packet_sha256": C_HASH}, {"id": "T2", "status": "completed", "ownership": ["plugins/nuclio-plugin/scripts/b.py"], "packet_sha256": D_HASH}],
            "blockers": [],
            "fix_budgets": {},
            "history": [{"event": "INITIALIZED", "from": None, "to": "contract_pending", "state_version": 1, "artifact_sha256": A_HASH, "reason": json.dumps({"heads": {"T1": "1111111", "T2": "2222222"}})}],
        }
        state_path = self.repo / "state.json"
        state_path.write_text(json.dumps(state_doc), encoding="utf-8")
        after = state_helper.start_completion(state_path, 7, packet)
        self.assertEqual(after["status"], "completing")
        metadata = json.loads(after["history"][0]["reason"])
        self.assertEqual(metadata["completion_identity"]["task_heads"], {"T1": "1111111", "T2": "2222222"})

    def test_finish_packet_binds_decision_plan_and_has_no_product_fix_authority(self):
        plan = finish_plan()
        packet = self.helper.finish_packet(self.repo, contract(), context(), finish_state(plan), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), plan, [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7)
        self.assert_schema_valid(packet)
        self.assertEqual(packet["role"], "finish")
        self.assertEqual(packet["completion_sha256"], C_HASH)
        self.assertEqual(packet["decision_sha256"], F_HASH)
        self.assertEqual(packet["finish_plan_sha256"], plan["finish_plan_sha256"])
        self.assertEqual(packet["knowledge_proposal"], {"summary": "retain validated decisions"})
        self.assertEqual(packet["knowledge_targets"], plan["knowledge_targets"])
        self.assertEqual(packet["archive_targets"], plan["archive_targets"])
        self.assertEqual(packet["index_targets"], plan["index_targets"])
        self.assertEqual(packet["archive_intent"], "archive change-local evidence after finish approval")
        self.assertNotIn("ownership", packet)
        self.assertNotIn("checks", packet)
        self.assertNotIn("fix", json.dumps(packet))
        gate_notes = json.loads(finish_state(plan)["gates"]["finish"]["notes"])
        self.assertEqual(gate_notes["finish_plan_sha256"], packet["finish_plan_sha256"])
        self.assertEqual(gate_notes["readiness"]["finish_plan_sha256"], packet["finish_plan_sha256"])
        overreach = finish_plan(); overreach["knowledge_targets"] = [finish_target("plugins/nuclio-plugin/scripts/a.py", None, "bad", "bad", F_HASH, "en", "contract_output_language")]; overreach["finish_plan_sha256"] = self_hash(overreach, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(overreach), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), overreach, [], 7)
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")
        missing = finish_plan(); missing.pop("archive_intent"); missing["finish_plan_sha256"] = self_hash(missing, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(plan), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), missing, [], 7)
        self.assertEqual(ctx.exception.code, "INVALID_INPUT")

    def test_finish_targets_are_exact_groups_and_fail_closed_for_overlap(self):
        plan = finish_plan()
        packet = self.helper.finish_packet(self.repo, contract(), context(), finish_state(plan), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), plan, [], 7)
        self.assertEqual([target["path"] for target in packet["knowledge_targets"]], [".dev-docs/knowledge/notes.md"])
        self.assertEqual([target["path"] for target in packet["archive_targets"]], [".dev-docs/archive/change.json"])
        self.assertEqual([target["path"] for target in packet["index_targets"]], [".dev-docs/changes/index.md"])
        self.assert_schema_valid(packet)

        no_index = finish_plan(include_index=False)
        no_index["knowledge_targets"].append(finish_target(".dev-docs/changes/index.md", None, "wrong", "wrong", F_HASH, "en", "contract_output_language"))
        no_index["finish_plan_sha256"] = self_hash(no_index, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(no_index), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), no_index, [], 7)
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")

        duplicate = finish_plan()
        duplicate["knowledge_targets"].append({**duplicate["knowledge_targets"][0], "reason": "duplicate same group"})
        duplicate["finish_plan_sha256"] = self_hash(duplicate, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(duplicate), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), duplicate, [], 7)
        self.assertEqual(ctx.exception.code, "INVALID_FINISH_PLAN")

        cross_group = finish_plan()
        cross_group["index_targets"][0] = {**cross_group["index_targets"][0], "path": ".dev-docs/knowledge/notes.md"}
        cross_group["finish_plan_sha256"] = self_hash(cross_group, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(cross_group), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), cross_group, [], 7)
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")

    def test_finish_packet_rejects_stale_approved_gate_plan_identity(self):
        plan = finish_plan()
        stale_gate = finish_state(plan)
        notes = json.loads(stale_gate["gates"]["finish"]["notes"])
        notes["finish_plan_sha256"] = D_HASH
        stale_gate["gates"]["finish"]["notes"] = json.dumps(notes)
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), stale_gate, "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), plan, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_FINISH_PLAN")

        stale_readiness = finish_state(plan)
        notes = json.loads(stale_readiness["gates"]["finish"]["notes"])
        notes["readiness"]["finish_plan_sha256"] = D_HASH
        stale_readiness["gates"]["finish"]["notes"] = json.dumps(notes)
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), stale_readiness, "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), plan, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_FINISH_PLAN")

        stale_version = finish_state(plan)
        notes = json.loads(stale_version["gates"]["finish"]["notes"])
        notes["readiness"]["decision_state_version"] = 9
        stale_version["gates"]["finish"]["notes"] = json.dumps(notes)
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), stale_version, "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), plan, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_DECISION")

        missing_notes = finish_state(plan)
        missing_notes["gates"]["finish"].pop("notes")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), missing_notes, "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), plan, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_DECISION")

        invalid_notes = finish_state(plan)
        invalid_notes["gates"]["finish"]["notes"] = "not json"
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), invalid_notes, "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), plan, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_DECISION")

    def test_finish_packet_rejects_stale_plan_decision_completion_and_identity(self):
        plan = finish_plan()
        stale_plan = dict(plan); stale_plan["knowledge_proposal"] = {"summary": "changed after hash"}
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(plan), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), stale_plan, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_FINISH_PLAN")

        stale_decision = decision_doc(); stale_decision["decision"]["decision_sha256"] = E_HASH
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(plan), "abcdef1", "abcdef9", stale_decision, completion_identity_doc(), plan, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_DECISION")

        stale_completion = completion_identity_doc(); stale_completion["completion_identity"]["completion_sha256"] = D_HASH
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(plan), "abcdef1", "abcdef9", decision_doc(), stale_completion, plan, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_COMPLETION")

        stale_contract_plan = finish_plan(); stale_contract_plan["contract_sha256"] = C_HASH; stale_contract_plan["finish_plan_sha256"] = self_hash(stale_contract_plan, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), finish_state(stale_contract_plan), "abcdef1", "abcdef9", decision_doc(), completion_identity_doc(), stale_contract_plan, [], 7)
        self.assertEqual(ctx.exception.code, "STALE_FINISH_PLAN")

    def test_finish_cli_rejects_markdown_json_inputs(self):
        plan = finish_plan()
        contract_path = self.repo / "contract.json"
        context_path = self.repo / "context.json"
        state_path = self.repo / "state.json"
        decision_path = self.repo / "decision.md"
        completion_path = self.repo / "completion.md"
        plan_path = self.repo / "finish-plan.md"
        out = self.repo / "finish-packet.json"
        contract_path.write_text(json.dumps(contract()), encoding="utf-8")
        context_path.write_text(json.dumps(context()), encoding="utf-8")
        state_path.write_text(json.dumps(finish_state(plan)), encoding="utf-8")
        decision_path.write_text(json.dumps(decision_doc()), encoding="utf-8")
        completion_path.write_text(json.dumps(completion_identity_doc()), encoding="utf-8")
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable, str(HELPER), "finish", "--repo", str(self.repo), "--contract-json", str(contract_path), "--context-json", str(context_path), "--state-json", str(state_path), "--base", "abcdef1", "--head", "abcdef9", "--decision-json", str(decision_path), "--completion-identity-json", str(completion_path), "--finish-plan-json", str(plan_path), "--output", str(out), "--expected-state-version", "7",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stderr)["code"], "INVALID_JSON_ARGUMENT")
        self.assertFalse(out.exists())

    def test_stale_contract_context_state_and_head_fail_closed(self):
        stale_contract = contract(); stale_contract["sha256"] = C_HASH
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.worker_packet(self.repo, stale_contract, context(), state(), "T1", "abcdef1", "abcdef1", [], 7)
        self.assertEqual(ctx.exception.code, "STALE_CONTRACT")
        stale_context = context(); stale_context["fingerprint"] = C_HASH
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.worker_packet(self.repo, contract(), stale_context, state(), "T1", "abcdef1", "abcdef1", [], 7)
        self.assertEqual(ctx.exception.code, "STALE_CONTEXT")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.worker_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef1", [], 6)
        self.assertEqual(ctx.exception.code, "STALE_STATE")

    def test_cli_writes_packet_once_and_refuses_overwrite(self):
        out = self.repo / "packet.json"
        proc = subprocess.run(
            [
                sys.executable, str(HELPER), "worker", "--repo", str(self.repo), "--contract-json", json.dumps(contract()), "--context-json", json.dumps(context()), "--state-json", json.dumps(state()), "--base", "abcdef1", "--head", "abcdef1", "--task-id", "T1", "--output", str(out), "--expected-state-version", "7",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(out.exists())
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["role"], "worker")
        envelope = json.loads(proc.stdout)
        self.assertEqual(envelope["identity"]["packet_id"], payload["packet_id"])
        proc2 = subprocess.run(
            [
                sys.executable, str(HELPER), "worker", "--repo", str(self.repo), "--contract-json", json.dumps(contract()), "--context-json", json.dumps(context()), "--state-json", json.dumps(state()), "--base", "abcdef1", "--head", "abcdef1", "--task-id", "T1", "--output", str(out), "--expected-state-version", "7",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc2.returncode, 2)
        self.assertEqual(json.loads(proc2.stderr)["code"], "OUTPUT_EXISTS")

    def test_cli_does_not_allow_dispatch_language_override(self):
        out = self.repo / "packet.json"
        proc = subprocess.run(
            [
                sys.executable, str(HELPER), "worker", "--repo", str(self.repo), "--contract-json", json.dumps(contract("zh-CN")), "--context-json", json.dumps(context()), "--state-json", json.dumps(state()), "--base", "abcdef1", "--head", "abcdef1", "--task-id", "T1", "--output", str(out), "--expected-state-version", "7", "--output-language", "en",
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unrecognized arguments: --output-language", proc.stderr)


if __name__ == "__main__":
    unittest.main()
