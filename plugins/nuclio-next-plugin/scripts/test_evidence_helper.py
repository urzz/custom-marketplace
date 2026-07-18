"""
Evidence helper tests.

## Contents

- [Fixture builders](#fixture-builders)
- [Snapshot and mutation map tests](#snapshot-and-mutation-map-tests)
- [Completion decision and finish tests](#completion-decision-and-finish-tests)
- [CLI trajectory tests](#cli-trajectory-tests)
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "plugins" / "nuclio-next-plugin" / "scripts" / "evidence-helper.py"
A_HASH = "a" * 64
B_HASH = "b" * 64
C_HASH = "c" * 64
D_HASH = "d" * 64


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
        "contract": {"acceptance": ["first acceptance", {"id": "AC-2", "text": "second acceptance"}]},
        "mutation_map_sha256": D_HASH,
        "tasks": [{"id": "T1", "status": "completed"}, {"id": "T2", "status": "completed"}],
        "history": [{"event": "INITIALIZED", "reason": json.dumps({"heads": {"T1": "1111111", "T2": "2222222"}})}],
    }


def acceptance():
    return [{"id": "A1", "accepted": True}, {"id": "AC-2", "accepted": True}]


def completed():
    return [{"task_id": "T1", "head": "1111111", "evidence_sha256": A_HASH}, {"task_id": "T2", "head": "2222222", "evidence_sha256": B_HASH}]


def decision():
    return {"Completion Verdict": {"result": "pass"}, "Remaining Risks": [], "Knowledge Proposal": [{"path": ".dev-docs/knowledge/notes.md"}], "Archive Decision": {"target": "archive"}}


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
        no_evidence = completed(); no_evidence[0].pop("evidence_sha256")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.completion_identity(state(), A_HASH, B_HASH, "abcdef1", "abcdef9", acceptance(), no_evidence)
        self.assertEqual(ctx.exception.code, "INVALID_IDENTITY")
        extra_acceptance = acceptance() + [{"id": "AX", "accepted": True}]
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.completion_identity(state(), A_HASH, B_HASH, "abcdef1", "abcdef9", extra_acceptance, completed())
        self.assertEqual(ctx.exception.code, "INCOMPLETE_ACCEPTANCE")
        stale = state(); stale["history"][0]["reason"] = json.dumps({"heads": {"T1": "1111111", "T2": "3333333"}})
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.completion_identity(stale, A_HASH, B_HASH, "abcdef1", "abcdef9", acceptance(), completed())
        self.assertEqual(ctx.exception.code, "STALE_HEAD")

    def test_decision_hash_is_stable_external_and_requires_four_sections(self):
        identity = self.helper.completion_identity(state(), A_HASH, B_HASH, "abcdef1", "abcdef9", acceptance(), completed())
        first = self.helper.decision_hash(decision(), identity)
        shuffled = {"Archive Decision": {"target": "archive"}, "Knowledge Proposal": [{"path": ".dev-docs/knowledge/notes.md"}], "Remaining Risks": [], "Completion Verdict": {"result": "pass"}}
        second = self.helper.decision_hash(shuffled, identity)
        self.assertEqual(first["decision_sha256"], second["decision_sha256"])
        self.assertNotIn("decision_sha256", json.dumps(decision()))
        bad = decision(); bad.pop("Archive Decision")
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.decision_hash(bad, identity)
        self.assertEqual(ctx.exception.code, "INVALID_DECISION")

    def test_finish_apply_journal_requires_target_binding_and_archive_outcome(self):
        plan = {"decision_sha256": C_HASH, "approval_identity": "finish-accept", "archive_intent": "archive validated change-local evidence", "knowledge_targets": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None}], "archive_targets": [{"path": ".dev-docs/archive/archive.json", "before_sha256": A_HASH}]}
        journal = {"decision_sha256": C_HASH, "approval_identity": "finish-accept", "archive_intent": "archive validated change-local evidence", "entries": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None, "after_sha256": B_HASH, "apply_result": "applied", "archive_result": "not_applicable"}, {"path": ".dev-docs/archive/archive.json", "before_sha256": A_HASH, "after_sha256": D_HASH, "apply_result": "applied", "archive_result": "archived"}]}
        valid = self.helper.validate_finish_apply(C_HASH, plan, journal)
        self.assertTrue(valid["valid"])
        over = json.loads(json.dumps(journal))
        over["entries"].append({"path": ".dev-docs/knowledge/extra.md", "before_sha256": None, "after_sha256": B_HASH, "apply_result": "applied", "archive_result": "not_applicable"})
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(C_HASH, plan, over)
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")
        product = json.loads(json.dumps(plan)); product["knowledge_targets"] = [{"path": "plugins/nuclio-next-plugin/scripts/a.py", "before_sha256": None}]
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(C_HASH, product, journal)
        self.assertEqual(ctx.exception.code, "KNOWLEDGE_TARGET_OVERREACH")
        bad_archive = json.loads(json.dumps(journal))
        bad_archive["entries"][1]["archive_result"] = "not_applicable"
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(C_HASH, plan, bad_archive)
        self.assertEqual(ctx.exception.code, "INVALID_FINISH_JOURNAL")
        bad_knowledge = json.loads(json.dumps(journal))
        bad_knowledge["entries"][0]["archive_result"] = "archived"
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(C_HASH, plan, bad_knowledge)
        self.assertEqual(ctx.exception.code, "INVALID_FINISH_JOURNAL")
        unchanged = json.loads(json.dumps(journal)); unchanged["entries"][0]["apply_result"] = "unchanged"
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(C_HASH, plan, unchanged)
        self.assertEqual(ctx.exception.code, "INVALID_FINISH_JOURNAL")
        missing = json.loads(json.dumps(journal)); missing["entries"] = missing["entries"][:1]
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(C_HASH, plan, missing)
        self.assertEqual(ctx.exception.code, "MISSING_FINISH_TARGET")
        mismatch = json.loads(json.dumps(journal)); mismatch["entries"][1]["before_sha256"] = B_HASH
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(C_HASH, plan, mismatch)
        self.assertEqual(ctx.exception.code, "STALE_TARGET")
        stale_intent = json.loads(json.dumps(journal)); stale_intent["archive_intent"] = "old intent"
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(C_HASH, plan, stale_intent)
        self.assertEqual(ctx.exception.code, "STALE_DECISION")
        stale = json.loads(json.dumps(journal)); stale["approval_identity"] = "old"
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.helper.validate_finish_apply(C_HASH, plan, stale)
        self.assertEqual(ctx.exception.code, "STALE_APPROVAL")

    def test_cli_temporary_git_trajectory_json_envelope(self):
        temp, repo, base, head = make_repo(); self.addCleanup(temp.cleanup)
        targets = json.dumps([{"path": "owned.txt", "mode": "modify"}, {"path": "new.txt", "mode": "create"}, {"path": "delete.txt", "mode": "delete"}])
        proc = subprocess.run([sys.executable, str(HELPER), "mutation-map", "--repo", str(repo), "--base", base, "--head", head, "--mutation-targets-json", targets], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mutation_map"]["result"], "ok")
        finish_plan = {"decision_sha256": C_HASH, "approval_identity": "finish-accept", "archive_intent": "archive validated change-local evidence", "knowledge_targets": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None}], "archive_targets": []}
        journal = {"decision_sha256": C_HASH, "approval_identity": "finish-accept", "archive_intent": "archive validated change-local evidence", "entries": [{"path": ".dev-docs/knowledge/notes.md", "before_sha256": None, "after_sha256": B_HASH, "apply_result": "applied", "archive_result": "not_applicable"}]}
        proc2 = subprocess.run([sys.executable, str(HELPER), "validate-finish-apply", "--decision-sha256", C_HASH, "--finish-plan-json", json.dumps(finish_plan), "--journal-json", json.dumps(journal)], text=True, capture_output=True)
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        self.assertTrue(json.loads(proc2.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
