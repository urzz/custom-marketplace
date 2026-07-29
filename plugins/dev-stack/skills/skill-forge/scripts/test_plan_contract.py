#!/usr/bin/env python3
"""Tests for the compact Skill Forge Plan contract."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from plan_contract import PlanContractError, validate_plan


SCRIPT = Path(__file__).with_name("plan_contract.py")


class PlanContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name) / "repo"
        self.run = self.repo / ".skill-forge" / "example-change"
        self.run.mkdir(parents=True)
        self.spec = self.run / "spec.md"
        self.plan = self.run / "plan.yaml"
        self.spec.write_text("# Confirmed Spec\n", encoding="utf-8")
        (self.repo / "existing").mkdir()
        (self.repo / "existing" / "skill.md").write_text("current\n", encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def base_plan(self):
        return {
            "schema_version": 1,
            "spec": "spec.md",
            "spec_sha256": hashlib.sha256(self.spec.read_bytes()).hexdigest(),
            "impacts": {
                "trigger_or_behavior_changed": True,
                "script_changed": False,
                "agent_permissions_changed": False,
                "external_side_effects_changed": False,
            },
            "tasks": [
                {
                    "id": 1,
                    "name": "Update workflow",
                    "files": {
                        "create": ["new/with space.md"],
                        "modify": ["existing/skill.md"],
                        "delete": [],
                    },
                    "steps": ["Implement the confirmed behavior"],
                    "acceptance": ["The deterministic contract passes"],
                    "checks": ["rg -n 'TODO' existing/skill.md"],
                }
            ],
        }

    def write_plan(self, payload=None):
        payload = self.base_plan() if payload is None else payload
        self.plan.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return payload

    def assert_error(self, code, plan_path=None, repo_root=None):
        with self.assertRaises(PlanContractError) as caught:
            validate_plan(plan_path or self.plan, repo_root or self.repo)
        self.assertEqual(caught.exception.code, code)

    def test_valid_plan_and_real_cli_examples(self):
        self.write_plan()
        summary = validate_plan(self.plan, self.repo)
        self.assertEqual(summary["task_count"], 1)
        self.assertEqual(summary["file_counts"], {"create": 1, "modify": 1, "delete": 0})

        hash_result = subprocess.run(
            [sys.executable, str(SCRIPT), "hash-spec", str(self.spec)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(hash_result.returncode, 0, hash_result.stderr)
        self.assertEqual(hash_result.stdout.strip(), self.base_plan()["spec_sha256"])

        validate_result = subprocess.run(
            [sys.executable, str(SCRIPT), "validate", str(self.plan), "--repo-root", str(self.repo)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(validate_result.returncode, 0, validate_result.stderr)
        self.assertTrue(json.loads(validate_result.stdout)["ok"])

    def test_rejects_duplicate_yaml_key_and_alias(self):
        payload = self.base_plan()
        dumped = yaml.safe_dump(payload, sort_keys=False)
        duplicated = dumped.replace("  script_changed: false\n", "  script_changed: false\n  script_changed: true\n")
        self.plan.write_text(duplicated, encoding="utf-8")
        self.assert_error("DUPLICATE_YAML_KEY")

        self.plan.write_text("schema_version: &version 1\nspec: spec.md\nspec_sha256: *version\n", encoding="utf-8")
        self.assert_error("YAML_ALIAS_NOT_ALLOWED")

    def test_rejects_spec_drift_and_invalid_reference(self):
        payload = self.write_plan()
        self.spec.write_text("# Changed after confirmation\n", encoding="utf-8")
        self.assert_error("SPEC_HASH_MISMATCH")

        payload["spec"] = "other.md"
        self.write_plan(payload)
        self.assert_error("INVALID_SPEC_REFERENCE")

    def test_rejects_duplicate_task_id(self):
        payload = self.base_plan()
        second = deepcopy(payload["tasks"][0])
        second["files"] = {"create": ["new/second.md"], "modify": [], "delete": []}
        payload["tasks"].append(second)
        self.write_plan(payload)
        self.assert_error("DUPLICATE_TASK_ID")

    def test_rejects_ownership_overlap_within_or_across_tasks(self):
        for across_tasks in (False, True):
            with self.subTest(across_tasks=across_tasks):
                payload = self.base_plan()
                if across_tasks:
                    payload["tasks"].append({
                        "id": 2,
                        "name": "Second task",
                        "files": {"create": ["new/with space.md"], "modify": [], "delete": []},
                        "steps": ["Implement second task"],
                        "acceptance": ["Second task passes"],
                        "checks": ["true"],
                    })
                else:
                    payload["tasks"][0]["files"]["delete"] = ["existing/skill.md"]
                self.write_plan(payload)
                self.assert_error("OWNERSHIP_OVERLAP")

    def test_rejects_unsafe_or_annotated_paths(self):
        bad_paths = (
            "/absolute.md",
            "../escape.md",
            "nested/../escape.md",
            "nested\\windows.md",
            "nested/*.md",
            "new/file.md (new)",
            " new/file.md",
        )
        for path in bad_paths:
            with self.subTest(path=path):
                payload = self.base_plan()
                payload["tasks"][0]["files"] = {"create": [path], "modify": [], "delete": []}
                self.write_plan(payload)
                self.assert_error("INVALID_REPO_PATH")

    def test_rejects_path_that_resolves_outside_repo(self):
        with tempfile.TemporaryDirectory() as outside_directory:
            (self.repo / "escape").symlink_to(outside_directory, target_is_directory=True)
            payload = self.base_plan()
            payload["tasks"][0]["files"] = {"create": ["escape/new.md"], "modify": [], "delete": []}
            self.write_plan(payload)
            self.assert_error("PATH_OUTSIDE_REPO")

    def test_rejects_file_precondition_mismatches(self):
        payload = self.base_plan()
        payload["tasks"][0]["files"] = {"create": ["existing/skill.md"], "modify": [], "delete": []}
        self.write_plan(payload)
        self.assert_error("CREATE_PATH_EXISTS")

        for operation in ("modify", "delete"):
            with self.subTest(operation=operation):
                payload = self.base_plan()
                payload["tasks"][0]["files"] = {"create": [], "modify": [], "delete": []}
                payload["tasks"][0]["files"][operation] = ["missing.md"]
                self.write_plan(payload)
                self.assert_error(f"{operation.upper()}_PATH_MISSING")

    def test_rejects_empty_checks_and_placeholders(self):
        payload = self.base_plan()
        payload["tasks"][0]["checks"] = []
        self.write_plan(payload)
        self.assert_error("INVALID_CHECKS")

        for field, value in (("name", "TODO"), ("steps", ["Implement TBD"]), ("acceptance", ["[待填写]"])):
            with self.subTest(field=field):
                payload = self.base_plan()
                payload["tasks"][0][field] = value
                self.write_plan(payload)
                self.assert_error("PLACEHOLDER_FOUND")

    def test_rejects_impact_shape_and_type(self):
        payload = self.base_plan()
        payload["impacts"]["extra"] = False
        self.write_plan(payload)
        self.assert_error("INVALID_IMPACTS")

        payload = self.base_plan()
        payload["impacts"]["script_changed"] = 0
        self.write_plan(payload)
        self.assert_error("INVALID_IMPACT_VALUE")

    def test_rejects_extra_task_keys_and_non_positive_ids(self):
        payload = self.base_plan()
        payload["tasks"][0]["meta"] = {}
        self.write_plan(payload)
        self.assert_error("INVALID_TASK_SCHEMA")

        for task_id in (0, -1, True, "1"):
            with self.subTest(task_id=task_id):
                payload = self.base_plan()
                payload["tasks"][0]["id"] = task_id
                self.write_plan(payload)
                self.assert_error("INVALID_TASK_ID")

    def test_rejects_plan_outside_repo(self):
        self.write_plan()
        with tempfile.TemporaryDirectory() as outside_directory:
            outside = Path(outside_directory) / "plan.yaml"
            outside.write_bytes(self.plan.read_bytes())
            self.assert_error("PLAN_OUTSIDE_REPO", plan_path=outside)

    def test_rejects_plan_outside_skill_forge_run(self):
        self.write_plan()
        misplaced = self.repo / "plan.yaml"
        misplaced.write_bytes(self.plan.read_bytes())
        self.assert_error("INVALID_PLAN_PATH", plan_path=misplaced)


if __name__ == "__main__":
    unittest.main()
