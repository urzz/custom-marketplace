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

    def start_completion_pass(self):
        self.complete_all_tasks()
        version = self.read_state()["state_version"]
        self.helper.start_completion(self.state_path, version, self.completion_packet())
        return self.helper.record_completion(self.state_path, version + 1, self.completion_pass())

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
        self.helper.record_completion(self.state_path, 9, self.completion_pass())
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "REQUEST_FINISH_DECISION")
        decision_sha = self.current_decision_sha()
        self.helper.finish_decision(self.state_path, 10, "accept", {"decision_sha256": decision_sha, "expected_decision_state_version": 9, "finish_plan_sha256": F_HASH, "decided_at": "2026-07-18T01:00:00Z"})
        self.assertEqual(self.helper.next_action(self.read_state())["action"], "APPLY_FINISH")
        self.helper.record_finish_apply(self.state_path, 11, {"decision_sha256": decision_sha, "finish_plan_sha256": F_HASH, "journal_sha256": A_HASH, "verified": True})
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
        missing_range = self.completion_pass()
        missing_range.pop("implementation_range")
        self.assert_error(lambda: self.helper.record_completion(self.state_path, 9, missing_range), "INVALID_IDENTITY")
        missing_acceptance = self.completion_pass()
        missing_acceptance.pop("acceptance_index_sha256")
        self.assert_error(lambda: self.helper.record_completion(self.state_path, 9, missing_acceptance), "INVALID_IDENTITY")

    def test_finish_accept_requires_generated_decision_hash_and_expected_state_version(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        self.assert_error(
            lambda: self.helper.finish_decision(
                self.state_path,
                10,
                "accept",
                {"decision_sha256": E_HASH, "expected_decision_state_version": 9, "finish_plan_sha256": F_HASH, "decided_at": "2026-07-18T03:00:00Z"},
            ),
            "STALE_DECISION",
        )
        decision_sha = self.current_decision_sha()
        self.assert_error(
            lambda: self.helper.finish_decision(
                self.state_path,
                10,
                "同意",
                {"decision_sha256": decision_sha, "expected_decision_state_version": 8, "finish_plan_sha256": F_HASH, "decided_at": "2026-07-18T03:00:00Z"},
            ),
            "STALE_DECISION",
        )

    def test_finish_request_changes_exact_token_invalidates_decision(self):
        self.init_state(); self.approve_contract(); self.start_completion_pass()
        decision_sha = self.current_decision_sha()
        self.assert_error(lambda: self.helper.finish_decision(self.state_path, 10, "request changes", {"decision_sha256": decision_sha, "decided_at": "2026-07-18T03:00:00Z"}), "INVALID_FINISH_DECISION")
        state = self.helper.finish_decision(self.state_path, 10, "request_changes", {"decision_sha256": decision_sha, "decided_at": "2026-07-18T03:00:00Z"})
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
                metadata = {"decision_sha256": decision_sha, "finish_plan_sha256": F_HASH, "reason": "because", "decided_at": "2026-07-18T02:00:00Z"}
                if canonical == "accept":
                    metadata["expected_decision_state_version"] = 9
                state = self.helper.finish_decision(self.state_path, 10, token, metadata)
                self.assertEqual(state["status"], expected_status)
                notes = json.loads(state["gates"]["finish"]["notes"])
                self.assertEqual(notes["decision"], canonical)
                self.assertEqual(state["history"][-1]["reason"], self.helper.canonical_json({**metadata, "decision": canonical}))

    def test_finish_rejects_non_exact_aliases_without_mutation(self):
        for token in ("继续", "我同意", "同意。", "request changes", "accept."):
            with self.subTest(token=token):
                self.state_path.unlink(missing_ok=True)
                self.init_state(); self.approve_contract(); self.start_completion_pass()
                decision_sha = self.current_decision_sha()
                self.assert_error(lambda: self.helper.finish_decision(self.state_path, 10, token, {"decision_sha256": decision_sha, "finish_plan_sha256": F_HASH, "expected_decision_state_version": 9, "decided_at": "2026-07-18T03:00:00Z"}), "INVALID_FINISH_DECISION")

    def test_finish_four_decisions_stale_decision_and_archive_gate(self):
        for decision, expected_status in [("defer", "deferred"), ("request_changes", "ready_to_execute"), ("reject", "rejected"), ("accept", "folding")]:
            with self.subTest(decision=decision):
                self.state_path.unlink(missing_ok=True)
                self.init_state(); self.approve_contract(); self.start_completion_pass()
                decision_sha = self.current_decision_sha()
                metadata = {"decision_sha256": decision_sha, "finish_plan_sha256": F_HASH, "reason": "because", "decided_at": "2026-07-18T02:00:00Z"}
                if decision == "accept":
                    metadata["expected_decision_state_version"] = 9
                state = self.helper.finish_decision(self.state_path, 10, decision, metadata)
                self.assertEqual(state["status"], expected_status)
                if decision == "accept":
                    self.assert_error(lambda: self.helper.record_finish_apply(self.state_path, 10, {"decision_sha256": decision_sha, "finish_plan_sha256": F_HASH, "journal_sha256": A_HASH, "verified": True}), "VERSION_MISMATCH")
                    self.assert_error(lambda: self.helper.record_finish_apply(self.state_path, 11, {"decision_sha256": B_HASH, "finish_plan_sha256": F_HASH, "journal_sha256": A_HASH, "verified": True}), "STALE_DECISION")
                    archived = self.helper.record_finish_apply(self.state_path, 11, {"decision_sha256": decision_sha, "finish_plan_sha256": F_HASH, "journal_sha256": A_HASH, "verified": True})
                    self.assertEqual(archived["status"], "archived")
                else:
                    self.assert_error(lambda: self.helper.record_finish_apply(self.state_path, 11, {"decision_sha256": decision_sha, "finish_plan_sha256": F_HASH, "journal_sha256": A_HASH, "verified": True}), "FINISH_NOT_ACCEPTED")

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
        self.helper.finish_decision(
            self.state_path,
            10,
            "accept",
            {
                "decision_sha256": decision_sha,
                "expected_decision_state_version": 9,
                "finish_plan_sha256": F_HASH,
                "decided_at": "2026-07-18T03:00:00Z",
            },
        )
        journal_path = Path(self.temp.name) / "finish-apply.md"
        journal_path.write_text(
            json.dumps(
                {
                    "decision_sha256": decision_sha,
                    "finish_plan_sha256": F_HASH,
                    "journal_sha256": A_HASH,
                    "verified": True,
                }
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
