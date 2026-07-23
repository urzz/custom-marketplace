#!/usr/bin/env python3
"""Deterministic integration tests for the skill-forge review state helper."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml


SCRIPTS_DIR = Path(__file__).resolve().parent
HELPER = SCRIPTS_DIR / "review-state-helper.py"
PLAN_QUERY = SCRIPTS_DIR / "plan-task-query.py"


class ReviewStateHelperTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        job_dir = os.environ.get("CLAUDE_JOB_DIR")
        temp_root = Path(job_dir) / "tmp" if job_dir else None
        if temp_root is not None:
            temp_root.mkdir(parents=True, exist_ok=True)
        self.temporary_directory = tempfile.TemporaryDirectory(dir=temp_root)
        self.repo = Path(self.temporary_directory.name)
        self.state = self.repo / "review-state.json"
        self.spec = self.repo / "spec.md"
        self.plan = self.repo / "plan.yaml"
        self.rubric_source = self.repo / "rubric-source.md"
        self.rubric_snapshot = self.repo / "rubric-snapshot.md"
        self.report = self.repo / "task-report.md"
        self.observation = self.repo / "observation.json"
        self.init_git_repo()
        self.spec.write_text("# Frozen spec\n", encoding="utf-8")
        self.rubric_source.write_text("# Frozen rubric\n", encoding="utf-8")
        self.write_plan(
            [
                {
                    "id": 1,
                    "name": "Task One",
                    "files": {
                        "create": ["owned/one.txt"],
                        "modify": ["owned/shared.txt"],
                        "delete": [],
                    },
                    "interfaces": {"consumes": "input", "produces": "output"},
                    "steps": ["Implement one"],
                    "acceptance_criteria": ["One works"],
                    "meta": {"model": "sonnet", "file_type": "script", "requires_execution_check": True},
                },
                {
                    "id": 2,
                    "name": "Task Two",
                    "files": {
                        "create": ["owned/two.txt"],
                        "modify": [],
                        "delete": [],
                    },
                    "interfaces": {"consumes": "input", "produces": "output"},
                    "steps": ["Implement two"],
                    "acceptance_criteria": ["Two works"],
                    "meta": {"model": "haiku", "file_type": "script", "requires_execution_check": False},
                },
            ]
        )
        self.initial_base = self.commit_file("owned/shared.txt", "base\n", "initial")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_helper(self, *args):
        return subprocess.run(
            [sys.executable, str(HELPER), *map(str, args)],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )

    def init_git_repo(self):
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test User"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.com"], check=True)

    def commit_file(self, path, content, message):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", path], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m", message], check=True)
        return subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def write_plan(self, tasks):
        payload = {
            "goal": "Deterministic review state",
            "architecture": "Controller and bounded agents",
            "global_constraints": ["Do not exceed ownership", "Use one shared budget"],
            "tasks": tasks,
        }
        self.plan.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def write_observation(self, payload):
        self.observation.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.observation

    def read_state(self):
        return json.loads(self.state.read_text(encoding="utf-8"))

    def json_stdout(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        return payload

    def json_error(self, result, code):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        payload = json.loads(result.stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], code)
        return payload

    def init_state(self):
        result = self.run_helper(
            "init",
            "--state", self.state,
            "--repo-root", self.repo,
            "--spec", self.spec,
            "--plan", self.plan,
            "--rubric-source", self.rubric_source,
            "--rubric-snapshot", self.rubric_snapshot,
            "--scope", "skill-forge",
            "--ticket", "none",
            "--initial-base", self.initial_base,
        )
        return self.json_stdout(result)

    def start_task(self, task_id=1, expected_head=None):
        return self.run_helper(
            "start-task", "--state", self.state, "--task-id", str(task_id),
            "--expected-head", expected_head or self.head(),
        )

    def head(self):
        return subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def implement_task(self, path="owned/one.txt", content="implementation\n"):
        self.json_stdout(self.start_task())
        base = self.head()
        new_head = self.commit_file(path, content, "feat(skill-forge): [Task 1] Task One")
        self.report.write_text("DONE\n", encoding="utf-8")
        result = self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", new_head, "--report", self.report,
        )
        self.json_stdout(result)
        return base, new_head

    def make_finding(
        self,
        finding_id="F-1",
        *,
        owner_task_id=1,
        gate="TASK_REVIEW",
        attempt=1,
        origin="NEW",
        severity="IMPORTANT",
        blocking=True,
        status="OPEN",
        path="owned/one.txt",
        required_fix_paths=None,
        rule_id="RULE-1",
        contract_ref="Task 1 acceptance",
        rubric_ref=None,
        failure_key="wrong-output",
        closure_actual=None,
    ):
        finding = {
            "id": finding_id,
            "owner_task_id": owner_task_id,
            "source_gate": gate,
            "attempt": attempt,
            "rule_id": rule_id,
            "failure_key": failure_key,
            "severity": severity,
            "blocking": blocking,
            "origin": origin,
            "status": status,
            "summary": "Observed deterministic failure",
            "path": path,
            "required_fix_paths": required_fix_paths if required_fix_paths is not None else [path],
            "base_evidence": {"command": "check-base", "exit_code": 1, "output": "base output"},
            "head_evidence": {"command": "check-head", "exit_code": 1, "output": "head output"},
            "closure_test": {
                "expected": {"command": "python3 check.py", "exit_code": 0, "output": "pass"},
                "actual": closure_actual,
            },
            "observations": [{"risk": "state mismatch", "check": "focused check"}],
            "resolution": None,
        }
        if rubric_ref is not None:
            finding["rubric_ref"] = rubric_ref
        else:
            finding["contract_ref"] = contract_ref
        return finding

    def make_observation(
        self,
        *,
        gate="TASK_REVIEW",
        verdict="FAIL",
        task_id=1,
        attempt=None,
        base_sha=None,
        head_sha=None,
        findings=None,
        cannot_verify=None,
        controller_resolutions=None,
    ):
        state = self.read_state()
        task = state["tasks"][str(task_id)]
        if attempt is None:
            if gate == "TASK_REVIEW":
                attempt = task["review_attempt"]
            elif state["workflow"]["status"] == "REVIEWING":
                owner = state["workflow"]["current_task_id"]
                attempt = state["tasks"][str(owner)]["review_attempt"]
            else:
                attempt = state["artifacts"]["gate_attempts"][gate]
        if gate != "TASK_REVIEW" and findings is not None:
            findings = [{**finding, "attempt": attempt} for finding in findings]
        if base_sha is None:
            base_sha = task["task_base"] if gate == "TASK_REVIEW" else state["workflow"]["initial_base"]
        if head_sha is None:
            head_sha = task["task_head"] if gate == "TASK_REVIEW" else state["workflow"]["current_head"]
        return {
            "schema_version": 1,
            "gate": gate,
            "verdict": verdict,
            "task_id": task_id if gate == "TASK_REVIEW" else None,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "rubric_sha256": state["workflow"]["rubric_sha256"],
            "attempt": attempt,
            "findings": findings or [],
            "cannot_verify": cannot_verify or [],
            "controller_resolutions": controller_resolutions or [],
        }

    def import_observation(self, payload):
        self.write_observation(payload)
        return self.run_helper("import-review", "--state", self.state, "--observation", self.observation)

    def pass_task_one(self):
        self.implement_task()
        result = self.import_observation(self.make_observation(verdict="PASS"))
        self.json_stdout(result)

    def reach_final_review(self):
        self.pass_task_one()
        self.json_stdout(self.start_task(task_id=2))
        base = self.head()
        task_two_head = self.commit_file("owned/two.txt", "two\n", "feat(skill-forge): [Task 2] Task Two")
        self.report.write_text("DONE\n", encoding="utf-8")
        self.json_stdout(self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "2",
            "--base-head", base, "--new-head", task_two_head, "--report", self.report,
        ))
        self.json_stdout(self.import_observation(self.make_observation(verdict="PASS", task_id=2)))

    def reset_to_initial_base(self):
        self.state.unlink(missing_ok=True)
        self.rubric_snapshot.unlink(missing_ok=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "reset", "--hard", "-q", self.initial_base],
            check=True,
        )

    def authorize_current(self, finding_ids):
        return self.run_helper(
            "authorize-fix", "--state", self.state, "--task-id", "1",
            "--finding-ids-json", json.dumps(finding_ids),
        )

    def record_fixed_commit(self, finding_ids, path="owned/one.txt", attempt=None, subject=None):
        state = self.read_state()
        task = state["tasks"]["1"]
        attempt = attempt or task["fix_attempt"]
        subject = subject or f"fix(skill-forge): [Task 1 Fix {attempt}] address authorized findings"
        base = self.head()
        new_head = self.commit_file(path, f"fix {attempt}\n", subject)
        report = self.repo / f"fix-{attempt}.json"
        report.write_text(
            json.dumps(
                {
                    "status": "FIXED",
                    "attempt": attempt,
                    "base_head_sha": base,
                    "new_head_sha": new_head,
                    "findings": [
                        {
                            "id": finding_id,
                            "action": "Applied bounded fix",
                            "changed_paths": [path],
                            "closure_test": {"command": "python3 check.py", "exit_code": 0, "output": "pass"},
                        }
                        for finding_id in finding_ids
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = self.run_helper(
            "record-fix", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", new_head, "--report", report,
        )
        self.json_stdout(result)
        return base, new_head

    def test_init_freezes_spec_plan_and_rubric_and_derives_task_ownership(self):
        self.init_state()
        state = self.read_state()
        self.assertEqual(
            set(state), {"schema_version", "workflow", "artifacts", "tasks", "findings", "history"}
        )
        self.assertEqual(state["schema_version"], 1)
        self.assertIsNone(state["workflow"]["ticket"])
        self.assertEqual(state["workflow"]["initial_base"], self.initial_base)
        self.assertRegex(state["workflow"]["spec_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(state["workflow"]["plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            state["workflow"]["rubric_sha256"],
            hashlib.sha256(self.rubric_source.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.rubric_snapshot.read_bytes(), self.rubric_source.read_bytes())
        self.assertEqual(
            state["tasks"]["1"]["ownership"],
            {"create": ["owned/one.txt"], "modify": ["owned/shared.txt"], "delete": []},
        )
        self.assertEqual(state["tasks"]["1"]["fix_budget"], {"maximum": 2, "used": 0, "remaining": 2})
        workflow_keys = {
            "scope", "ticket", "repo_root", "initial_base", "current_head",
            "spec_path", "spec_sha256", "plan_path", "plan_sha256",
            "rubric_snapshot_path", "rubric_sha256", "status", "current_gate",
            "current_task_id",
        }
        task_keys = {
            "status", "task_base", "task_head", "ownership", "risk_level", "review_policy",
            "expected_subject", "fix_budget", "review_attempt", "fix_attempt", "open_blocking_findings",
            "resolved_findings", "baseline_findings", "authorized_finding_ids",
            "previous_open_blocker_fingerprints", "cannot_verify", "deterministic_evidence",
        }
        history_keys = {
            "event", "from", "to", "task_id", "gate", "attempt",
            "base_sha", "head_sha", "finding_ids",
        }
        self.assertEqual(set(state["workflow"]), workflow_keys)
        self.assertEqual(set(state["tasks"]["1"]), task_keys)
        self.assertEqual(state["artifacts"]["run_risk_level"], "L3")
        self.assertEqual(state["tasks"]["1"]["risk_level"], "L3")
        self.assertEqual(state["tasks"]["1"]["review_policy"], "task-and-final")
        self.assertEqual(state["tasks"]["1"]["expected_subject"], "feat(skill-forge): [Task 1] Task One")
        self.assertEqual(state["artifacts"]["controller_resolutions"], [])
        self.assertEqual(set(state["history"][0]), history_keys)
        self.assertEqual(state["history"][0]["event"], "INITIALIZED")

    def test_init_rejects_non_exact_or_duplicate_task_paths(self):
        bad_paths = ["/absolute.txt", "../escape.txt", "owned/*.txt", "owned/one.txt (new)"]
        for index, bad_path in enumerate(bad_paths):
            with self.subTest(path=bad_path):
                self.rubric_snapshot.unlink(missing_ok=True)
                self.state.unlink(missing_ok=True)
                self.write_plan([{"id": 1, "name": "Bad", "files": {"create": [bad_path], "modify": [], "delete": []}}])
                self.json_error(self.run_helper(
                    "init", "--state", self.state, "--repo-root", self.repo, "--spec", self.spec,
                    "--plan", self.plan, "--rubric-source", self.rubric_source,
                    "--rubric-snapshot", self.rubric_snapshot, "--scope", "skill-forge",
                    "--ticket", "none", "--initial-base", self.initial_base,
                ), "INVALID_OWNERSHIP_PATH")
        self.rubric_snapshot.unlink(missing_ok=True)
        self.write_plan([{
            "id": 1, "name": "Duplicate",
            "files": {"create": ["owned/same.txt"], "modify": ["owned/same.txt"], "delete": []},
        }])
        self.json_error(self.run_helper(
            "init", "--state", self.state, "--repo-root", self.repo, "--spec", self.spec,
            "--plan", self.plan, "--rubric-source", self.rubric_source,
            "--rubric-snapshot", self.rubric_snapshot, "--scope", "skill-forge",
            "--ticket", "none", "--initial-base", self.initial_base,
        ), "DUPLICATE_OWNERSHIP_PATH")

    def test_risk_policy_plan_contract_accepts_l2_mixed_and_rejects_illegal_downgrade(self):
        self.write_plan([
            {
                "id": 1,
                "name": "Docs deterministic",
                "files": {"create": ["owned/one.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "doc", "produces": "doc"},
                "steps": ["Edit documentation"],
                "acceptance_criteria": ["Static check passes"],
                "meta": {
                    "model": "sonnet", "file_type": "markdown", "requires_execution_check": False,
                    "risk_level": "L2", "review_policy": "final-only",
                },
            },
            {
                "id": 2,
                "name": "Routing gate update",
                "files": {"create": ["owned/two.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "Routing", "produces": "Gate behavior"},
                "steps": ["Update routing"],
                "acceptance_criteria": ["Reviewer still runs"],
                "meta": {
                    "model": "sonnet", "file_type": "script", "requires_execution_check": True,
                    "risk_level": "L2", "review_policy": "task-and-final",
                },
            },
        ])
        self.init_state()
        state = self.read_state()
        self.assertEqual(state["artifacts"]["run_risk_level"], "L2")
        self.assertEqual(state["tasks"]["1"]["review_policy"], "final-only")
        self.assertEqual(state["tasks"]["2"]["review_policy"], "task-and-final")

        self.reset_to_initial_base()
        self.write_plan([
            {
                "id": 1,
                "name": "Gate shortcut",
                "files": {"create": ["owned/one.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "Gate", "produces": "state"},
                "steps": ["Change Gate authority"],
                "acceptance_criteria": ["Covered"],
                "meta": {
                    "model": "sonnet", "file_type": "script", "requires_execution_check": True,
                    "risk_level": "L2", "review_policy": "final-only",
                },
            }
        ])
        self.json_error(self.run_helper(
            "init", "--state", self.state, "--repo-root", self.repo, "--spec", self.spec,
            "--plan", self.plan, "--rubric-source", self.rubric_source,
            "--rubric-snapshot", self.rubric_snapshot, "--scope", "skill-forge",
            "--ticket", "none", "--initial-base", self.initial_base,
        ), "INVALID_REVIEW_POLICY")

    def test_l3_run_rejects_l2_final_only_mixed_policy(self):
        self.write_plan([
            {
                "id": 1,
                "name": "High risk helper state change",
                "files": {"create": ["owned/one.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "state", "produces": "helper transition"},
                "steps": ["Change review-state transition"],
                "acceptance_criteria": ["Per-task review required"],
                "meta": {
                    "model": "sonnet", "file_type": "script", "requires_execution_check": True,
                    "risk_level": "L3", "review_policy": "task-and-final",
                },
            },
            {
                "id": 2,
                "name": "Doc deterministic cleanup",
                "files": {"create": ["owned/two.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "doc", "produces": "doc"},
                "steps": ["Edit documentation"],
                "acceptance_criteria": ["Static check passes"],
                "meta": {
                    "model": "sonnet", "file_type": "markdown", "requires_execution_check": False,
                    "risk_level": "L2", "review_policy": "final-only",
                },
            },
        ])
        self.json_error(self.run_helper(
            "init", "--state", self.state, "--repo-root", self.repo, "--spec", self.spec,
            "--plan", self.plan, "--rubric-source", self.rubric_source,
            "--rubric-snapshot", self.rubric_snapshot, "--scope", "skill-forge",
            "--ticket", "none", "--initial-base", self.initial_base,
        ), "INVALID_REVIEW_POLICY")

        self.reset_to_initial_base()
        self.write_plan([
            {
                "id": 1,
                "name": "Strict task one",
                "files": {"create": ["owned/one.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "state", "produces": "helper transition"},
                "steps": ["Change review-state transition"],
                "acceptance_criteria": ["Per-task review required"],
                "meta": {
                    "model": "sonnet", "file_type": "script", "requires_execution_check": True,
                    "risk_level": "L3", "review_policy": "task-and-final",
                },
            },
            {
                "id": 2,
                "name": "Strict task two",
                "files": {"create": ["owned/two.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "state", "produces": "helper transition"},
                "steps": ["Change helper transition"],
                "acceptance_criteria": ["Per-task review required"],
                "meta": {
                    "model": "sonnet", "file_type": "script", "requires_execution_check": True,
                    "risk_level": "L3", "review_policy": "task-and-final",
                },
            },
        ])
        self.init_state()
        state = self.read_state()
        self.assertEqual(state["artifacts"]["run_risk_level"], "L3")
        self.assertEqual(state["tasks"]["1"]["review_policy"], "task-and-final")
        self.assertEqual(state["tasks"]["2"]["review_policy"], "task-and-final")

    def test_l3_requires_task_and_final_policy(self):
        self.write_plan([
            {
                "id": 1,
                "name": "Strict task",
                "files": {"create": ["owned/one.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "input", "produces": "output"},
                "steps": ["Implement"],
                "acceptance_criteria": ["Works"],
                "meta": {
                    "model": "sonnet", "file_type": "script", "requires_execution_check": True,
                    "risk_level": "L3", "review_policy": "final-only",
                },
            }
        ])
        self.json_error(self.run_helper(
            "init", "--state", self.state, "--repo-root", self.repo, "--spec", self.spec,
            "--plan", self.plan, "--rubric-source", self.rubric_source,
            "--rubric-snapshot", self.rubric_snapshot, "--scope", "skill-forge",
            "--ticket", "none", "--initial-base", self.initial_base,
        ), "INVALID_REVIEW_POLICY")

    def test_final_only_requires_fresh_pass_evidence_and_skips_task_reviewer(self):
        self.write_plan([
            {
                "id": 1,
                "name": "Task One",
                "files": {"create": ["owned/one.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "input", "produces": "output"},
                "steps": ["Implement one"],
                "acceptance_criteria": ["One works"],
                "meta": {
                    "model": "sonnet", "file_type": "script", "requires_execution_check": True,
                    "risk_level": "L2", "review_policy": "final-only",
                },
            },
            {
                "id": 2,
                "name": "Task Two",
                "files": {"create": ["owned/two.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "input", "produces": "output"},
                "steps": ["Implement two"],
                "acceptance_criteria": ["Two works"],
                "meta": {
                    "model": "haiku", "file_type": "script", "requires_execution_check": False,
                    "risk_level": "L2", "review_policy": "task-and-final",
                },
            },
        ])
        self.init_state()
        self.json_stdout(self.start_task())
        base = self.head()
        new_head = self.commit_file("owned/one.txt", "implementation\n", "feat(skill-forge): [Task 1] Task One")
        evidence = self.repo / "deterministic.json"
        evidence.write_text(json.dumps({
            "task_id": 1,
            "base_sha": base,
            "head_sha": new_head,
            "command": "python3 -m unittest focused",
            "exit_code": 0,
            "result_summary": "fresh PASS",
            "artifact_identity": {"path": "owned/one.txt", "sha256": "abc"},
        }), encoding="utf-8")
        self.report.write_text("DONE\n", encoding="utf-8")
        self.json_stdout(self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", new_head, "--report", self.report,
            "--deterministic-evidence", evidence,
        ))
        state = self.read_state()
        self.assertEqual(state["tasks"]["1"]["status"], "PASSED")
        self.assertEqual(state["workflow"]["current_task_id"], 2)
        self.assertEqual(self.json_stdout(self.run_helper("next-action", "--state", self.state))["action"], "DISPATCH_IMPLEMENTER")

    def test_final_only_deterministic_fail_does_not_dispatch_reviewer(self):
        self.write_plan([
            {
                "id": 1,
                "name": "Task One",
                "files": {"create": ["owned/one.txt"], "modify": [], "delete": []},
                "interfaces": {"consumes": "input", "produces": "output"},
                "steps": ["Implement one"],
                "acceptance_criteria": ["One works"],
                "meta": {
                    "model": "sonnet", "file_type": "script", "requires_execution_check": True,
                    "risk_level": "L2", "review_policy": "final-only",
                },
            }
        ])
        self.init_state()
        self.json_stdout(self.start_task())
        base = self.head()
        new_head = self.commit_file("owned/one.txt", "implementation\n", "feat(skill-forge): [Task 1] Task One")
        evidence = self.repo / "deterministic-fail.json"
        evidence.write_text(json.dumps({
            "task_id": 1,
            "base_sha": base,
            "head_sha": new_head,
            "command": "python3 check.py",
            "exit_code": 1,
            "result_summary": "fresh FAIL",
            "artifact_identity": "check-log:1",
        }), encoding="utf-8")
        self.report.write_text("DONE\n", encoding="utf-8")
        before = self.state.read_bytes()
        self.json_error(self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", new_head, "--report", self.report,
            "--deterministic-evidence", evidence,
        ), "DETERMINISTIC_CHECK_FAILED")
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(self.json_stdout(self.run_helper("next-action", "--state", self.state))["action"], "DISPATCH_IMPLEMENTER")

    def test_pre_upgrade_implementing_state_hydrates_legacy_contract_on_record_implementation(self):
        self.init_state()
        self.json_stdout(self.start_task())
        legacy_state = self.read_state()
        legacy_state["artifacts"].pop("run_risk_level", None)
        for task in legacy_state["tasks"].values():
            task.pop("risk_level", None)
            task.pop("review_policy", None)
            task.pop("expected_subject", None)
            task.pop("deterministic_evidence", None)
        self.state.write_text(json.dumps(legacy_state), encoding="utf-8")
        base = self.head()
        new_head = self.commit_file("owned/one.txt", "implementation\n", "feat(skill-forge): [Task 1] Task One")
        self.report.write_text("DONE\n", encoding="utf-8")
        self.json_stdout(self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", new_head, "--report", self.report,
        ))
        state = self.read_state()
        self.assertEqual(state["artifacts"]["run_risk_level"], "L3")
        self.assertEqual(state["tasks"]["1"]["risk_level"], "L3")
        self.assertEqual(state["tasks"]["1"]["review_policy"], "task-and-final")
        self.assertEqual(state["tasks"]["1"]["expected_subject"], "feat(skill-forge): [Task 1] Task One")
        self.assertEqual(state["tasks"]["1"]["status"], "REVIEWING")
        self.assertEqual(self.json_stdout(self.run_helper("next-action", "--state", self.state))["action"], "DISPATCH_REVIEWER")

    def test_pre_upgrade_legacy_state_next_action_does_not_persist_new_fields(self):
        self.init_state()
        self.json_stdout(self.start_task())
        legacy_state = self.read_state()
        legacy_state["artifacts"].pop("run_risk_level", None)
        legacy_state["tasks"]["1"].pop("expected_subject", None)
        self.state.write_text(json.dumps(legacy_state), encoding="utf-8")
        before = self.state.read_bytes()
        self.assertEqual(self.json_stdout(self.run_helper("next-action", "--state", self.state))["action"], "DISPATCH_IMPLEMENTER")
        self.assertEqual(self.state.read_bytes(), before)

    def test_record_implementation_enforces_single_commit_and_expected_subject(self):
        self.init_state()
        self.json_stdout(self.start_task())
        base = self.head()
        bad_subject = self.commit_file("owned/one.txt", "implementation\n", "wrong subject")
        self.report.write_text("DONE\n", encoding="utf-8")
        before = self.state.read_bytes()
        self.json_error(self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", bad_subject, "--report", self.report,
        ), "COMMIT_SUBJECT_MISMATCH")
        self.assertEqual(self.state.read_bytes(), before)

        self.reset_to_initial_base()
        self.init_state()
        self.json_stdout(self.start_task())
        base = self.head()
        self.commit_file("owned/one.txt", "one\n", "feat(skill-forge): [Task 1] Task One")
        two = self.commit_file("owned/shared.txt", "two\n", "feat(skill-forge): [Task 1] Task One")
        self.report.write_text("DONE\n", encoding="utf-8")
        self.json_error(self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", two, "--report", self.report,
        ), "COMMIT_COUNT_MISMATCH")

    def test_record_fix_uses_authorized_fix_subject_and_recovers_legacy_fixing_state(self):
        finding = self.make_finding(
            "TASK1-L3-RUN-POLICY-001",
            rule_id="TASK1_STEP_1_2_L3_STRICT_POLICY",
            failure_key="l3_run_accepts_l2_final_only_policy",
        )
        expected_subject = "fix(skill-forge): [Task 1 Fix 1] address authorized findings"
        noncanonical_subject = "fix(skill-forge): [Task 1] enforce strict L3 run policy"

        self.init_state()
        self.implement_task()
        self.json_stdout(self.import_observation(self.make_observation(findings=[finding])))
        self.json_stdout(self.authorize_current(["TASK1-L3-RUN-POLICY-001"]))
        self.assertEqual(self.read_state()["tasks"]["1"]["expected_fix_subject"], expected_subject)
        self.record_fixed_commit(["TASK1-L3-RUN-POLICY-001"], subject=expected_subject)

        self.reset_to_initial_base()
        self.init_state()
        self.implement_task()
        self.json_stdout(self.import_observation(self.make_observation(findings=[finding])))
        self.json_stdout(self.authorize_current(["TASK1-L3-RUN-POLICY-001"]))
        base = self.head()
        bad_head = self.commit_file("owned/one.txt", "bad fix\n", noncanonical_subject)
        bad_report = self.repo / "bad-policy-fix.json"
        bad_report.write_text(json.dumps({
            "status": "FIXED",
            "attempt": 1,
            "base_head_sha": base,
            "new_head_sha": bad_head,
            "findings": [{
                "id": "TASK1-L3-RUN-POLICY-001",
                "action": "Applied bounded fix",
                "changed_paths": ["owned/one.txt"],
                "closure_test": {"command": "python3 check.py", "exit_code": 0, "output": "pass"},
            }],
        }), encoding="utf-8")
        before = self.state.read_bytes()
        self.json_error(self.run_helper(
            "record-fix", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", bad_head, "--report", bad_report,
        ), "COMMIT_SUBJECT_MISMATCH")
        self.assertEqual(self.state.read_bytes(), before)

        self.reset_to_initial_base()
        self.init_state()
        self.implement_task()
        self.json_stdout(self.import_observation(self.make_observation(findings=[finding])))
        self.json_stdout(self.authorize_current(["TASK1-L3-RUN-POLICY-001"]))
        legacy_state = self.read_state()
        legacy_state["tasks"]["1"].pop("expected_fix_subject")
        self.state.write_text(json.dumps(legacy_state), encoding="utf-8")
        self.record_fixed_commit(["TASK1-L3-RUN-POLICY-001"], subject=expected_subject)

    def test_hash_drift_rejects_every_mutating_command(self):
        command_builders = [
            lambda: self.start_task(),
            lambda: self.run_helper(
                "record-implementation", "--state", self.state, "--task-id", "1",
                "--base-head", self.head(), "--new-head", self.head(), "--report", self.report,
            ),
            lambda: self.run_helper("import-review", "--state", self.state, "--observation", self.observation),
            lambda: self.authorize_current([]),
            lambda: self.run_helper(
                "record-fix", "--state", self.state, "--task-id", "1", "--base-head", self.head(),
                "--new-head", self.head(), "--report", self.report,
            ),
            lambda: self.run_helper(
                "advance-gate", "--state", self.state, "--gate", "SQUASH_APPROVAL",
                "--result", "UNSQUASHED", "--head", self.head(),
            ),
        ]
        for command_builder in command_builders:
            with self.subTest(command=command_builder):
                self.state.unlink(missing_ok=True)
                self.rubric_snapshot.unlink(missing_ok=True)
                self.spec.write_text("# Frozen spec\n", encoding="utf-8")
                self.init_state()
                before = self.state.read_bytes()
                self.spec.write_text("drift\n", encoding="utf-8")
                self.json_error(command_builder(), "ARTIFACT_HASH_DRIFT")
                self.assertEqual(self.state.read_bytes(), before)

    def test_task_base_is_immutable_and_task_head_accumulates_commits(self):
        self.init_state()
        original_base, implementation_head = self.implement_task()
        finding = self.make_finding()
        self.json_stdout(self.import_observation(self.make_observation(findings=[finding])))
        self.json_stdout(self.authorize_current(["F-1"]))
        _, fix_head = self.record_fixed_commit(["F-1"])
        task = self.read_state()["tasks"]["1"]
        self.assertEqual(task["task_base"], original_base)
        self.assertEqual(task["task_head"], fix_head)
        self.assertNotEqual(task["task_head"], implementation_head)

    def test_record_implementation_rejects_changed_paths_outside_ownership(self):
        self.init_state()
        self.json_stdout(self.start_task())
        base = self.head()
        new_head = self.commit_file("outside.txt", "bad\n", "outside")
        self.report.write_text("DONE\n", encoding="utf-8")
        before = self.state.read_bytes()
        result = self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", new_head, "--report", self.report,
        )
        self.json_error(result, "OWNERSHIP_VIOLATION")
        self.assertEqual(self.state.read_bytes(), before)

    def test_baseline_finding_is_non_blocking_and_does_not_consume_budget(self):
        cases = [
            ("TASK_REVIEW", "BASELINE", "IMPORTANT", True),
            ("FINAL_REVIEW", "BASELINE", "IMPORTANT", True),
            ("STRUCTURAL_VALIDATION", "NEW", "MINOR", True),
            ("BEHAVIORAL_VALIDATION", "NEW", "IMPORTANT", False),
        ]
        for gate, origin, severity, blocking in cases:
            with self.subTest(gate=gate, origin=origin, severity=severity, blocking=blocking):
                self.reset_to_initial_base()
                self.init_state()
                if gate == "TASK_REVIEW":
                    self.implement_task()
                else:
                    self.reach_final_review()
                    for prior_gate in ("FINAL_REVIEW", "STRUCTURAL_VALIDATION"):
                        if prior_gate == gate:
                            break
                        self.json_stdout(self.import_observation(
                            self.make_observation(gate=prior_gate, verdict="PASS")
                        ))
                finding = self.make_finding(
                    "HARMLESS", gate=gate, owner_task_id=1 if gate == "TASK_REVIEW" else None,
                    origin=origin, severity=severity, blocking=blocking, status="OPEN",
                    path="legacy/debt.txt", required_fix_paths=["legacy/debt.txt"],
                    rule_id=f"{gate}-HARMLESS",
                )
                self.json_stdout(self.import_observation(self.make_observation(
                    gate=gate, verdict="PASS", findings=[finding]
                )))
                state = self.read_state()
                self.assertFalse(state["findings"]["HARMLESS"]["blocking"])
                self.assertNotEqual(state["workflow"]["status"], "HALTED_SCOPE_BLOCKED")
                self.assertNotEqual(state["workflow"]["status"], "HALTED_NEEDS_DECISION")
                self.assertEqual(state["tasks"]["1"]["fix_budget"]["used"], 0)

    def test_new_and_regression_blockers_authorize_one_grouped_fix(self):
        self.init_state()
        self.implement_task()
        findings = [
            self.make_finding("F-1", origin="NEW", rule_id="R-1", failure_key="one"),
            self.make_finding("F-2", origin="REGRESSION", rule_id="R-2", failure_key="two"),
        ]
        self.json_stdout(self.import_observation(self.make_observation(findings=findings)))
        needs = self.json_stdout(self.run_helper("needs-fix", "--state", self.state, "--task-id", "1"))
        self.assertEqual(needs["finding_ids"], ["F-1", "F-2"])
        self.assertTrue(needs["allowed"])
        authorized = self.json_stdout(self.authorize_current(["F-2", "F-1"]))
        self.assertEqual(authorized["finding_ids"], ["F-1", "F-2"])
        task = self.read_state()["tasks"]["1"]
        self.assertEqual(task["fix_budget"], {"maximum": 2, "used": 1, "remaining": 1})
        self.assertEqual(task["authorized_finding_ids"], ["F-1", "F-2"])

        self.reset_to_initial_base()
        self.init_state()
        self.implement_task()
        duplicate_a = self.make_finding("DUP-A", rule_id="DUP", failure_key="same")
        duplicate_b = self.make_finding("DUP-B", rule_id="DUP", failure_key="same")
        self.json_stdout(self.import_observation(
            self.make_observation(findings=[duplicate_a, duplicate_b])
        ))
        state = self.read_state()
        self.assertEqual(list(state["findings"]), ["DUP-A"])
        self.assertEqual(state["tasks"]["1"]["open_blocking_findings"], ["DUP-A"])
        self.assertEqual(len(state["findings"]["DUP-A"]["observation_history"]), 2)

        self.json_stdout(self.authorize_current(["DUP-A"]))
        self.record_fixed_commit(["DUP-A"])
        cross_attempt = self.make_finding("DUP-A", attempt=2, rule_id="DUP", failure_key="same")
        self.json_stdout(self.import_observation(
            self.make_observation(attempt=2, findings=[cross_attempt])
        ))
        state = self.read_state()
        self.assertEqual(list(state["findings"]), ["DUP-A"])
        self.assertEqual(len(state["findings"]["DUP-A"]["observation_history"]), 3)
        self.assertEqual(state["workflow"]["status"], "HALTED_NO_PROGRESS")

    def test_minor_suggestion_and_out_of_contract_cannot_authorize_fix(self):
        self.init_state()
        self.implement_task()
        minor = self.make_finding("MINOR", severity="MINOR", rule_id="MINOR")
        suggestion = self.make_finding("SUGGEST", blocking=False, severity="IMPORTANT", rule_id="SUGGEST")
        self.json_stdout(self.import_observation(
            self.make_observation(verdict="PASS", findings=[minor, suggestion])
        ))
        state = self.read_state()
        self.assertEqual(state["tasks"]["1"]["fix_budget"]["used"], 0)
        self.assertFalse(state["findings"]["MINOR"]["blocking"])
        self.assertFalse(state["findings"]["SUGGEST"]["blocking"])

        self.state.unlink()
        self.rubric_snapshot.unlink()
        subprocess.run(["git", "-C", str(self.repo), "reset", "--hard", "-q", self.initial_base], check=True)
        self.init_state()
        self.implement_task()
        disputed = self.make_finding("CONTRACT", origin="OUT_OF_CONTRACT")
        self.json_stdout(self.import_observation(self.make_observation(findings=[disputed])))
        state = self.read_state()
        self.assertEqual(state["workflow"]["status"], "HALTED_CONTRACT_DISPUTE")
        self.assertEqual(state["tasks"]["1"]["fix_budget"]["used"], 0)
        self.assertEqual(self.json_stdout(self.run_helper("next-action", "--state", self.state))["action"], "HALT")

    def test_fix_budget_is_shared_across_all_four_gates_and_third_fix_halts(self):
        for gate in ("TASK_REVIEW", "FINAL_REVIEW", "STRUCTURAL_VALIDATION", "BEHAVIORAL_VALIDATION"):
            with self.subTest(shared_budget_gate=gate):
                self.reset_to_initial_base()
                self.init_state()
                state = self.read_state()
                state["tasks"]["1"]["fix_budget"] = {"maximum": 2, "used": 1, "remaining": 1}
                state["tasks"]["1"]["status"] = "FIX_REQUIRED"
                state["tasks"]["1"]["open_blocking_findings"] = [f"{gate}-F"]
                state["workflow"]["status"] = "FIX_REQUIRED"
                state["workflow"]["current_gate"] = gate
                state["workflow"]["current_task_id"] = 1
                self.state.write_text(json.dumps(state), encoding="utf-8")
                self.json_stdout(self.authorize_current([f"{gate}-F"]))
                self.assertEqual(
                    self.read_state()["tasks"]["1"]["fix_budget"],
                    {"maximum": 2, "used": 2, "remaining": 0},
                )

        self.reset_to_initial_base()
        self.init_state()
        self.implement_task()
        first = self.make_finding("TASK-F", gate="TASK_REVIEW", attempt=1, rule_id="TASK")
        self.json_stdout(self.import_observation(self.make_observation(findings=[first])))
        self.json_stdout(self.authorize_current(["TASK-F"]))
        self.record_fixed_commit(["TASK-F"])
        closed = self.make_finding(
            "TASK-F", gate="TASK_REVIEW", attempt=2, status="RESOLVED", rule_id="TASK",
            closure_actual={"command": "python3 check.py", "exit_code": 0, "output": "pass"},
        )
        self.json_stdout(self.import_observation(self.make_observation(verdict="PASS", attempt=2, findings=[closed])))
        self.assertEqual(self.read_state()["workflow"]["current_task_id"], 2)

        self.json_stdout(self.start_task(task_id=2))
        base = self.head()
        head = self.commit_file("owned/two.txt", "task two\n", "feat(skill-forge): [Task 2] Task Two")
        self.report.write_text("DONE\n", encoding="utf-8")
        self.json_stdout(self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "2",
            "--base-head", base, "--new-head", head, "--report", self.report,
        ))
        self.json_stdout(self.import_observation(self.make_observation(verdict="PASS", task_id=2)))

        final_finding = self.make_finding(
            "FINAL-F", gate="FINAL_REVIEW", owner_task_id=None, path="owned/one.txt",
            required_fix_paths=["owned/one.txt"], attempt=1, rule_id="FINAL",
        )
        final_observation = self.make_observation(
            gate="FINAL_REVIEW", verdict="FAIL", task_id=1, findings=[final_finding]
        )
        self.json_stdout(self.import_observation(final_observation))
        self.json_stdout(self.authorize_current(["FINAL-F"]))
        self.record_fixed_commit(["FINAL-F"], attempt=2)
        final_closed = self.make_finding(
            "FINAL-F", gate="FINAL_REVIEW", owner_task_id=None, path="owned/one.txt",
            required_fix_paths=["owned/one.txt"], attempt=2, status="RESOLVED", rule_id="FINAL",
            closure_actual={"command": "python3 check.py", "exit_code": 0, "output": "pass"},
        )
        second_final = self.make_finding(
            "FINAL-NEW", gate="FINAL_REVIEW", owner_task_id=None, path="owned/one.txt",
            required_fix_paths=["owned/one.txt"], attempt=2, rule_id="FINAL-NEW",
        )
        self.json_stdout(self.import_observation(self.make_observation(
            gate="FINAL_REVIEW", verdict="FAIL", findings=[final_closed, second_final], attempt=3,
        )))
        result = self.authorize_current(["FINAL-NEW"])
        self.json_error(result, "FIX_BUDGET_EXHAUSTED")
        state = self.read_state()
        self.assertEqual(state["workflow"]["status"], "HALTED_BUDGET_EXHAUSTED")
        self.assertEqual(state["tasks"]["1"]["fix_budget"], {"maximum": 2, "used": 2, "remaining": 0})

    def test_record_fix_requires_changed_head_authorized_ids_and_closure_evidence(self):
        self.init_state()
        self.implement_task()
        self.json_stdout(self.import_observation(self.make_observation(findings=[self.make_finding()])))
        self.json_stdout(self.authorize_current(["F-1"]))
        base = self.head()
        cases = [
            ({"status": "FIXED", "attempt": 1, "base_head_sha": base, "new_head_sha": base, "findings": []}, "HEAD_NOT_CHANGED"),
        ]
        for payload, expected_code in cases:
            report = self.repo / "bad-fix.json"
            report.write_text(json.dumps(payload), encoding="utf-8")
            self.json_error(self.run_helper(
                "record-fix", "--state", self.state, "--task-id", "1",
                "--base-head", base, "--new-head", base, "--report", report,
            ), expected_code)

        new_head = self.commit_file("owned/one.txt", "fix\n", "fix(skill-forge): [Task 1 Fix 1] address authorized findings")
        bad_reports = [
            ({"status": "FIXED", "attempt": 1, "base_head_sha": base, "new_head_sha": new_head, "findings": []}, "FINDING_SET_MISMATCH"),
            ({
                "status": "FIXED", "attempt": 1, "base_head_sha": base, "new_head_sha": new_head,
                "findings": [{"id": "F-1", "action": "fix", "changed_paths": ["owned/one.txt"]}],
            }, "INVALID_FIX_REPORT"),
        ]
        for index, (payload, expected_code) in enumerate(bad_reports):
            report = self.repo / f"bad-{index}.json"
            report.write_text(json.dumps(payload), encoding="utf-8")
            self.json_error(self.run_helper(
                "record-fix", "--state", self.state, "--task-id", "1",
                "--base-head", base, "--new-head", new_head, "--report", report,
            ), expected_code)
        good = self.repo / "good.json"
        good.write_text(json.dumps({
            "status": "FIXED", "attempt": 1, "base_head_sha": base, "new_head_sha": new_head,
            "findings": [{
                "id": "F-1", "action": "fix", "changed_paths": ["owned/one.txt"],
                "closure_test": {"command": "check", "exit_code": 0, "output": "pass"},
            }],
        }), encoding="utf-8")
        self.json_stdout(self.run_helper(
            "record-fix", "--state", self.state, "--task-id", "1",
            "--base-head", base, "--new-head", new_head, "--report", good,
        ))

    def test_rereview_requires_every_targeted_finding_open_or_resolved(self):
        self.init_state()
        self.implement_task()
        findings = [self.make_finding("F-1", rule_id="R1"), self.make_finding("F-2", rule_id="R2")]
        self.json_stdout(self.import_observation(self.make_observation(findings=findings)))
        self.json_stdout(self.authorize_current(["F-1", "F-2"]))
        self.record_fixed_commit(["F-1", "F-2"])
        only_one = self.make_finding("F-1", attempt=2, status="OPEN", rule_id="R1")
        before = self.state.read_bytes()
        self.json_error(
            self.import_observation(self.make_observation(attempt=2, findings=[only_one])),
            "MISSING_TARGETED_FINDING",
        )
        self.assertEqual(self.state.read_bytes(), before)

    def test_unchanged_blocker_set_halts_no_progress(self):
        self.init_state()
        self.implement_task()
        first = self.make_finding("F-1", rule_id="R1")
        self.json_stdout(self.import_observation(self.make_observation(findings=[first])))
        self.json_stdout(self.authorize_current(["F-1"]))
        self.record_fixed_commit(["F-1"])
        unchanged = self.make_finding("F-1", attempt=2, status="OPEN", rule_id="R1")
        self.json_stdout(self.import_observation(self.make_observation(attempt=2, findings=[unchanged])))
        self.assertEqual(self.read_state()["workflow"]["status"], "HALTED_NO_PROGRESS")

    def test_old_blockers_not_reduced_plus_new_blocker_halts_regression(self):
        self.init_state()
        self.implement_task()
        first = self.make_finding("F-1", rule_id="R1")
        self.json_stdout(self.import_observation(self.make_observation(findings=[first])))
        self.json_stdout(self.authorize_current(["F-1"]))
        self.record_fixed_commit(["F-1"])
        old_open = self.make_finding("F-1", attempt=2, status="OPEN", rule_id="R1")
        new_open = self.make_finding("F-2", attempt=2, status="OPEN", rule_id="R2", failure_key="new")
        self.json_stdout(self.import_observation(self.make_observation(attempt=2, findings=[old_open, new_open])))
        self.assertEqual(self.read_state()["workflow"]["status"], "HALTED_REGRESSION")

    def test_resolved_finding_reappearance_becomes_regression(self):
        self.init_state()
        self.implement_task()
        first = self.make_finding("F-1", rule_id="R1")
        self.json_stdout(self.import_observation(self.make_observation(findings=[first])))
        self.json_stdout(self.authorize_current(["F-1"]))
        self.record_fixed_commit(["F-1"])
        resolved = self.make_finding(
            "F-1", attempt=2, status="RESOLVED", rule_id="R1",
            closure_actual={"command": "check", "exit_code": 0, "output": "pass"},
        )
        new_issue = self.make_finding("F-2", attempt=2, rule_id="R2")
        self.json_stdout(self.import_observation(self.make_observation(attempt=2, findings=[resolved, new_issue])))
        self.json_stdout(self.authorize_current(["F-2"]))
        self.record_fixed_commit(["F-2"], attempt=2)
        resolved_second = self.make_finding(
            "F-2", attempt=3, status="RESOLVED", rule_id="R2",
            closure_actual={"command": "check", "exit_code": 0, "output": "pass"},
        )
        reappeared = self.make_finding("F-3", attempt=3, rule_id="R1")
        self.json_stdout(self.import_observation(
            self.make_observation(attempt=3, findings=[resolved_second, reappeared])
        ))
        state = self.read_state()
        self.assertNotIn("F-3", state["findings"])
        self.assertEqual(state["findings"]["F-1"]["origin"], "REGRESSION")
        self.assertEqual(state["findings"]["F-1"]["status"], "OPEN")
        self.assertEqual(state["findings"]["F-1"]["observation_history"][-1]["observed_id"], "F-3")

    def test_final_or_validation_finding_requires_unique_owner_task(self):
        cases = [
            ("FINAL_REVIEW", "owned/one.txt", ["owned/one.txt"], "FIX_REQUIRED", 1),
            ("STRUCTURAL_VALIDATION", "outside.txt", ["outside.txt"], "HALTED_NEEDS_DECISION", None),
            (
                "BEHAVIORAL_VALIDATION", "owned/shared.txt",
                ["owned/one.txt", "owned/two.txt"], "HALTED_NEEDS_DECISION", None,
            ),
        ]
        for gate, path, required_paths, expected, expected_owner in cases:
            with self.subTest(gate=gate, expected=expected):
                self.reset_to_initial_base()
                self.init_state()
                self.reach_final_review()
                for prior_gate in ("FINAL_REVIEW", "STRUCTURAL_VALIDATION"):
                    if prior_gate == gate:
                        break
                    self.json_stdout(self.import_observation(
                        self.make_observation(gate=prior_gate, verdict="PASS")
                    ))
                finding = self.make_finding(
                    "OWNER", gate=gate, owner_task_id=None, path=path,
                    required_fix_paths=required_paths, rule_id=f"{gate}-OWNER",
                )
                self.json_stdout(self.import_observation(self.make_observation(
                    gate=gate, verdict="FAIL", findings=[finding]
                )))
                state = self.read_state()
                self.assertEqual(state["workflow"]["status"], expected)
                if expected_owner is not None:
                    self.assertEqual(state["findings"]["OWNER"]["owner_task_id"], expected_owner)

        self.reset_to_initial_base()
        self.init_state()
        self.reach_final_review()
        findings = [
            self.make_finding(
                "OWNER-1", gate="FINAL_REVIEW", owner_task_id=None,
                required_fix_paths=["owned/one.txt"], rule_id="OWNER-1",
            ),
            self.make_finding(
                "OWNER-2", gate="FINAL_REVIEW", owner_task_id=None,
                path="owned/two.txt", required_fix_paths=["owned/two.txt"], rule_id="OWNER-2",
            ),
        ]
        self.json_stdout(self.import_observation(self.make_observation(
            gate="FINAL_REVIEW", verdict="FAIL", findings=findings
        )))
        state = self.read_state()
        self.assertEqual(state["workflow"]["status"], "HALTED_NEEDS_DECISION")
        self.assertEqual(
            {finding_id: finding["owner_task_id"] for finding_id, finding in state["findings"].items()},
            {"OWNER-1": 1, "OWNER-2": 2},
        )
        self.assertEqual(state["tasks"]["1"]["fix_budget"]["used"], 0)
        self.assertEqual(state["tasks"]["2"]["fix_budget"]["used"], 0)

    def test_required_fix_path_outside_ownership_halts_scope_blocked(self):
        self.init_state()
        self.implement_task()
        outside = self.make_finding("OUT", path="outside.txt", required_fix_paths=["outside.txt"])
        self.json_stdout(self.import_observation(self.make_observation(findings=[outside])))
        self.assertEqual(self.read_state()["workflow"]["status"], "HALTED_SCOPE_BLOCKED")
        self.assertEqual(self.read_state()["tasks"]["1"]["fix_budget"]["used"], 0)

        for gate in ("TASK_REVIEW", "FINAL_REVIEW", "STRUCTURAL_VALIDATION", "BEHAVIORAL_VALIDATION"):
            for required_paths in ([], ["owned/one.txt", "owned/one.txt"]):
                with self.subTest(gate=gate, required_paths=required_paths):
                    self.reset_to_initial_base()
                    self.init_state()
                    if gate == "TASK_REVIEW":
                        self.implement_task()
                    else:
                        self.reach_final_review()
                        for prior_gate in ("FINAL_REVIEW", "STRUCTURAL_VALIDATION"):
                            if prior_gate == gate:
                                break
                            self.json_stdout(self.import_observation(
                                self.make_observation(gate=prior_gate, verdict="PASS")
                            ))
                    finding = self.make_finding(
                        "BOUNDS", gate=gate,
                        owner_task_id=1 if gate == "TASK_REVIEW" else None,
                        required_fix_paths=required_paths, rule_id=f"{gate}-BOUNDS",
                    )
                    before = self.state.read_bytes()
                    self.json_error(self.import_observation(self.make_observation(
                        gate=gate, verdict="FAIL", findings=[finding]
                    )), "INVALID_FINDING_SCHEMA")
                    self.assertEqual(self.state.read_bytes(), before)
                    self.assertEqual(self.read_state()["tasks"]["1"]["fix_budget"]["used"], 0)

    def test_cannot_verify_requires_controller_resolution_before_pass(self):
        cannot = [{"id": "CV-1", "summary": "Needs controller decision", "contract_ref": "Task 1"}]
        self.init_state()
        self.implement_task()
        self.json_stdout(self.import_observation(self.make_observation(
            verdict="PASS", cannot_verify=cannot
        )))
        state = self.read_state()
        self.assertEqual(state["tasks"]["1"]["status"], "HALTED_NEEDS_DECISION")
        self.assertEqual(state["tasks"]["1"]["cannot_verify"][0]["id"], "CV-1")

        invalid_resolutions = [
            [{"id": "CV-1"}],
            [
                {"id": "CV-1", "action": "ACCEPT", "reason": "verified"},
                {"id": "CV-1", "action": "ACCEPT", "reason": "duplicate"},
            ],
            [{"id": "CV-2", "action": "ACCEPT", "reason": "unknown"}],
        ]
        for resolution in invalid_resolutions:
            with self.subTest(resolution=resolution):
                self.reset_to_initial_base()
                self.init_state()
                self.implement_task()
                before = self.state.read_bytes()
                self.json_error(self.import_observation(self.make_observation(
                    verdict="PASS", cannot_verify=cannot, controller_resolutions=resolution
                )), "INVALID_CONTROLLER_RESOLUTION")
                self.assertEqual(self.state.read_bytes(), before)

        self.reset_to_initial_base()
        self.init_state()
        self.implement_task()
        resolution = [{"id": "CV-1", "action": "ACCEPT", "reason": "Controller verified evidence"}]
        self.json_stdout(self.import_observation(self.make_observation(
            verdict="PASS", cannot_verify=cannot, controller_resolutions=resolution
        )))
        state = self.read_state()
        self.assertEqual(state["tasks"]["1"]["status"], "PASSED")
        self.assertEqual(state["tasks"]["1"]["cannot_verify"], [])
        self.assertEqual(state["artifacts"]["controller_resolutions"], resolution)
        state["tasks"]["1"]["status"] = "REVIEWING"
        state["workflow"]["status"] = "REVIEWING"
        state["workflow"]["current_gate"] = "TASK_REVIEW"
        state["workflow"]["current_task_id"] = 1
        self.state.write_text(json.dumps(state), encoding="utf-8")
        before = self.state.read_bytes()
        self.json_error(self.import_observation(self.make_observation(
            verdict="PASS", cannot_verify=cannot, controller_resolutions=resolution
        )), "INVALID_CONTROLLER_RESOLUTION")
        self.assertEqual(self.state.read_bytes(), before)

    def test_invalid_schema_sha_attempt_and_transition_are_rejected(self):
        self.init_state()
        self.json_error(self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "1",
            "--base-head", self.head(), "--new-head", self.head(), "--report", self.report,
        ), "INVALID_TRANSITION")
        self.implement_task()
        valid = self.make_observation(verdict="PASS")
        collision = self.make_finding("COLLISION", rule_id="ONE", failure_key="one")
        self.json_stdout(self.import_observation(self.make_observation(findings=[collision])))
        state = self.read_state()
        state["tasks"]["1"]["status"] = "REVIEWING"
        state["workflow"]["status"] = "REVIEWING"
        self.state.write_text(json.dumps(state), encoding="utf-8")
        conflicting = self.make_finding("COLLISION", rule_id="TWO", failure_key="two")
        before = self.state.read_bytes()
        self.json_error(
            self.import_observation(self.make_observation(findings=[conflicting])),
            "FINDING_ID_COLLISION",
        )
        self.assertEqual(self.state.read_bytes(), before)

        state = self.read_state()
        state["findings"] = {}
        state["tasks"]["1"]["open_blocking_findings"] = []
        self.state.write_text(json.dumps(state), encoding="utf-8")
        valid = self.make_observation(verdict="PASS")
        variants = [
            ({**valid, "schema_version": 2}, "INVALID_OBSERVATION_SCHEMA"),
            ({**valid, "base_sha": "short"}, "INVALID_SHA"),
            ({**valid, "head_sha": "0" * 40}, "HEAD_MISMATCH"),
            ({**valid, "attempt": 99}, "ATTEMPT_MISMATCH"),
        ]
        for payload, code in variants:
            with self.subTest(code=code):
                before = self.state.read_bytes()
                self.json_error(self.import_observation(payload), code)
                self.assertEqual(self.state.read_bytes(), before)

        schema_type_cases = [
            ("finding.source_gate", "source_gate", [], "INVALID_FINDING_SCHEMA"),
            ("finding.severity", "severity", [], "INVALID_FINDING_SCHEMA"),
            ("finding.origin", "origin", [], "INVALID_FINDING_SCHEMA"),
            ("finding.status", "status", [], "INVALID_FINDING_SCHEMA"),
            ("finding.attempt", "attempt", True, "INVALID_FINDING_SCHEMA"),
            ("observation.schema_version", "schema_version", True, "INVALID_OBSERVATION_SCHEMA"),
            ("observation.gate", "gate", [], "INVALID_OBSERVATION_SCHEMA"),
            ("observation.verdict", "verdict", [], "INVALID_OBSERVATION_SCHEMA"),
            ("observation.attempt", "attempt", True, "INVALID_OBSERVATION_SCHEMA"),
        ]
        for target, field, invalid_value, code in schema_type_cases:
            with self.subTest(target=target):
                payload = self.make_observation(findings=[self.make_finding()])
                container = payload["findings"][0] if target.startswith("finding.") else payload
                container[field] = invalid_value
                before = self.state.read_bytes()
                result = self.import_observation(payload)
                state_unchanged = self.state.read_bytes() == before
                self.state.write_bytes(before)
                error = self.json_error(result, code)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(result.stderr.strip().splitlines()), 1)
                self.assertEqual(set(error), {"ok", "code"})
                self.assertTrue(state_unchanged)

        malformed = {
            "rule_id": 7,
            "failure_key": "",
            "contract_ref": 9,
            "summary": [],
            "path": 1,
            "base_evidence": {"command": "base"},
            "head_evidence": "head",
            "closure_test": {"expected": {"command": "check", "exit_code": "0", "output": "pass"}},
            "observations": [{"risk": "risk"}],
            "resolution": [],
        }
        original = self.make_finding()
        for field, invalid_value in malformed.items():
            with self.subTest(field=field):
                finding = copy.deepcopy(original)
                finding[field] = invalid_value
                before = self.state.read_bytes()
                result = self.import_observation(self.make_observation(findings=[finding]))
                error = self.json_error(result, "INVALID_FINDING_SCHEMA")
                self.assertEqual(set(error), {"ok", "code"})
                self.assertEqual(self.state.read_bytes(), before)

        state_payload = self.read_state()
        state_payload["workflow"] = []
        self.state.write_text(json.dumps(state_payload), encoding="utf-8")
        self.json_error(self.run_helper("next-action", "--state", self.state), "INVALID_STATE_SCHEMA")

    def test_failed_atomic_replace_preserves_previous_readable_state(self):
        self.init_state()
        before = self.state.read_bytes()
        spec = importlib.util.spec_from_file_location("review_state_helper", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with mock.patch.object(module.os, "replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                module.atomic_write_json(self.state, {"corrupt": True})
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(json.loads(self.state.read_text())["schema_version"], 1)
        leftovers = list(self.repo.glob(f".{self.state.name}.*.tmp"))
        self.assertEqual(leftovers, [])

    def test_api_failure_without_observation_keeps_state_and_budget_unchanged(self):
        self.init_state()
        self.implement_task()
        before = self.state.read_bytes()
        first_action = self.json_stdout(self.run_helper("next-action", "--state", self.state))["action"]
        second_action = self.json_stdout(self.run_helper("next-action", "--state", self.state))["action"]
        self.assertEqual(first_action, "DISPATCH_REVIEWER")
        self.assertEqual(second_action, first_action)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(self.read_state()["tasks"]["1"]["fix_budget"]["used"], 0)

        stale = self.make_observation(verdict="PASS")
        self.commit_file("outside.txt", "unreviewed\n", "out-of-band")
        before = self.state.read_bytes()
        self.json_error(self.import_observation(stale), "HEAD_MISMATCH")
        self.assertEqual(self.state.read_bytes(), before)

    def test_next_action_returns_one_legal_action_for_each_state(self):
        legal_actions = {
            "DISPATCH_IMPLEMENTER", "DISPATCH_REVIEWER", "DISPATCH_FIXER",
            "RUN_FINAL_REVIEW", "RUN_STRUCTURAL_VALIDATION", "RUN_BEHAVIORAL_VALIDATION",
            "REQUEST_SQUASH_APPROVAL", "COMPLETE", "HALT",
        }
        states = [
            ("READY", "TASK_IMPLEMENTATION", "DISPATCH_IMPLEMENTER"),
            ("IMPLEMENTING", "TASK_IMPLEMENTATION", "DISPATCH_IMPLEMENTER"),
            ("REVIEWING", "TASK_REVIEW", "DISPATCH_REVIEWER"),
            ("FIX_REQUIRED", "TASK_REVIEW", "DISPATCH_FIXER"),
            ("FIXING", "TASK_REVIEW", "DISPATCH_FIXER"),
            ("REVIEWING", "FINAL_REVIEW", "RUN_FINAL_REVIEW"),
            ("FINAL_REVIEW", "FINAL_REVIEW", "RUN_FINAL_REVIEW"),
            ("REVIEWING", "STRUCTURAL_VALIDATION", "RUN_STRUCTURAL_VALIDATION"),
            ("STRUCTURAL_VALIDATION", "STRUCTURAL_VALIDATION", "RUN_STRUCTURAL_VALIDATION"),
            ("REVIEWING", "BEHAVIORAL_VALIDATION", "RUN_BEHAVIORAL_VALIDATION"),
            ("BEHAVIORAL_VALIDATION", "BEHAVIORAL_VALIDATION", "RUN_BEHAVIORAL_VALIDATION"),
            ("SQUASH_APPROVAL", "SQUASH_APPROVAL", "REQUEST_SQUASH_APPROVAL"),
            ("COMPLETE", "SQUASH_APPROVAL", "COMPLETE"),
            ("COMPLETE_UNSQUASHED", "SQUASH_APPROVAL", "COMPLETE"),
            ("HALTED_NO_PROGRESS", "TASK_REVIEW", "HALT"),
        ]
        for status, gate, expected in states:
            with self.subTest(status=status, gate=gate):
                self.reset_to_initial_base()
                self.init_state()
                state = self.read_state()
                state["workflow"]["status"] = status
                state["workflow"]["current_gate"] = gate
                self.state.write_text(json.dumps(state), encoding="utf-8")
                action = self.json_stdout(
                    self.run_helper("next-action", "--state", self.state)
                )["action"]
                self.assertEqual(action, expected)
                self.assertIn(action, legal_actions)
        self.final_validation_post_fix_retry_is_gate_aware_and_bounded()

    def final_validation_post_fix_retry_is_gate_aware_and_bounded(self):
        next_status = {
            "FINAL_REVIEW": "STRUCTURAL_VALIDATION",
            "STRUCTURAL_VALIDATION": "BEHAVIORAL_VALIDATION",
            "BEHAVIORAL_VALIDATION": "SQUASH_APPROVAL",
        }
        retry_action = {
            "FINAL_REVIEW": "RUN_FINAL_REVIEW",
            "STRUCTURAL_VALIDATION": "RUN_STRUCTURAL_VALIDATION",
            "BEHAVIORAL_VALIDATION": "RUN_BEHAVIORAL_VALIDATION",
        }
        post_pass_action = {
            "FINAL_REVIEW": "RUN_STRUCTURAL_VALIDATION",
            "STRUCTURAL_VALIDATION": "RUN_BEHAVIORAL_VALIDATION",
            "BEHAVIORAL_VALIDATION": "REQUEST_SQUASH_APPROVAL",
        }
        for gate in next_status:
            for outcome in ("NO_PROGRESS", "REGRESSION", "RESOLVED"):
                with self.subTest(gate=gate, outcome=outcome):
                    self.reset_to_initial_base()
                    self.init_state()
                    self.reach_final_review()
                    for prior_gate in ("FINAL_REVIEW", "STRUCTURAL_VALIDATION"):
                        if prior_gate == gate:
                            break
                        self.json_stdout(self.import_observation(
                            self.make_observation(gate=prior_gate, verdict="PASS")
                        ))
                    finding = self.make_finding(
                        "GATE-F", gate=gate, owner_task_id=None,
                        required_fix_paths=["owned/one.txt"], rule_id=f"{gate}-F",
                    )
                    self.json_stdout(self.import_observation(self.make_observation(
                        gate=gate, verdict="FAIL", findings=[finding]
                    )))
                    self.json_stdout(self.authorize_current(["GATE-F"]))
                    self.record_fixed_commit(["GATE-F"])
                    state = self.read_state()
                    self.assertEqual(state["workflow"]["current_gate"], gate)
                    self.assertEqual(
                        self.json_stdout(self.run_helper(
                            "next-action", "--state", self.state
                        ))["action"],
                        retry_action[gate],
                    )
                    if outcome == "RESOLVED":
                        state["tasks"]["1"]["cannot_verify"] = [
                            {"id": "STALE-HANDOFF", "summary": "Resolved before retry"}
                        ]
                        self.state.write_text(json.dumps(state), encoding="utf-8")
                    attempt = state["tasks"]["1"]["review_attempt"]
                    retry = [self.make_finding(
                        "GATE-F", gate=gate, owner_task_id=None, attempt=attempt,
                        required_fix_paths=["owned/one.txt"], rule_id=f"{gate}-F",
                        status="RESOLVED" if outcome == "RESOLVED" else "OPEN",
                        closure_actual=(
                            {"command": "check", "exit_code": 0, "output": "pass"}
                            if outcome == "RESOLVED" else None
                        ),
                    )]
                    if outcome == "REGRESSION":
                        retry.append(self.make_finding(
                            "GATE-NEW", gate=gate, owner_task_id=None, attempt=attempt,
                            required_fix_paths=["owned/one.txt"], rule_id=f"{gate}-NEW",
                            failure_key="new",
                        ))
                    verdict = "PASS" if outcome == "RESOLVED" else "FAIL"
                    self.json_stdout(self.import_observation(self.make_observation(
                        gate=gate, verdict=verdict, attempt=attempt, findings=retry
                    )))
                    state = self.read_state()
                    expected = {
                        "NO_PROGRESS": "HALTED_NO_PROGRESS",
                        "REGRESSION": "HALTED_REGRESSION",
                        "RESOLVED": next_status[gate],
                    }[outcome]
                    self.assertEqual(state["workflow"]["status"], expected)
                    if outcome == "RESOLVED":
                        owner = state["tasks"]["1"]
                        action = self.json_stdout(
                            self.run_helper("next-action", "--state", self.state)
                        )["action"]
                        self.assertEqual(
                            (
                                owner["status"],
                                state["workflow"]["current_task_id"],
                                state["workflow"]["current_gate"],
                                action,
                                owner["authorized_finding_ids"],
                                owner["open_blocking_findings"],
                                owner["previous_open_blocker_fingerprints"],
                                owner["cannot_verify"],
                            ),
                            (
                                "PASSED",
                                None,
                                next_status[gate],
                                post_pass_action[gate],
                                [],
                                [],
                                [],
                                [],
                            ),
                        )
                    event = state["history"][-1]
                    self.assertEqual(event["base_sha"], state["workflow"]["initial_base"])
                    self.assertEqual(event["head_sha"], state["workflow"]["current_head"])
                    if outcome == "RESOLVED":
                        self.assertEqual(event["task_id"], 1)
                        self.assertEqual(event["finding_ids"], ["GATE-F"])

    def test_all_pass_reaches_squash_approval_and_both_completion_states(self):
        self.init_state()
        self.pass_task_one()
        self.json_stdout(self.start_task(task_id=2))
        base = self.head()
        task_two_head = self.commit_file("owned/two.txt", "two\n", "feat(skill-forge): [Task 2] Task Two")
        self.report.write_text("DONE\n", encoding="utf-8")
        self.json_stdout(self.run_helper(
            "record-implementation", "--state", self.state, "--task-id", "2",
            "--base-head", base, "--new-head", task_two_head, "--report", self.report,
        ))
        self.json_stdout(self.import_observation(self.make_observation(verdict="PASS", task_id=2)))
        for gate in ("FINAL_REVIEW", "STRUCTURAL_VALIDATION", "BEHAVIORAL_VALIDATION"):
            self.json_stdout(self.import_observation(self.make_observation(gate=gate, verdict="PASS")))
        self.assertEqual(
            self.json_stdout(self.run_helper("next-action", "--state", self.state))["action"],
            "REQUEST_SQUASH_APPROVAL",
        )

        pristine = self.state.read_bytes()
        head = self.head()
        for result_name, expected_status in (("UNSQUASHED", "COMPLETE_UNSQUASHED"), ("SQUASHED", "COMPLETE")):
            with self.subTest(result=result_name):
                completion_state = self.repo / f"review-state-{result_name.lower()}.json"
                completion_state.write_bytes(pristine)
                self.json_stdout(self.run_helper(
                    "advance-gate", "--state", completion_state, "--gate", "SQUASH_APPROVAL",
                    "--result", result_name, "--head", head,
                ))
                state = json.loads(completion_state.read_text(encoding="utf-8"))
                self.assertEqual(state["workflow"]["status"], expected_status)
                self.assertEqual(
                    self.json_stdout(self.run_helper("next-action", "--state", completion_state))["action"],
                    "COMPLETE",
                )

    def test_review_package_contains_full_multi_commit_range_and_refuses_overwrite(self):
        second = self.commit_file("owned/one.txt", "one\n", "one")
        third = self.commit_file("owned/two.txt", "two\n", "feat(skill-forge): [Task 2] Task Two")
        output = self.repo / "review.diff"
        result = self.json_stdout(self.run_helper(
            "review-package", "--repo-root", self.repo, "--base", self.initial_base,
            "--head", third, "--output", output,
        ))
        text = output.read_text(encoding="utf-8")
        self.assertIn(f"# Review package: {self.initial_base}..{third}", text)
        self.assertIn("## Commits", text)
        self.assertIn(second[:7], text)
        self.assertIn(third[:7], text)
        self.assertIn("## Files changed", text)
        self.assertIn("## Diff", text)
        self.assertIn("owned/one.txt", text)
        self.assertIn("owned/two.txt", text)
        self.assertEqual(result["commit_count"], 2)
        self.json_error(self.run_helper(
            "review-package", "--repo-root", self.repo, "--base", self.initial_base,
            "--head", third, "--output", output,
        ), "OUTPUT_EXISTS")

    def test_plan_task_query_supports_only_stable_run_dir_markdown_and_json_output(self):
        run_dir = self.repo / ".skill-forge" / "run-1"
        run_dir.mkdir(parents=True)
        run_plan = run_dir / "plan.yaml"
        run_plan.write_bytes(self.plan.read_bytes())
        markdown_output = run_dir / "task.md"
        json_output = run_dir / "task.json"
        markdown = subprocess.run(
            [sys.executable, str(PLAN_QUERY), str(run_plan), "1", "--output", str(markdown_output), "--format", "markdown"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertEqual(Path(markdown.stdout.strip()), markdown_output.resolve())
        self.assertIn("## Global Constraints", markdown_output.read_text(encoding="utf-8"))
        result = subprocess.run(
            [sys.executable, str(PLAN_QUERY), str(run_plan), "1", "--output", str(json_output), "--format", "json"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(json_output.read_text(encoding="utf-8"))
        self.assertEqual(
            set(payload), {"schema_version", "goal", "architecture", "global_constraints", "task"}
        )
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["task"]["id"], 1)
        self.assertEqual(payload["task"]["meta"]["risk_level"], "L3")
        self.assertEqual(payload["task"]["meta"]["review_policy"], "task-and-final")
        self.assertEqual(payload["global_constraints"], ["Do not exceed ownership", "Use one shared budget"])
        duplicate = subprocess.run(
            [sys.executable, str(PLAN_QUERY), str(run_plan), "1", "--output", str(json_output), "--format", "json"],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("output already exists", duplicate.stderr)
        missing_output = subprocess.run(
            [sys.executable, str(PLAN_QUERY), str(run_plan), "2"],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(missing_output.returncode, 0)
        self.assertIn("--output", missing_output.stderr)
        outside = subprocess.run(
            [sys.executable, str(PLAN_QUERY), str(run_plan), "2", "--output", str(self.repo / "outside.md")],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(outside.returncode, 0)
        self.assertIn("output must be inside plan run directory", outside.stderr)


if __name__ == "__main__":
    unittest.main()
