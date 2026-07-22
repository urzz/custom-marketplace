"""
Evidence helper tests.

## Contents

- [Fixture builders](#fixture-builders)
- [Snapshot and mutation map tests](#snapshot-and-mutation-map-tests)
- [Completion decision and Finish tests](#completion-decision-and-finish-tests)
- [CLI trajectory tests](#cli-trajectory-tests)
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
except ImportError:  # pragma: no cover - optional test dependency
    jsonschema = None

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "evidence-helper.py"
A_HASH = "a" * 64
B_HASH = "b" * 64
C_HASH = "c" * 64
D_HASH = "d" * 64
E_HASH = "e" * 64


def load_helper():
    spec = importlib.util.spec_from_file_location("evidence_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return proc.stdout.strip()


def make_repo():
    temp = tempfile.TemporaryDirectory()
    repo = Path(temp.name)
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    (repo / "owned.txt").write_text("old\n", encoding="utf-8")
    (repo / "delete.txt").write_text("gone\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "owned.txt").write_text("new\n", encoding="utf-8")
    (repo / "new.txt").write_text("created\n", encoding="utf-8")
    (repo / "delete.txt").unlink()
    git(repo, "add", ".")
    git(repo, "commit", "-m", "head")
    head = git(repo, "rev-parse", "HEAD")
    return temp, repo, base, head


def make_rename_repo(commit_rename=True):
    temp = tempfile.TemporaryDirectory()
    repo = Path(temp.name)
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    (repo / "old.txt").write_text("same\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "mv", "old.txt", "new.txt")
    if commit_rename:
        git(repo, "commit", "-m", "rename")
        head = git(repo, "rev-parse", "HEAD")
    else:
        head = base
    return temp, repo, base, head


def make_copy_repo(commit_copy=True):
    temp = tempfile.TemporaryDirectory()
    repo = Path(temp.name)
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    (repo / "old.txt").write_text("same\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "copy.txt").write_text("same\n", encoding="utf-8")
    git(repo, "add", ".")
    if commit_copy:
        git(repo, "commit", "-m", "copy")
        head = git(repo, "rev-parse", "HEAD")
    else:
        head = base
    return temp, repo, base, head


def state():
    return {
        "state_version": 9,
        "contract_sha256": A_HASH,
        "context_fingerprint": B_HASH,
        "contract": {"output_language": "zh-CN", "acceptance": ["first acceptance", {"id": "AC-2", "text": "second acceptance"}]},
        "mutation_map_sha256": D_HASH,
        "tasks": [{"id": "T1", "status": "completed"}, {"id": "T2", "status": "completed"}],
        "history": [{"event": "INITIALIZED", "reason": json.dumps({"heads": {"T1": "1111111", "T2": "2222222"}})}],
    }


def acceptance():
    return [{"id": "A1", "accepted": True}, {"id": "AC-2", "accepted": True}]


def completed():
    return [{"task_id": "T1", "head": "1111111", "evidence_sha256": A_HASH}, {"task_id": "T2", "head": "2222222", "evidence_sha256": B_HASH}]


def decision():
    return {"Completion Verdict": {"result": "通过", "summary": "所有任务已完成"}, "Remaining Risks": ["无剩余风险"], "Knowledge Proposal": [{"path": ".dev-docs/knowledge/notes.md", "body": "保留已验证决策"}], "Archive Decision": {"target": "archive", "body": "归档变更证据"}}


def evidence_doc(kind, payload):
    return {
        "schema_version": 1,
        "evidence_id": f"{kind}-1",
        "kind": kind,
        "change_id": "change-1",
        "contract_sha256": A_HASH,
        "context_fingerprint": B_HASH,
        "state_version": 9,
        "created_at": "2026-07-22T00:00:00Z",
        kind: payload,
    }


def make_handoff(helper, repo):
    change_root = repo / ".dev-docs" / "changes" / "change-1"
    change_root.mkdir(parents=True, exist_ok=True)
    (change_root / "evidence").mkdir(parents=True, exist_ok=True)
    completion_md = change_root / "evidence" / "completion.md"
    decision_md = change_root / "evidence" / "decision.md"
    completion_md.write_text("# Completion\nAll tasks done.\n", encoding="utf-8")
    decision_md.write_text("# Decision\nProposal only.\n", encoding="utf-8")
    (repo / ".dev-docs" / "knowledge").mkdir(parents=True, exist_ok=True)
    existing = repo / ".dev-docs" / "knowledge" / "existing.md"
    existing.write_text("old knowledge\n", encoding="utf-8")
    existing_sha = helper.sha256_bytes(existing.read_bytes())
    completion_payload = {
        "proposal_sha256": C_HASH,
        "mutation_map_sha256": D_HASH,
        "check_summary_sha256": E_HASH,
        "task_heads": {"T1": "1111111", "T2": "2222222"},
        "task_evidence": {"T1": A_HASH, "T2": B_HASH},
        "task_evidence_sha256": helper.sha256_value({"T1": A_HASH, "T2": B_HASH}),
        "implementation_range": {"base": "abcdef1", "head": "abcdef9"},
        "acceptance_index_sha256": helper.sha256_value(acceptance()),
        "residual_risks": [],
        "markdown_sha256": helper.sha256_bytes(completion_md.read_bytes()),
    }
    completion_payload["completion_sha256"] = helper.self_hash(completion_payload, "completion_sha256")
    decision_payload = {
        "completion_sha256": completion_payload["completion_sha256"],
        "decision_state_version": 10,
        "markdown_sha256": helper.sha256_bytes(decision_md.read_bytes()),
        **decision(),
    }
    decision_payload["decision_sha256"] = helper.self_hash(decision_payload, "decision_sha256")
    finish_plan = {
        "schema_version": 1,
        "contract_sha256": A_HASH,
        "context_fingerprint": B_HASH,
        "completion_sha256": completion_payload["completion_sha256"],
        "decision_sha256": decision_payload["decision_sha256"],
        "mutation_map_sha256": D_HASH,
        "acceptance_index_sha256": helper.sha256_value(acceptance()),
        "implementation_range": {"base": "abcdef1", "head": "abcdef9"},
        "task_heads": {"T1": "1111111", "T2": "2222222"},
        "decision_state_version": 10,
        "archive_intent": "archive validated change-local evidence",
        "knowledge_proposal": decision_payload["Knowledge Proposal"],
        "knowledge_targets": [
            {"path": ".dev-docs/knowledge/notes.md", "before_sha256": None, "proposed_after_summary": "new notes", "reason": "preserve validated decision", "source_evidence": completion_payload["completion_sha256"], "target_language": "zh-CN", "language_source": "contract_output_language"},
            {"path": ".dev-docs/knowledge/existing.md", "before_sha256": existing_sha, "proposed_after_summary": "update notes", "reason": "refresh existing target", "source_evidence": completion_payload["completion_sha256"], "target_language": "zh-CN", "language_source": "existing_target"},
        ],
        "archive_targets": [
            {"path": ".dev-docs/archive/change-1.json", "before_sha256": None, "proposed_after_summary": "archive packet", "reason": "archive evidence", "source_evidence": decision_payload["decision_sha256"], "target_language": "zh-CN", "language_source": "contract_output_language"}
        ],
        "index_targets": [
            {"path": ".dev-docs/changes/index.md", "before_sha256": None, "proposed_after_summary": "change index", "reason": "index archived change", "source_evidence": decision_payload["decision_sha256"], "target_language": "zh-CN", "language_source": "contract_output_language"}
        ],
    }
    finish_plan["finish_plan_sha256"] = helper.self_hash(finish_plan, "finish_plan_sha256")
    completion_doc = evidence_doc("completion", completion_payload)
    decision_doc = evidence_doc("decision", decision_payload)
    (change_root / "state.json").write_text(json.dumps(state()), encoding="utf-8")
    (change_root / "evidence" / "completion.json").write_text(json.dumps(completion_doc), encoding="utf-8")
    (change_root / "evidence" / "decision.json").write_text(json.dumps(decision_doc), encoding="utf-8")
    (change_root / "evidence" / "finish-plan.json").write_text(json.dumps(finish_plan), encoding="utf-8")
    return change_root, completion_doc, decision_doc, finish_plan, completion_md, decision_md


class EvidenceHelperTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()

    def test_snapshot_covers_present_absent_and_deleted_file_states(self):
        temp, repo, _base, _head = make_repo(); self.addCleanup(temp.cleanup)
        snap = self.helper.snapshot(repo, ["owned.txt", "missing.txt", "already-deleted.txt"], ["already-deleted.txt"])
        states = {entry["path"]: entry["state"] for entry in snap["snapshots"]}
        self.assertEqual(states["owned.txt"], "present")
        self.assertEqual(states["missing.txt"], "absent")
        self.assertEqual(states["already-deleted.txt"], "deleted")
        self.assertRegex(snap["snapshot_sha256"], r"^[0-9a-f]{64}$")

    def test_fingerprint_binds_contract_context_state_task_head_and_detects_drift(self):
        fp = self.helper.fingerprint(A_HASH, B_HASH, 5, "abcdef1", [{"path": "x", "state": "absent"}])
        expected = fp["identity"].copy()
        again = self.helper.fingerprint(A_HASH, B_HASH, 5, "abcdef1", [{"path": "x", "state": "absent"}], expected)
        self.assertEqual(again["identity"]["fingerprint"], expected["fingerprint"])
        expected["task_head"] = "stale"
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.fingerprint(A_HASH, B_HASH, 5, "abcdef1", [{"path": "x", "state": "absent"}], expected)
        self.assertEqual(ctx.exception.code, "STALE_FINGERPRINT")

    def test_mutation_map_allows_subset_and_blocks_overreach_and_dirty_paths(self):
        temp, repo, base, head = make_repo(); self.addCleanup(temp.cleanup)
        targets = [{"path": "owned.txt", "mode": "modify"}, {"path": "new.txt", "mode": "create"}, {"path": "delete.txt", "mode": "delete"}]
        mutation = self.helper.mutation_map(repo, base, head, targets)
        self.assertEqual(mutation["mutation_map"]["result"], "ok")
        self.assertEqual(sorted(mutation["mutation_map"]["changed_paths"]), ["delete.txt", "new.txt", "owned.txt"])
        over = self.helper.mutation_map(repo, base, head, [{"path": "owned.txt", "mode": "modify"}])
        self.assertEqual(over["mutation_map"]["result"], "blocked")
        self.assertTrue(any(blocker["id"] == "MUTATION_OVERREACH" for blocker in over["mutation_map"]["blockers"]))
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        dirty = self.helper.mutation_map(repo, base, head, targets)
        self.assertIn("dirty.txt", dirty["mutation_map"]["changed_paths"])
        self.assertEqual(dirty["mutation_map"]["result"], "blocked")

    def test_mutation_map_represents_committed_rename_source_delete_and_destination_create(self):
        temp, repo, base, head = make_rename_repo(commit_rename=True); self.addCleanup(temp.cleanup)
        mutation = self.helper.mutation_map(repo, base, head, [{"path": "old.txt", "mode": "delete"}, {"path": "new.txt", "mode": "create"}])
        entries = {entry["path"]: entry for entry in mutation["mutation_map"]["entries"]}
        self.assertEqual(mutation["mutation_map"]["result"], "ok")
        self.assertEqual(entries["old.txt"]["mode"], "delete")
        self.assertEqual(entries["new.txt"]["mode"], "create")
        destination_only = self.helper.mutation_map(repo, base, head, [{"path": "new.txt", "mode": "modify"}])
        self.assertEqual(destination_only["mutation_map"]["result"], "blocked")
        self.assertIn("old.txt", [blocker["path"] for blocker in destination_only["mutation_map"]["blockers"]])

    def test_mutation_map_represents_dirty_rename_source_delete_and_destination_create(self):
        temp, repo, base, head = make_rename_repo(commit_rename=False); self.addCleanup(temp.cleanup)
        mutation = self.helper.mutation_map(repo, base, head, [{"path": "old.txt", "mode": "delete"}, {"path": "new.txt", "mode": "create"}])
        entries = {entry["path"]: entry for entry in mutation["mutation_map"]["entries"]}
        self.assertEqual(mutation["mutation_map"]["result"], "ok")
        self.assertTrue(entries["old.txt"]["dirty"])
        self.assertEqual(entries["old.txt"]["mode"], "delete")
        self.assertEqual(entries["new.txt"]["mode"], "create")
        destination_only = self.helper.mutation_map(repo, base, head, [{"path": "new.txt", "mode": "modify"}])
        self.assertEqual(destination_only["mutation_map"]["result"], "blocked")
        self.assertIn("old.txt", [blocker["path"] for blocker in destination_only["mutation_map"]["blockers"]])

    def test_mutation_map_represents_committed_and_dirty_copy_as_source_delete_destination_create(self):
        temp, repo, base, head = make_copy_repo(commit_copy=True); self.addCleanup(temp.cleanup)
        committed = self.helper.mutation_map(repo, base, head, [{"path": "old.txt", "mode": "delete"}, {"path": "copy.txt", "mode": "create"}])
        entries = {entry["path"]: entry for entry in committed["mutation_map"]["entries"]}
        self.assertEqual(committed["mutation_map"]["result"], "ok")
        self.assertEqual(entries["old.txt"]["mode"], "delete")
        self.assertEqual(entries["copy.txt"]["mode"], "create")
        temp2, repo2, base2, head2 = make_copy_repo(commit_copy=False); self.addCleanup(temp2.cleanup)
        dirty = self.helper.mutation_map(repo2, base2, head2, [{"path": "old.txt", "mode": "delete"}, {"path": "copy.txt", "mode": "create"}])
        dirty_entries = {entry["path"]: entry for entry in dirty["mutation_map"]["entries"]}
        self.assertEqual(dirty["mutation_map"]["result"], "ok")
        self.assertEqual(dirty_entries["copy.txt"]["mode"], "create")

    def test_validate_task_evidence_rejects_reviewer_overreach_bypass(self):
        temp, repo, base, head = make_repo(); self.addCleanup(temp.cleanup)
        blocked = self.helper.mutation_map(repo, base, head, [{"path": "owned.txt", "mode": "modify"}])
        evidence = {"task_id": "T1", "changed_paths": blocked["mutation_map"]["changed_paths"], "mutation_map_sha256": blocked["mutation_map"]["sha256"], "reviewer_verdict": "PASS"}
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_task_evidence(evidence, blocked)
        self.assertEqual(ctx.exception.code, "MUTATION_OVERREACH")

    def test_completion_identity_requires_all_tasks_and_full_acceptance(self):
        identity = self.helper.completion_identity(state(), A_HASH, B_HASH, "abcdef1", "abcdef9", acceptance(), completed())
        self.assertRegex(identity["completion_identity"]["completion_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(identity["completion_identity"]["task_evidence"], {"T1": A_HASH, "T2": B_HASH})
        self.assertEqual(identity["completion_identity"]["mutation_map_sha256"], D_HASH)
        bad_acceptance = acceptance(); bad_acceptance[0]["accepted"] = False
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.completion_identity(state(), A_HASH, B_HASH, "abcdef1", "abcdef9", bad_acceptance, completed())
        self.assertEqual(ctx.exception.code, "INCOMPLETE_ACCEPTANCE")
        incomplete = completed()[:1]
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.completion_identity(state(), A_HASH, B_HASH, "abcdef1", "abcdef9", acceptance(), incomplete)
        self.assertEqual(ctx.exception.code, "TASKS_INCOMPLETE")

    def test_decision_hash_is_stable_external_and_requires_four_sections(self):
        identity = self.helper.completion_identity(state(), A_HASH, B_HASH, "abcdef1", "abcdef9", acceptance(), completed())
        md_hash = self.helper.sha256_bytes(b"decision markdown")
        first = self.helper.decision_hash(decision(), identity, 10, md_hash)
        shuffled = {"Archive Decision": {"target": "archive", "body": "归档变更证据"}, "Knowledge Proposal": [{"path": ".dev-docs/knowledge/notes.md", "body": "保留已验证决策"}], "Remaining Risks": ["无剩余风险"], "Completion Verdict": {"result": "通过", "summary": "所有任务已完成"}}
        second = self.helper.decision_hash(shuffled, identity, 10, md_hash)
        self.assertEqual(first["decision_sha256"], second["decision_sha256"])
        self.assertNotIn("decision_sha256", json.dumps(decision()))
        bad = decision(); bad.pop("Archive Decision")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.decision_hash(bad, identity, 10, md_hash)
        self.assertEqual(ctx.exception.code, "INVALID_DECISION")

    def test_finish_handoff_validates_five_files_and_schema_contract(self):
        temp, repo, _base, _head = make_repo(); self.addCleanup(temp.cleanup)
        _change_root, completion_doc, decision_doc, plan, completion_md, decision_md = make_handoff(self.helper, repo)
        result = self.helper.validate_finish_handoff(state(), completion_doc, decision_doc, plan, {"completion_md": completion_md, "decision_md": decision_md, "repo": repo})
        self.assertTrue(result["valid"])
        self.assertEqual(result["decision_sha256"], decision_doc["decision"]["decision_sha256"])
        bad_plan = json.loads(json.dumps(plan)); bad_plan["extra"] = True
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_plan(bad_plan, "zh-CN")
        self.assertEqual(ctx.exception.code, "INVALID_FINISH_PLAN")
        missing = json.loads(json.dumps(plan)); missing.pop("archive_intent")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_plan(missing, "zh-CN")
        self.assertEqual(ctx.exception.code, "INVALID_FINISH_PLAN")

    def test_finish_readiness_fresh_missing_and_stale_decision(self):
        temp, repo, _base, _head = make_repo(); self.addCleanup(temp.cleanup)
        change_root, _completion_doc, _decision_doc, _plan, _completion_md, _decision_md = make_handoff(self.helper, repo)
        ready = self.helper.finish_readiness(change_root, A_HASH, B_HASH)
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["current_action"], "request_finish_acceptance")
        for key in ("ready", "current_action", "artifacts", "identity_comparison", "failure_code", "repair_hint", "decision_sha256", "finish_plan_sha256", "decision_state_version"):
            self.assertIn(key, ready)
        (change_root / "evidence" / "finish-plan.json").unlink()
        missing = self.helper.finish_readiness(change_root, A_HASH, B_HASH)
        self.assertFalse(missing["ready"])
        self.assertEqual(missing["failure_code"], "MISSING_FINISH_HANDOFF")
        _change_root, _completion_doc, decision_doc, _plan, _completion_md, _decision_md = make_handoff(self.helper, repo)
        decision_doc["decision"]["completion_sha256"] = C_HASH
        (change_root / "evidence" / "decision.json").write_text(json.dumps(decision_doc), encoding="utf-8")
        stale = self.helper.finish_readiness(change_root, A_HASH, B_HASH)
        self.assertFalse(stale["ready"])
        self.assertEqual(stale["failure_code"], "STALE_DECISION")


    def test_finish_readiness_ignores_root_level_only_handoff(self):
        temp, repo, _base, _head = make_repo(); self.addCleanup(temp.cleanup)
        change_root, _completion_doc, _decision_doc, _plan, _completion_md, _decision_md = make_handoff(self.helper, repo)
        for name in ("completion.md", "completion.json", "decision.md", "decision.json", "finish-plan.json"):
            (change_root / name).write_bytes((change_root / "evidence" / name).read_bytes())
            (change_root / "evidence" / name).unlink()
        readiness = self.helper.finish_readiness(change_root, A_HASH, B_HASH)
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["failure_code"], "MISSING_FINISH_HANDOFF")
        for artifact_name in ("completion_md", "completion_json", "decision_md", "decision_json", "finish_plan_json"):
            self.assertFalse(readiness["artifacts"][artifact_name]["exists"])
            self.assertIn("/evidence/", readiness["artifacts"][artifact_name].get("path", "") if "path" in readiness["artifacts"][artifact_name] else str(change_root / "evidence"))

    def test_markdown_json_mismatch_self_hash_and_invalid_markdown_as_json(self):
        temp, repo, _base, _head = make_repo(); self.addCleanup(temp.cleanup)
        _change_root, completion_doc, decision_doc, plan, completion_md, decision_md = make_handoff(self.helper, repo)
        self.assertEqual(completion_doc["completion"]["completion_sha256"], self.helper.self_hash(completion_doc["completion"], "completion_sha256"))
        self.assertNotEqual(completion_doc["completion"]["completion_sha256"], self.helper.sha256_value(completion_doc["completion"]))
        completion_md.write_text("# Drift\n", encoding="utf-8")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_handoff(state(), completion_doc, decision_doc, plan, {"completion_md": completion_md, "decision_md": decision_md, "repo": repo})
        self.assertEqual(ctx.exception.code, "MARKDOWN_HASH_MISMATCH")
        proc = subprocess.run([sys.executable, str(HELPER), "validate-finish-handoff", "--state-json", json.dumps(state()), "--completion-json", str(completion_md), "--decision-json", json.dumps(decision_doc), "--finish-plan-json", json.dumps(plan), "--completion-md", str(completion_md), "--decision-md", str(decision_md)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("INVALID_JSON_FILE", proc.stderr)

    def test_target_groups_are_mutually_exclusive_and_index_path_is_index_only(self):
        temp, repo, _base, _head = make_repo(); self.addCleanup(temp.cleanup)
        _change_root, _completion_doc, _decision_doc, plan, _completion_md, _decision_md = make_handoff(self.helper, repo)
        duplicate = json.loads(json.dumps(plan))
        duplicate["archive_targets"].append({**duplicate["knowledge_targets"][0], "path": ".dev-docs/archive/change-1.json"})
        duplicate["archive_targets"][1]["path"] = duplicate["knowledge_targets"][0]["path"]
        duplicate["finish_plan_sha256"] = self.helper.self_hash(duplicate, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_plan(duplicate, "zh-CN")
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")
        wrong_index = json.loads(json.dumps(plan))
        wrong_index["knowledge_targets"].append({**wrong_index["index_targets"][0]})
        wrong_index["finish_plan_sha256"] = self.helper.self_hash(wrong_index, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_plan(wrong_index, "zh-CN")
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")
        product = json.loads(json.dumps(plan))
        product["knowledge_targets"][0]["path"] = "plugins/nuclio-plugin/scripts/a.py"
        product["finish_plan_sha256"] = self.helper.self_hash(product, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_plan(product, "zh-CN")
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")
        change_evidence = json.loads(json.dumps(plan))
        change_evidence["archive_targets"][0]["path"] = ".dev-docs/changes/change-1/completion.md"
        change_evidence["finish_plan_sha256"] = self.helper.self_hash(change_evidence, "finish_plan_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_plan(change_evidence, "zh-CN")
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")

    def test_finish_handoff_rejects_before_drift(self):
        temp, repo, _base, _head = make_repo(); self.addCleanup(temp.cleanup)
        _change_root, completion_doc, decision_doc, plan, completion_md, decision_md = make_handoff(self.helper, repo)
        (repo / ".dev-docs" / "knowledge" / "existing.md").write_text("changed\n", encoding="utf-8")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_handoff(state(), completion_doc, decision_doc, plan, {"completion_md": completion_md, "decision_md": decision_md, "repo": repo})
        self.assertEqual(ctx.exception.code, "STALE_TARGET")

    def test_finish_apply_reads_actual_repo_bytes_and_rejects_after_mismatch(self):
        temp, repo, _base, _head = make_repo(); self.addCleanup(temp.cleanup)
        _change_root, _completion_doc, decision_doc, plan, _completion_md, _decision_md = make_handoff(self.helper, repo)
        for target in plan["knowledge_targets"] + plan["archive_targets"] + plan["index_targets"]:
            path = repo / target["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"after {target['path']}\n", encoding="utf-8")
        entries = []
        for target in plan["knowledge_targets"] + plan["archive_targets"] + plan["index_targets"]:
            entries.append({"path": target["path"], "before_sha256": target["before_sha256"], "after_sha256": self.helper.sha256_bytes((repo / target["path"]).read_bytes()), "reason": target["reason"], "target_language": target["target_language"], "language_source": target["language_source"], "apply_result": "applied", "archive_result": "archived" if target["path"].startswith(".dev-docs/archive/") else "not_applicable"})
        journal = {"decision_sha256": decision_doc["decision"]["decision_sha256"], "finish_plan_sha256": plan["finish_plan_sha256"], "approval_identity": "accept:2026-07-22", "archive_intent": plan["archive_intent"], "entries": entries, "verified": True}
        journal["journal_sha256"] = self.helper.self_hash(journal, "journal_sha256")
        valid = self.helper.validate_finish_apply(decision_doc["decision"]["decision_sha256"], plan, journal, repo)
        self.assertTrue(valid["verified"])
        self.assertIn(".dev-docs/changes/index.md", valid["covered_paths"])
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(decision_doc["decision"]["decision_sha256"], plan, journal)
        self.assertEqual(ctx.exception.code, "REPO_AUTHORITY_REQUIRED")
        proc = subprocess.run([sys.executable, str(HELPER), "validate-finish-apply", "--decision-sha256", decision_doc["decision"]["decision_sha256"], "--finish-plan-json", json.dumps(plan), "--journal-json", json.dumps(journal)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn('"ok":true', proc.stdout)
        (repo / entries[0]["path"]).write_text("drift\n", encoding="utf-8")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(decision_doc["decision"]["decision_sha256"], plan, journal, repo)
        self.assertEqual(ctx.exception.code, "STALE_TARGET")

    def test_evidence_schema_enforces_all_seven_kind_exclusivity_and_task_id_contract(self):
        if jsonschema is None:
            self.skipTest("jsonschema not installed")
        temp, repo, _base, _head = make_repo(); self.addCleanup(temp.cleanup)
        _change_root, completion_doc, decision_doc, plan, _completion_md, _decision_md = make_handoff(self.helper, repo)
        for target in plan["knowledge_targets"] + plan["archive_targets"] + plan["index_targets"]:
            path = repo / target["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"after {target['path']}\n", encoding="utf-8")
        entries = []
        for target in plan["knowledge_targets"] + plan["archive_targets"] + plan["index_targets"]:
            entries.append({"path": target["path"], "before_sha256": target["before_sha256"], "after_sha256": self.helper.sha256_bytes((repo / target["path"]).read_bytes()), "reason": target["reason"], "target_language": target["target_language"], "language_source": target["language_source"], "apply_result": "applied", "archive_result": "archived" if target["path"].startswith(".dev-docs/archive/") else "not_applicable"})
        journal_payload = {"decision_sha256": decision_doc["decision"]["decision_sha256"], "finish_plan_sha256": plan["finish_plan_sha256"], "approval_identity": "accept:2026-07-22", "archive_intent": plan["archive_intent"], "entries": entries, "verified": True}
        journal_payload["journal_sha256"] = self.helper.self_hash(journal_payload, "journal_sha256")
        check = {"command": ["python3", "-m", "unittest"], "exit_code": 0, "output_sha256": C_HASH}
        payloads = {
            "implementation": {
                "base_head": "abcdef1",
                "new_head": "abcdef9",
                "changed_paths": ["plugins/nuclio-plugin/scripts/evidence-helper.py"],
                "ownership_sha256": D_HASH,
                "checks": [check],
            },
            "validation": {"checks": [check], "result": "success"},
            "review": {"review_package_sha256": E_HASH, "findings": [{"id": "R1", "severity": "blocking", "summary": "review finding"}]},
            "mutation_map": {
                "entries": [
                    {
                        "path": "plugins/nuclio-plugin/schemas/evidence.schema.json",
                        "mode": "modify",
                        "before": {"path": "plugins/nuclio-plugin/schemas/evidence.schema.json", "sha256": A_HASH},
                        "after": {"path": "plugins/nuclio-plugin/schemas/evidence.schema.json", "sha256": B_HASH},
                    }
                ],
                "sha256": D_HASH,
            },
            "completion": completion_doc["completion"],
            "decision": decision_doc["decision"],
            "finish_apply_journal": journal_payload,
        }
        kind_to_payload = {
            "task_implementation": "implementation",
            "task_validation": "validation",
            "task_review": "review",
            "mutation_map": "mutation_map",
            "completion": "completion",
            "decision": "decision",
            "finish_apply_journal": "finish_apply_journal",
        }
        task_kinds = {"task_implementation", "task_validation", "task_review"}
        finish_kinds = {"completion", "decision", "finish_apply_journal"}
        base_doc = {
            "schema_version": 1,
            "evidence_id": "schema-kind-1",
            "change_id": "change-1",
            "contract_sha256": A_HASH,
            "context_fingerprint": B_HASH,
            "state_version": 9,
            "created_at": "2026-07-22T00:00:00Z",
        }
        schema = json.loads((ROOT / "plugins" / "nuclio-plugin" / "schemas" / "evidence.schema.json").read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)

        def fixture(kind):
            payload_name = kind_to_payload[kind]
            doc = {**base_doc, "evidence_id": f"{kind}-1", "kind": kind, payload_name: payloads[payload_name]}
            if kind in task_kinds:
                doc["task_id"] = "T1"
            return doc

        for kind in kind_to_payload:
            with self.subTest(kind=kind, case="legal_fixture_pass"):
                validator.validate(fixture(kind))
            missing_payload = fixture(kind)
            missing_payload.pop(kind_to_payload[kind])
            with self.subTest(kind=kind, case="missing_payload_fail"):
                with self.assertRaises(jsonschema.ValidationError):
                    validator.validate(missing_payload)
            if kind in task_kinds:
                missing_task_id = fixture(kind)
                missing_task_id.pop("task_id")
                with self.subTest(kind=kind, case="task_kind_missing_task_id_fail"):
                    with self.assertRaises(jsonschema.ValidationError):
                        validator.validate(missing_task_id)
            else:
                illegal_task_id = fixture(kind)
                illegal_task_id["task_id"] = "T1"
                with self.subTest(kind=kind, case="non_task_kind_task_id_fail"):
                    with self.assertRaises(jsonschema.ValidationError):
                        validator.validate(illegal_task_id)
            if kind in finish_kinds:
                finish_task_id = fixture(kind)
                finish_task_id["task_id"] = "T1"
                with self.subTest(kind=kind, case="finish_sidecar_task_id_fail"):
                    with self.assertRaises(jsonschema.ValidationError):
                        validator.validate(finish_task_id)
            for other_kind, other_payload_name in kind_to_payload.items():
                if other_kind == kind:
                    continue
                mixed = fixture(kind)
                mixed[other_payload_name] = payloads[other_payload_name]
                with self.subTest(kind=kind, other_payload=other_payload_name, case="cross_kind_payload_fail"):
                    with self.assertRaises(jsonschema.ValidationError):
                        validator.validate(mixed)

        for forbidden in ("implementation", "validation", "review", "mutation_map"):
            explicit = fixture("completion")
            explicit[forbidden] = payloads[forbidden]
            with self.subTest(kind="completion", explicit_forbidden=forbidden):
                with self.assertRaises(jsonschema.ValidationError):
                    validator.validate(explicit)
        explicit_task_id = fixture("completion")
        explicit_task_id["task_id"] = "T1"
        with self.subTest(kind="completion", explicit_forbidden="task_id"):
            with self.assertRaises(jsonschema.ValidationError):
                validator.validate(explicit_task_id)

    def test_cli_temporary_git_trajectory_json_envelope(self):
        temp, repo, base, head = make_repo(); self.addCleanup(temp.cleanup)
        targets = json.dumps([{"path": "owned.txt", "mode": "modify"}, {"path": "new.txt", "mode": "create"}, {"path": "delete.txt", "mode": "delete"}])
        proc = subprocess.run([sys.executable, str(HELPER), "mutation-map", "--repo", str(repo), "--base", base, "--head", head, "--mutation-targets-json", targets], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mutation_map"]["result"], "ok")
        change_root, _completion_doc, _decision_doc, _plan, _completion_md, _decision_md = make_handoff(self.helper, repo)
        proc2 = subprocess.run([sys.executable, str(HELPER), "finish-readiness", "--change-root", str(change_root), "--contract-sha256", A_HASH, "--context-fingerprint", B_HASH], text=True, capture_output=True)
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        self.assertTrue(json.loads(proc2.stdout)["ready"])


if __name__ == "__main__":
    unittest.main()
