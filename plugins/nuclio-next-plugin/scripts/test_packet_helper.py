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

import jsonschema

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "plugins" / "nuclio-next-plugin" / "scripts" / "packet-helper.py"
STATE_HELPER = ROOT / "plugins" / "nuclio-next-plugin" / "scripts" / "state-helper.py"
SCHEMA = ROOT / "plugins" / "nuclio-next-plugin" / "schemas" / "packet.schema.json"
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


def contract():
    return {
        "schema_version": 1,
        "change_id": "change-alpha",
        "contract_version": "v1",
        "sha256": A_HASH,
        "acceptance": [{"id": "AC-object", "text": "object id acceptance"}, "string acceptance", {"text": "object without id"}],
        "tasks": [
            {
                "id": "T1",
                "name": "Task one",
                "owner": "owner-a",
                "dependencies": [],
                "mutation_targets": [{"path": "plugins/nuclio-next-plugin/scripts/a.py", "mode": "create"}],
                "handoffs": {"inputs": [], "outputs": ["artifact-a"]},
                "checks": {"focused": [{"name": "focused", "command": ["python3", "test.py"]}], "full": [{"name": "full", "command": ["python3", "all.py"]}]},
                "rollback": "delete a.py",
            },
            {
                "id": "T2",
                "name": "Task two",
                "owner": "owner-a",
                "dependencies": ["T1"],
                "mutation_targets": [{"path": "plugins/nuclio-next-plugin/scripts/b.py", "mode": "modify"}],
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
            "worker": [{"id": "worker-ref", "path": "plugins/nuclio-next-plugin/references/execution.md"}],
            "reviewer": [{"id": "review-ref", "path": "plugins/nuclio-next-plugin/references/authority.md"}],
            "completion": [{"id": "completion-ref", "path": "plugins/nuclio-next-plugin/references/execution.md"}],
            "finish": [{"id": "plugins/nuclio-next-plugin/references/finish.md", "path": "plugins/nuclio-next-plugin/references/finish.md"}],
        },
    }


def state(all_completed=False):
    tasks = [
        {"id": "T1", "status": "completed" if all_completed else "ready", "ownership": ["plugins/nuclio-next-plugin/scripts/a.py"], "packet_sha256": C_HASH},
        {"id": "T2", "status": "completed" if all_completed else "pending", "ownership": ["plugins/nuclio-next-plugin/scripts/b.py"], "packet_sha256": D_HASH},
    ]
    return {
        "schema_version": 1,
        "state_version": 7,
        "change_id": "change-alpha",
        "status": "executing",
        "contract": {"path": ".dev-docs/contract.yaml", "sha256": A_HASH, "version": "v1"},
        "context": {"path": ".dev-docs/context.jsonl", "fingerprint": B_HASH, "entries": ["all-context"]},
        "tasks": tasks,
        "gates": {"contract": {"status": "approved"}, "finish": {"status": "none"}},
        "history": [{"event": "INITIALIZED", "reason": json.dumps({"heads": {"T1": "1111111", "T2": "2222222"}})}],
    }


def mutation_map():
    return {"mutation_map": {"sha256": E_HASH, "changed_paths": ["plugins/nuclio-next-plugin/scripts/a.py"], "blockers": []}}


def completed_tasks():
    return [{"task_id": "T1", "head": "1111111", "evidence_sha256": A_HASH}, {"task_id": "T2", "head": "2222222", "evidence_sha256": B_HASH}]


def acceptance_index():
    return [{"id": "AC-object", "accepted": True, "evidence": "tests"}, {"id": "A2", "accepted": True, "evidence": "review"}, {"id": "A3", "accepted": True, "evidence": "contract"}]


def finish_plan():
    return {
        "decision_sha256": F_HASH,
        "finish_plan_sha256": D_HASH,
        "knowledge_proposal": {"summary": "retain validated decisions"},
        "knowledge_targets": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None}],
        "archive_targets": [{"path": ".dev-docs/archive/change.json", "before_sha256": A_HASH}],
        "archive_intent": "archive change-local evidence after finish approval",
    }


class PacketHelperTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.validator = jsonschema.Draft202012Validator(self.schema)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)

    def assert_schema_valid(self, packet):
        errors = sorted(self.validator.iter_errors(packet), key=lambda error: list(error.absolute_path))
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_all_four_generated_packet_roles_conform_to_authoritative_schema(self):
        packets = [
            self.helper.worker_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef1", [{"path": "handoff.json", "state": "absent"}], 7),
            self.helper.reviewer_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef2", mutation_map(), {"evidence_paths": ["evidence/t1.json"]}, [{"path": "iface.py", "state": "present", "sha256": A_HASH}], 7),
            self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), completed_tasks(), acceptance_index(), {"evidence_paths": ["validation.json"]}, ["risk-1"], 7),
            self.helper.finish_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", {"decision_sha256": F_HASH}, {"completion_identity": {"completion_sha256": C_HASH}}, finish_plan(), [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7),
        ]
        for packet in packets:
            with self.subTest(role=packet["role"]):
                self.assert_schema_valid(packet)

    def test_worker_packet_is_minimal_and_binds_current_task_only(self):
        packet = self.helper.worker_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef1", [{"path": "handoff.json", "state": "absent"}], 7)
        self.assert_schema_valid(packet)
        self.assertEqual(packet["role"], "worker")
        self.assertEqual(packet["contract_sha256"], A_HASH)
        self.assertEqual(packet["context_fingerprint"], B_HASH)
        self.assertEqual(packet["state_version"], 7)
        self.assertEqual(packet["ownership"], [{"path": "plugins/nuclio-next-plugin/scripts/a.py", "mode": "create"}])
        self.assertIn("worker-ref", packet["handoffs"])
        self.assertNotIn("review-ref", packet["handoffs"])
        self.assertNotIn("tasks", packet)
        self.assertNotIn("source", packet)
        self.assertRegex(packet["packet_id"], r"^[0-9a-f]{64}$")

    def test_reviewer_packet_is_read_only_and_has_no_fix_or_gate_authority(self):
        packet = self.helper.reviewer_packet(self.repo, contract(), context(), state(), "T1", "abcdef1", "abcdef2", mutation_map(), {"evidence_paths": ["evidence/t1.json"]}, [{"path": "iface.py", "state": "present", "sha256": A_HASH}], 7)
        self.assert_schema_valid(packet)
        self.assertEqual(packet["role"], "reviewer")
        self.assertEqual(packet["ownership"], [{"path": "plugins/nuclio-next-plugin/scripts/a.py", "mode": "read"}])
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

    def test_generated_completion_packet_starts_state_helper_completion(self):
        state_helper = load_state_helper()
        packet = self.helper.completion_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", mutation_map(), completed_tasks(), acceptance_index(), {"evidence_paths": ["validation.json"]}, [], 7)
        state_doc = {
            "schema_version": 1,
            "state_version": 7,
            "change_id": "change-alpha",
            "status": "executing",
            "contract": {"path": ".dev-docs/contract.yaml", "sha256": A_HASH, "version": "v1", "acceptance": contract()["acceptance"]},
            "context": {"path": ".dev-docs/context.jsonl", "fingerprint": B_HASH, "entries": ["all-context"]},
            "gates": {"contract": {"status": "approved", "artifact_sha256": A_HASH, "context_fingerprint": B_HASH, "state_version": 1}, "finish": {"status": "none"}},
            "tasks": [{"id": "T1", "status": "completed", "ownership": ["plugins/nuclio-next-plugin/scripts/a.py"], "packet_sha256": C_HASH}, {"id": "T2", "status": "completed", "ownership": ["plugins/nuclio-next-plugin/scripts/b.py"], "packet_sha256": D_HASH}],
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
        completion = {"completion_identity": {"completion_sha256": C_HASH}}
        packet = self.helper.finish_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", {"decision_sha256": F_HASH}, completion, plan, [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}], 7)
        self.assert_schema_valid(packet)
        self.assertEqual(packet["role"], "finish")
        self.assertEqual(packet["completion_sha256"], C_HASH)
        self.assertEqual(packet["decision_sha256"], F_HASH)
        self.assertEqual(packet["finish_plan_sha256"], D_HASH)
        self.assertEqual(packet["knowledge_proposal"], {"summary": "retain validated decisions"})
        self.assertEqual(packet["knowledge_targets"], [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None}])
        self.assertEqual(packet["archive_targets"], [{"path": ".dev-docs/archive/change.json", "before_sha256": A_HASH}])
        self.assertEqual(packet["archive_intent"], "archive change-local evidence after finish approval")
        self.assertNotIn("ownership", packet)
        self.assertNotIn("checks", packet)
        self.assertNotIn("fix", json.dumps(packet))
        overreach = finish_plan(); overreach["knowledge_targets"] = [{"path": "plugins/nuclio-next-plugin/scripts/a.py", "before_sha256": None}]
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", {"decision_sha256": F_HASH}, completion, overreach, [], 7)
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")
        missing = finish_plan(); missing.pop("archive_intent")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.finish_packet(self.repo, contract(), context(), state(all_completed=True), "abcdef1", "abcdef9", {"decision_sha256": F_HASH}, completion, missing, [], 7)
        self.assertEqual(ctx.exception.code, "INVALID_INPUT")

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


if __name__ == "__main__":
    unittest.main()
