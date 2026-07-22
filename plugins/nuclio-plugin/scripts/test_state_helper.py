"""
State helper tests.

## Contents

- [Fixture builders](#fixture-builders)
- [Initialization and freshness tests](#initialization-and-freshness-tests)
- [Task execution and fix budget tests](#task-execution-and-fix-budget-tests)
- [Completion and finish tests](#completion-and-finish-tests)
- [CLI and atomicity tests](#cli-and-atomicity-tests)
"""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "state-helper.py"
EVIDENCE_HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "evidence-helper.py"
STATE_SCHEMA = ROOT / "plugins" / "nuclio-plugin" / "schemas" / "state.schema.json"
A_HASH = "a" * 64
B_HASH = "b" * 64
C_HASH = "c" * 64
D_HASH = "d" * 64
E_HASH = "e" * 64
F_HASH = "f" * 64


def load_helper():
    spec = importlib.util.spec_from_file_location("state_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_evidence_helper():
    spec = importlib.util.spec_from_file_location("evidence_helper_for_state_tests", EVIDENCE_HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract_identity(**overrides):
    identity = {"path": ".dev-docs/changes/change-alpha/contract.yaml", "sha256": A_HASH, "version": "v1", "change_id": "change-alpha", "output_language": "zh-CN"}
    identity.update(overrides)
    return identity


def context_identity(**overrides):
    identity = {"path": ".dev-docs/changes/change-alpha/context.jsonl", "fingerprint": B_HASH, "entries": ["contract-ref", "worker-ref"]}
    identity.update(overrides)
    return identity


def task_graph():
    return [
        {"id": "T1", "owner": "owner-a", "dependencies": [], "ownership": [{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "create"}]},
        {"id": "T2", "owner": "owner-a", "dependencies": ["T1"], "ownership": [{"path": "plugins/nuclio-plugin/scripts/b.py", "mode": "modify"}]},
    ]


def approval(token="approve", **overrides):
    payload = {"approval_id": "approval-1", "approved_at": "2026-07-18T00:00:00Z", "approved_by": "user", "token": token}
    payload.update(overrides)
    return payload


def worker_packet(helper, task_id="T1", state_version=2, output_language="zh-CN", ownership=None, role="worker", change_id="change-alpha", contract_sha256=A_HASH, context_fingerprint=B_HASH):
    ownership = ownership or ([{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "create"}] if task_id == "T1" else [{"path": "plugins/nuclio-plugin/scripts/b.py", "mode": "modify"}])
    packet = {
        "schema_version": 1,
        "role": role,
        "change_id": change_id,
        "contract_sha256": contract_sha256,
        "context_fingerprint": context_fingerprint,
        "state_version": state_version,
        "output_language": output_language,
        "task_id": task_id,
        "ownership": ownership,
        "range": {"base_head": "abc1234", "expected_dirty_state": "clean"},
        "snapshots": [],
        "checks": {"focused": [], "full": []},
        "handoffs": [],
    }
    packet["packet_id"] = helper.sha256_value(packet)
    return packet


def packet_sha(helper, task_id="T1", state_version=2, **overrides):
    return helper.sha256_value(worker_packet(helper, task_id=task_id, state_version=state_version, **overrides))


def impl(task_id="T1", head="def5678", implementation_sha256=E_HASH, packet_sha256=None, base_head="abc1234"):
    return {
        "task_id": task_id,
        "packet_sha256": packet_sha256 or "",
        "base_head": base_head,
        "new_head": head,
        "implementation_sha256": implementation_sha256,
        "changed_paths": ["plugins/nuclio-plugin/scripts/a.py" if task_id == "T1" else "plugins/nuclio-plugin/scripts/b.py"],
    }


def pass_review(task_id="T1", review_sha256=F_HASH):
    return {"task_id": task_id, "review_sha256": review_sha256, "verdict": "PASS", "findings": []}


def fail_review(task_id="T1", owner="owner-a", finding_id="F1", fingerprint="fp-1", path="plugins/nuclio-plugin/scripts/a.py"):
    return {
        "task_id": task_id,
        "review_sha256": F_HASH,
        "verdict": "FAIL",
        "findings": [{"id": finding_id, "severity": "blocking", "owner": owner, "fingerprint": fingerprint, "path": path, "reason": "blocking issue"}],
    }


class StateHelperTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state_path = Path(self.temp.name) / "state.json"

    def init_state(self):
        return self.helper.init_state(self.state_path, contract_identity(), context_identity(), task_graph())

    def read_state(self):
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def current_packet_sha(self, task_id="T1"):
        for task in self.read_state()["tasks"]:
            if task["id"] == task_id:
                return task["packet_sha256"]
        raise AssertionError(f"unknown task {task_id}")

    def approve_contract(self, expected_version=1, contract=None, context=None, approval_payload=None):
        return self.helper.approve_contract(self.state_path, expected_version, contract or contract_identity(), context or context_identity(), approval_payload or approval())

    def complete_t1(self):
        version = self.read_state()["state_version"]
        packet = worker_packet(self.helper, "T1", version)
        self.helper.start_task(self.state_path, version, "T1", packet)
        self.helper.record_implementation(self.state_path, version + 1, impl(packet_sha256=self.helper.sha256_value(packet)))
        self.helper.import_task_review(self.state_path, version + 2, pass_review())

    def complete_all_tasks(self):
        if self.read_state()["tasks"][0]["status"] != "completed":
            self.complete_t1()
        version = self.read_state()["state_version"]
        packet = worker_packet(self.helper, "T2", version)
        self.helper.start_task(self.state_path, version, "T2", packet)
        self.helper.record_implementation(self.state_path, version + 1, impl("T2", head="fedcba9", packet_sha256=self.helper.sha256_value(packet)))
        self.helper.import_task_review(self.state_path, version + 2, pass_review("T2", review_sha256=A_HASH))

    def completion_identity(self):
        return {
            "contract_sha256": A_HASH,
            "context_fingerprint": B_HASH,
            "task_heads": {"T1": "def5678", "T2": "fedcba9"},
            "implementation_range": {"base": "abc1234", "head": "fedcba9"},
            "acceptance_index_sha256": B_HASH,
        }

    def completion_packet(self, **overrides):
        packet = self.completion_identity()
        packet.update(overrides)
        return packet

    def completion_pass(self, **overrides):
        completion = {"verdict": "PASS", "proposal_sha256": C_HASH, "mutation_map_sha256": D_HASH, **self.completion_identity()}
        completion.update(overrides)
        return completion

    def current_decision_sha(self):
        return self.read_state()["decision"]["decision_sha256"]

    def current_finish_plan_sha(self):
        return self.read_state()["decision"]["finish_plan_sha256"]

    def self_hash(self, payload, field):
        return self.helper.sha256_value({key: payload[key] for key in sorted(payload) if key != field})

    def file_sha(self, path):
        return load_evidence_helper().sha256_bytes(Path(path).read_bytes())

    def ensure_change_root_state_path(self):
        change_root = Path(self.temp.name) / "repo" / ".dev-docs" / "changes" / "change-alpha"
        change_root.mkdir(parents=True, exist_ok=True)
        target_state = change_root / "state.json"
        if self.state_path.exists() and self.state_path != target_state:
            target_state.write_bytes(self.state_path.read_bytes())
        self.state_path = target_state
        return change_root

    def write_finish_handoff(self, change_root=None):
        change_root = change_root or self.ensure_change_root_state_path()
        repo = change_root.parents[2]
        (repo / ".dev-docs" / "knowledge").mkdir(parents=True, exist_ok=True)
        (repo / ".dev-docs" / "archive").mkdir(parents=True, exist_ok=True)
        (repo / ".dev-docs" / "changes").mkdir(parents=True, exist_ok=True)
        completion_md = change_root / "completion.md"
        decision_md = change_root / "decision.md"
        completion_md.write_text("# Completion\nAll tasks done.\n", encoding="utf-8")
        decision_md.write_text("# Decision\nProposal only.\n", encoding="utf-8")
        completion_payload = {
            "proposal_sha256": C_HASH,
            "mutation_map_sha256": D_HASH,
            "check_summary_sha256": E_HASH,
            "task_heads": {"T1": "def5678", "T2": "fedcba9"},
            "task_evidence": {"T1": E_HASH, "T2": A_HASH},
            "task_evidence_sha256": self.helper.sha256_value({"T1": E_HASH, "T2": A_HASH}),
            "implementation_range": {"base": "abc1234", "head": "fedcba9"},
            "acceptance_index_sha256": B_HASH,
            "residual_risks": [],
            "markdown_sha256": self.helper.sha256_value(completion_md.read_bytes().decode("utf-8")),
        }
        completion_payload["markdown_sha256"] = load_evidence_helper().sha256_bytes(completion_md.read_bytes())
        completion_payload["completion_sha256"] = self.self_hash(completion_payload, "completion_sha256")
        decision_payload = {
            "completion_sha256": completion_payload["completion_sha256"],
            "decision_state_version": self.read_state()["state_version"] + 2,
            "markdown_sha256": load_evidence_helper().sha256_bytes(decision_md.read_bytes()),
            "Completion Verdict": {"result": "PASS", "summary": "all tasks completed"},
            "Remaining Risks": [],
            "Knowledge Proposal": [{"path": ".dev-docs/knowledge/notes.md", "body": "preserve decision"}],
            "Archive Decision": {"target": "archive", "body": "archive evidence"},
        }
        decision_payload["decision_sha256"] = self.self_hash(decision_payload, "decision_sha256")
        finish_plan = {
            "schema_version": 1,
            "contract_sha256": A_HASH,
            "context_fingerprint": B_HASH,
            "completion_sha256": completion_payload["completion_sha256"],
            "decision_sha256": decision_payload["decision_sha256"],
            "mutation_map_sha256": D_HASH,
            "acceptance_index_sha256": B_HASH,
            "implementation_range": {"base": "abc1234", "head": "fedcba9"},
            "task_heads": {"T1": "def5678", "T2": "fedcba9"},
            "decision_state_version": decision_payload["decision_state_version"],
            "archive_intent": "archive validated change-local evidence",
            "knowledge_proposal": decision_payload["Knowledge Proposal"],
            "knowledge_targets": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None, "proposed_after_summary": "new notes", "reason": "preserve validated decision", "source_evidence": completion_payload["completion_sha256"], "target_language": "zh-CN", "language_source": "contract_output_language"}],
            "archive_targets": [{"path": ".dev-docs/archive/change-alpha.json", "before_sha256": None, "proposed_after_summary": "archive packet", "reason": "archive evidence", "source_evidence": decision_payload["decision_sha256"], "target_language": "zh-CN", "language_source": "contract_output_language"}],
            "index_targets": [{"path": ".dev-docs/changes/index.md", "before_sha256": None, "proposed_after_summary": "change index", "reason": "index archived change", "source_evidence": decision_payload["decision_sha256"], "target_language": "zh-CN", "language_source": "contract_output_language"}],
        }
        finish_plan["finish_plan_sha256"] = self.self_hash(finish_plan, "finish_plan_sha256")
        completion_doc = {"schema_version": 1, "evidence_id": "completion-1", "kind": "completion", "change_id": "change-alpha", "contract_sha256": A_HASH, "context_fingerprint": B_HASH, "state_version": self.read_state()["state_version"], "created_at": "2026-07-18T01:00:00Z", "completion": completion_payload}
        decision_doc = {"schema_version": 1, "evidence_id": "decision-1", "kind": "decision", "change_id": "change-alpha", "contract_sha256": A_HASH, "context_fingerprint": B_HASH, "state_version": self.read_state()["state_version"], "created_at": "2026-07-18T01:00:00Z", "decision": decision_payload}
        (change_root / "completion.json").write_text(json.dumps(completion_doc), encoding="utf-8")
        (change_root / "decision.json").write_text(json.dumps(decision_doc), encoding="utf-8")
        (change_root / "finish-plan.json").write_text(json.dumps(finish_plan), encoding="utf-8")
        return change_root, completion_doc, decision_doc, finish_plan

    def write_finish_apply_targets(self, change_root=None):
        change_root = change_root or self.state_path.parent
        repo = change_root.parents[2]
        targets = {
            ".dev-docs/knowledge/notes.md": "preserve decision\n",
            ".dev-docs/archive/change-alpha.json": '{"archived":true}\n',
            ".dev-docs/changes/index.md": "- change-alpha archived\n",
        }
        for rel_path, content in targets.items():
            target = repo / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return targets

    def finish_apply_journal(self, approval_identity, change_root=None):
        change_root = change_root or self.state_path.parent
        repo = change_root.parents[2]
        finish_plan = json.loads((change_root / "finish-plan.json").read_text(encoding="utf-8"))
        self.write_finish_apply_targets(change_root)
        entries = []
        for group_name, archive_result in (("knowledge_targets", "not_applicable"), ("archive_targets", "archived"), ("index_targets", "not_applicable")):
            for target in finish_plan[group_name]:
                entries.append(
                    {
                        "path": target["path"],
                        "before_sha256": target["before_sha256"],
                        "after_sha256": self.file_sha(repo / target["path"]),
                        "reason": target["reason"],
                        "target_language": target["target_language"],
                        "language_source": target["language_source"],
                        "apply_result": "applied",
                        "archive_result": archive_result,
                    }
                )
        journal = {
            "decision_sha256": finish_plan["decision_sha256"],
            "finish_plan_sha256": finish_plan["finish_plan_sha256"],
            "approval_identity": approval_identity,
            "archive_intent": finish_plan["archive_intent"],
            "entries": entries,
            "verified": True,
        }
        journal["journal_sha256"] = self.self_hash(journal, "journal_sha256")
        return journal

    def start_completion_pass(self):
        self.complete_all_tasks()
        version = self.read_state()["state_version"]
        self.helper.start_completion(self.state_path, version, self.completion_packet())
        change_root, _completion_doc, _decision_doc, _finish_plan = self.write_finish_handoff()
        return self.helper.record_completion(self.state_path, version + 1, self.completion_pass(change_root=str(change_root)))

    def assert_error(self, fn, code):
        before = self.state_path.read_bytes() if self.state_path.exists() else b""
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            fn()
        self.assertEqual(ctx.exception.code, code)
        after = self.state_path.read_bytes() if self.state_path.exists() else b""
        self.assertEqual(before, after)

    def test_init_creates_contract_pending_and_artifact_is_not_approval(self):
        state = self.init_state()
        self.assertEqual(state["status"], "contract_pending")
        self.assertEqual(state["gates"]["contract"]["status"], "pending")
        self.assertEqual(self.helper.next_action(state)["action"], "REQUEST_CONTRACT_APPROVAL")
        self.assertNotEqual(self.helper.next_action(state)["action"], "DISPATCH_IMPLEMENTER")
        self.assertEqual(state["tasks"][0]["status"], "ready")
        self.assertEqual(state["tasks"][1]["status"], "pending")

    def test_approval_requires_fresh_identity_and_version(self):
        self.init_state()
        state = self.approve_contract()
        self.assertEqual(state["status"], "ready_to_execute")
        self.assertEqual(state["gates"]["contract"]["status"], "approved")
        self.assertEqual(self.helper.next_action(state)["action"], "DISPATCH_IMPLEMENTER")
        self.assert_error(lambda: self.approve_contract(expected_version=1), "VERSION_MISMATCH")

    def test_contract_approval_accepts_exact_aliases_and_persists_canonical_token(self):
        for token in ("approve", "批准", "同意", "继续", "  同意\n"):
            with self.subTest(token=token):
                self.state_path.unlink(missing_ok=True)
                self.init_state()
                state = self.approve_contract(approval_payload=approval(token=token))
                notes = json.loads(state["gates"]["contract"]["notes"])
                self.assertEqual(notes["token"], "approve")
                self.assertNotIn(str(token).strip(), state["history"][-1].get("reason", ""))

    def test_contract_approval_rejects_non_exact_aliases_without_mutation(self):
        for token in ("", "我同意", "同意。", "approve.", "request changes"):
            with self.subTest(token=token):
                self.state_path.unlink(missing_ok=True)
                self.init_state()
                code = "INVALID_CONTRACT_APPROVAL" if token else "INVALID_INPUT"
                self.assert_error(lambda: self.approve_contract(approval_payload=approval(token=token)), code)

    def test_stale_contract_and_context_invalidate_without_auto_approval(self):
        self.init_state()
        with self.assertRaises(self.helper.ProtocolError) as contract_ctx:
            self.approve_contract(contract=contract_identity(sha256=B_HASH))
        self.assertEqual(contract_ctx.exception.code, "STALE_CONTRACT")
        state = self.read_state()
        self.assertEqual(state["status"], "drafting_contract")
        self.assertEqual(state["gates"]["contract"]["status"], "stale")
        self.init_state()
        with self.assertRaises(self.helper.ProtocolError) as context_ctx:
            self.approve_contract(context=context_identity(fingerprint=C_HASH), approval_payload=approval(token="同意"))
        self.assertEqual(context_ctx.exception.code, "STALE_CONTEXT")
        self.assertEqual(self.read_state()["status"], "context_stale")
        self.assertEqual(self.read_state()["gates"]["contract"]["status"], "stale")

    def test_every_normal_state_has_stable_next_action(self):
        self.init_state()
        self.assertEqual(self.helper.inspect_state(self.read_state())["status"], "contract_pending")
        self.approve_contract()
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "DISPATCH_IMPLEMENTER")
        packet = worker_packet(self.helper, "T1", 2)
        self.helper.start_task(self.state_path, 2, "T1", packet)
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "DISPATCH_IMPLEMENTER")
        self.helper.record_implementation(self.state_path, 3, impl(packet_sha256=self.helper.sha256_value(packet)))
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "DISPATCH_REVIEWER")
        self.helper.import_task_review(self.state_path, 4, pass_review())
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "DISPATCH_IMPLEMENTER")
        self.complete_all_tasks()
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "RUN_COMPLETION_REVIEW")
        self.helper.start_completion(self.state_path, 8, self.completion_packet())
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "RUN_COMPLETION_REVIEW")
        change_root, _completion_doc, _decision_doc, _finish_plan = self.write_finish_handoff()
        self.helper.record_completion(self.state_path, 9, self.completion_pass(change_root=str(change_root)))
        self.assertEqual(self.helper.next_action(self.state_path)["action"], "REQUEST_FINISH_DECISION")
        decision_sha = self.current_decision_sha()
        finish_plan_sha = self.current_finish_plan_sha()
        self.helper.finish_decision(self.state_path, 10, "accept", {"decision_sha256": decision_sha, "expected_decision_state_version": 11, "finish_plan_sha256": finish_plan_sha, "decided_at": "2026-07-18T01:00:00Z", "change_root": str(change_root)})
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "APPLY_FINISH")
        self.helper.record_finish_apply(self.state_path, 11, self.finish_apply_journal("accept:2026-07-18T01:00:00Z", change_root))
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "COMPLETE")

    def test_dependency_order_packet_and_task_pass_are_enforced(self):
        self.init_state(); self.approve_contract()
        self.assert_error(lambda: self.helper.start_task(self.state_path, 2, "T2", worker_packet(self.helper, "T2", 2)), "DEPENDENCY_NOT_COMPLETE")
        self.assert_error(lambda: self.helper.start_task(self.state_path, 2, "T1", worker_packet(self.helper, "T1", 2, ownership=[{"path": "plugins/nuclio-plugin/scripts/b.py", "mode": "modify"}])), "STALE_OWNERSHIP")
        packet = worker_packet(self.helper, "T1", 2)
        self.helper.start_task(self.state_path, 2, "T1", packet)
        self.assert_error(lambda: self.helper.import_task_review(self.state_path, 3, pass_review()), "TASK_NOT_REVIEWING")
        self.helper.record_implementation(self.state_path, 3, impl(packet_sha256=self.helper.sha256_value(packet)))
        self.helper.import_task_review(self.state_path, 4, pass_review())
        self.assertEqual(self.read_state()["tasks"][0]["status"], "completed")

    def test_worker_packet_bind_negative_cases_are_atomic_and_fail_closed(self):
        self.init_state(); self.approve_contract()
        self.assertNotIn("packet_sha256", self.read_state()["tasks"][0])
        self.assert_error(lambda: self.helper.start_task(self.state_path, 2, "T1", worker_packet(self.helper, "T1", 1)), "STALE_PACKET")
        self.assert_error(lambda: self.helper.start_task(self.state_path, 2, "T1", worker_packet(self.helper, "T2", 2)), "WRONG_TASK")
        self.assert_error(lambda: self.helper.start_task(self.state_path, 2, "T1", worker_packet(self.helper, "T1", 2, ownership=[{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "delete"}])), "STALE_OWNERSHIP")
        self.assert_error(lambda: self.helper.start_task(self.state_path, 2, "T1", worker_packet(self.helper, "T1", 2, role="reviewer")), "INVALID_PACKET_SCHEMA")
        tampered = worker_packet(self.helper, "T1", 2)
        tampered["output_language"] = "en"
        self.assert_error(lambda: self.helper.start_task(self.state_path, 2, "T1", tampered), "PACKET_ID_MISMATCH")
        packet = worker_packet(self.helper, "T1", 2)
        started = self.helper.start_task(self.state_path, 2, "T1", packet)
        self.assertEqual(started["tasks"][0]["status"], "implementing")
        retry = self.helper.start_task(self.state_path, 3, "T1", packet)
        self.assertEqual(retry["state_version"], 3)
        replacement = worker_packet(self.helper, "T1", 3)
        self.assert_error(lambda: self.helper.start_task(self.state_path, 3, "T1", replacement), "PACKET_ALREADY_BOUND")

        self.state_path.unlink()
        self.init_state(); self.approve_contract()
        unbound = self.read_state(); unbound["status"] = "executing"; unbound["state_version"] = 2
        self.state_path.write_text(self.helper.canonical_json(unbound) + "\n", encoding="utf-8")
        self.assert_error(lambda: self.helper.record_implementation(self.state_path, 2, impl(packet_sha256=C_HASH)), "PACKET_UNBOUND")

    def test_worker_packet_contract_shape_is_validated_before_binding(self):
        cases = [
            ("range", "not-an-object"),
            ("range", {"base_head": "not-a-hex-ref", "expected_dirty_state": "clean"}),
            ("range", {"base_head": "abc1234", "new_head": "not-a-hex-ref", "expected_dirty_state": "clean"}),
            ("range", {"base_head": "abc1234", "expected_dirty_state": "dirty"}),
            ("snapshots", "not-a-list"),
            ("snapshots", [{"path": "plugins/nuclio-plugin/scripts/a.py"}]),
            ("checks", "not-an-object"),
            ("checks", {"focused": "not-a-list", "full": []}),
            ("checks", {"focused": [{"name": "unit", "command": []}], "full": []}),
            ("handoffs", "not-a-list"),
            ("handoffs", [""]),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.state_path.unlink(missing_ok=True)
                self.init_state(); self.approve_contract()
                packet = worker_packet(self.helper, "T1", 2)
                packet[field] = value
                packet["packet_id"] = self.helper._packet_id(packet)
                self.assert_error(lambda: self.helper.start_task(self.state_path, 2, "T1", packet), "INVALID_PACKET_SCHEMA")
                self.assertNotIn("packet_sha256", self.read_state()["tasks"][0])

    def test_worker_packet_bool_versions_fail_schema_before_identity_or_binding(self):
        for field in ("schema_version", "state_version"):
            with self.subTest(field=field):
                self.state_path.unlink(missing_ok=True)
                self.init_state(); self.approve_contract()
                packet = worker_packet(self.helper, "T1", 2)
                packet[field] = True
                packet["packet_id"] = self.helper._packet_id(packet)
                self.assert_error(lambda: self.helper.start_task(self.state_path, 2, "T1", packet), "INVALID_PACKET_SCHEMA")
                self.assertNotIn("packet_sha256", self.read_state()["tasks"][0])

    def test_fail_fix_shared_max2_budget_no_progress_cross_owner(self):
        self.init_state(); self.approve_contract(); packet = worker_packet(self.helper, "T1", 2); self.helper.start_task(self.state_path, 2, "T1", packet); self.helper.record_implementation(self.state_path, 3, impl(packet_sha256=self.helper.sha256_value(packet)))
        self.helper.import_task_review(self.state_path, 4, fail_review())
        state = self.read_state()
        self.assertEqual(state["status"], "repair_required")
        self.assertEqual(self.helper.next_action(state)["action"], "DISPATCH_FIXER")
        self.helper.needs_fix(self.state_path, 5, "T1", ["F1"])
        self.helper.authorize_fix(self.state_path, 6, "T1", ["F1"])
        state = self.read_state()
        self.assertEqual(state["fix_budgets"]["owner-a"]["used"], 1)
        self.assert_error(lambda: self.helper.record_fix(self.state_path, 7, impl(head="def5678", base_head="def5678", packet_sha256=self.current_packet_sha())), "NO_PROGRESS")
        self.helper.record_fix(self.state_path, 7, impl(head="def5678-fixed", implementation_sha256=A_HASH, base_head="def5678", packet_sha256=self.current_packet_sha()))
        self.assert_error(lambda: self.helper.import_task_review(self.state_path, 8, fail_review(owner="owner-b", finding_id="FX")), "CROSS_OWNER_FINDING")
        self.helper.import_task_review(self.state_path, 8, fail_review(finding_id="F2", fingerprint="fp-2"))
        self.helper.needs_fix(self.state_path, 9, "T1", ["F2"])
        self.helper.authorize_fix(self.state_path, 10, "T1", ["F2"])
        self.assertEqual(self.read_state()["fix_budgets"]["owner-a"]["remaining"], 0)
        self.assert_error(lambda: self.helper.authorize_fix(self.state_path, 11, "T1", ["F2"]), "BUDGET_EXHAUSTED")

    def test_record_fix_requires_base_head_to_match_current_task_head(self):
        self.init_state(); self.approve_contract(); packet = worker_packet(self.helper, "T1", 2); self.helper.start_task(self.state_path, 2, "T1", packet); self.helper.record_implementation(self.state_path, 3, impl(packet_sha256=self.helper.sha256_value(packet)))
        self.helper.import_task_review(self.state_path, 4, fail_review())
        self.helper.authorize_fix(self.state_path, 5, "T1", ["F1"])
        self.assert_error(lambda: self.helper.record_fix(self.state_path, 6, impl(head="def5678-fixed", implementation_sha256=A_HASH, base_head="stale-unrelated-head", packet_sha256=self.current_packet_sha())), "STALE_HEAD")
        state = self.helper.record_fix(self.state_path, 6, impl(head="def5678-fixed", implementation_sha256=A_HASH, base_head="def5678", packet_sha256=self.current_packet_sha()))
        self.assertEqual(state["tasks"][0]["status"], "reviewing")
        self.assertEqual(self.helper._metadata(state)["heads"]["T1"], "def5678-fixed")

    def test_completion_requires_all_tasks_and_handles_pass_fail(self):
        self.init_state(); self.approve_contract(); self.complete_t1()
        self.assert_error(lambda: self.helper.start_completion(self.state_path, 5, {"implementation_range": {"base": "abc1234", "head": "def5678"}, "acceptance_index_sha256": B_HASH}), "TASKS_INCOMPLETE")
        packet = worker_packet(self.helper, "T2", 5); self.helper.start_task(self.state_path, 5, "T2", packet); self.helper.record_implementation(self.state_path, 6, impl("T2", head="fedcba9", packet_sha256=self.helper.sha256_value(packet))); self.helper.import_task_review(self.state_path, 7, pass_review("T2", review_sha256=A_HASH))
        self.helper.start_completion(self.state_path, 8, self.completion_packet())
        state = self.helper.record_completion(self.state_path, 9, {"verdict": "FAIL", "blocking_owner": "owner-a", "finding_id": "CF1", "reason": "completion blocker"})
        self.assertEqual(state["status"], "repair_required")
        self.assertNotIn("decision", state)

    def test_completion_fail_owner_mapped_blocker_can_be_authorized_with_shared_budget(self):
        self.init_state(); self.approve_contract(); self.complete_all_tasks()
        self.helper.start_completion(self.state_path, 8, self.completion_packet())
        state = self.helper.record_completion(self.state_path, 9, {"verdict": "FAIL", "blocking_owner": "owner-a", "finding_id": "CF1", "reason": "completion blocker"})
        self.assertEqual(state["status"], "repair_required")
        self.assertEqual(state["blockers"][-1]["id"], "T1:CF1")
        self.helper.authorize_fix(self.state_path, 10, "T1", ["CF1"])
        state = self.read_state()
        self.assertEqual(state["tasks"][0]["status"], "fixing")
        self.assertEqual(state["fix_budgets"]["owner-a"]["used"], 1)
        self.assertEqual(state["fix_budgets"]["owner-a"]["remaining"], 1)

    def test_completion_fail_only_blocks_mapped_owner_and_repair_resumes_completion(self):
        self.init_state(); self.approve_contract(); self.complete_all_tasks()
        self.helper.start_completion(self.state_path, 8, self.completion_packet())
        state = self.helper.record_completion(self.state_path, 9, {"verdict": "FAIL", "blocking_owner": "owner-a", "task_id": "T1", "finding_id": "CF1", "reason": "completion blocker"})
        self.assertEqual(state["status"], "repair_required")
        self.assertEqual(state["tasks"][0]["status"], "blocked")
        self.assertEqual(state["tasks"][1]["status"], "completed")
        self.assertEqual(self.helper.next_action(state)["action"], "DISPATCH_FIXER")
        self.assertNotIn("completion_identity", self.helper._metadata(state))
        self.helper.authorize_fix(self.state_path, 10, "T1", ["CF1"])
        self.helper.record_fix(self.state_path, 11, impl(head="def5678-repaired", implementation_sha256=A_HASH, base_head="def5678", packet_sha256=self.current_packet_sha()))
        self.helper.import_task_review(self.state_path, 12, pass_review("T1", review_sha256=B_HASH))
        repaired = self.read_state()
        self.assertEqual(repaired["tasks"][0]["status"], "completed")
        self.assertEqual(repaired["tasks"][1]["status"], "completed")
        self.assertEqual(repaired["status"], "executing")
        self.assertEqual(self.helper.next_action(repaired)["action"], "RUN_COMPLETION_REVIEW")
        refreshed_packet = self.completion_packet(task_heads={"T1": "def5678-repaired", "T2": "fedcba9"}, implementation_range={"base": "abc1234", "head": "def5678-repaired"})
        self.helper.start_completion(self.state_path, 13, refreshed_packet)

    def test_completion_pass_requires_full_identity_and_leaves_state_unchanged(self):
        self.init_state(); self.approve_contract(); self.complete_all_tasks()
        self.helper.start_completion(self.state_path, 8, self.completion_packet())
        self.write_finish_handoff()
        missing_range = self.completion_pass(change_root=str(self.state_path.parent))
        missing_range.pop("implementation_range")
        self.assert_error(lambda: self.helper.record_completion(self.state_path, 9, missing_range), "INVALID_IDENTITY")
        missing_acceptance = self.completion_pass(change_root=str(self.state_path.parent))
        missing_acceptance.pop("acceptance_index_sha256")
        self.assert_error(lambda: self.helper.record_completion(self.state_path, 9, missing_acceptance), "INVALID_IDENTITY")

    def test_record_completion_requires_projected_disk_handoff_and_schema_valid_state(self):
        self.init_state(); self.approve_contract(); self.complete_all_tasks()
        self.helper.start_completion(self.state_path, 8, self.completion_packet())
        change_root, _completion_doc, _decision_doc, finish_plan = self.write_finish_handoff()
        state = self.helper.record_completion(self.state_path, 9, self.completion_pass(change_root=str(change_root)))
        self.assertEqual(state["status"], "decision_pending")
        self.assertEqual(state["completion"]["completion_sha256"], finish_plan["completion_sha256"])
        self.assertEqual(state["decision"]["decision_sha256"], finish_plan["decision_sha256"])
        self.assertEqual(state["decision"]["finish_plan_sha256"], finish_plan["finish_plan_sha256"])
        self.assertEqual(state["decision"]["decision_state_version"], 11)
        self.helper.JSON_SCHEMA_HELPER.validate_instance(STATE_SCHEMA, state)

    def test_record_completion_missing_sidecar_does_not_enter_decision_pending(self):
        self.init_state(); self.approve_contract(); self.complete_all_tasks()
        self.helper.start_completion(self.state_path, 8, self.completion_packet())
        change_root, _completion_doc, _decision_doc, _finish_plan = self.write_finish_handoff()
        (change_root / "finish-plan.json").unlink()
        self.assert_error(lambda: self.helper.record_completion(self.state_path, 9, self.completion_pass(change_root=str(change_root))), "MISSING_FINISH_HANDOFF")
        state = self.read_state()
        self.assertEqual(state["status"], "completing")
        self.assertNotIn("decision", state)

    def test_legacy_rebuild_route_and_canonical_drift_halt(self):
        self.init_state(); self.approve_contract(); self.complete_all_tasks()
        self.helper.start_completion(self.state_path, 8, self.completion_packet())
        self.write_finish_handoff()
        state = self.read_state()
        state["status"] = "decision_pending"
        state["completion"] = {"proposal_sha256": C_HASH, "mutation_map_sha256": D_HASH, "state_version": 9, **self.completion_identity()}
        state["decision"] = {"decision_sha256": E_HASH, "state_version": 9, "approved": False}
        self.state_path.write_text(self.helper.canonical_json(state) + "\n", encoding="utf-8")
        self.assertEqual(self.helper.next_action(self.state_path)["action"], "REBUILD_FINISH_HANDOFF")
        self.assertEqual(self.helper.record_finish_handoff(self.state_path, 9, str(self.state_path.parent))["decision"]["approved"], False)
        (self.state_path.parent / "decision.md").write_text("# Drift\n", encoding="utf-8")
        halted = self.helper.next_action(self.state_path)
        self.assertEqual(halted["action"], "HALT")
        self.assertEqual(halted["code"], "MARKDOWN_HASH_MISMATCH")

    def test_finish_accept_requires_fresh_readiness_not_bare_metadata_hash(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        decision_sha = self.current_decision_sha()
        finish_plan_sha = self.current_finish_plan_sha()
        (self.state_path.parent / "finish-plan.json").unlink()
        self.assert_error(
            lambda: self.helper.finish_decision(
                self.state_path,
                10,
                "accept",
                {"decision_sha256": decision_sha, "expected_decision_state_version": 11, "finish_plan_sha256": finish_plan_sha, "decided_at": "2026-07-18T03:00:00Z", "change_root": str(self.state_path.parent)},
            ),
            "MISSING_FINISH_HANDOFF",
        )

    def test_finish_request_changes_defer_reject_do_not_apply_long_term_targets(self):
        for decision, expected_status in (("request_changes", "ready_to_execute"), ("defer", "deferred"), ("reject", "rejected")):
            with self.subTest(decision=decision):
                self.state_path.unlink(missing_ok=True)
                self.init_state(); self.approve_contract(); self.start_completion_pass()
                decision_sha = self.current_decision_sha()
                finish_plan_sha = self.current_finish_plan_sha()
                state = self.helper.finish_decision(self.state_path, 10, decision, {"decision_sha256": decision_sha, "finish_plan_sha256": finish_plan_sha, "decided_at": "2026-07-18T03:00:00Z", "change_root": str(self.state_path.parent)})
                self.assertEqual(state["status"], expected_status)
                self.assertNotEqual(state["status"], "folding")
                self.assert_error(lambda: self.helper.record_finish_apply(self.state_path, 11, {"decision_sha256": decision_sha, "finish_plan_sha256": finish_plan_sha, "journal_sha256": A_HASH, "verified": True, "approval_identity": "accept:2026-07-18"}), "FINISH_NOT_ACCEPTED")

    def test_record_finish_apply_requires_verified_json_journal_and_approval_identity(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        decision_sha = self.current_decision_sha()
        finish_plan_sha = self.current_finish_plan_sha()
        self.helper.finish_decision(self.state_path, 10, "accept", {"decision_sha256": decision_sha, "expected_decision_state_version": 11, "finish_plan_sha256": finish_plan_sha, "decided_at": "2026-07-18T03:00:00Z", "change_root": str(self.state_path.parent)})
        self.assert_error(lambda: self.helper.record_finish_apply(self.state_path, 11, {"decision_sha256": decision_sha, "finish_plan_sha256": finish_plan_sha, "journal_sha256": A_HASH, "verified": True}), "INVALID_FINISH_JOURNAL")
        journal = self.finish_apply_journal("accept:2026-07-18T03:00:00Z")
        archived = self.helper.record_finish_apply(self.state_path, 11, journal)
        self.assertEqual(archived["status"], "archived")

    def test_record_finish_apply_rejects_fake_verified_minimal_journal_before_archive(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        decision_sha = self.current_decision_sha()
        finish_plan_sha = self.current_finish_plan_sha()
        self.helper.finish_decision(self.state_path, 10, "accept", {"decision_sha256": decision_sha, "expected_decision_state_version": 11, "finish_plan_sha256": finish_plan_sha, "decided_at": "2026-07-18T03:00:00Z", "change_root": str(self.state_path.parent)})
        fake_journal = {"decision_sha256": decision_sha, "finish_plan_sha256": finish_plan_sha, "journal_sha256": A_HASH, "verified": True, "approval_identity": "accept:2026-07-18T03:00:00Z"}
        self.assert_error(lambda: self.helper.record_finish_apply(self.state_path, 11, fake_journal), "INVALID_FINISH_JOURNAL")
        self.assertEqual(self.read_state()["status"], "folding")

    def test_folding_partial_canonical_identity_is_invalid_state_schema(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        decision_sha = self.current_decision_sha()
        finish_plan_sha = self.current_finish_plan_sha()
        self.helper.finish_decision(self.state_path, 10, "accept", {"decision_sha256": decision_sha, "expected_decision_state_version": 11, "finish_plan_sha256": finish_plan_sha, "decided_at": "2026-07-18T03:00:00Z", "change_root": str(self.state_path.parent)})
        state = self.read_state()
        state["completion"] = {"proposal_sha256": C_HASH, "mutation_map_sha256": D_HASH, "state_version": 9}
        state["decision"] = {"decision_sha256": decision_sha, "state_version": 10, "approved": True}
        self.state_path.write_text(self.helper.canonical_json(state) + "\n", encoding="utf-8")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.load_state(self.state_path)
        self.assertEqual(ctx.exception.code, "INVALID_STATE_SCHEMA")

    def test_decision_pending_partial_canonical_marker_is_invalid_state_schema(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        state = self.read_state()
        state["completion"] = {"completion_sha256": state["completion"]["completion_sha256"], "proposal_sha256": C_HASH, "mutation_map_sha256": D_HASH, "state_version": 9}
        state["decision"] = {"decision_sha256": state["decision"]["decision_sha256"], "finish_plan_sha256": state["decision"]["finish_plan_sha256"], "state_version": 9, "approved": False}
        self.state_path.write_text(self.helper.canonical_json(state) + "\n", encoding="utf-8")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.load_state(self.state_path)
        self.assertEqual(ctx.exception.code, "INVALID_STATE_SCHEMA")

    def test_finish_accept_requires_generated_decision_hash_and_expected_state_version(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        finish_plan_sha = self.current_finish_plan_sha()
        self.assert_error(
            lambda: self.helper.finish_decision(
                self.state_path,
                10,
                "accept",
                {"decision_sha256": E_HASH, "expected_decision_state_version": 11, "finish_plan_sha256": finish_plan_sha, "decided_at": "2026-07-18T03:00:00Z", "change_root": str(self.state_path.parent)},
            ),
            "STALE_DECISION",
        )
        decision_sha = self.current_decision_sha()
        self.assert_error(
            lambda: self.helper.finish_decision(
                self.state_path,
                10,
                "同意",
                {"decision_sha256": decision_sha, "expected_decision_state_version": 8, "finish_plan_sha256": finish_plan_sha, "decided_at": "2026-07-18T03:00:00Z", "change_root": str(self.state_path.parent)},
            ),
            "STALE_DECISION",
        )

    def test_finish_request_changes_exact_token_invalidates_decision(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        decision_sha = self.current_decision_sha()
        self.assert_error(lambda: self.helper.finish_decision(self.state_path, 10, "request changes", {"decision_sha256": decision_sha, "decided_at": "2026-07-18T03:00:00Z"}), "INVALID_FINISH_DECISION")
        state = self.helper.finish_decision(self.state_path, 10, "request_changes", {"decision_sha256": decision_sha, "finish_plan_sha256": self.current_finish_plan_sha(), "decided_at": "2026-07-18T03:00:00Z", "change_root": str(self.state_path.parent)})
        self.assertEqual(state["status"], "ready_to_execute")
        self.assertEqual(state["gates"]["finish"]["status"], "stale")
        self.assertFalse(state["decision"]["approved"])

    def test_finish_accepts_exact_aliases_and_persists_canonical_decision(self):
        cases = [
            ("accept", "accept", "folding"),
            ("同意", "accept", "folding"),
            ("  同意\n", "accept", "folding"),
            ("request_changes", "request_changes", "ready_to_execute"),
            ("要求修改", "request_changes", "ready_to_execute"),
            ("defer", "defer", "deferred"),
            ("暂缓", "defer", "deferred"),
            ("reject", "reject", "rejected"),
            ("拒绝", "reject", "rejected"),
        ]
        for token, canonical, expected_status in cases:
            with self.subTest(token=token):
                self.state_path.unlink(missing_ok=True)
                self.init_state(); self.approve_contract(); self.start_completion_pass()
                decision_sha = self.current_decision_sha()
                metadata = {"decision_sha256": decision_sha, "finish_plan_sha256": self.current_finish_plan_sha(), "reason": "because", "decided_at": "2026-07-18T02:00:00Z", "change_root": str(self.state_path.parent), "expected_decision_state_version": 11}
                state = self.helper.finish_decision(self.state_path, 10, token, metadata)
                self.assertEqual(state["status"], expected_status)
                notes = json.loads(state["gates"]["finish"]["notes"])
                self.assertEqual(notes["decision"], canonical)
                history_reason = json.loads(state["history"][-1]["reason"])
                self.assertEqual(history_reason["decision"], canonical)
                self.assertEqual(history_reason["readiness"]["decision_sha256"], decision_sha)
                self.assertEqual(history_reason["readiness"]["finish_plan_sha256"], metadata["finish_plan_sha256"])

    def test_finish_rejects_non_exact_aliases_without_mutation(self):
        for token in ("继续", "我同意", "同意。", "request changes", "accept."):
            with self.subTest(token=token):
                self.state_path.unlink(missing_ok=True)
                self.init_state(); self.approve_contract(); self.start_completion_pass()
                decision_sha = self.current_decision_sha()
                self.assert_error(lambda: self.helper.finish_decision(self.state_path, 10, token, {"decision_sha256": decision_sha, "finish_plan_sha256": F_HASH, "expected_decision_state_version": 11, "decided_at": "2026-07-18T03:00:00Z"}), "INVALID_FINISH_DECISION")

    def test_finish_four_decisions_stale_decision_and_archive_gate(self):
        for decision, expected_status in [("defer", "deferred"), ("request_changes", "ready_to_execute"), ("reject", "rejected"), ("accept", "folding")]:
            with self.subTest(decision=decision):
                self.state_path.unlink(missing_ok=True)
                self.init_state(); self.approve_contract(); self.start_completion_pass()
                decision_sha = self.current_decision_sha()
                finish_plan_sha = self.current_finish_plan_sha()
                metadata = {"decision_sha256": decision_sha, "finish_plan_sha256": finish_plan_sha, "reason": "because", "decided_at": "2026-07-18T02:00:00Z", "change_root": str(self.state_path.parent), "expected_decision_state_version": 11}
                state = self.helper.finish_decision(self.state_path, 10, decision, metadata)
                self.assertEqual(state["status"], expected_status)
                if decision == "accept":
                    self.assert_error(lambda: self.helper.record_finish_apply(self.state_path, 10, {"decision_sha256": decision_sha, "finish_plan_sha256": finish_plan_sha, "journal_sha256": A_HASH, "verified": True, "approval_identity": "accept:2026-07-18T02:00:00Z"}), "VERSION_MISMATCH")
                    stale_journal = self.finish_apply_journal("accept:2026-07-18T02:00:00Z")
                    stale_journal["decision_sha256"] = B_HASH
                    stale_journal["journal_sha256"] = self.self_hash(stale_journal, "journal_sha256")
                    self.assert_error(lambda: self.helper.record_finish_apply(self.state_path, 11, stale_journal), "STALE_DECISION")
                    archived = self.helper.record_finish_apply(self.state_path, 11, self.finish_apply_journal("accept:2026-07-18T02:00:00Z"))
                    self.assertEqual(archived["status"], "archived")
                else:
                    self.assert_error(lambda: self.helper.record_finish_apply(self.state_path, 11, {"decision_sha256": decision_sha, "finish_plan_sha256": finish_plan_sha, "journal_sha256": A_HASH, "verified": True, "approval_identity": "accept:2026-07-18T02:00:00Z"}), "FINISH_NOT_ACCEPTED")

    def test_invalid_transition_atomic_bytes_and_resume_next_action(self):
        self.init_state(); self.approve_contract()
        before = self.state_path.read_bytes()
        self.assert_error(lambda: self.helper.record_implementation(self.state_path, 2, impl()), "PACKET_UNBOUND")
        self.assertEqual(before, self.state_path.read_bytes())
        resumed = self.helper.load_state(self.state_path)
        self.assertEqual(self.helper.next_action(resumed)["action"], "DISPATCH_IMPLEMENTER")

    def test_cli_json_envelope(self):
        proc = subprocess.run([sys.executable, str(HELPER), "init", str(self.state_path), "--contract-identity-json", json.dumps(contract_identity()), "--context-identity-json", json.dumps(context_identity()), "--task-graph-json", json.dumps(task_graph())], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual(out["state"]["status"], "contract_pending")
        proc = subprocess.run([sys.executable, str(HELPER), "start-task", str(self.state_path), "--expected-version", "1", "--task-id", "T1", "--packet-json", json.dumps(worker_packet(self.helper, "T1", 1))], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(json.loads(proc.stderr)["code"], "CONTRACT_NOT_APPROVED")

    def test_cli_record_finish_apply_accepts_journal_file_path(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        decision_sha = self.current_decision_sha()
        finish_plan_sha = self.current_finish_plan_sha()
        self.helper.finish_decision(
            self.state_path,
            10,
            "accept",
            {
                "decision_sha256": decision_sha,
                "expected_decision_state_version": 11,
                "finish_plan_sha256": finish_plan_sha,
                "decided_at": "2026-07-18T03:00:00Z",
                "change_root": str(self.state_path.parent),
            },
        )
        md_path = Path(self.temp.name) / "finish-apply.md"
        md_path.write_text("# journal\n", encoding="utf-8")
        rejected = subprocess.run([sys.executable, str(HELPER), "record-finish-apply", str(self.state_path), "--expected-version", "11", "--journal-json", str(md_path)], text=True, capture_output=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(json.loads(rejected.stderr)["code"], "INVALID_FINISH_JOURNAL")
        journal_path = Path(self.temp.name) / "finish-apply.json"
        journal_path.write_text(
            json.dumps(
                self.finish_apply_journal("accept:2026-07-18T03:00:00Z")
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(HELPER),
                "record-finish-apply",
                str(self.state_path),
                "--expected-version",
                "11",
                "--journal-json",
                str(journal_path),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual(out["state"]["status"], "archived")


if __name__ == "__main__":
    unittest.main()
