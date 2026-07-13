import importlib.util
import inspect
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).with_name("task-helper.py")


def load_task_helper_module():
    spec = importlib.util.spec_from_file_location("task_helper_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALID_PLAN = """tasks:
  - id: T1
    title: First task
    depends_on: []
    acceptance:
      - Preserve state fields
    verification:
      commands:
        - python3 -m unittest t1
    rollback:
      strategy: Revert T1 files
  - id: T2
    title: Second task
    depends_on: [T1]
    acceptance:
      - Extract only matching context
    verification:
      notes: Manual check is sufficient
    rollback:
      strategy: Revert T2 files
metadata:
  owner: test
"""


CANONICAL_PLAN = """change_id: 0001
 title: wrong indentation ignored before tasks
title: Canonical compatibility
tasks:
  - id: T4A
    title: Align Design output
    status: pending
    depends_on: []
    files_hint:
      - plugins/nuclio-plugin/skills/design/SKILL.md
      - plugins/nuclio-plugin/scripts/task-helper.py
    context_refs:
      - plugins/nuclio-plugin/references/protocol.md
      - design-task-4
    mutation_targets:
      - plugins/nuclio-plugin/scripts/task-helper.py
    ownership_handoffs: []
    acceptance:
      - Accept canonical task metadata
    verification:
      commands:
        - python3 -m unittest plugins/nuclio-plugin/scripts/test_task_helper.py
    rollback:
      strategy: Revert helper compatibility changes
  - id: T4B
    title: Accept migrated status fields
    status: completed
    depends_on: [T4A]
    files_hint: []
    context_refs: []
    mutation_targets: []
    ownership_handoffs: []
    acceptance:
      - Accept inline empty canonical lists
    verification:
      commands: []
      notes: "Static validation is sufficient"
    rollback:
      strategy: Revert T4B files
verification:
  notes: top-level verification is outside task parsing
rollback:
  strategy: top-level rollback is outside task parsing
"""


CANONICAL_IMPLEMENT_MANIFEST = [
    {"path": "docs/canonical.md", "kind": "reference", "mode": "required", "reason": "shared"},
    {"path": "src/canonical.py", "kind": "source", "mode": "required", "reason": "t4a", "tasks": ["T4A"]},
]
CANONICAL_VERIFY_MANIFEST = [
    {"path": "tests/canonical.txt", "kind": "test", "mode": "required", "reason": "verify"},
]


IMPLEMENT_MANIFEST = [
    {"path": "docs/all.md", "kind": "reference", "mode": "required", "reason": "all tasks"},
    {"path": "docs/missing-tasks.md", "kind": "reference", "mode": "jit", "reason": "default all"},
    {"path": "src/t1.py", "kind": "source", "mode": "required", "reason": "t1", "tasks": ["T1"]},
    {"path": "src/t2.py", "kind": "source", "mode": "required", "reason": "t2", "tasks": ["T2"]},
]
VERIFY_MANIFEST = [
    {"path": "tests/t1.txt", "kind": "test", "mode": "required", "reason": "verify t1", "tasks": ["T1"]},
]


def render_task_block(task_id, depends_on="[]", mutation_targets=None, ownership_handoffs=None, files_hint=None):
    mutation_targets = [] if mutation_targets is None else mutation_targets
    ownership_handoffs = [] if ownership_handoffs is None else ownership_handoffs
    files_hint = [] if files_hint is None else files_hint
    lines = [
        f"  - id: {task_id}",
        f"    title: Task {task_id}",
        "    status: pending",
        f"    depends_on: {depends_on}",
    ]
    if files_hint:
        lines.append("    files_hint:")
        lines.extend(f"      - {path}" for path in files_hint)
    else:
        lines.append("    files_hint: []")
    lines.append("    context_refs: []")
    if mutation_targets:
        lines.append("    mutation_targets:")
        lines.extend(f"      - {path}" for path in mutation_targets)
    else:
        lines.append("    mutation_targets: []")
    if ownership_handoffs:
        lines.append("    ownership_handoffs:")
        for handoff in ownership_handoffs:
            lines.append(f"      - path: {handoff['path']}")
            lines.append(f"        from_task: {handoff['from_task']}")
            lines.append(f"        to_task: {handoff['to_task']}")
    else:
        lines.append("    ownership_handoffs: []")
    lines.extend([
        "    acceptance:",
        f"      - Accept {task_id}",
        "    verification:",
        "      commands:",
        f"        - python3 -m unittest {task_id}",
        "    rollback:",
        f"      strategy: Revert {task_id}",
    ])
    return "\n".join(lines)


def ownership_plan(*task_blocks):
    return "tasks:\n" + "\n".join(task_blocks) + "\n"


class TaskHelperCliTests(unittest.TestCase):
    def run_helper(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def stdout_json(self, result):
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"stdout was not JSON: {result.stdout!r}; stderr={result.stderr!r}; {exc}")

    def write_jsonl(self, path, entries):
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")

    def make_change(self, root, plan=VALID_PLAN, implement_entries=None, verify_entries=None):
        change = pathlib.Path(root) / "change"
        (change / "context").mkdir(parents=True)
        (change / "state.json").write_text(
            json.dumps({"phase": "implement", "status": "ready", "gates": {"design": "approved"}}),
            encoding="utf-8",
        )
        (change / "plan.yaml").write_text(plan, encoding="utf-8")
        self.write_jsonl(change / "context" / "implement.jsonl", IMPLEMENT_MANIFEST if implement_entries is None else implement_entries)
        self.write_jsonl(change / "context" / "verify.jsonl", VERIFY_MANIFEST if verify_entries is None else verify_entries)
        return change

    def make_ownership_change(self, root, plan):
        return self.make_change(
            root,
            plan=plan,
            implement_entries=[{"path": "docs/ownership.md", "kind": "reference", "mode": "required", "reason": "ownership", "tasks": ["*"]}],
            verify_entries=[{"path": "tests/ownership.txt", "kind": "test", "mode": "required", "reason": "ownership", "tasks": ["*"]}],
        )

    def test_validate_change_accepts_valid_plan_and_reports_stable_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(tmp)

            result = self.run_helper("validate-change", "--change", str(change))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = self.stdout_json(result)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["change_path"], str(change))
            self.assertEqual(payload["task_order"], ["T1", "T2"])
            self.assertEqual(payload["task_count"], 2)
            self.assertEqual(payload["implement_manifest_entries"], 4)
            self.assertEqual(payload["verify_manifest_entries"], 1)

    def test_extract_task_writes_single_task_brief_with_matching_normalized_manifest_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(tmp)
            output = pathlib.Path(tmp) / "briefs" / "T1.md"

            result = self.run_helper("extract-task", "--change", str(change), "--task", "T1", "--output", str(output))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = self.stdout_json(result)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["task"], "T1")
            brief = output.read_text(encoding="utf-8")
            self.assertIn("# Nucl.io Task Brief: T1", brief)
            self.assertIn("## Gate and State Summary", brief)
            self.assertIn("## Original Task Definition", brief)
            self.assertIn("## Matching Context Manifest Entries", brief)
            self.assertIn("## Evidence Output Contract", brief)
            self.assertIn("  - id: T1\n", brief)
            self.assertNotIn("  - id: T2\n", brief)
            self.assertIn('"tasks": ["*"]', brief)
            self.assertIn('"path": "docs/missing-tasks.md"', brief)
            self.assertIn('"path": "src/t1.py"', brief)
            self.assertNotIn('"path": "src/t2.py"', brief)
            self.assertIn("- Design Gate: `approved`", brief)
            self.assertIn("- Implementer report: `evidence/tasks/T1/implementer.md`", brief)

    def test_validate_change_accepts_canonical_task_metadata_and_extracts_verbatim_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(
                tmp,
                plan=CANONICAL_PLAN,
                implement_entries=CANONICAL_IMPLEMENT_MANIFEST,
                verify_entries=CANONICAL_VERIFY_MANIFEST,
            )
            output = pathlib.Path(tmp) / "briefs" / "T4A.md"

            validate = self.run_helper("validate-change", "--change", str(change))
            self.assertEqual(validate.returncode, 0, validate.stdout + validate.stderr)
            payload = self.stdout_json(validate)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["task_order"], ["T4A", "T4B"])

            extract = self.run_helper("extract-task", "--change", str(change), "--task", "T4A", "--output", str(output))
            self.assertEqual(extract.returncode, 0, extract.stdout + extract.stderr)
            brief = output.read_text(encoding="utf-8")
            self.assertIn("    status: pending\n", brief)
            self.assertIn("    files_hint:\n      - plugins/nuclio-plugin/skills/design/SKILL.md\n", brief)
            self.assertIn("    context_refs:\n      - plugins/nuclio-plugin/references/protocol.md\n      - design-task-4\n", brief)
            self.assertNotIn("  - id: T4B\n", brief)

    def assert_invalid_plan(self, plan, expected_fragment):
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_ownership_change(tmp, plan)
            result = self.run_helper("validate-change", "--change", str(change))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = self.stdout_json(result)
            self.assertFalse(payload["ok"])
            self.assertIn(expected_fragment, payload["error"])

    def test_validate_change_rejects_invalid_plan_shapes(self):
        cases = [
            (VALID_PLAN.replace("  - id: T2", "  - id: T1"), "duplicate task id"),
            (VALID_PLAN.replace("depends_on: [T1]", "depends_on: [NOPE]"), "unknown dependency"),
            (VALID_PLAN.replace("depends_on: []", "depends_on: [T2]"), "dependency cycle"),
            (VALID_PLAN.replace("    acceptance:\n      - Preserve state fields\n", ""), "missing acceptance"),
            (VALID_PLAN.replace("    verification:\n      commands:\n        - python3 -m unittest t1\n", ""), "missing verification"),
            (VALID_PLAN.replace("    rollback:\n      strategy: Revert T1 files\n", ""), "missing rollback"),
            (VALID_PLAN.replace("  - id: T1", "    - id: T1"), "invalid tasks block"),
        ]
        for plan, expected in cases:
            with self.subTest(expected=expected):
                self.assert_invalid_plan(plan, expected)

    def test_validate_change_rejects_duplicate_inline_dependencies_with_structured_json(self):
        plan = VALID_PLAN.replace("depends_on: [T1]", "depends_on: [T1, T1]", 1)
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(tmp, plan=plan)
            result = self.run_helper("validate-change", "--change", str(change))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        payload = self.stdout_json(result)
        self.assertFalse(payload["ok"])
        self.assertIn("duplicate dependency", payload["error"])
        self.assertIn("T2", payload["detail"])
        self.assertIn("T1", payload["detail"])

    def test_validate_change_rejects_duplicate_nested_dependencies_with_structured_json(self):
        plan = VALID_PLAN.replace("depends_on: [T1]", "depends_on:\n      - T1\n      - T1", 1)
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(tmp, plan=plan)
            result = self.run_helper("validate-change", "--change", str(change))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        payload = self.stdout_json(result)
        self.assertFalse(payload["ok"])
        self.assertIn("duplicate dependency", payload["error"])
        self.assertIn("T2", payload["detail"])
        self.assertIn("T1", payload["detail"])

    def test_validate_change_rejects_same_path_multi_owner_without_handoff(self):
        plan = ownership_plan(
            render_task_block("T1", mutation_targets=["src/shared.py"]),
            render_task_block("T4", depends_on="[T1]", mutation_targets=["src/shared.py"]),
        )
        self.assert_invalid_plan(plan, "ownership handoff")

    def test_validate_change_rejects_handoff_without_dependency(self):
        plan = ownership_plan(
            render_task_block("T1", mutation_targets=["src/shared.py"]),
            render_task_block(
                "T4",
                mutation_targets=["src/shared.py"],
                ownership_handoffs=[{"path": "src/shared.py", "from_task": "T1", "to_task": "T4"}],
            ),
        )
        self.assert_invalid_plan(plan, "handoff dependency")

    def test_validate_change_accepts_linear_handoff_and_derives_single_final_owner(self):
        plan = ownership_plan(
            render_task_block("T1", mutation_targets=["src/shared.py"]),
            render_task_block(
                "T4",
                depends_on="[T1]",
                mutation_targets=["src/shared.py"],
                ownership_handoffs=[{"path": "src/shared.py", "from_task": "T1", "to_task": "T4"}],
            ),
            render_task_block(
                "T9",
                depends_on="[T4]",
                mutation_targets=["src/shared.py"],
                ownership_handoffs=[{"path": "src/shared.py", "from_task": "T4", "to_task": "T9"}],
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_ownership_change(tmp, plan)
            result = self.run_helper("validate-change", "--change", str(change))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = self.stdout_json(result)
        self.assertEqual(payload["ownership_table"], [
            {
                "path": "src/shared.py",
                "owners": ["T1", "T4", "T9"],
                "handoffs": [
                    {"path": "src/shared.py", "from_task": "T1", "to_task": "T4"},
                    {"path": "src/shared.py", "from_task": "T4", "to_task": "T9"},
                ],
                "final_owner": "T9",
            }
        ])
        self.assertEqual(payload["task_contract"]["ownership_table"][0]["final_owner"], "T9")
        self.assertNotIn("files_hint", json.dumps(payload["task_contract"], sort_keys=True))
        self.assertNotIn("status", json.dumps(payload["task_contract"], sort_keys=True))

    def test_validate_change_accepts_reverse_plan_order_handoff(self):
        plan = ownership_plan(
            render_task_block(
                "T4",
                depends_on="[T1]",
                mutation_targets=["src/shared.py"],
                ownership_handoffs=[{"path": "src/shared.py", "from_task": "T1", "to_task": "T4"}],
            ),
            render_task_block("T1", mutation_targets=["src/shared.py"]),
        )
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_ownership_change(tmp, plan)
            result = self.run_helper("validate-change", "--change", str(change))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.stdout_json(result)["ownership_table"][0]
        self.assertEqual(row["owners"], ["T1", "T4"])
        self.assertEqual(row["final_owner"], "T4")

    def test_validate_change_accepts_reverse_plan_order_multi_hop_handoff(self):
        plan = ownership_plan(
            render_task_block(
                "T9",
                depends_on="[T4]",
                mutation_targets=["src/shared.py"],
                ownership_handoffs=[{"path": "src/shared.py", "from_task": "T4", "to_task": "T9"}],
            ),
            render_task_block("T1", mutation_targets=["src/shared.py"]),
            render_task_block(
                "T4",
                depends_on="[T1]",
                mutation_targets=["src/shared.py"],
                ownership_handoffs=[{"path": "src/shared.py", "from_task": "T1", "to_task": "T4"}],
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_ownership_change(tmp, plan)
            result = self.run_helper("validate-change", "--change", str(change))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.stdout_json(result)["ownership_table"][0]
        self.assertEqual(row["owners"], ["T1", "T4", "T9"])
        self.assertEqual(row["final_owner"], "T9")
        self.assertEqual(
            [(edge["from_task"], edge["to_task"]) for edge in row["handoffs"]],
            [("T1", "T4"), ("T4", "T9")],
        )

    def test_validate_change_rejects_control_plane_mutation_targets_but_not_files_hints(self):
        blocked = [
            ".git",
            ".git/config",
            ".dev-docs/changes",
            ".dev-docs/changes/change/state.json",
            ".superpowers/sdd",
            ".superpowers/sdd/task-1-report.md",
        ]
        for path in blocked:
            with self.subTest(path=path):
                self.assert_invalid_plan(
                    ownership_plan(render_task_block("T1", mutation_targets=[path])),
                    "invalid mutation target",
                )

        plan = ownership_plan(render_task_block("T1", files_hint=blocked))
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_ownership_change(tmp, plan)
            result = self.run_helper("validate-change", "--change", str(change))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.stdout_json(result)["ownership_table"], [])

    def test_task_contract_is_stable_across_equivalent_ownership_declaration_order(self):
        handoffs = [
            {"path": "src/z.py", "from_task": "T1", "to_task": "T2"},
            {"path": "src/a.py", "from_task": "T1", "to_task": "T2"},
        ]
        first = ownership_plan(
            render_task_block("T1", mutation_targets=["src/z.py", "go.mod", "src/a.py"]),
            render_task_block("T2", depends_on="[T1]", mutation_targets=["src/z.py", "src/a.py"], ownership_handoffs=handoffs),
        )
        second = ownership_plan(
            render_task_block("T1", mutation_targets=["src/a.py", "src/z.py", "go.mod"]),
            render_task_block("T2", depends_on="[T1]", mutation_targets=["src/a.py", "src/z.py"], ownership_handoffs=list(reversed(handoffs))),
        )
        contracts = []
        for plan in (first, second):
            with tempfile.TemporaryDirectory() as tmp:
                change = self.make_ownership_change(tmp, plan)
                result = self.run_helper("validate-change", "--change", str(change))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                contracts.append(self.stdout_json(result)["task_contract"])
        self.assertEqual(contracts[0], contracts[1])
        self.assertEqual(contracts[0]["tasks"][0]["mutation_targets"], ["go.mod", "src/a.py", "src/z.py"])

    def test_extract_task_does_not_build_task_contract(self):
        helper = load_task_helper_module()
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(tmp)
            output = pathlib.Path(tmp) / "brief.md"
            args = helper.argparse.Namespace(change=change, task="T1", output=output)
            with mock.patch.object(helper, "build_task_contract", side_effect=AssertionError("extract built contract")):
                result = helper.extract_task(args)
        self.assertEqual(result, 0)

    def test_ownership_handoffs_reuse_precomputed_dependency_ancestors(self):
        helper = load_task_helper_module()
        tasks = []
        for index in range(40):
            task_id = f"T{index}"
            tasks.append(
                {
                    "id": task_id,
                    "depends_on": [] if index == 0 else [f"T{index - 1}"],
                    "mutation_targets": ["src/shared.py"],
                    "ownership_handoffs": [] if index == 0 else [{"path": "src/shared.py", "from_task": f"T{index - 1}", "to_task": task_id}],
                }
            )
        original = helper.build_dependency_ancestors
        with mock.patch.object(helper, "build_dependency_ancestors", wraps=original) as cached:
            table = helper.build_ownership_table(tasks)
        self.assertEqual(cached.call_count, 1)
        self.assertEqual(table[0]["final_owner"], "T39")

    def test_validate_change_rejects_handoff_cycle_branch_gap_and_dangling_task(self):
        cases = [
            (
                ownership_plan(
                    render_task_block("T1", depends_on="[T4]", mutation_targets=["src/shared.py"], ownership_handoffs=[{"path": "src/shared.py", "from_task": "T4", "to_task": "T1"}]),
                    render_task_block("T4", depends_on="[T1]", mutation_targets=["src/shared.py"], ownership_handoffs=[{"path": "src/shared.py", "from_task": "T1", "to_task": "T4"}]),
                ),
                "dependency cycle",
            ),
            (
                ownership_plan(
                    render_task_block("T1", mutation_targets=["src/shared.py"]),
                    render_task_block("T4", depends_on="[T1]", mutation_targets=["src/shared.py"], ownership_handoffs=[{"path": "src/shared.py", "from_task": "T1", "to_task": "T4"}]),
                    render_task_block("T9", depends_on="[T1]", mutation_targets=["src/shared.py"], ownership_handoffs=[{"path": "src/shared.py", "from_task": "T1", "to_task": "T9"}]),
                ),
                "ownership branch",
            ),
            (
                ownership_plan(
                    render_task_block("T1", mutation_targets=["src/shared.py"]),
                    render_task_block("T4", depends_on="[T1]", mutation_targets=["src/shared.py"]),
                    render_task_block("T9", depends_on="[T4]", mutation_targets=["src/shared.py"], ownership_handoffs=[{"path": "src/shared.py", "from_task": "T1", "to_task": "T9"}]),
                ),
                "ownership handoff gap",
            ),
            (
                ownership_plan(
                    render_task_block("T1", mutation_targets=["src/shared.py"]),
                    render_task_block("T4", depends_on="[T1]", mutation_targets=["src/shared.py"], ownership_handoffs=[{"path": "src/shared.py", "from_task": "NOPE", "to_task": "T4"}]),
                ),
                "unknown handoff task",
            ),
        ]
        for plan, expected in cases:
            with self.subTest(expected=expected):
                self.assert_invalid_plan(plan, expected)

    def test_validate_change_rejects_unsafe_and_aliased_mutation_targets(self):
        bad_values = [
            "/abs.md",
            "../up.md",
            "safe/../up.md",
            "safe/./same.md",
            "docs//same.md",
            "docs\\same.md",
            "docs/*.md",
            "docs/?.md",
            "docs/[abc].md",
            "docs/",
            ".",
            "./",
            ".dev-docs",
            "~",
            "~/secret.md",
            "file:secret.md",
            "https://example.com/file.md",
            "C:/absolute/file.md",
            "\\\\server\\share\\file.md",
        ]
        for bad_value in bad_values:
            with self.subTest(value=bad_value):
                plan = ownership_plan(render_task_block("T1", mutation_targets=[bad_value]))
                self.assert_invalid_plan(plan, "invalid task path")
        duplicate_plan = ownership_plan(render_task_block("T1", mutation_targets=["src/a.py", "src/a.py"]))
        self.assert_invalid_plan(duplicate_plan, "duplicate mutation target")

    def test_validate_change_does_not_treat_files_hint_as_ownership(self):
        plan = ownership_plan(
            render_task_block("T1", files_hint=["src/shared.py"]),
            render_task_block("T4", depends_on="[T1]", files_hint=["src/shared.py"]),
        )
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_ownership_change(tmp, plan)
            result = self.run_helper("validate-change", "--change", str(change))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = self.stdout_json(result)
        self.assertEqual(payload["ownership_table"], [])
        self.assertNotIn("src/shared.py", json.dumps(payload["task_contract"].get("ownership_table", [])))

    def test_extract_task_includes_only_approved_ownership_slice(self):
        plan = ownership_plan(
            render_task_block("T1", mutation_targets=["src/shared.py", "src/t1.py"]),
            render_task_block(
                "T4",
                depends_on="[T1]",
                mutation_targets=["src/shared.py"],
                ownership_handoffs=[{"path": "src/shared.py", "from_task": "T1", "to_task": "T4"}],
            ),
            render_task_block(
                "T9",
                depends_on="[T4]",
                mutation_targets=["src/shared.py"],
                ownership_handoffs=[{"path": "src/shared.py", "from_task": "T4", "to_task": "T9"}],
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_ownership_change(tmp, plan)
            output = pathlib.Path(tmp) / "briefs" / "T4.md"
            result = self.run_helper("extract-task", "--change", str(change), "--task", "T4", "--output", str(output))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            brief = output.read_text(encoding="utf-8")

        self.assertIn("## Approved Ownership Slice", brief)
        self.assertIn('"mutation_targets": ["src/shared.py"]', brief)
        self.assertIn('"incoming_handoffs": [{"from_task": "T1", "path": "src/shared.py", "to_task": "T4"}]', brief)
        self.assertIn('"outgoing_handoffs": [{"from_task": "T4", "path": "src/shared.py", "to_task": "T9"}]', brief)
        self.assertIn('"final_owners": [{"final_owner": "T9", "path": "src/shared.py"}]', brief)
        self.assertIn("files_hint is non-authoritative", brief)
        self.assertNotIn('"path": "src/t1.py"', brief)

    def test_extract_task_rejects_unknown_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(tmp)
            output = pathlib.Path(tmp) / "brief.md"

            result = self.run_helper("extract-task", "--change", str(change), "--task", "NOPE", "--output", str(output))

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertFalse(self.stdout_json(result)["ok"])
            self.assertFalse(output.exists())

    def assert_invalid_manifest(self, implement_entries, expected_fragment):
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(tmp, implement_entries=implement_entries)
            result = self.run_helper("validate-change", "--change", str(change))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = self.stdout_json(result)
            self.assertFalse(payload["ok"])
            self.assertIn(expected_fragment, payload["error"])

    def assert_invalid_manifest_field_cli(self, manifest_name, field, value, expected_fragment):
        entry = {"path": "x.md", "kind": "reference", "mode": "required", "reason": "valid reason", "tasks": ["T1"]}
        entry[field] = value
        manifest_kwargs = {"implement_entries": IMPLEMENT_MANIFEST, "verify_entries": VERIFY_MANIFEST}
        manifest_kwargs[f"{manifest_name}_entries"] = [entry]
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(tmp, **manifest_kwargs)
            output = pathlib.Path(tmp) / "brief.md"
            commands = [
                ("validate-change", "--change", str(change)),
                ("extract-task", "--change", str(change), "--task", "T1", "--output", str(output)),
            ]
            for command in commands:
                with self.subTest(command=command[0]):
                    if output.exists():
                        output.unlink()
                    result = self.run_helper(*command)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    payload = self.stdout_json(result)
                    self.assertFalse(payload["ok"])
                    self.assertIn(expected_fragment, payload["error"])
                    self.assertFalse(output.exists())

    def test_manifest_kind_and_reason_must_be_non_empty_strings_for_implement_and_verify_cli(self):
        bad_values = [None, [], {}, 1, "", "   "]
        for manifest_name in ["implement", "verify"]:
            for field in ["kind", "reason"]:
                for value in bad_values:
                    with self.subTest(manifest=manifest_name, field=field, value=repr(value)):
                        self.assert_invalid_manifest_field_cli(manifest_name, field, value, f"invalid {field}")

    def test_manifest_kind_remains_open_non_empty_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(
                tmp,
                implement_entries=[{"path": "x.md", "kind": "custom-kind", "mode": "required", "reason": "valid", "tasks": ["T1"]}],
                verify_entries=[{"path": "y.md", "kind": "another.kind", "mode": "jit", "reason": "valid", "tasks": ["T2"]}],
            )

            result = self.run_helper("validate-change", "--change", str(change))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(self.stdout_json(result)["ok"])

    def test_validate_change_rejects_invalid_manifest_entries(self):
        bad_jsonl = "{bad json\n"
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(tmp)
            (change / "context" / "implement.jsonl").write_text(bad_jsonl, encoding="utf-8")
            result = self.run_helper("validate-change", "--change", str(change))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("invalid JSONL", self.stdout_json(result)["error"])

        cases = [
            ([[]], "manifest entry must be object"),
            ([{"path": "x.md", "kind": "reference", "mode": "later", "reason": "bad"}], "invalid mode"),
            ([{"path": "x.md", "kind": "reference", "mode": "required", "reason": "bad", "tasks": "T1"}], "tasks must be a string array"),
            ([{"path": "x.md", "kind": "reference", "mode": "required", "reason": "bad", "tasks": ["NOPE"]}], "unknown task"),
        ]
        for entries, expected in cases:
            with self.subTest(expected=expected):
                self.assert_invalid_manifest(entries, expected)

    def test_validate_change_rejects_unsafe_manifest_paths(self):
        bad_paths = [
            "/abs.md",
            "../up.md",
            "safe/../up.md",
            "..\\secret.md",
            "docs\\..\\secret.md",
            "docs/*.md",
            "docs/?.md",
            "docs/[abc].md",
            "docs/",
            ".",
            "./",
            ".dev-docs",
            ".dev-docs/",
        ]
        for bad_path in bad_paths:
            with self.subTest(path=bad_path):
                self.assert_invalid_manifest(
                    [{"path": bad_path, "kind": "reference", "mode": "required", "reason": "bad path", "tasks": ["T1"]}],
                    "invalid manifest path",
                )

    def test_validate_change_rejects_blank_verification_command_items(self):
        plan = VALID_PLAN.replace(
            "        - python3 -m unittest t1\n",
            "        -    \n",
            1,
        )
        self.assert_invalid_plan(plan, "missing verification")

    def test_validate_change_rejects_inline_verification_and_rollback_placeholders(self):
        cases = [
            (VALID_PLAN.replace("    verification:\n      commands:\n        - python3 -m unittest t1\n", "    verification: TODO\n"), "missing verification"),
            (VALID_PLAN.replace("    verification:\n      commands:\n        - python3 -m unittest t1\n", "    verification:\n      commands:\n"), "missing verification"),
            (VALID_PLAN.replace("    verification:\n      commands:\n        - python3 -m unittest t1\n", "    verification:\n      notes: \n"), "invalid task block line"),
            (VALID_PLAN.replace("    rollback:\n      strategy: Revert T1 files\n", "    rollback: later\n"), "missing rollback"),
            (VALID_PLAN.replace("    rollback:\n      strategy: Revert T1 files\n", "    rollback:\n      strategy: \n"), "invalid task block line"),
        ]
        for plan, expected in cases:
            with self.subTest(expected=expected):
                self.assert_invalid_plan(plan, expected)

    def test_validate_change_accepts_design_empty_commands_with_non_empty_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(
                tmp,
                plan=CANONICAL_PLAN,
                implement_entries=CANONICAL_IMPLEMENT_MANIFEST,
                verify_entries=CANONICAL_VERIFY_MANIFEST,
            )
            result = self.run_helper("validate-change", "--change", str(change))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(self.stdout_json(result)["ok"])

    def test_validate_change_rejects_invalid_inline_verification_commands_lists(self):
        design_verification = '    verification:\n      commands: []\n      notes: "Static validation is sufficient"\n'
        cases = [
            ('    verification:\n      commands: [python3 -m unittest]\n      notes: "Static validation is sufficient"\n', "invalid task block line"),
            ('    verification:\n      commands: []\n', "missing verification"),
            ('    verification:\n      commands: []\n      notes: ""\n', "missing verification"),
            ('    verification:\n      commands: []\n      notes: \'\'\n', "missing verification"),
            ('    verification:\n      commands: []\n        - python3 -m unittest\n      notes: "Static validation is sufficient"\n', "invalid task block line"),
        ]
        for replacement, expected in cases:
            with self.subTest(replacement=replacement):
                self.assert_invalid_plan(CANONICAL_PLAN.replace(design_verification, replacement, 1), expected)

    def test_validate_change_requires_exact_task_headers_and_dependency_tokens(self):
        cases = [
            (VALID_PLAN.replace("  - id: T1", " - id: T1"), "invalid tasks block"),
            (VALID_PLAN.replace("  - id: T1", "   - id: T1"), "invalid tasks block"),
            (VALID_PLAN.replace("  - id: T1", "  - id: \"T1\""), "invalid tasks block"),
            (VALID_PLAN.replace("  - id: T1", "  - id: 'T1'"), "invalid tasks block"),
            (VALID_PLAN.replace("  - id: T1", "  - id: \"T1"), "invalid tasks block"),
            (VALID_PLAN.replace("  - id: T1", "  - id: T1\""), "invalid tasks block"),
            (VALID_PLAN.replace("  - id: T1", "  - id:  T1"), "invalid tasks block"),
            (VALID_PLAN.replace("  - id: T1", "  - id:T1"), "invalid tasks block"),
            (VALID_PLAN.replace("depends_on: [T1]", "depends_on: [\"T1\"]"), "invalid dependency id"),
            (VALID_PLAN.replace("depends_on: [T1]", "depends_on: ['T1']"), "invalid dependency id"),
            (VALID_PLAN.replace("depends_on: [T1]", "depends_on:\n      - \"T1\""), "invalid dependency id"),
        ]
        for plan, expected in cases:
            with self.subTest(expected=expected):
                self.assert_invalid_plan(plan, expected)

    def test_validate_change_rejects_invalid_task_block_indentation_and_unknown_content(self):
        insertion = "    title: First task\n"
        cases = [
            " mystery: value\n",
            "   mystery: value\n",
            "     mystery: value\n",
            "\tmystery: value\n",
            "    mystery: value\n",
        ]
        for invalid_line in cases:
            with self.subTest(line=repr(invalid_line)):
                self.assert_invalid_plan(
                    VALID_PLAN.replace(insertion, insertion + invalid_line, 1),
                    "invalid task block line",
                )

    def test_validate_change_rejects_duplicate_required_task_fields(self):
        for field_line in [
            "    title: Duplicate\n",
            "    depends_on: []\n",
            "    acceptance:\n      - Duplicate\n",
            "    verification:\n      notes: Duplicate\n",
            "    rollback:\n      strategy: Duplicate\n",
        ]:
            with self.subTest(field=field_line.split(":", 1)[0].strip()):
                plan = VALID_PLAN.replace("    title: First task\n", "    title: First task\n" + field_line, 1)
                self.assert_invalid_plan(plan, "duplicate task field")

    def test_validate_change_rejects_invalid_canonical_status(self):
        for status in ["todo", "done", "", "Pending"]:
            with self.subTest(status=status):
                replacement = f"    status: {status}\n"
                plan = CANONICAL_PLAN.replace("    status: pending\n", replacement, 1)
                self.assert_invalid_plan(plan, "invalid task status")

    def test_validate_change_rejects_duplicate_canonical_fields(self):
        cases = [
            "    status: blocked\n",
            "    files_hint: []\n",
            "    context_refs: []\n",
        ]
        for field_line in cases:
            with self.subTest(field=field_line.split(":", 1)[0].strip()):
                plan = CANONICAL_PLAN.replace("    status: pending\n", "    status: pending\n" + field_line, 1)
                self.assert_invalid_plan(plan, "duplicate task field")

    def test_validate_change_rejects_incomplete_canonical_field_set(self):
        cases = [
            ("    status: pending\n", "missing status"),
            (
                "    files_hint:\n      - plugins/nuclio-plugin/skills/design/SKILL.md\n      - plugins/nuclio-plugin/scripts/task-helper.py\n",
                "missing files_hint",
            ),
            (
                "    context_refs:\n      - plugins/nuclio-plugin/references/protocol.md\n      - design-task-4\n",
                "missing context_refs",
            ),
        ]
        for field_block, expected in cases:
            with self.subTest(expected=expected):
                self.assert_invalid_plan(CANONICAL_PLAN.replace(field_block, "", 1), expected)

    def test_validate_change_rejects_empty_nested_canonical_lists(self):
        cases = [
            ("    files_hint:\n      - plugins/nuclio-plugin/skills/design/SKILL.md\n      - plugins/nuclio-plugin/scripts/task-helper.py\n", "    files_hint:\n"),
            ("    context_refs:\n      - plugins/nuclio-plugin/references/protocol.md\n      - design-task-4\n", "    context_refs:\n"),
        ]
        for old, new in cases:
            with self.subTest(field=new.strip().rstrip(":")):
                self.assert_invalid_plan(CANONICAL_PLAN.replace(old, new, 1), "missing canonical list")

    def test_validate_change_rejects_non_empty_inline_canonical_lists(self):
        cases = [
            ("    files_hint:\n      - plugins/nuclio-plugin/skills/design/SKILL.md\n      - plugins/nuclio-plugin/scripts/task-helper.py\n", "    files_hint: [plugins/nuclio-plugin/skills/design/SKILL.md]\n"),
            ("    context_refs:\n      - plugins/nuclio-plugin/references/protocol.md\n      - design-task-4\n", "    context_refs: [plugins/nuclio-plugin/references/protocol.md]\n"),
        ]
        for old, new in cases:
            with self.subTest(field=new.split(":", 1)[0].strip()):
                self.assert_invalid_plan(CANONICAL_PLAN.replace(old, new, 1), "invalid task block line")

    def test_validate_change_rejects_unsafe_files_hint_paths(self):
        bad_values = [
            "/abs.md",
            "../up.md",
            "safe/../up.md",
            "..\\secret.md",
            "docs\\..\\secret.md",
            "docs/*.md",
            "docs/?.md",
            "docs/[abc].md",
            "docs/",
            "docs\\",
            ".",
            "./",
            ".dev-docs",
            ".dev-docs/",
            ".dev-docs\\",
            "~",
            "~/secret.md",
            "file:secret.md",
            "http:docs/file.md",
            "https://example.com/file.md",
            "C:\\absolute\\file.md",
            "\\\\server\\share\\file.md",
        ]
        for bad_value in bad_values:
            with self.subTest(value=bad_value):
                plan = CANONICAL_PLAN.replace(
                    "      - plugins/nuclio-plugin/skills/design/SKILL.md\n",
                    f"      - {bad_value}\n",
                    1,
                )
                self.assert_invalid_plan(plan, "invalid task path")

    def test_validate_change_rejects_quoted_files_hint_paths(self):
        for bad_value in ['"../outside.md"', "'/etc/passwd'", '"C:\\secret"']:
            with self.subTest(value=bad_value):
                plan = CANONICAL_PLAN.replace(
                    "      - plugins/nuclio-plugin/skills/design/SKILL.md\n",
                    f"      - {bad_value}\n",
                    1,
                )
                self.assert_invalid_plan(plan, "invalid task path")

    def test_validate_change_rejects_unsafe_context_ref_paths_but_accepts_identifiers(self):
        bad_values = [
            "/abs.md",
            "../up.md",
            "safe/../up.md",
            "..\\secret.md",
            "docs\\..\\secret.md",
            "docs/*.md",
            "docs/?.md",
            "docs/[abc].md",
            "docs/",
            "docs\\",
            ".",
            "./",
            ".dev-docs",
            ".dev-docs/",
            ".dev-docs\\",
            "~",
            "~/secret.md",
            "file:secret.md",
            "http:docs/file.md",
            "https://example.com/file.md",
            "C:/absolute/file.md",
            "//server/share/file.md",
            "*",
            "ref?name",
            "ref[name]",
            "ref name",
        ]
        for bad_value in bad_values:
            with self.subTest(value=bad_value):
                plan = CANONICAL_PLAN.replace(
                    "      - plugins/nuclio-plugin/references/protocol.md\n",
                    f"      - {bad_value}\n",
                    1,
                )
                self.assert_invalid_plan(plan, "invalid task path")

    def test_validate_change_rejects_quoted_context_ref_paths(self):
        for bad_value in ['"../outside.md"', "'/etc/passwd'", '"C:\\secret"']:
            with self.subTest(value=bad_value):
                plan = CANONICAL_PLAN.replace(
                    "      - plugins/nuclio-plugin/references/protocol.md\n",
                    f"      - {bad_value}\n",
                    1,
                )
                self.assert_invalid_plan(plan, "invalid task path")

    def test_validate_change_rejects_unknown_canonical_same_level_field(self):
        plan = CANONICAL_PLAN.replace("    status: pending\n", "    status: pending\n    owner: design\n", 1)
        self.assert_invalid_plan(plan, "invalid task block line")

    def test_validate_change_rejects_non_string_modes_with_structured_json(self):
        for mode in [[], {}, None, 1]:
            with self.subTest(mode=mode):
                self.assert_invalid_manifest(
                    [{"path": "x.md", "kind": "reference", "mode": mode, "reason": "bad"}],
                    "invalid mode",
                )

    def test_validate_change_wraps_invalid_utf8_as_structured_json(self):
        targets = [
            "state.json",
            "plan.yaml",
            "context/implement.jsonl",
            "context/verify.jsonl",
        ]
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                change = self.make_change(tmp)
                (change / target).write_bytes(b"\xff")
                result = self.run_helper("validate-change", "--change", str(change))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                payload = self.stdout_json(result)
                self.assertFalse(payload["ok"])
                self.assertIn("failed to read", payload["error"])

    def test_validate_change_rejects_windows_drive_and_unc_manifest_paths(self):
        bad_paths = [
            "C:\\absolute\\file.md",
            "C:/absolute/file.md",
            "\\\\server\\share\\file.md",
            "\\server\\share\\file.md",
            "//server/share/file.md",
        ]
        for bad_path in bad_paths:
            with self.subTest(path=bad_path):
                self.assert_invalid_manifest(
                    [{"path": bad_path, "kind": "reference", "mode": "required", "reason": "bad path", "tasks": ["T1"]}],
                    "invalid manifest path",
                )

    def test_validate_change_does_not_read_manifest_target_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            change = self.make_change(
                tmp,
                implement_entries=[
                    {"path": "does/not/exist.md", "kind": "reference", "mode": "required", "reason": "shape only", "tasks": ["T1"]}
                ],
            )

            result = self.run_helper("validate-change", "--change", str(change))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(self.stdout_json(result)["ok"])


if __name__ == "__main__":
    unittest.main()
