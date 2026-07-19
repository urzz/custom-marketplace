"""
Contract helper tests.

## Contents

- [Fixture builders](#fixture-builders)
- [Validation and derivation tests](#validation-and-derivation-tests)
- [CLI envelope tests](#cli-envelope-tests)
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "contract-helper.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("contract_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract_text(extra=""):
    return textwrap.dedent(f"""
    schema_version: 1
    change_id: change-alpha
    contract_version: v1
    intent:
      goals:
        - Ship deterministic helpers
      non_goals:
        - Do not approve gates
      confirmed_answers: []
    acceptance:
      - Helpers validate contracts
    constraints:
      - Stay inside mutation targets
    design:
      boundaries: Only helpers derive authority.
      data_flow: Contract and context feed helper outputs.
      contracts: JSON envelopes are stable.
      tradeoffs: YAML subset is intentionally small.
    tasks:
      - id: T1
        name: First task
        owner: worker-a
        dependencies: []
        mutation_targets:
          - path: plugins/nuclio-plugin/scripts/a.py
            mode: create
        handoffs:
          inputs: []
          outputs:
            - artifact-a
          report: reports/t1.md
          evidence:
            - evidence/t1.json
        checks:
          focused:
            - name: focused
              command:
                - python3
                - -m
                - unittest
          full:
            - name: full
              command:
                - python3
                - -m
                - unittest
        rollback: Delete created file.
    context_policy:
      required:
        - base-context
      jit:
        - id: interface-jit
          retrieval_trigger: Need interface details
          budget: 2
      forbidden:
        - full_conversation
        - all_docs
      budget:
        total: 5
        by_audience:
          worker: 3
    validation:
      focused:
        - name: focused-change
          command:
            - python3
            - -m
            - unittest
      full:
        - name: full-change
          command:
            - python3
            - -m
            - unittest
      change_wide:
        - name: change-wide
          command:
            - python3
            - -m
            - unittest
    migration_or_rollout:
      detection: Detect legacy files explicitly.
      preview: Show migration preview.
      opt_in: User passes explicit opt-in.
      verification: Verify converted identities.
      rollback: Stop without silent conversion.
    {extra}
    """).strip() + "\n"


class ContractHelperTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()

    def write_contract(self, body):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "contract.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def load(self, body):
        return self.helper.load_contract(self.write_contract(body))

    def test_valid_simple_contract_summary_identity_and_ownership(self):
        contract = self.load(contract_text())
        summary = self.helper.build_summary(contract)
        self.assertFalse(summary["approval"])
        self.assertIn("not an approval", summary["approval_notice"])
        self.assertEqual(summary["acceptance_count"], 1)
        self.assertEqual(summary["task_graph"], [{"id": "T1", "dependencies": []}])
        identity = self.helper.build_identity(contract)
        self.assertEqual(identity["change_id"], "change-alpha")
        self.assertEqual(identity["contract_version"], "v1")
        self.assertRegex(identity["sha256"], r"^[0-9a-f]{64}$")
        ownership = self.helper.derive_ownership(contract)
        entry = ownership["paths"]["plugins/nuclio-plugin/scripts/a.py"]
        self.assertEqual(entry["owner_chain"], ["T1"])
        self.assertEqual(entry["final_owner"], "T1")

    def test_valid_complex_handoff_allows_linear_overlap(self):
        body = contract_text().replace(
            "context_policy:",
            """  - id: T2
        name: Second task
        owner: worker-b
        dependencies:
          - T1
        mutation_targets:
          - path: plugins/nuclio-plugin/scripts/a.py
            mode: modify
        handoffs:
          inputs:
            - artifact-a
          outputs:
            - artifact-b
          report: reports/t2.md
          evidence: []
        checks:
          focused:
            - name: focused2
              command:
                - python3
          full:
            - name: full2
              command:
                - python3
        rollback: Restore from T1 handoff.
context_policy:""",
        )
        contract = self.load(body)
        ownership = self.helper.derive_ownership(contract)
        entry = ownership["paths"]["plugins/nuclio-plugin/scripts/a.py"]
        self.assertEqual(entry["owner_chain"], ["T1", "T2"])
        self.assertEqual(entry["final_owner"], "T2")
        self.assertEqual(entry["incoming_handoff"]["from"], "T1")
        self.assertEqual(entry["outgoing_handoff"]["to"], "T2")

    def assert_contract_error(self, body, code):
        with self.assertRaises(self.helper.ProtocolError) as ctx:
            self.load(body)
        self.assertEqual(ctx.exception.code, code)

    def test_rejects_duplicate_task_ids(self):
        body = contract_text().replace(
            "context_policy:",
            """  - id: T1
        name: Duplicate task
        owner: worker-b
        dependencies: []
        mutation_targets:
          - path: plugins/nuclio-plugin/scripts/b.py
            mode: create
        handoffs:
          inputs: []
          outputs: []
        checks:
          focused:
            - name: focused2
              command:
                - python3
          full:
            - name: full2
              command:
                - python3
        rollback: Delete duplicate.
context_policy:""",
        )
        self.assert_contract_error(body, "DUPLICATE_TASK_ID")

    def test_rejects_dangling_dependency_and_cycle(self):
        dangling = contract_text().replace("dependencies: []", "dependencies:\n          - NOPE")
        self.assert_contract_error(dangling, "DANGLING_DEPENDENCY")
        cycle = contract_text().replace("dependencies: []", "dependencies:\n          - T1")
        self.assert_contract_error(cycle, "DEPENDENCY_CYCLE")

    def test_rejects_dangling_handoff_and_no_owner_acceptance(self):
        dangling = contract_text().replace("inputs: []", "inputs:\n            - missing-artifact")
        self.assert_contract_error(dangling, "DANGLING_HANDOFF")
        no_owner = contract_text().replace("owner: worker-a", "owner: ''")
        self.assert_contract_error(no_owner, "NO_OWNER_ACCEPTANCE")

    def test_rejects_empty_validation(self):
        empty = contract_text().replace("  focused:\n    - name: focused-change\n      command:\n        - python3\n        - -m\n        - unittest", "  focused: []")
        self.assert_contract_error(empty, "EMPTY_VALIDATION")

    def test_rejects_path_traversal_glob_protected_and_directory_paths(self):
        for bad_path in ["../x.py", "plugins/**/*.py", ".git/config", ".dev-docs/changes/x.md", ".superpowers/sdd/old.md", "plugins/nuclio-plugin/scripts/", "plugins/nuclio-plugin/scripts"]:
            body = contract_text().replace("plugins/nuclio-plugin/scripts/a.py", bad_path)
            self.assert_contract_error(body, "INVALID_MUTATION_PATH")

    def test_allows_future_concrete_file_path(self):
        future_path = "plugins/nuclio-plugin/scripts/future-contract-helper-output.py"
        self.assertFalse((ROOT / future_path).exists())
        contract = self.load(contract_text().replace("plugins/nuclio-plugin/scripts/a.py", future_path))
        self.assertEqual(contract["tasks"][0]["mutation_targets"][0]["path"], future_path)

    def test_rejects_overlap_without_handoff(self):
        body = contract_text().replace(
            "context_policy:",
            """  - id: T2
        name: Second task
        owner: worker-b
        dependencies:
          - T1
        mutation_targets:
          - path: plugins/nuclio-plugin/scripts/a.py
            mode: modify
        handoffs:
          inputs: []
          outputs: []
        checks:
          focused:
            - name: focused2
              command:
                - python3
          full:
            - name: full2
              command:
                - python3
        rollback: Restore.
context_policy:""",
        )
        self.assert_contract_error(body, "OWNERSHIP_OVERLAP")

    def test_identity_is_stable_for_semantic_equivalence_and_changes_on_authority(self):
        compact = self.load(contract_text())
        noisy = self.load("\n# comment\n" + contract_text().replace("change_id: change-alpha", "change_id: change-alpha  # inline"))
        self.assertEqual(self.helper.build_identity(compact)["sha256"], self.helper.build_identity(noisy)["sha256"])
        changed = self.load(contract_text().replace("Helpers validate contracts", "Helpers validate changed contracts"))
        self.assertNotEqual(self.helper.build_identity(compact)["sha256"], self.helper.build_identity(changed)["sha256"])

    def test_cli_error_envelope(self):
        path = self.write_contract(contract_text().replace("dependencies: []", "dependencies:\n          - NOPE"))
        proc = subprocess.run([sys.executable, str(HELPER), "validate", str(path)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        envelope = json.loads(proc.stderr)
        self.assertEqual(envelope["ok"], False)
        self.assertEqual(envelope["code"], "DANGLING_DEPENDENCY")


if __name__ == "__main__":
    unittest.main()
