"""
Nuclio fresh-process Finish resume tests.

## Contents

- [Helpers](#helpers)
- [Fixture builder](#fixture-builder)
- [Fresh-process success path](#fresh-process-success-path)
- [Fail-closed resume tests](#fail-closed-resume-tests)
"""

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "plugins" / "nuclio-plugin" / "scripts"
STATE_HELPER = SCRIPTS / "state-helper.py"
PACKET_HELPER = SCRIPTS / "packet-helper.py"
EVIDENCE_HELPER = SCRIPTS / "evidence-helper.py"

A_HASH = "a" * 64
B_HASH = "b" * 64
C_HASH = "c" * 64
D_HASH = "d" * 64
E_HASH = "e" * 64
F_HASH = "f" * 64


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_value(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def self_hash(value, self_field):
    return sha256_value({key: value[key] for key in sorted(value) if key != self_field})


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")
    return path


class FinishResumeCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.change_root = self.repo / ".dev-docs" / "changes" / "change-alpha"
        self.change_root.mkdir(parents=True)
        self.state_path = self.change_root / "state.json"
        self.contract_path = self.change_root / "contract.json"
        self.context_path = self.change_root / "context.json"
        self.contract_identity_path = self.change_root / "contract-identity.json"
        self.context_identity_path = self.change_root / "context-identity.json"
        self.task_graph_path = self.change_root / "task-graph.json"
        self._write_contract_context_inputs()

    def run_json(self, command, expected=0):
        proc = subprocess.run(command, text=True, capture_output=True)
        if proc.returncode != expected:
            self.fail(f"expected exit {expected}, got {proc.returncode}\ncommand={command}\nstdout={proc.stdout}\nstderr={proc.stderr}")
        payload_text = proc.stdout if expected == 0 else proc.stderr
        return json.loads(payload_text)

    def read_state(self):
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_contract_context_inputs(self):
        contract = {
            "schema_version": 1,
            "change_id": "change-alpha",
            "contract_version": "v1",
            "version": "v1",
            "sha256": A_HASH,
            "output_language": "zh-CN",
            "acceptance": [{"id": "A1", "text": "fresh-process Finish resume works"}],
            "tasks": [
                {
                    "id": "T1",
                    "name": "Task one",
                    "owner": "owner-a",
                    "dependencies": [],
                    "mutation_targets": [{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "create"}],
                    "checks": {"focused": [], "full": []},
                    "handoffs": {"inputs": [], "outputs": []},
                },
                {
                    "id": "T2",
                    "name": "Task two",
                    "owner": "owner-a",
                    "dependencies": ["T1"],
                    "mutation_targets": [{"path": "plugins/nuclio-plugin/scripts/b.py", "mode": "modify"}],
                    "checks": {"focused": [], "full": []},
                    "handoffs": {"inputs": [], "outputs": []},
                },
            ],
            "validation": {"focused": [], "full": [], "change_wide": []},
        }
        context = {"fingerprint": B_HASH, "entries": ["contract-ref", "finish-ref"], "split": {"finish": [{"id": "finish-ref", "path": "plugins/nuclio-plugin/references/finish.md"}]}}
        contract_identity = {"path": ".dev-docs/changes/change-alpha/contract.yaml", "sha256": A_HASH, "version": "v1", "change_id": "change-alpha", "output_language": "zh-CN"}
        context_identity = {"path": ".dev-docs/changes/change-alpha/context.jsonl", "fingerprint": B_HASH, "entries": ["contract-ref", "finish-ref"]}
        task_graph = [
            {"id": "T1", "owner": "owner-a", "dependencies": [], "ownership": [{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "create"}]},
            {"id": "T2", "owner": "owner-a", "dependencies": ["T1"], "ownership": [{"path": "plugins/nuclio-plugin/scripts/b.py", "mode": "modify"}]},
        ]
        write_json(self.contract_path, contract)
        write_json(self.context_path, context)
        write_json(self.contract_identity_path, contract_identity)
        write_json(self.context_identity_path, context_identity)
        write_json(self.task_graph_path, task_graph)

    def initialize_and_complete_work(self):
        self.run_json([sys.executable, str(STATE_HELPER), "init", str(self.state_path), "--contract-identity-json", str(self.contract_identity_path), "--context-identity-json", str(self.context_identity_path), "--task-graph-json", str(self.task_graph_path)])
        approval_path = write_json(self.change_root / "approval.json", {"approval_id": "contract-approval", "approved_at": "2026-07-22T00:00:00Z", "token": "approve"})
        self.run_json([sys.executable, str(STATE_HELPER), "approve-contract", str(self.state_path), "--expected-version", "1", "--contract-identity-json", str(self.contract_identity_path), "--context-identity-json", str(self.context_identity_path), "--approval-json", str(approval_path)])
        self._complete_task("T1", "abcdef1", "1111111", "plugins/nuclio-plugin/scripts/a.py", E_HASH, F_HASH)
        self._complete_task("T2", "1111111", "2222222", "plugins/nuclio-plugin/scripts/b.py", A_HASH, B_HASH)
        completed_tasks = [{"task_id": "T1", "head": "1111111", "evidence_sha256": E_HASH}, {"task_id": "T2", "head": "2222222", "evidence_sha256": A_HASH}]
        mutation_map = {"mutation_map": {"sha256": D_HASH, "changed_paths": ["plugins/nuclio-plugin/scripts/a.py", "plugins/nuclio-plugin/scripts/b.py"], "blockers": []}}
        acceptance_index = [{"id": "A1", "accepted": True, "evidence": "task evidence"}]
        completed_path = write_json(self.change_root / "completed-tasks.json", completed_tasks)
        mutation_path = write_json(self.change_root / "mutation-map.json", mutation_map)
        acceptance_path = write_json(self.change_root / "acceptance-index.json", acceptance_index)
        completion_packet_path = self.change_root / "completion-packet.json"
        self.run_json([
            sys.executable, str(PACKET_HELPER), "completion", "--repo", str(self.repo), "--contract-json", str(self.contract_path), "--context-json", str(self.context_path), "--state-json", str(self.state_path), "--base", "abcdef1", "--head", "2222222", "--mutation-map-json", str(mutation_path), "--completed-tasks-json", str(completed_path), "--acceptance-index-json", str(acceptance_path), "--validation-evidence-json", "{}", "--remaining-risks-json", "[]", "--output", str(completion_packet_path), "--expected-state-version", "8",
        ])
        self.run_json([sys.executable, str(STATE_HELPER), "start-completion", str(self.state_path), "--expected-version", "8", "--packet-json", str(completion_packet_path)])
        packet = json.loads(completion_packet_path.read_text(encoding="utf-8"))
        self.write_work_handoff(packet)
        completion_claim = {
            "verdict": "PASS",
            "contract_sha256": A_HASH,
            "context_fingerprint": B_HASH,
            "task_heads": {"T1": "1111111", "T2": "2222222"},
            "implementation_range": {"base": "abcdef1", "head": "2222222"},
            "acceptance_index_sha256": packet["acceptance_index_sha256"],
            "change_root": str(self.change_root),
        }
        claim_path = write_json(self.change_root / "completion-pass.json", completion_claim)
        return self.run_json([sys.executable, str(STATE_HELPER), "record-completion", str(self.state_path), "--expected-version", "9", "--completion-json", str(claim_path), "--change-root", str(self.change_root)])

    def _complete_task(self, task_id, base, head, changed_path, implementation_sha, review_sha):
        version = self.read_state()["state_version"]
        packet_path = self.change_root / f"worker-{task_id}.json"
        packet_result = self.run_json([
            sys.executable, str(PACKET_HELPER), "worker", "--repo", str(self.repo), "--contract-json", str(self.contract_path), "--context-json", str(self.context_path), "--state-json", str(self.state_path), "--base", base, "--head", head, "--task-id", task_id, "--handoff-snapshots-json", "[]", "--output", str(packet_path), "--expected-state-version", str(version),
        ])
        self.run_json([sys.executable, str(STATE_HELPER), "start-task", str(self.state_path), "--expected-version", str(version), "--task-id", task_id, "--packet-json", str(packet_path)])
        evidence = {"task_id": task_id, "packet_sha256": packet_result["identity"]["packet_sha256"], "base_head": base, "new_head": head, "implementation_sha256": implementation_sha, "changed_paths": [changed_path]}
        evidence_path = write_json(self.change_root / f"implementation-{task_id}.json", evidence)
        self.run_json([sys.executable, str(STATE_HELPER), "record-implementation", str(self.state_path), "--expected-version", str(version + 1), "--evidence-json", str(evidence_path)])
        review = {"task_id": task_id, "review_sha256": review_sha, "verdict": "PASS", "findings": []}
        review_path = write_json(self.change_root / f"review-{task_id}.json", review)
        self.run_json([sys.executable, str(STATE_HELPER), "import-task-review", str(self.state_path), "--expected-version", str(version + 2), "--review-json", str(review_path)])

    def write_work_handoff(self, completion_packet):
        (self.change_root / "evidence").mkdir(parents=True, exist_ok=True)
        completion_md = self.change_root / "evidence" / "completion.md"
        decision_md = self.change_root / "evidence" / "decision.md"
        completion_md.write_text("# Completion\n全部 Task 已完成，等待 Finish decision。\n", encoding="utf-8")
        decision_md.write_text("# Decision\n\n## Completion Verdict\nPASS\n\n## Remaining Risks\nnone\n\n## Knowledge Proposal\nwrite approved targets\n\n## Archive Decision\narchive accepted change\n", encoding="utf-8")
        completion_payload = {
            "proposal_sha256": C_HASH,
            "mutation_map_sha256": D_HASH,
            "check_summary_sha256": E_HASH,
            "task_heads": completion_packet["task_heads"],
            "task_evidence": completion_packet["task_evidence"],
            "task_evidence_sha256": completion_packet["task_evidence_sha256"],
            "implementation_range": completion_packet["implementation_range"],
            "acceptance_index_sha256": completion_packet["acceptance_index_sha256"],
            "residual_risks": [],
            "markdown_sha256": file_sha(completion_md),
        }
        completion_payload["completion_sha256"] = self_hash(completion_payload, "completion_sha256")
        decision_payload = {
            "completion_sha256": completion_payload["completion_sha256"],
            "decision_state_version": self.read_state()["state_version"] + (2 if self.read_state()["status"] == "completing" else 1),
            "markdown_sha256": file_sha(decision_md),
            "Completion Verdict": {"result": "PASS", "summary": "all tasks completed"},
            "Remaining Risks": [],
            "Knowledge Proposal": [{"path": ".dev-docs/knowledge/notes.md", "summary": "write knowledge after accept"}],
            "Archive Decision": {"archive": ".dev-docs/archive/change-alpha.json", "index": ".dev-docs/changes/index.md"},
        }
        decision_payload["decision_sha256"] = self_hash(decision_payload, "decision_sha256")
        finish_plan = {
            "schema_version": 1,
            "contract_sha256": A_HASH,
            "context_fingerprint": B_HASH,
            "completion_sha256": completion_payload["completion_sha256"],
            "decision_sha256": decision_payload["decision_sha256"],
            "mutation_map_sha256": D_HASH,
            "acceptance_index_sha256": completion_packet["acceptance_index_sha256"],
            "implementation_range": completion_packet["implementation_range"],
            "task_heads": completion_packet["task_heads"],
            "decision_state_version": decision_payload["decision_state_version"],
            "archive_intent": "archive accepted change-local evidence",
            "knowledge_proposal": decision_payload["Knowledge Proposal"],
            "knowledge_targets": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None, "proposed_after_summary": "Nuclio fresh-process resume note", "reason": "preserve accepted completion", "source_evidence": completion_payload["completion_sha256"], "target_language": "zh-CN", "language_source": "contract_output_language"}],
            "archive_targets": [{"path": ".dev-docs/archive/change-alpha.json", "before_sha256": None, "proposed_after_summary": "archive accepted change", "reason": "archive accepted evidence", "source_evidence": decision_payload["decision_sha256"], "target_language": "zh-CN", "language_source": "contract_output_language"}],
            "index_targets": [{"path": ".dev-docs/changes/index.md", "before_sha256": None, "proposed_after_summary": "index archived change", "reason": "index archived change", "source_evidence": decision_payload["decision_sha256"], "target_language": "zh-CN", "language_source": "contract_output_language"}],
        }
        finish_plan["finish_plan_sha256"] = self_hash(finish_plan, "finish_plan_sha256")
        completion_doc = {"schema_version": 1, "evidence_id": "completion-1", "kind": "completion", "change_id": "change-alpha", "contract_sha256": A_HASH, "context_fingerprint": B_HASH, "state_version": self.read_state()["state_version"], "created_at": "2026-07-22T00:01:00Z", "completion": completion_payload}
        decision_doc = {"schema_version": 1, "evidence_id": "decision-1", "kind": "decision", "change_id": "change-alpha", "contract_sha256": A_HASH, "context_fingerprint": B_HASH, "state_version": self.read_state()["state_version"], "created_at": "2026-07-22T00:01:00Z", "decision": decision_payload}
        write_json(self.change_root / "evidence" / "completion.json", completion_doc)
        write_json(self.change_root / "evidence" / "decision.json", decision_doc)
        write_json(self.change_root / "evidence" / "finish-plan.json", finish_plan)
        return completion_doc, decision_doc, finish_plan

    def accept_and_derive_finish_packet(self):
        state = self.read_state()
        metadata = {
            "decision_sha256": state["decision"]["decision_sha256"],
            "finish_plan_sha256": state["decision"]["finish_plan_sha256"],
            "expected_decision_state_version": state["decision"]["decision_state_version"],
            "decided_at": "2026-07-22T00:02:00Z",
            "approval_identity": "accept:fresh-process",
            "change_root": str(self.change_root),
        }
        metadata_path = write_json(self.change_root / "finish-decision.json", metadata)
        self.run_json([sys.executable, str(STATE_HELPER), "finish-decision", str(self.state_path), "--expected-version", str(state["state_version"]), "--decision", "accept", "--metadata-json", str(metadata_path), "--change-root", str(self.change_root)])
        self.assertEqual(self.run_json([sys.executable, str(STATE_HELPER), "next-action", str(self.state_path)])["next_action"]["action"], "APPLY_FINISH")
        snapshots_path = write_json(self.change_root / "knowledge-snapshots.json", [{"path": ".dev-docs/knowledge/notes.md", "state": "absent"}])
        packet_path = self.change_root / "finish-packet.json"
        completion_payload = json.loads((self.change_root / "evidence" / "completion.json").read_text(encoding="utf-8"))["completion"]
        completion_identity_path = write_json(self.change_root / "completion-identity.json", {"completion_identity": {"contract_sha256": A_HASH, "context_fingerprint": B_HASH, **completion_payload}})
        self.run_json([
            sys.executable, str(PACKET_HELPER), "finish", "--repo", str(self.repo), "--contract-json", str(self.contract_path), "--context-json", str(self.context_path), "--state-json", str(self.state_path), "--base", "abcdef1", "--head", "2222222", "--decision-json", str(self.change_root / "evidence" / "decision.json"), "--completion-identity-json", str(completion_identity_path), "--finish-plan-json", str(self.change_root / "evidence" / "finish-plan.json"), "--knowledge-snapshots-json", str(snapshots_path), "--output", str(packet_path), "--expected-state-version", str(self.read_state()["state_version"]),
        ])
        return json.loads(packet_path.read_text(encoding="utf-8"))

    def apply_targets_and_write_journal(self, finish_packet, wrong_after=False):
        entries = []
        content_by_path = {
            ".dev-docs/knowledge/notes.md": "# Notes\n\n已接受的完成摘要。\n",
            ".dev-docs/archive/change-alpha.json": canonical_json({"change_id": "change-alpha", "archived": True}) + "\n",
            ".dev-docs/changes/index.md": "- change-alpha: archived\n",
        }
        for group, archive_result in (("knowledge_targets", "not_applicable"), ("archive_targets", "archived"), ("index_targets", "not_applicable")):
            for target in finish_packet[group]:
                target_path = self.repo / target["path"]
                before = file_sha(target_path) if target_path.exists() else None
                self.assertEqual(before, target["before_sha256"])
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content_by_path[target["path"]], encoding="utf-8")
                after = file_sha(target_path)
                entries.append({"path": target["path"], "before_sha256": target["before_sha256"], "after_sha256": (A_HASH if wrong_after and target["path"] == ".dev-docs/knowledge/notes.md" else after), "reason": target["reason"], "target_language": target["target_language"], "language_source": target["language_source"], "apply_result": "applied", "archive_result": archive_result})
        journal = {"decision_sha256": finish_packet["decision_sha256"], "finish_plan_sha256": finish_packet["finish_plan_sha256"], "approval_identity": "accept:fresh-process", "archive_intent": finish_packet["archive_intent"], "entries": entries, "verified": True}
        journal["journal_sha256"] = self_hash(journal, "journal_sha256")
        return write_json(self.change_root / "evidence" / "finish-apply.json", journal)

    def test_fresh_process_work_handoff_finish_accept_packet_apply_archive(self):
        self.initialize_and_complete_work()
        inspect = self.run_json([sys.executable, str(STATE_HELPER), "inspect", str(self.state_path)])["inspect"]
        self.assertEqual(inspect["status"], "decision_pending")
        readiness = self.run_json([sys.executable, str(EVIDENCE_HELPER), "finish-readiness", "--change-root", str(self.change_root), "--contract-sha256", A_HASH, "--context-fingerprint", B_HASH])
        self.assertTrue(readiness)
        self.assertEqual(self.run_json([sys.executable, str(STATE_HELPER), "next-action", str(self.state_path)])["next_action"]["action"], "REQUEST_FINISH_DECISION")
        finish_packet = self.accept_and_derive_finish_packet()
        self.assertEqual([target["path"] for target in finish_packet["index_targets"]], [".dev-docs/changes/index.md"])
        journal_path = self.apply_targets_and_write_journal(finish_packet)
        self.run_json([sys.executable, str(EVIDENCE_HELPER), "validate-finish-apply", "--repo", str(self.repo), "--decision-sha256", finish_packet["decision_sha256"], "--finish-plan-json", str(self.change_root / "evidence" / "finish-plan.json"), "--journal-json", str(journal_path)])
        self.run_json([sys.executable, str(STATE_HELPER), "record-finish-apply", str(self.state_path), "--expected-version", str(self.read_state()["state_version"]), "--journal-json", str(journal_path)])
        self.assertEqual(self.run_json([sys.executable, str(STATE_HELPER), "next-action", str(self.state_path)])["next_action"]["action"], "COMPLETE")
        self.assertIn("已接受", (self.repo / ".dev-docs" / "knowledge" / "notes.md").read_text(encoding="utf-8"))
        self.assertIn("change-alpha", (self.repo / ".dev-docs" / "changes" / "index.md").read_text(encoding="utf-8"))

    def test_legacy_handoff_rebuild_then_canonical_drift_halts(self):
        self.initialize_and_complete_work()
        state = self.read_state()
        completion_doc = json.loads((self.change_root / "evidence" / "completion.json").read_text())
        decision_doc = json.loads((self.change_root / "evidence" / "decision.json").read_text())
        finish_plan = json.loads((self.change_root / "evidence" / "finish-plan.json").read_text())
        decision_doc["decision"]["decision_state_version"] = 12
        decision_doc["decision"]["decision_sha256"] = self_hash(decision_doc["decision"], "decision_sha256")
        finish_plan["decision_state_version"] = 12
        finish_plan["decision_sha256"] = decision_doc["decision"]["decision_sha256"]
        finish_plan["finish_plan_sha256"] = self_hash(finish_plan, "finish_plan_sha256")
        write_json(self.change_root / "evidence" / "decision.json", decision_doc)
        write_json(self.change_root / "evidence" / "finish-plan.json", finish_plan)
        state["completion"] = {"proposal_sha256": C_HASH, "mutation_map_sha256": D_HASH, "state_version": 9, "contract_sha256": A_HASH, "context_fingerprint": B_HASH, "task_heads": {"T1": "1111111", "T2": "2222222"}, "implementation_range": {"base": "abcdef1", "head": "2222222"}, "acceptance_index_sha256": completion_doc["completion"]["acceptance_index_sha256"]}
        state["decision"] = {"decision_sha256": E_HASH, "state_version": 9, "approved": False}
        self.state_path.write_text(canonical_json(state) + "\n", encoding="utf-8")
        self.assertEqual(self.run_json([sys.executable, str(STATE_HELPER), "next-action", str(self.state_path)])["next_action"]["action"], "REBUILD_FINISH_HANDOFF")
        self.run_json([sys.executable, str(STATE_HELPER), "record-finish-handoff", str(self.state_path), "--expected-version", "10", "--change-root", str(self.change_root)])
        (self.change_root / "evidence" / "decision.md").write_text("# drift\n", encoding="utf-8")
        halted = self.run_json([sys.executable, str(STATE_HELPER), "next-action", str(self.state_path)])["next_action"]
        self.assertEqual(halted["action"], "HALT")
        self.assertEqual(halted["code"], "MARKDOWN_HASH_MISMATCH")

    def test_missing_plan_stale_decision_markdown_json_and_target_failures(self):
        self.initialize_and_complete_work()
        plan_path = self.change_root / "evidence" / "finish-plan.json"
        saved_plan = plan_path.read_text(encoding="utf-8")
        plan_path.unlink()
        readiness = self.run_json([sys.executable, str(EVIDENCE_HELPER), "finish-readiness", "--change-root", str(self.change_root), "--contract-sha256", A_HASH, "--context-fingerprint", B_HASH])
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["failure_code"], "MISSING_FINISH_HANDOFF")
        plan_path.write_text(saved_plan, encoding="utf-8")

        decision_doc = json.loads((self.change_root / "evidence" / "decision.json").read_text(encoding="utf-8"))
        decision_doc["decision"]["completion_sha256"] = E_HASH
        decision_doc["decision"]["decision_sha256"] = self_hash(decision_doc["decision"], "decision_sha256")
        write_json(self.change_root / "evidence" / "decision.json", decision_doc)
        readiness = self.run_json([sys.executable, str(EVIDENCE_HELPER), "finish-readiness", "--change-root", str(self.change_root), "--contract-sha256", A_HASH, "--context-fingerprint", B_HASH])
        self.assertEqual(readiness["failure_code"], "STALE_DECISION")
        self.write_work_handoff(json.loads((self.change_root / "completion-packet.json").read_text(encoding="utf-8")))

        out = self.change_root / "bad-finish-packet.json"
        proc = subprocess.run([sys.executable, str(PACKET_HELPER), "finish", "--repo", str(self.repo), "--contract-json", str(self.contract_path), "--context-json", str(self.context_path), "--state-json", str(self.state_path), "--base", "abcdef1", "--head", "2222222", "--decision-json", str(self.change_root / "evidence" / "decision.md"), "--completion-identity-json", str(self.change_root / "evidence" / "completion.json"), "--finish-plan-json", str(self.change_root / "evidence" / "finish-plan.json"), "--output", str(out)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stderr)["code"], "INVALID_JSON_ARGUMENT")

        bad_plan = json.loads((self.change_root / "evidence" / "finish-plan.json").read_text(encoding="utf-8"))
        bad_plan["knowledge_targets"] = [{**bad_plan["knowledge_targets"][0], "path": ".dev-docs/changes/index.md"}]
        bad_plan["finish_plan_sha256"] = self_hash(bad_plan, "finish_plan_sha256")
        bad_plan_path = write_json(self.change_root / "bad-classification-plan.json", bad_plan)
        proc = subprocess.run([sys.executable, str(EVIDENCE_HELPER), "validate-finish-handoff", "--state-json", str(self.state_path), "--completion-json", str(self.change_root / "evidence" / "completion.json"), "--decision-json", str(self.change_root / "evidence" / "decision.json"), "--finish-plan-json", str(bad_plan_path), "--completion-md", str(self.change_root / "evidence" / "completion.md"), "--decision-md", str(self.change_root / "evidence" / "decision.md"), "--repo", str(self.repo)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stderr)["code"], "KNOWLEDGE_TARGET_OVERREACH")

        (self.repo / ".dev-docs" / "knowledge").mkdir(parents=True, exist_ok=True)
        (self.repo / ".dev-docs" / "knowledge" / "notes.md").write_text("drift before accept\n", encoding="utf-8")
        readiness = self.run_json([sys.executable, str(EVIDENCE_HELPER), "finish-readiness", "--change-root", str(self.change_root), "--contract-sha256", A_HASH, "--context-fingerprint", B_HASH])
        self.assertEqual(readiness["failure_code"], "STALE_TARGET")


    def test_root_level_only_handoff_is_not_recoverable_authority(self):
        self.initialize_and_complete_work()
        for name in ("completion.md", "completion.json", "decision.md", "decision.json", "finish-plan.json"):
            (self.change_root / name).write_bytes((self.change_root / "evidence" / name).read_bytes())
            (self.change_root / "evidence" / name).unlink()
        readiness = self.run_json([sys.executable, str(EVIDENCE_HELPER), "finish-readiness", "--change-root", str(self.change_root), "--contract-sha256", A_HASH, "--context-fingerprint", B_HASH])
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["failure_code"], "MISSING_FINISH_HANDOFF")
        halted = self.run_json([sys.executable, str(STATE_HELPER), "next-action", str(self.state_path)])["next_action"]
        self.assertEqual(halted["action"], "HALT")
        self.assertEqual(halted["code"], "MISSING_FINISH_HANDOFF")

    def test_journal_after_hash_mismatch_fails_closed(self):
        self.initialize_and_complete_work()
        finish_packet = self.accept_and_derive_finish_packet()
        journal_path = self.apply_targets_and_write_journal(finish_packet, wrong_after=True)
        proc = subprocess.run([sys.executable, str(EVIDENCE_HELPER), "validate-finish-apply", "--repo", str(self.repo), "--decision-sha256", finish_packet["decision_sha256"], "--finish-plan-json", str(self.change_root / "evidence" / "finish-plan.json"), "--journal-json", str(journal_path)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stderr)["code"], "STALE_TARGET")
        self.assertEqual(self.read_state()["status"], "folding")


if __name__ == "__main__":
    unittest.main()
