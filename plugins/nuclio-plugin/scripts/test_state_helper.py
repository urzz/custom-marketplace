import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).with_name("state-helper.py")
VALID_BLOCKER_RECORD_ID = "sha256:" + "a" * 64


class StateHelperCliTests(unittest.TestCase):
    def run_helper(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def write_json(self, path, payload):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def read_stdout_json(self, result):
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"stdout was not JSON: {result.stdout!r}; stderr={result.stderr!r}; {exc}")

    def canonical_blocker(
        self,
        kind,
        task_id="T1",
        *,
        code="blocked",
        evidence=None,
        reason="needs recovery",
        blocker_occurrence=1,
        blocker_record_id=VALID_BLOCKER_RECORD_ID,
    ):
        if evidence is None:
            evidence = f"evidence/tasks/{task_id}/implementer.md"
        return {
            "kind": kind,
            "code": code,
            "evidence": evidence,
            "reason": reason,
            "blocker_occurrence": blocker_occurrence,
            "blocker_record_id": blocker_record_id,
        }

    def valid_reapproval_state(self, *, current_task=None, tasks=None):
        if tasks is None:
            tasks = {
                "T1": {
                    "status": "blocked",
                    "attempts": 1,
                    "blocker": self.canonical_blocker("design_revision", "T1", reason="design changed"),
                    "reason": "design changed",
                    "manual_repair_authorization": "sha256:" + "1" * 64,
                }
            }
        state = {
            "phase": "design",
            "status": "draft",
            "gates": {"brief": "approved", "design": "pending", "qa": "pending"},
            "tasks": tasks,
            "implementation": {"approved_control_plane": {"design.md": "H1"}, "base_sha": "abc123"},
            "evidence": {"existing": ["red"]},
        }
        if current_task is not None:
            state["current_task"] = current_task
        return state

    def run_approve_design_revision(self, state_path, unblock_tasks):
        return self.run_helper(
            "approve-design-revision",
            "--state",
            str(state_path),
            "--approved-control-plane",
            json.dumps({"design.md": "H2", "plan.yaml": "P2"}),
            "--unblock-tasks",
            json.dumps(unblock_tasks),
            "--allow-approval",
        )

    def task_contract(self, tasks):
        normalized = []
        owners_by_path = {}
        for task in tasks:
            item = {
                "id": task["id"],
                "depends_on": task.get("depends_on", []),
                "acceptance": task.get("acceptance", [f"accept {task['id']}"]),
                "verification": task.get("verification", {"commands": [f"verify {task['id']}"]}),
                "context_refs": task.get("context_refs", [f"CTX-{task['id']}"]),
                "mutation_targets": sorted(task.get("mutation_targets", [f"src/{task['id']}.py"])),
                "ownership_handoffs": sorted(
                    task.get("ownership_handoffs", []),
                    key=lambda handoff: (handoff["path"], handoff["from_task"], handoff["to_task"]),
                ),
            }
            normalized.append(item)
            for path in item["mutation_targets"]:
                owners_by_path.setdefault(path, []).append(item["id"])
        ownership_table = []
        for path in sorted(owners_by_path):
            owners = owners_by_path[path]
            handoffs = []
            for item in normalized:
                handoffs.extend(h for h in item["ownership_handoffs"] if h["path"] == path)
            ownership_table.append(
                {"path": path, "owners": owners, "handoffs": handoffs, "final_owner": owners[-1]}
            )
        return {
            "plan_order": [task["id"] for task in normalized],
            "tasks": normalized,
            "ownership_table": ownership_table,
        }

    def snapshot_ref(self, kind, task_id, path, *, from_task=None, attempt=1, review_cycle=1, hash_char="a"):
        path_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
        if kind == "completion":
            filename = f"completion-{task_id}-{path_id}-a{attempt}-r{review_cycle}.json"
        elif kind == "live":
            filename = f"live-{task_id}-{path_id}-a{attempt}-r{review_cycle}.json"
        else:
            filename = f"dependency-{from_task}-to-{task_id}-{path_id}-a{attempt}-r{review_cycle}.json"
        ref = {
            "evidence_path": f"evidence/tasks/{task_id}/snapshots/{filename}",
            "record_hash": "sha256:" + hash_char * 64,
            "path": path,
            "path_id": path_id,
        }
        if kind == "dependency":
            ref["incoming_edge"] = {"path": path, "from": from_task, "to": task_id}
        return ref

    def revision_state(self, contract, *, tasks=None, implementation=None):
        if tasks is None:
            tasks = {
                task_id: {"status": "pending", "attempts": 0}
                for task_id in contract["plan_order"]
            }
        base_implementation = {
            "approved_control_plane": {"design.md": "H1"},
            "approved_task_contract": contract,
            "completed_tasks": [],
        }
        if implementation:
            base_implementation.update(implementation)
        return {
            "phase": "design",
            "status": "draft",
            "gates": {"brief": "approved", "design": "pending", "qa": "pending"},
            "tasks": tasks,
            "implementation": base_implementation,
        }

    def run_contract_revision(self, state_path, contract, affected_tasks, reason="requirements changed", *extra):
        return self.run_helper(
            "approve-design-revision",
            "--state",
            str(state_path),
            "--approved-control-plane",
            json.dumps({"design.md": "H2", "plan.yaml": "P2"}),
            "--task-contract",
            json.dumps(contract),
            "--affected-tasks",
            json.dumps(affected_tasks),
            "--revision-reason",
            reason,
            "--allow-approval",
            *extra,
        )

    def run_design_revision_preflight(
        self, state_path, contract, affected_tasks, reason="requirements changed", *extra
    ):
        return self.run_helper(
            "validate-design-revision",
            "--state",
            str(state_path),
            "--approved-control-plane",
            json.dumps({"design.md": "H2", "plan.yaml": "P2"}),
            "--task-contract",
            json.dumps(contract),
            "--affected-tasks",
            json.dumps(affected_tasks),
            "--revision-reason",
            reason,
            *extra,
        )

    def test_inspect_state_returns_defensive_summary_fields_and_empty_optional_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            change = pathlib.Path(tmp)
            (change / "context").mkdir()
            (change / "plan.yaml").write_text("tasks: []\n", encoding="utf-8")
            (change / "context" / "implement.jsonl").write_text("", encoding="utf-8")
            self.write_json(
                change / "state.json",
                {
                    "phase": "implement",
                    "status": "ready",
                    "current_task": {"id": "T1"},
                    "gates": {"design": "approved"},
                    "artifacts": {"plan": "plan.yaml"},
                    "active": {"change": "demo"},
                },
            )

            result = self.run_helper("inspect-state", "--change", str(change))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["phase"], "implement")
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["current_task"], {"id": "T1"})
            self.assertEqual(payload["gates"], {"design": "approved"})
            self.assertEqual(payload["artifacts"], {"plan": "plan.yaml"})
            self.assertEqual(payload["tasks"], {})
            self.assertEqual(payload["implementation"], {})
            self.assertEqual(payload["evidence"], {})
            self.assertEqual(payload["active"], {"change": "demo"})
            self.assertEqual(payload["missing_files"], [])

    def test_inspect_state_replaces_non_object_optional_summaries_with_empty_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            change = pathlib.Path(tmp)
            self.write_json(
                change / "state.json",
                {
                    "phase": "implement",
                    "status": "ready",
                    "gates": [],
                    "artifacts": "bad",
                    "tasks": ["bad"],
                    "implementation": None,
                    "evidence": "bad",
                    "active": "raw-active",
                },
            )

            result = self.run_helper("inspect-state", "--change", str(change))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertEqual(payload["gates"], {})
            self.assertEqual(payload["artifacts"], {})
            self.assertEqual(payload["tasks"], {})
            self.assertEqual(payload["implementation"], {})
            self.assertEqual(payload["evidence"], {})
            self.assertEqual(payload["active"], "raw-active")
            self.assertCountEqual(
                payload["missing_files"],
                ["plan.yaml", "context/implement.jsonl"],
            )

    def test_merge_state_preserves_unknown_nested_metadata_unrelated_gate_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            self.write_json(
                state_path,
                {
                    "phase": "design",
                    "unknown_top": {"keep": True},
                    "metadata": {"owner": "alice", "nested": {"keep": 1}},
                    "gates": {"brief": "approved", "design": "pending"},
                    "evidence": {"existing": ["red"]},
                },
            )
            patch = json.dumps(
                {
                    "metadata": {"nested": {"add": 2}},
                    "gates": {"design": "pending-review"},
                    "status": "working",
                }
            )

            result = self.run_helper("merge-state", "--state", str(state_path), "--patch", patch)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["unknown_top"], {"keep": True})
            self.assertEqual(state["metadata"], {"owner": "alice", "nested": {"keep": 1, "add": 2}})
            self.assertEqual(state["gates"], {"brief": "approved", "design": "pending-review"})
            self.assertEqual(state["evidence"], {"existing": ["red"]})
            self.assertEqual(state["status"], "working")

    def test_merge_state_rejects_gate_approval_without_allow_approval_and_returns_json_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            original = {"gates": {"design": "pending"}, "metadata": {"keep": True}}
            self.write_json(state_path, original)

            result = self.run_helper(
                "merge-state",
                "--state",
                str(state_path),
                "--patch",
                json.dumps({"gates": {"design": "approved"}}),
            )

            self.assertEqual(result.returncode, 1)
            payload = self.read_stdout_json(result)
            self.assertFalse(payload["ok"])
            self.assertIn("approval", payload["error"])
            self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), original)

    def test_merge_state_allows_explicit_gate_approval_and_preserves_other_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            self.write_json(
                state_path,
                {"gates": {"brief": "approved", "design": "pending"}, "metadata": {"keep": True}},
            )

            result = self.run_helper(
                "merge-state",
                "--state",
                str(state_path),
                "--patch",
                json.dumps({"gates": {"design": "approved"}}),
                "--allow-approval",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["gates"], {"brief": "approved", "design": "approved"})
            self.assertEqual(state["metadata"], {"keep": True})

    def test_merge_state_rejects_unpaired_surrogate_patch_before_write_without_overwriting_or_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            self.write_json(state_path, {"gates": {"design": "pending"}, "metadata": {"keep": True}})
            original_bytes = state_path.read_bytes()

            result = self.run_helper(
                "merge-state",
                "--state",
                str(state_path),
                "--patch",
                json.dumps({"metadata": {"bad": "\ud800"}}),
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertFalse(payload["ok"])
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(state_path.read_bytes(), original_bytes)

    def test_approve_design_revision_rejects_unpaired_surrogate_control_plane_before_write_without_overwriting_or_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            self.write_json(state_path, self.valid_reapproval_state())
            original_bytes = state_path.read_bytes()

            result = self.run_helper(
                "approve-design-revision",
                "--state",
                str(state_path),
                "--approved-control-plane",
                json.dumps({"design.md": "\ud800"}),
                "--unblock-tasks",
                json.dumps(["T1"]),
                "--allow-approval",
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertFalse(payload["ok"])
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(state_path.read_bytes(), original_bytes)

    def test_approve_design_revision_rejects_preserved_surrogate_state_field_before_write_without_overwriting_or_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            state = self.valid_reapproval_state()
            state["metadata"] = {"preserve": "\ud800"}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            original_bytes = state_path.read_bytes()

            result = self.run_approve_design_revision(state_path, ["T1"])

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertFalse(payload["ok"])
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(state_path.read_bytes(), original_bytes)

    def test_replace_object_replaces_approved_control_plane_and_preserves_unrelated_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            self.write_json(
                state_path,
                {
                    "phase": "implement",
                    "unknown_top": {"keep": True},
                    "gates": {"design": "pending", "qa": "pending"},
                    "evidence": {"existing": ["red"]},
                    "implementation": {
                        "approved_control_plane": {
                            "design.md": "H1",
                            "context/old.jsonl": "OLD",
                        },
                        "notes": {"keep": True},
                    },
                },
            )

            result = self.run_helper(
                "replace-object",
                "--state",
                str(state_path),
                "--object-path",
                "implementation.approved_control_plane",
                "--value",
                json.dumps({"design.md": "H2"}),
                "--allow-approval",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["state_path"], str(state_path))
            self.assertEqual(payload["replaced_object_path"], "implementation.approved_control_plane")
            self.assertTrue(payload["updated"])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["implementation"]["approved_control_plane"], {"design.md": "H2"})
            self.assertNotIn("context/old.jsonl", state["implementation"]["approved_control_plane"])
            self.assertEqual(state["implementation"]["notes"], {"keep": True})
            self.assertEqual(state["unknown_top"], {"keep": True})
            self.assertEqual(state["gates"], {"design": "pending", "qa": "pending"})
            self.assertEqual(state["evidence"], {"existing": ["red"]})

    def test_replace_object_requires_allow_approval_and_leaves_state_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            self.write_json(
                state_path,
                {"implementation": {"approved_control_plane": {"design.md": "H1"}}},
            )
            original_bytes = state_path.read_bytes()

            result = self.run_helper(
                "replace-object",
                "--state",
                str(state_path),
                "--object-path",
                "implementation.approved_control_plane",
                "--value",
                json.dumps({"design.md": "H2"}),
            )

            self.assertEqual(result.returncode, 1)
            payload = self.read_stdout_json(result)
            self.assertFalse(payload["ok"])
            self.assertIn("approval", payload["error"])
            self.assertEqual(state_path.read_bytes(), original_bytes)

    def test_replace_object_rejects_invalid_inputs_without_overwriting_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            cases = [
                (
                    "non_allowlisted_path",
                    {"implementation": {"approved_control_plane": {"design.md": "H1"}}},
                    "implementation.other",
                    json.dumps({"design.md": "H2"}),
                ),
                (
                    "non_object_value",
                    {"implementation": {"approved_control_plane": {"design.md": "H1"}}},
                    "implementation.approved_control_plane",
                    json.dumps(["design.md", "H2"]),
                ),
                (
                    "invalid_json_value",
                    {"implementation": {"approved_control_plane": {"design.md": "H1"}}},
                    "implementation.approved_control_plane",
                    "{not json",
                ),
            ]

            for name, original_state, object_path, value in cases:
                state_path = tmp_path / f"{name}.json"
                self.write_json(state_path, original_state)
                original_bytes = state_path.read_bytes()

                result = self.run_helper(
                    "replace-object",
                    "--state",
                    str(state_path),
                    "--object-path",
                    object_path,
                    "--value",
                    value,
                    "--allow-approval",
                )

                self.assertEqual(result.returncode, 1, name)
                self.assertFalse(self.read_stdout_json(result)["ok"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

            invalid_state = tmp_path / "invalid-state.json"
            invalid_state.write_text("{not json", encoding="utf-8")
            invalid_state_bytes = invalid_state.read_bytes()
            non_object_state = tmp_path / "non-object-state.json"
            non_object_state.write_text("[]", encoding="utf-8")
            non_object_state_bytes = non_object_state.read_bytes()

            for state_path, original_bytes in (
                (invalid_state, invalid_state_bytes),
                (non_object_state, non_object_state_bytes),
            ):
                result = self.run_helper(
                    "replace-object",
                    "--state",
                    str(state_path),
                    "--object-path",
                    "implementation.approved_control_plane",
                    "--value",
                    json.dumps({"design.md": "H2"}),
                    "--allow-approval",
                )

                self.assertEqual(result.returncode, 1, str(state_path))
                self.assertFalse(self.read_stdout_json(result)["ok"], str(state_path))
                self.assertEqual(state_path.read_bytes(), original_bytes, str(state_path))

    def test_replace_object_creates_missing_implementation_without_approving_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            self.write_json(state_path, {"gates": {"design": "pending"}, "evidence": {"keep": True}})

            result = self.run_helper(
                "replace-object",
                "--state",
                str(state_path),
                "--object-path",
                "implementation.approved_control_plane",
                "--value",
                json.dumps({"design.md": "H2"}),
                "--allow-approval",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["implementation"]["approved_control_plane"], {"design.md": "H2"})
            self.assertEqual(state["gates"], {"design": "pending"})
            self.assertEqual(state["evidence"], {"keep": True})

    def test_replace_object_rejects_existing_non_object_implementation_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for name, implementation in (
                ("null", None),
                ("string", "bad"),
                ("array", []),
            ):
                state_path = tmp_path / f"{name}.json"
                self.write_json(state_path, {"implementation": implementation, "gates": {"design": "pending"}})
                original_bytes = state_path.read_bytes()

                result = self.run_helper(
                    "replace-object",
                    "--state",
                    str(state_path),
                    "--object-path",
                    "implementation.approved_control_plane",
                    "--value",
                    json.dumps({"design.md": "H2"}),
                    "--allow-approval",
                )

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertIn("implementation", payload["error"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_replaces_control_plane_and_unblocks_only_design_revision_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            design_blocker = self.canonical_blocker(
                "design_revision", "T1", code="control_plane_changed", reason="design changed"
            )
            resolved_blocker = self.canonical_blocker(
                "resolved_evidence", "T2", code="missing_token", reason="waiting for token"
            )
            self.write_json(
                state_path,
                {
                    "phase": "design",
                    "status": "draft",
                    "current_task": {"id": "T1", "attempt": 1, "status": "blocked"},
                    "unknown_top": {"keep": True},
                    "gates": {"brief": "approved", "design": "pending", "qa": "pending"},
                    "tasks": {
                        "T1": {
                            "status": "blocked",
                            "attempts": 1,
                            "blocker": design_blocker,
                            "reason": "design changed",
                            "manual_repair_authorization": "sha256:" + "1" * 64,
                            "history": ["old blocker"],
                        },
                        "T2": {
                            "status": "blocked",
                            "attempts": 0,
                            "blocker": resolved_blocker,
                            "reason": "waiting for token",
                            "design_revision_authorization": "sha256:" + "4" * 64,
                        },
                        "T3": {"status": "pending", "attempts": 0, "manual_repair_authorization": "sha256:" + "3" * 64, "notes": {"keep": True}},
                    },
                    "implementation": {
                        "approved_control_plane": {"design.md": "H1", "context/old.jsonl": "OLD"},
                        "base_sha": "abc123",
                    },
                    "evidence": {"existing": ["red"]},
                },
            )

            result = self.run_approve_design_revision(state_path, ["T1"])

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertEqual(
                payload,
                {
                    "ok": True,
                    "state_path": str(state_path),
                    "approved_control_plane_replaced": True,
                    "unblocked_tasks": ["T1"],
                    "updated": True,
                },
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "design")
            self.assertEqual(state["status"], "draft")
            self.assertIsNone(state["current_task"])
            self.assertEqual(state["gates"], {"brief": "approved", "design": "approved", "qa": "pending"})
            self.assertEqual(
                state["implementation"],
                {
                    "approved_control_plane": {"design.md": "H2", "plan.yaml": "P2"},
                    "base_sha": "abc123",
                },
            )
            self.assertEqual(state["tasks"]["T1"]["status"], "pending")
            self.assertEqual(state["tasks"]["T1"]["blocker"], None)
            self.assertEqual(state["tasks"]["T1"]["reason"], None)
            self.assertEqual(state["tasks"]["T1"]["manual_repair_authorization"], None)
            self.assertEqual(state["tasks"]["T1"].get("design_revision_authorization"), None)
            self.assertEqual(state["tasks"]["T1"]["history"], ["old blocker"])
            self.assertEqual(state["tasks"]["T2"]["status"], "blocked")
            self.assertEqual(state["tasks"]["T2"]["blocker"], resolved_blocker)
            self.assertEqual(state["tasks"]["T2"]["reason"], "waiting for token")
            self.assertNotIn("manual_repair_authorization", state["tasks"]["T2"])
            self.assertEqual(state["tasks"]["T2"]["design_revision_authorization"], "sha256:" + "4" * 64)
            self.assertEqual(
                state["tasks"]["T3"],
                {
                    "status": "pending",
                    "attempts": 0,
                    "manual_repair_authorization": "sha256:" + "3" * 64,
                    "notes": {"keep": True},
                },
            )
            self.assertEqual(state["unknown_top"], {"keep": True})
            self.assertEqual(state["evidence"], {"existing": ["red"]})

    def test_approve_design_revision_creates_missing_implementation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            self.write_json(
                state_path,
                {
                    "gates": {"design": "pending"},
                    "tasks": {
                        "T1": {
                            "status": "blocked",
                            "attempts": 0,
                            "blocker": self.canonical_blocker("design_revision", "T1", reason="r"),
                            "reason": "r",
                        }
                    },
                },
            )

            result = self.run_helper(
                "approve-design-revision",
                "--state",
                str(state_path),
                "--approved-control-plane",
                json.dumps({"design.md": "H2"}),
                "--unblock-tasks",
                json.dumps(["T1"]),
                "--allow-approval",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["implementation"]["approved_control_plane"], {"design.md": "H2"})
            self.assertEqual(state["gates"]["design"], "approved")
            self.assertEqual(state["tasks"]["T1"]["status"], "pending")

    def test_approve_design_revision_fail_closed_invalid_inputs_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            valid_state = {
                "gates": {"design": "pending"},
                "tasks": {
                    "T1": {
                        "status": "blocked",
                        "attempts": 0,
                        "blocker": self.canonical_blocker("design_revision", "T1", reason="r"),
                        "reason": "r",
                    },
                    "T2": {"status": "pending", "attempts": 0},
                },
                "implementation": {"approved_control_plane": {"design.md": "H1"}},
            }
            cases = [
                ("missing_allow", valid_state, json.dumps({"design.md": "H2"}), json.dumps(["T1"]), []),
                ("invalid_control_plane_json", valid_state, "{not json", json.dumps(["T1"]), ["--allow-approval"]),
                ("non_object_control_plane", valid_state, json.dumps(["design.md", "H2"]), json.dumps(["T1"]), ["--allow-approval"]),
                ("invalid_unblock_json", valid_state, json.dumps({"design.md": "H2"}), "{not json", ["--allow-approval"]),
                ("non_array_unblock", valid_state, json.dumps({"design.md": "H2"}), json.dumps({"T1": True}), ["--allow-approval"]),
                ("non_string_task_id", valid_state, json.dumps({"design.md": "H2"}), json.dumps(["T1", 2]), ["--allow-approval"]),
                ("duplicate_task_id", valid_state, json.dumps({"design.md": "H2"}), json.dumps(["T1", "T1"]), ["--allow-approval"]),
                ("unknown_task_id", valid_state, json.dumps({"design.md": "H2"}), json.dumps(["T9"]), ["--allow-approval"]),
                ("task_not_blocked", valid_state, json.dumps({"design.md": "H2"}), json.dumps(["T2"]), ["--allow-approval"]),
                (
                    "omitted_design_revision_task",
                    {
                        "gates": {"design": "pending"},
                        "tasks": {
                            "T1": {
                                "status": "blocked",
                                "attempts": 0,
                                "blocker": self.canonical_blocker("design_revision", "T1", reason="r1"),
                                "reason": "r1",
                            },
                            "T2": {
                                "status": "blocked",
                                "attempts": 0,
                                "blocker": self.canonical_blocker("design_revision", "T2", reason="r2"),
                                "reason": "r2",
                            },
                        },
                    },
                    json.dumps({"design.md": "H2"}),
                    json.dumps(["T1"]),
                    ["--allow-approval"],
                ),
                ("null_implementation", {**valid_state, "implementation": None}, json.dumps({"design.md": "H2"}), json.dumps(["T1"]), ["--allow-approval"]),
                ("string_implementation", {**valid_state, "implementation": "bad"}, json.dumps({"design.md": "H2"}), json.dumps(["T1"]), ["--allow-approval"]),
                ("array_implementation", {**valid_state, "implementation": []}, json.dumps({"design.md": "H2"}), json.dumps(["T1"]), ["--allow-approval"]),
                ("malformed_gates", {**valid_state, "gates": []}, json.dumps({"design.md": "H2"}), json.dumps(["T1"]), ["--allow-approval"]),
                ("malformed_tasks", {**valid_state, "tasks": []}, json.dumps({"design.md": "H2"}), json.dumps(["T1"]), ["--allow-approval"]),
                ("missing_design_gate", {**valid_state, "gates": {}}, json.dumps({"design.md": "H2"}), json.dumps(["T1"]), ["--allow-approval"]),
                ("approved_design_gate", {**valid_state, "gates": {"design": "approved"}}, json.dumps({"design.md": "H2"}), json.dumps(["T1"]), ["--allow-approval"]),
            ]

            for name, original_state, control_plane, unblock_tasks, extra_args in cases:
                state_path = tmp_path / f"{name}.json"
                self.write_json(state_path, original_state)
                original_bytes = state_path.read_bytes()

                result = self.run_helper(
                    "approve-design-revision",
                    "--state",
                    str(state_path),
                    "--approved-control-plane",
                    control_plane,
                    "--unblock-tasks",
                    unblock_tasks,
                    *extra_args,
                )

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_includes_pending_design_revision_authorization_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            current_task = {"id": "T1", "attempt": 1, "status": "blocked"}
            self.write_json(
                state_path,
                self.valid_reapproval_state(
                    current_task=current_task,
                    tasks={
                        "T1": {
                            "status": "blocked",
                            "attempts": 1,
                            "blocker": self.canonical_blocker("design_revision", "T1", reason="r1"),
                            "reason": "r1",
                            "manual_repair_authorization": "sha256:" + "1" * 64,
                        },
                        "T2": {
                            "status": "pending",
                            "attempts": 2,
                            "fix_cycle": 2,
                            "review_cycle": 3,
                            "design_revision_authorization": "sha256:" + "4" * 64,
                            "task_scope_fingerprint": "sha256:" + "5" * 64,
                            "notes": {"keep": True},
                        },
                        "T3": {
                            "status": "completed",
                            "attempts": 1,
                            "manual_repair_authorization": "sha256:" + "6" * 64,
                        },
                    },
                ),
            )

            result = self.run_approve_design_revision(state_path, ["T1", "T2"])

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertEqual(payload["unblocked_tasks"], ["T1", "T2"])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIsNone(state["current_task"])
            self.assertEqual(state["tasks"]["T1"]["status"], "pending")
            self.assertIsNone(state["tasks"]["T1"]["manual_repair_authorization"])
            self.assertIsNone(state["tasks"]["T1"]["design_revision_authorization"])
            self.assertIsNone(state["tasks"]["T1"]["blocker"])
            self.assertIsNone(state["tasks"]["T1"]["reason"])
            self.assertEqual(state["tasks"]["T2"]["status"], "pending")
            self.assertEqual(state["tasks"]["T2"]["attempts"], 2)
            self.assertEqual(state["tasks"]["T2"]["fix_cycle"], 2)
            self.assertEqual(state["tasks"]["T2"]["review_cycle"], 3)
            self.assertIsNone(state["tasks"]["T2"]["manual_repair_authorization"])
            self.assertIsNone(state["tasks"]["T2"]["design_revision_authorization"])
            self.assertEqual(state["tasks"]["T2"]["task_scope_fingerprint"], "sha256:" + "5" * 64)
            self.assertEqual(state["tasks"]["T2"]["notes"], {"keep": True})
            self.assertEqual(
                state["tasks"]["T3"],
                {
                    "status": "completed",
                    "attempts": 1,
                    "manual_repair_authorization": "sha256:" + "6" * 64,
                },
            )

    def test_approve_design_revision_requires_pending_design_revision_authorization_set_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            self.write_json(
                state_path,
                self.valid_reapproval_state(
                    tasks={
                        "T1": {
                            "status": "blocked",
                            "attempts": 1,
                            "blocker": self.canonical_blocker("design_revision", "T1", reason="r1"),
                            "reason": "r1",
                        },
                        "T2": {
                            "status": "pending",
                            "attempts": 1,
                            "design_revision_authorization": "sha256:" + "2" * 64,
                        },
                        "T3": {"status": "pending", "attempts": 0},
                    },
                ),
            )
            original_bytes = state_path.read_bytes()

            result = self.run_approve_design_revision(state_path, ["T1"])

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertFalse(payload["ok"])
            self.assertIn("missing_design_eligible_tasks", payload["detail"])
            self.assertEqual(state_path.read_bytes(), original_bytes)

    def test_approve_design_revision_requires_exact_design_revision_task_set_without_overwriting(self):
        design_t1 = {
            "status": "blocked",
            "attempts": 1,
            "blocker": self.canonical_blocker("design_revision", "T1", reason="design changed"),
            "reason": "design changed",
        }
        design_t2 = {
            "status": "blocked",
            "attempts": 0,
            "blocker": self.canonical_blocker("design_revision", "T2", reason="plan changed"),
            "reason": "plan changed",
        }
        resolved_t3 = {
            "status": "blocked",
            "attempts": 0,
            "blocker": self.canonical_blocker("resolved_evidence", "T3", reason="waiting for token"),
            "reason": "waiting for token",
        }
        pending_t4 = {"status": "pending", "attempts": 0}
        cases = [
            ("omits_design_revision_task", ["T1"]),
            ("includes_resolved_evidence_task", ["T1", "T2", "T3"]),
            ("includes_pending_task", ["T1", "T2", "T4"]),
            ("includes_unknown_task", ["T1", "T2", "T9"]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for name, unblock_tasks in cases:
                state_path = tmp_path / f"{name}.json"
                self.write_json(
                    state_path,
                    self.valid_reapproval_state(
                        tasks={"T1": design_t1, "T2": design_t2, "T3": resolved_t3, "T4": pending_t4}
                    ),
                )
                original_bytes = state_path.read_bytes()

                result = self.run_approve_design_revision(state_path, unblock_tasks)

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_rejects_malformed_authorization_ids_without_overwriting(self):
        malformed_values = [
            ("manual_repair_bool", "manual_repair_authorization", True),
            ("manual_repair_wrong_prefix", "manual_repair_authorization", "SHA256:" + "a" * 64),
            ("manual_repair_short", "manual_repair_authorization", "sha256:" + "a" * 63),
            ("manual_repair_uppercase", "manual_repair_authorization", "sha256:" + "A" * 64),
            ("design_revision_bool", "design_revision_authorization", True),
            ("design_revision_wrong_prefix", "design_revision_authorization", "SHA256:" + "a" * 64),
            ("design_revision_short", "design_revision_authorization", "sha256:" + "a" * 63),
            ("design_revision_uppercase", "design_revision_authorization", "sha256:" + "A" * 64),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for name, field, value in malformed_values:
                state_path = tmp_path / f"{name}.json"
                task = {
                    "status": "blocked",
                    "attempts": 1,
                    "blocker": self.canonical_blocker("design_revision", "T1", reason="r"),
                    "reason": "r",
                }
                task[field] = value
                self.write_json(state_path, self.valid_reapproval_state(tasks={"T1": task}))
                original_bytes = state_path.read_bytes()

                result = self.run_approve_design_revision(state_path, ["T1"])

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertIn("authorization", payload["error"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_rejects_dual_authorization_fields_for_any_status_without_overwriting(self):
        dual_authorization = {
            "manual_repair_authorization": "sha256:" + "1" * 64,
            "design_revision_authorization": "sha256:" + "2" * 64,
        }
        status_task_cases = [
            (
                "blocked_design_revision",
                {
                    "status": "blocked",
                    "attempts": 1,
                    "blocker": self.canonical_blocker("design_revision", "T1", reason="r"),
                    "reason": "r",
                    **dual_authorization,
                },
                ["T1"],
            ),
            (
                "blocked_resolved_evidence",
                {
                    "status": "blocked",
                    "attempts": 1,
                    "blocker": self.canonical_blocker("resolved_evidence", "T1", reason="r"),
                    "reason": "r",
                    **dual_authorization,
                },
                [],
            ),
            ("pending", {"status": "pending", "attempts": 1, **dual_authorization}, []),
            ("in_progress", {"status": "in_progress", "attempts": 1, **dual_authorization}, []),
            ("completed", {"status": "completed", "attempts": 1, **dual_authorization}, []),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for name, task, unblock_tasks in status_task_cases:
                state_path = tmp_path / f"{name}.json"
                self.write_json(state_path, self.valid_reapproval_state(tasks={"T1": task}))
                original_bytes = state_path.read_bytes()

                result = self.run_approve_design_revision(state_path, unblock_tasks)

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertIn("must not both be non-null", payload["error"], name)
                self.assertEqual(payload["detail"], "T1", name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_rejects_malformed_blockers_without_overwriting(self):
        malformed_blocker_cases = [
            ("null_blocker", None),
            ("string_blocker", "design changed"),
            ("array_blocker", []),
            ("missing_kind", {"code": "c", "evidence": "evidence/tasks/T1/implementer.md", "reason": "r"}),
            (
                "unknown_kind",
                {"kind": "design", "code": "c", "evidence": "evidence/tasks/T1/implementer.md", "reason": "r"},
            ),
            (
                "empty_code",
                {"kind": "design_revision", "code": "", "evidence": "evidence/tasks/T1/implementer.md", "reason": "r"},
            ),
            (
                "missing_code",
                {"kind": "design_revision", "evidence": "evidence/tasks/T1/implementer.md", "reason": "r"},
            ),
            (
                "non_string_code",
                {"kind": "design_revision", "code": ["c"], "evidence": "evidence/tasks/T1/implementer.md", "reason": "r"},
            ),
            (
                "missing_reason",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/tasks/T1/implementer.md"},
            ),
            (
                "empty_reason",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/tasks/T1/implementer.md", "reason": ""},
            ),
            (
                "non_string_reason",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/tasks/T1/implementer.md", "reason": {"r": True}},
            ),
            (
                "missing_evidence",
                {"kind": "design_revision", "code": "c", "reason": "r"},
            ),
            (
                "empty_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "", "reason": "r"},
            ),
            (
                "non_string_evidence",
                {"kind": "design_revision", "code": "c", "evidence": ["evidence.md"], "reason": "r"},
            ),
            (
                "absolute_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "/tmp/evidence.md", "reason": "r"},
            ),
            (
                "windows_absolute_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "C:/tmp/evidence.md", "reason": "r"},
            ),
            (
                "windows_unc_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "//server/share/evidence.md", "reason": "r"},
            ),
            (
                "uri_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "file://evidence.md", "reason": "r"},
            ),
            (
                "tilde_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "~/evidence.md", "reason": "r"},
            ),
            (
                "dot_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "./evidence.md", "reason": "r"},
            ),
            (
                "dotdot_traversal_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/../secret.md", "reason": "r"},
            ),
            (
                "empty_segment_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "evidence//task.md", "reason": "r"},
            ),
            (
                "trailing_separator_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/tasks/", "reason": "r"},
            ),
            (
                "embedded_nul_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/tasks/T1/\x00review.md", "reason": "r"},
            ),
            (
                "embedded_newline_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/tasks/T1/\nreview.md", "reason": "r"},
            ),
            (
                "embedded_carriage_return_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/tasks/T1/\rreview.md", "reason": "r"},
            ),
            (
                "embedded_ascii_control_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/tasks/T1/\x1freview.md", "reason": "r"},
            ),
            (
                "embedded_del_evidence",
                {"kind": "design_revision", "code": "c", "evidence": "evidence/tasks/T1/\x7freview.md", "reason": "r"},
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for name, blocker in malformed_blocker_cases:
                state_path = tmp_path / f"{name}.json"
                self.write_json(
                    state_path,
                    self.valid_reapproval_state(
                        tasks={
                            "T1": {
                                "status": "blocked",
                                "attempts": 1,
                                "blocker": blocker,
                                "reason": "r",
                            }
                        }
                    ),
                )
                original_bytes = state_path.read_bytes()

                result = self.run_approve_design_revision(state_path, ["T1"])

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertIn("blocker", payload["error"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_rejects_blocker_evidence_ascii_controls_without_overwriting_or_traceback(self):
        for name, control in (
            ("nul", "\x00"),
            ("newline", "\n"),
            ("carriage_return", "\r"),
            ("unit_separator", "\x1f"),
            ("del", "\x7f"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / f"{name}.json"
                evidence = f"evidence/tasks/T1/{control}review.md"
                blocker = self.canonical_blocker("design_revision", "T1", evidence=evidence, reason="r")
                state = self.valid_reapproval_state(
                    tasks={"T1": {"status": "blocked", "attempts": 1, "blocker": blocker, "reason": "r"}}
                )
                self.write_json(path, state)
                before = path.read_bytes()

                result = self.run_approve_design_revision(path, ["T1"])

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"])
                self.assertIn("blocker.evidence", payload["error"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_rejects_malformed_blocker_identity_for_all_blocked_tasks_without_overwriting(self):
        valid_design_blocker = self.canonical_blocker("design_revision", "T1", reason="design changed")
        valid_resolved_blocker = self.canonical_blocker(
            "resolved_evidence", "T2", reason="waiting for token", blocker_record_id="sha256:" + "b" * 64
        )
        malformed_values = [
            ("missing_occurrence", "blocker_occurrence", None),
            ("null_occurrence", "blocker_occurrence", None),
            ("bool_occurrence", "blocker_occurrence", True),
            ("zero_occurrence", "blocker_occurrence", 0),
            ("negative_occurrence", "blocker_occurrence", -1),
            ("float_occurrence", "blocker_occurrence", 1.5),
            ("string_occurrence", "blocker_occurrence", "1"),
            ("missing_record_id", "blocker_record_id", None),
            ("nonstring_record_id", "blocker_record_id", 123),
            ("wrong_prefix_record_id", "blocker_record_id", "SHA256:" + "a" * 64),
            ("non64hex_record_id", "blocker_record_id", "sha256:" + "a" * 63),
            ("uppercase_record_id", "blocker_record_id", "sha256:" + "A" * 64),
        ]
        task_reason_cases = [
            ("missing_task_reason", None),
            ("null_task_reason", None),
            ("mismatched_task_reason", "different reason"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for kind in ("design_revision", "resolved_evidence"):
                for name, field, value in malformed_values:
                    blocker = self.canonical_blocker(kind, "T1", reason="design changed")
                    if name.startswith("missing_"):
                        blocker.pop(field)
                    else:
                        blocker[field] = value
                    state_path = tmp_path / f"{kind}_{name}.json"
                    self.write_json(
                        state_path,
                        self.valid_reapproval_state(
                            tasks={
                                "T1": {
                                    "status": "blocked",
                                    "attempts": 1,
                                    "blocker": blocker,
                                    "reason": "design changed",
                                }
                            }
                        ),
                    )
                    original_bytes = state_path.read_bytes()

                    result = self.run_approve_design_revision(state_path, ["T1"] if kind == "design_revision" else [])

                    self.assertEqual(result.returncode, 1, f"{kind}_{name}")
                    payload = self.read_stdout_json(result)
                    self.assertFalse(payload["ok"], f"{kind}_{name}")
                    self.assertIn("blocker", payload["error"], f"{kind}_{name}")
                    self.assertEqual(state_path.read_bytes(), original_bytes, f"{kind}_{name}")

            for kind in ("design_revision", "resolved_evidence"):
                for name, task_reason in task_reason_cases:
                    blocker = self.canonical_blocker(kind, "T1", reason="design changed")
                    task = {
                        "status": "blocked",
                        "attempts": 1,
                        "blocker": blocker,
                        "reason": task_reason,
                    }
                    if name == "missing_task_reason":
                        task.pop("reason")
                    state_path = tmp_path / f"{kind}_{name}.json"
                    self.write_json(state_path, self.valid_reapproval_state(tasks={"T1": task}))
                    original_bytes = state_path.read_bytes()

                    result = self.run_approve_design_revision(state_path, ["T1"] if kind == "design_revision" else [])

                    self.assertEqual(result.returncode, 1, f"{kind}_{name}")
                    payload = self.read_stdout_json(result)
                    self.assertFalse(payload["ok"], f"{kind}_{name}")
                    self.assertIn("reason", payload["error"], f"{kind}_{name}")
                    self.assertEqual(state_path.read_bytes(), original_bytes, f"{kind}_{name}")

            state_path = tmp_path / "malformed_resolved_evidence_alongside_valid_design.json"
            malformed_resolved_blocker = dict(valid_resolved_blocker)
            malformed_resolved_blocker.pop("blocker_record_id")
            self.write_json(
                state_path,
                self.valid_reapproval_state(
                    tasks={
                        "T1": {
                            "status": "blocked",
                            "attempts": 1,
                            "blocker": valid_design_blocker,
                            "reason": "design changed",
                        },
                        "T2": {
                            "status": "blocked",
                            "attempts": 0,
                            "blocker": malformed_resolved_blocker,
                            "reason": "waiting for token",
                        },
                    }
                ),
            )
            original_bytes = state_path.read_bytes()

            result = self.run_approve_design_revision(state_path, ["T1"])

            self.assertEqual(result.returncode, 1, "malformed_resolved_evidence_alongside_valid_design")
            payload = self.read_stdout_json(result)
            self.assertFalse(payload["ok"], "malformed_resolved_evidence_alongside_valid_design")
            self.assertIn("blocker", payload["error"], "malformed_resolved_evidence_alongside_valid_design")
            self.assertEqual(state_path.read_bytes(), original_bytes, "malformed_resolved_evidence_alongside_valid_design")

    def test_approve_design_revision_preserves_current_task_for_unrecovered_blocked_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = pathlib.Path(tmp) / "state.json"
            current_task = {"id": "T2", "attempt": 0, "status": "blocked"}
            resolved_blocker = self.canonical_blocker("resolved_evidence", "T2", reason="r2")
            self.write_json(
                state_path,
                self.valid_reapproval_state(
                    current_task=current_task,
                    tasks={
                        "T1": {
                            "status": "blocked",
                            "attempts": 1,
                            "blocker": self.canonical_blocker("design_revision", "T1", reason="r1"),
                            "reason": "r1",
                        },
                        "T2": {
                            "status": "blocked",
                            "attempts": 0,
                            "blocker": resolved_blocker,
                            "reason": "r2",
                        },
                    },
                ),
            )

            result = self.run_approve_design_revision(state_path, ["T1"])

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["current_task"], current_task)
            self.assertEqual(state["tasks"]["T2"]["status"], "blocked")
            self.assertEqual(state["tasks"]["T2"]["blocker"], resolved_blocker)

    def test_approve_design_revision_rejects_malformed_current_task_without_overwriting(self):
        malformed_current_task_cases = [
            ("string_pointer", "T1"),
            ("array_pointer", []),
            ("missing_id", {"attempt": 1, "status": "blocked"}),
            ("missing_attempt", {"id": "T1", "status": "blocked"}),
            ("missing_status", {"id": "T1", "attempt": 1}),
            ("extra_field", {"id": "T1", "attempt": 1, "status": "blocked", "note": "not canonical"}),
            ("unknown_id", {"id": "T9", "attempt": 1, "status": "blocked"}),
            ("negative_attempt", {"id": "T1", "attempt": -1, "status": "blocked"}),
            ("float_attempt", {"id": "T1", "attempt": 1.0, "status": "blocked"}),
            ("bool_attempt", {"id": "T1", "attempt": True, "status": "blocked"}),
            ("attempt_mismatch", {"id": "T1", "attempt": 2, "status": "blocked"}),
            ("status_mismatch", {"id": "T1", "attempt": 1, "status": "pending"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for name, current_task in malformed_current_task_cases:
                state_path = tmp_path / f"{name}.json"
                self.write_json(state_path, self.valid_reapproval_state(current_task=current_task))
                original_bytes = state_path.read_bytes()

                result = self.run_approve_design_revision(state_path, ["T1"])

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertIn("current_task", payload["error"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_rejects_malformed_referenced_task_attempts_without_overwriting(self):
        malformed_attempts_cases = [
            ("true_attempts", True, 1),
            ("false_attempts", False, 0),
            ("negative_attempts", -1, 0),
            ("float_attempts", 1.0, 1),
            ("string_attempts", "1", 1),
            ("missing_attempts", None, 0),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for name, task_attempts, pointer_attempt in malformed_attempts_cases:
                state_path = tmp_path / f"{name}.json"
                task = {
                    "status": "blocked",
                    "blocker": self.canonical_blocker("design_revision", "T1", reason="r"),
                    "reason": "r",
                }
                if name != "missing_attempts":
                    task["attempts"] = task_attempts
                self.write_json(
                    state_path,
                    self.valid_reapproval_state(
                        current_task={"id": "T1", "attempt": pointer_attempt, "status": "blocked"},
                        tasks={"T1": task},
                    ),
                )
                original_bytes = state_path.read_bytes()

                result = self.run_approve_design_revision(state_path, ["T1"])

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertIn("attempts", payload["error"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_rejects_non_object_task_entries_without_overwriting(self):
        malformed_task_cases = [
            ("null_task", None),
            ("list_task", []),
            ("string_task", "blocked"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for name, malformed_task in malformed_task_cases:
                state_path = tmp_path / f"{name}.json"
                self.write_json(
                    state_path,
                    {
                        "gates": {"design": "pending"},
                        "tasks": {
                            "T1": {"status": "blocked", "attempts": 0, "blocker": self.canonical_blocker("design_revision", "T1", reason="r"), "reason": "r"},
                            "T2": malformed_task,
                        },
                        "implementation": {"approved_control_plane": {"design.md": "H1"}},
                    },
                )
                original_bytes = state_path.read_bytes()

                result = self.run_helper(
                    "approve-design-revision",
                    "--state",
                    str(state_path),
                    "--approved-control-plane",
                    json.dumps({"design.md": "H2"}),
                    "--unblock-tasks",
                    json.dumps(["T1"]),
                    "--allow-approval",
                )

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertIn("object", payload["error"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_rejects_malformed_task_statuses_without_overwriting(self):
        malformed_status_cases = [
            ("missing_status", {}),
            ("null_status", {"status": None}),
            ("list_status", {"status": []}),
            ("object_status", {"status": {"value": "blocked"}}),
            ("unknown_status", {"status": "waiting"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            for name, malformed_task in malformed_status_cases:
                state_path = tmp_path / f"{name}.json"
                self.write_json(
                    state_path,
                    {
                        "gates": {"design": "pending"},
                        "tasks": {
                            "T1": {"status": "blocked", "attempts": 0, "blocker": self.canonical_blocker("design_revision", "T1", reason="r"), "reason": "r"},
                            "T2": malformed_task,
                        },
                        "implementation": {"approved_control_plane": {"design.md": "H1"}},
                    },
                )
                original_bytes = state_path.read_bytes()

                result = self.run_helper(
                    "approve-design-revision",
                    "--state",
                    str(state_path),
                    "--approved-control-plane",
                    json.dumps({"design.md": "H2"}),
                    "--unblock-tasks",
                    json.dumps(["T1"]),
                    "--allow-approval",
                )

                self.assertEqual(result.returncode, 1, name)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"], name)
                self.assertIn("status", payload["error"], name)
                self.assertEqual(state_path.read_bytes(), original_bytes, name)

    def test_approve_design_revision_resets_affected_completed_tasks_and_preserves_history(self):
        old = self.task_contract([{"id": "T1"}, {"id": "T2", "depends_on": ["T1"]}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["new acceptance"]
        tasks = {
            "T1": {
                "status": "completed", "attempts": 3, "fix_cycle": 2, "review_cycle": 4,
                "task_scope_fingerprint": "sha256:" + "1" * 64,
                "review_clean_fingerprint": "sha256:" + "2" * 64,
                "reports": ["evidence/tasks/T1/review.md"],
            },
            "T2": {"status": "completed", "attempts": 1},
        }
        implementation = {
            "completed_tasks": ["T1", "T2"],
            "task_fingerprints": {"T1": ["old-fingerprint"], "T2": ["keep"]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old, tasks=tasks, implementation=implementation))
            result = self.run_contract_revision(path, new, ["T2", "T1"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(path.read_text(encoding="utf-8"))
            for task_id in ("T1", "T2"):
                self.assertEqual(state["tasks"][task_id]["status"], "pending")
                self.assertEqual(state["tasks"][task_id]["revalidation"], "required")
            self.assertEqual(state["tasks"]["T1"]["attempts"], 3)
            self.assertEqual(state["tasks"]["T1"]["fix_cycle"], 2)
            self.assertEqual(state["tasks"]["T1"]["review_cycle"], 4)
            self.assertEqual(state["tasks"]["T1"]["reports"], ["evidence/tasks/T1/review.md"])
            self.assertNotIn("task_scope_fingerprint", state["tasks"]["T1"])
            self.assertNotIn("review_clean_fingerprint", state["tasks"]["T1"])
            self.assertEqual(state["implementation"]["completed_tasks"], [])
            self.assertEqual(state["implementation"]["task_fingerprints"], implementation["task_fingerprints"])
            audit = state["implementation"]["design_revisions"][-1]
            self.assertEqual(audit["reason"], "requirements changed")
            self.assertEqual(audit["declared_affected_tasks"], ["T1", "T2"])
            self.assertEqual(audit["required_affected_tasks"], ["T1", "T2"])
            self.assertEqual(audit["invalidated_evidence"]["T1"]["task_scope_fingerprint"], "sha256:" + "1" * 64)

    def test_approve_design_revision_invalidates_only_affected_current_snapshot_refs_and_audits_old_refs(self):
        old = self.task_contract([{"id": "T1"}, {"id": "T2"}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        affected_refs = {
            "completion_snapshot_refs": [self.snapshot_ref("completion", "T1", "src/T1.py", hash_char="a")],
            "dependency_handoff_snapshot_refs": [],
            "live_snapshot_refs": [self.snapshot_ref("live", "T1", "src/T1.py", hash_char="c")],
        }
        unaffected_refs = {
            "completion_snapshot_refs": [self.snapshot_ref("completion", "T2", "src/T2.py", hash_char="d")],
            "dependency_handoff_snapshot_refs": [],
            "live_snapshot_refs": [self.snapshot_ref("live", "T2", "src/T2.py", hash_char="e")],
        }
        tasks = {
            "T1": {"status": "completed", "attempts": 1, **affected_refs},
            "T2": {"status": "completed", "attempts": 2, **unaffected_refs},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old, tasks=tasks, implementation={"completed_tasks": ["T1", "T2"]}))

            result = self.run_contract_revision(path, new, ["T1"])

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(path.read_text(encoding="utf-8"))
            for field in affected_refs:
                self.assertEqual(state["tasks"]["T1"][field], [])
            for field, refs in unaffected_refs.items():
                self.assertEqual(state["tasks"]["T2"][field], refs)
            audit = state["implementation"]["design_revisions"][-1]["invalidated_evidence"]["T1"]
            for field, refs in affected_refs.items():
                self.assertEqual(audit[field], refs)

    def test_approve_design_revision_legacy_mode_preserves_snapshot_refs(self):
        refs = {
            "completion_snapshot_refs": [{"opaque": "completion"}],
            "dependency_handoff_snapshot_refs": [{"opaque": "dependency"}],
            "live_snapshot_refs": [{"opaque": "live"}],
        }
        task = {
            "status": "blocked",
            "attempts": 1,
            "blocker": self.canonical_blocker("design_revision", "T1", reason="changed"),
            "reason": "changed",
            **refs,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.valid_reapproval_state(tasks={"T1": task}))

            result = self.run_approve_design_revision(path, ["T1"])

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            updated_task = json.loads(path.read_text(encoding="utf-8"))["tasks"]["T1"]
            for field, value in refs.items():
                self.assertEqual(updated_task[field], value)

    def test_approve_design_revision_rejects_malformed_current_snapshot_refs_without_overwriting_or_traceback(self):
        old = self.task_contract([{"id": "T1"}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        for field in (
            "completion_snapshot_refs",
            "dependency_handoff_snapshot_refs",
            "live_snapshot_refs",
        ):
            for malformed in (None, "current", {}, True):
                with self.subTest(field=field, malformed=malformed), tempfile.TemporaryDirectory() as tmp:
                    path = pathlib.Path(tmp) / "state.json"
                    state = self.revision_state(
                        old,
                        tasks={"T1": {"status": "completed", "attempts": 1, field: malformed}},
                        implementation={"completed_tasks": ["T1"]},
                    )
                    self.write_json(path, state)
                    before = path.read_bytes()

                    result = self.run_contract_revision(path, new, ["T1"])

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    payload = self.read_stdout_json(result)
                    self.assertFalse(payload["ok"])
                    self.assertIn(field, payload["error"])
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_preserves_unaffected_completed_tasks(self):
        old = self.task_contract([{"id": "T1"}, {"id": "T2"}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["verification"] = {"commands": ["new verification"]}
        tasks = {
            "T1": {"status": "completed", "attempts": 1},
            "T2": {"status": "completed", "attempts": 2, "task_scope_fingerprint": "sha256:" + "3" * 64},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old, tasks=tasks, implementation={"completed_tasks": ["T1", "T2"]}))
            result = self.run_contract_revision(path, new, ["T1"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(state["tasks"]["T2"], tasks["T2"])
            self.assertEqual(state["implementation"]["completed_tasks"], ["T2"])

    def test_approve_design_revision_rejects_missing_affected_task_without_overwriting(self):
        old = self.task_contract([{"id": "T1"}, {"id": "T2", "depends_on": ["T1"]}])
        new = json.loads(json.dumps(old)); new["tasks"][0]["acceptance"] = ["changed"]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"; self.write_json(path, self.revision_state(old)); before = path.read_bytes()
            result = self.run_contract_revision(path, new, ["T1"])
            self.assertEqual(result.returncode, 1)
            self.assertEqual(
                self.read_stdout_json(result)["detail"],
                {"missing_affected_tasks": ["T2"], "extra_affected_tasks": [], "duplicate_affected_tasks": []},
            )
            self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_rejects_extra_duplicate_and_unknown_affected_tasks_without_overwriting(self):
        old = self.task_contract([{"id": "T1"}, {"id": "T2"}]); new = json.loads(json.dumps(old)); new["tasks"][0]["acceptance"] = ["changed"]
        with tempfile.TemporaryDirectory() as tmp:
            for name, affected in (("extra", ["T1", "T2"]), ("duplicate", ["T1", "T1"]), ("unknown", ["T1", "T9"])):
                path = pathlib.Path(tmp) / f"{name}.json"; self.write_json(path, self.revision_state(old)); before = path.read_bytes()
                result = self.run_contract_revision(path, new, affected)
                self.assertEqual(result.returncode, 1, name)
                detail = self.read_stdout_json(result)["detail"]
                self.assertIn("missing_affected_tasks", detail, name)
                self.assertIn("extra_affected_tasks", detail, name)
                if name == "duplicate":
                    self.assertEqual(detail["duplicate_affected_tasks"], ["T1"])
                self.assertEqual(path.read_bytes(), before, name)

    def test_approve_design_revision_computes_old_and_new_dependency_closure(self):
        old = self.task_contract([
            {"id": "T1"}, {"id": "T2", "depends_on": ["T1"]}, {"id": "T3", "depends_on": ["T2"]}, {"id": "T4"}
        ])
        new = self.task_contract([
            {"id": "T1"}, {"id": "T2"}, {"id": "T3", "depends_on": ["T2"]}, {"id": "T4", "depends_on": ["T1"]}
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"; self.write_json(path, self.revision_state(old))
            result = self.run_contract_revision(path, new, ["T1", "T2", "T3", "T4"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.read_stdout_json(result)["required_affected_tasks"], ["T1", "T2", "T3", "T4"])

    def test_approve_design_revision_includes_changed_handoff_chain_owners(self):
        handoff = {"path": "src/shared.py", "from_task": "T1", "to_task": "T2"}
        old = self.task_contract([{"id": "T1", "mutation_targets": ["src/shared.py"]}, {"id": "T2"}])
        new = self.task_contract([
            {"id": "T1", "mutation_targets": ["src/shared.py"]},
            {"id": "T2", "depends_on": ["T1"], "mutation_targets": ["src/shared.py"], "ownership_handoffs": [handoff]},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"; self.write_json(path, self.revision_state(old))
            result = self.run_contract_revision(path, new, ["T2", "T1"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.read_stdout_json(result)["required_affected_tasks"], ["T1", "T2"])

    def test_approve_design_revision_replaces_control_plane_and_task_contract_once(self):
        old = self.task_contract([{"id": "T1"}]); new = json.loads(json.dumps(old)); new["tasks"][0]["context_refs"] = ["CTX-NEW"]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"; self.write_json(path, self.revision_state(old))
            result = self.run_contract_revision(path, new, ["T1"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(state["implementation"]["approved_control_plane"], {"design.md": "H2", "plan.yaml": "P2"})
            self.assertEqual(state["implementation"]["approved_task_contract"], new)
            self.assertEqual(len(state["implementation"]["design_revisions"]), 1)
            self.assertEqual(state["gates"]["design"], "approved")

    def test_approve_design_revision_rejects_affected_in_progress_task_without_overwriting(self):
        old = self.task_contract([{"id": "T1"}])
        new = json.loads(json.dumps(old)); new["tasks"][0]["acceptance"] = ["changed"]
        state = self.revision_state(
            old,
            tasks={"T1": {"status": "in_progress", "attempts": 1}},
        )
        state["current_task"] = {"id": "T1", "attempt": 1, "status": "in_progress"}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"; self.write_json(path, state); before = path.read_bytes()
            result = self.run_contract_revision(path, new, ["T1"])
            self.assertEqual(result.returncode, 1)
            self.assertIn("in_progress", self.read_stdout_json(result)["error"])
            self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_rejects_added_deleted_or_renamed_task_ids_without_overwriting(self):
        old = self.task_contract([{"id": "T1"}, {"id": "T2"}])
        variants = {
            "added": self.task_contract([{"id": "T1"}, {"id": "T2"}, {"id": "T3"}]),
            "deleted": self.task_contract([{"id": "T1"}]),
            "renamed": self.task_contract([{"id": "T1"}, {"id": "T9"}]),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, new in variants.items():
                path = pathlib.Path(tmp) / f"{name}.json"; self.write_json(path, self.revision_state(old)); before = path.read_bytes()
                result = self.run_contract_revision(path, new, [])
                self.assertEqual(result.returncode, 1, name); self.assertIn("Task ID set", self.read_stdout_json(result)["error"])
                self.assertEqual(path.read_bytes(), before, name)

    def assert_contract_revision_rejected_without_overwrite(self, old_contract, new_contract, name):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / f"{name}.json"
            self.write_json(path, self.revision_state(old_contract))
            before = path.read_bytes()
            result = self.run_contract_revision(path, new_contract, [])
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertFalse(self.read_stdout_json(result)["ok"])
            self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_accepts_multi_path_handoffs_when_task_declaration_order_differs_from_path_order(self):
        paths = ["src/z-last.py", "src/a-first.py"]
        handoffs = [
            {"path": path, "from_task": "T1", "to_task": "T2"}
            for path in paths
        ]
        old = self.task_contract([{"id": "T1"}, {"id": "T2", "depends_on": ["T1"]}])
        new = self.task_contract([
            {"id": "T1", "mutation_targets": paths},
            {
                "id": "T2", "depends_on": ["T1"], "mutation_targets": paths,
                "ownership_handoffs": handoffs,
            },
        ])
        self.assertEqual(
            [row["path"] for row in new["ownership_table"]],
            ["src/a-first.py", "src/z-last.py"],
        )
        self.assertEqual(
            [handoff["path"] for handoff in new["tasks"][1]["ownership_handoffs"]],
            ["src/a-first.py", "src/z-last.py"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old))
            result = self.run_contract_revision(path, new, ["T2", "T1"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.read_stdout_json(result)["required_affected_tasks"], ["T1", "T2"])

    def test_approve_design_revision_contract_path_grammar_matches_task_helper(self):
        for suffix in ("]", "{", "}"):
            with self.subTest(suffix=suffix):
                old = self.task_contract([{"id": "T1", "mutation_targets": [f"src/file{suffix}.py"]}])
                new = json.loads(json.dumps(old))
                new["tasks"][0]["acceptance"] = ["changed"]
                with tempfile.TemporaryDirectory() as tmp:
                    path = pathlib.Path(tmp) / "state.json"
                    self.write_json(path, self.revision_state(old))
                    result = self.run_contract_revision(path, new, ["T1"])
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_approve_design_revision_rejects_unhashable_contract_values_without_overwriting_or_traceback(self):
        valid = self.task_contract([{"id": "T1"}])
        cases = []
        for name, target in (("object_mutation_target", {"path": "src/T1.py"}), ("list_mutation_target", ["src/T1.py"])):
            malformed = json.loads(json.dumps(valid))
            malformed["tasks"][0]["mutation_targets"] = [target]
            cases.append((name, malformed))
        for name, mutate in (
            ("object_plan_order_id", lambda contract: contract.__setitem__("plan_order", [{"id": "T1"}])),
            ("list_dependency_id", lambda contract: contract["tasks"][0].__setitem__("depends_on", [["T1"]])),
            ("object_owner", lambda contract: contract["ownership_table"][0].__setitem__("owners", [{"id": "T1"}])),
            ("list_final_owner", lambda contract: contract["ownership_table"][0].__setitem__("final_owner", ["T1"])),
        ):
            malformed = json.loads(json.dumps(valid))
            mutate(malformed)
            cases.append((name, malformed))

        handoff_valid = self.task_contract([
            {"id": "T1", "mutation_targets": ["src/shared.py"]},
            {
                "id": "T2", "depends_on": ["T1"], "mutation_targets": ["src/shared.py"],
                "ownership_handoffs": [{"path": "src/shared.py", "from_task": "T1", "to_task": "T2"}],
            },
        ])
        for name, field, value in (
            ("object_handoff_from", "from_task", {"id": "T1"}),
            ("list_handoff_to", "to_task", ["T2"]),
        ):
            malformed = json.loads(json.dumps(handoff_valid))
            malformed["tasks"][1]["ownership_handoffs"][0][field] = value
            cases.append((name, malformed))

        for name, malformed_contract in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / f"{name}.json"
                self.write_json(path, self.revision_state(valid))
                before = path.read_bytes()
                result = self.run_contract_revision(path, malformed_contract, [])
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertFalse(self.read_stdout_json(result)["ok"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_rejects_malformed_completed_tasks_without_overwriting_or_traceback(self):
        valid = self.task_contract([{"id": "T1"}, {"id": "T2"}])
        cases = (
            ("object", {"T1": True}),
            ("unhashable_object_item", ["T1", {"id": "T2"}]),
            ("unhashable_list_item", ["T1", ["T2"]]),
            ("unknown", ["T9"]),
            ("duplicate", ["T1", "T1"]),
        )
        for name, completed_tasks in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / f"{name}.json"
                state = self.revision_state(
                    valid,
                    implementation={"completed_tasks": completed_tasks},
                )
                self.write_json(path, state)
                before = path.read_bytes()

                result = self.run_contract_revision(path, valid, [])

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertFalse(self.read_stdout_json(result)["ok"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_allows_missing_completed_tasks_for_compatibility(self):
        old = self.task_contract([{"id": "T1"}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        state = self.revision_state(old)
        state["implementation"].pop("completed_tasks")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, state)

            result = self.run_contract_revision(path, new, ["T1"])

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["implementation"]["completed_tasks"], [])

    def test_approve_design_revision_rejects_whitespace_only_contract_text_without_overwriting_or_traceback(self):
        valid = self.task_contract([{"id": "T1"}])
        cases = (
            ("new_acceptance", "new", "acceptance", lambda contract: contract["tasks"][0].__setitem__("acceptance", ["   "])),
            ("new_command", "new", "commands", lambda contract: contract["tasks"][0]["verification"].__setitem__("commands", ["\t"])),
            ("new_notes", "new", "notes", lambda contract: contract["tasks"][0].__setitem__("verification", {"commands": [], "notes": "\r\n"})),
            ("old_acceptance", "old", "acceptance", lambda contract: contract["tasks"][0].__setitem__("acceptance", ["   "])),
            ("old_command", "old", "commands", lambda contract: contract["tasks"][0]["verification"].__setitem__("commands", ["\t"])),
            ("old_notes", "old", "notes", lambda contract: contract["tasks"][0].__setitem__("verification", {"commands": [], "notes": "\r\n"})),
        )
        for name, side, expected_error, mutate in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                old = json.loads(json.dumps(valid))
                new = json.loads(json.dumps(valid))
                mutate(old if side == "old" else new)
                path = pathlib.Path(tmp) / f"{name}.json"
                self.write_json(path, self.revision_state(old))
                before = path.read_bytes()

                result = self.run_contract_revision(path, new, [])

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"])
                self.assertIn(expected_error, payload["error"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_accepts_topological_handoff_owner_order_independent_of_plan_order(self):
        handoff = {"path": "src/shared.py", "from_task": "T1", "to_task": "T4"}
        old = self.task_contract([{"id": "T4", "depends_on": ["T1"]}, {"id": "T1"}])
        new = self.task_contract([
            {
                "id": "T4", "depends_on": ["T1"], "mutation_targets": ["src/shared.py"],
                "ownership_handoffs": [handoff],
            },
            {"id": "T1", "mutation_targets": ["src/shared.py"]},
        ])
        new["ownership_table"][0] = {
            "path": "src/shared.py",
            "owners": ["T1", "T4"],
            "handoffs": [handoff],
            "final_owner": "T4",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old))

            result = self.run_contract_revision(path, new, ["T4", "T1"])

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.read_stdout_json(result)["required_affected_tasks"], ["T4", "T1"])

    def test_approve_design_revision_rejects_contract_control_plane_mutation_targets_without_overwriting_or_traceback(self):
        valid = self.task_contract([{"id": "T1"}])
        for blocked_path in (".git/config", ".dev-docs/changes/change/state.json", ".superpowers/sdd/report.md"):
            for side in ("old", "new"):
                with self.subTest(path=blocked_path, side=side), tempfile.TemporaryDirectory() as tmp:
                    old = json.loads(json.dumps(valid))
                    new = json.loads(json.dumps(valid))
                    malformed = old if side == "old" else new
                    malformed["tasks"][0]["mutation_targets"] = [blocked_path]
                    malformed["ownership_table"] = [{
                        "path": blocked_path,
                        "owners": ["T1"],
                        "handoffs": [],
                        "final_owner": "T1",
                    }]
                    path = pathlib.Path(tmp) / f"{side}.json"
                    self.write_json(path, self.revision_state(old))
                    before = path.read_bytes()

                    result = self.run_contract_revision(path, new, [])

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertFalse(self.read_stdout_json(result)["ok"])
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_rejects_malformed_new_contract_without_overwriting(self):
        handoff = {"path": "src/shared.py", "from_task": "T1", "to_task": "T2"}
        valid = self.task_contract([
            {"id": "T1", "mutation_targets": ["src/shared.py"]},
            {
                "id": "T2", "depends_on": ["T1"],
                "mutation_targets": ["src/shared.py"], "ownership_handoffs": [handoff],
            },
        ])
        cases = {}

        malformed = json.loads(json.dumps(valid)); malformed["ownership_table"][0]["handoffs"] = {}
        cases["handoffs_non_array"] = malformed
        malformed = json.loads(json.dumps(valid)); malformed["ownership_table"][0]["handoffs"][0]["from_task"] = "T9"
        cases["unknown_endpoint"] = malformed
        malformed = json.loads(json.dumps(valid)); malformed["ownership_table"].append(json.loads(json.dumps(malformed["ownership_table"][0])))
        cases["duplicate_ownership_path"] = malformed
        malformed = json.loads(json.dumps(valid)); malformed["tasks"][0]["mutation_targets"] = []
        cases["row_mutation_targets_mismatch"] = malformed
        malformed = json.loads(json.dumps(valid)); malformed["ownership_table"][0]["handoffs"] = []
        cases["broken_chain"] = malformed

        three_owner = self.task_contract([
            {"id": "T1", "mutation_targets": ["src/shared.py"]},
            {
                "id": "T2", "depends_on": ["T1"], "mutation_targets": ["src/shared.py"],
                "ownership_handoffs": [{"path": "src/shared.py", "from_task": "T1", "to_task": "T2"}],
            },
            {
                "id": "T3", "depends_on": ["T2"], "mutation_targets": ["src/shared.py"],
                "ownership_handoffs": [{"path": "src/shared.py", "from_task": "T2", "to_task": "T3"}],
            },
        ])
        malformed = json.loads(json.dumps(three_owner))
        branch = {"path": "src/shared.py", "from_task": "T1", "to_task": "T3"}
        malformed["ownership_table"][0]["handoffs"].append(branch)
        malformed["tasks"][2]["ownership_handoffs"].append(branch)
        cases["branch_extra_chain"] = malformed

        malformed = self.task_contract([
            {"id": "T1", "depends_on": ["T2"]},
            {"id": "T2", "depends_on": ["T1"]},
        ])
        cases["dependency_cycle"] = malformed

        for name, malformed_contract in cases.items():
            with self.subTest(name=name):
                self.assert_contract_revision_rejected_without_overwrite(valid, malformed_contract, name)

    def test_approve_design_revision_rejects_malformed_old_contract_without_overwriting(self):
        valid = self.task_contract([{"id": "T1"}])
        malformed_old = json.loads(json.dumps(valid))
        malformed_old["ownership_table"][0]["owners"] = ["T1", "T1"]
        self.assert_contract_revision_rejected_without_overwrite(malformed_old, valid, "malformed_old_contract")

    def test_approve_design_revision_rejects_uri_scheme_context_refs_in_new_contract_without_overwriting_or_traceback(self):
        valid = self.task_contract([{"id": "T1"}])
        for context_ref in ("file:secret", "https:artifact"):
            with self.subTest(context_ref=context_ref), tempfile.TemporaryDirectory() as tmp:
                malformed_new = json.loads(json.dumps(valid))
                malformed_new["tasks"][0]["context_refs"] = [context_ref]
                path = pathlib.Path(tmp) / "state.json"
                self.write_json(path, self.revision_state(valid))
                before = path.read_bytes()

                result = self.run_contract_revision(path, malformed_new, ["T1"])

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertFalse(self.read_stdout_json(result)["ok"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_rejects_windows_drive_context_refs_in_old_contract_without_overwriting_or_traceback(self):
        valid = self.task_contract([{"id": "T1"}])
        malformed_old = json.loads(json.dumps(valid))
        malformed_old["tasks"][0]["context_refs"] = ["C:relative"]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(malformed_old))
            before = path.read_bytes()

            result = self.run_contract_revision(path, valid, ["T1"])

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertFalse(self.read_stdout_json(result)["ok"])
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_rejects_noncanonical_contract_order_without_overwriting_or_traceback(self):
        handoffs = [
            {"path": "src/a.py", "from_task": "T1", "to_task": "T2"},
            {"path": "src/z.py", "from_task": "T1", "to_task": "T2"},
        ]
        valid = self.task_contract([
            {"id": "T1", "mutation_targets": ["src/z.py", "src/a.py"]},
            {
                "id": "T2", "depends_on": ["T1"],
                "mutation_targets": ["src/z.py", "src/a.py"],
                "ownership_handoffs": list(reversed(handoffs)),
            },
        ])
        mutations = (
            ("mutation_targets_reordered", "canonical sorted order", lambda contract: contract["tasks"][0].__setitem__(
                "mutation_targets", list(reversed(contract["tasks"][0]["mutation_targets"]))
            )),
            ("mutation_targets_duplicate", "duplicate mutation target", lambda contract: contract["tasks"][0].__setitem__(
                "mutation_targets", contract["tasks"][0]["mutation_targets"] + [contract["tasks"][0]["mutation_targets"][0]]
            )),
            ("task_handoffs_reordered", "canonical sorted order", lambda contract: contract["tasks"][1].__setitem__(
                "ownership_handoffs", list(reversed(contract["tasks"][1]["ownership_handoffs"]))
            )),
            ("ownership_table_reordered", "canonical path order", lambda contract: contract.__setitem__(
                "ownership_table", list(reversed(contract["ownership_table"]))
            )),
        )
        for name, expected_error, mutate in mutations:
            for side in ("old", "new"):
                with self.subTest(name=name, side=side), tempfile.TemporaryDirectory() as tmp:
                    old = json.loads(json.dumps(valid))
                    new = json.loads(json.dumps(valid))
                    mutate(old if side == "old" else new)
                    path = pathlib.Path(tmp) / f"{name}-{side}.json"
                    self.write_json(path, self.revision_state(old))
                    before = path.read_bytes()

                    result = self.run_contract_revision(path, new, [])

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    payload = self.read_stdout_json(result)
                    self.assertFalse(payload["ok"])
                    self.assertIn(expected_error, payload["error"])
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_rejects_surrounding_whitespace_in_contract_text_without_overwriting_or_traceback(self):
        valid = self.task_contract([{"id": "T1"}])
        mutations = (
            ("acceptance_leading", lambda contract: contract["tasks"][0].__setitem__("acceptance", [" accept T1"])),
            ("acceptance_trailing", lambda contract: contract["tasks"][0].__setitem__("acceptance", ["accept T1 "])),
            ("command_leading", lambda contract: contract["tasks"][0]["verification"].__setitem__("commands", [" verify T1"])),
            ("command_trailing", lambda contract: contract["tasks"][0]["verification"].__setitem__("commands", ["verify T1 "])),
            ("notes_leading", lambda contract: contract["tasks"][0].__setitem__(
                "verification", {"commands": [], "notes": " manual verification"}
            )),
            ("notes_trailing", lambda contract: contract["tasks"][0].__setitem__(
                "verification", {"commands": [], "notes": "manual verification "}
            )),
        )
        for name, mutate in mutations:
            for side in ("old", "new"):
                with self.subTest(name=name, side=side), tempfile.TemporaryDirectory() as tmp:
                    old = json.loads(json.dumps(valid))
                    new = json.loads(json.dumps(valid))
                    mutate(old if side == "old" else new)
                    path = pathlib.Path(tmp) / f"{name}-{side}.json"
                    self.write_json(path, self.revision_state(old))
                    before = path.read_bytes()

                    result = self.run_contract_revision(path, new, [])

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertFalse(self.read_stdout_json(result)["ok"])
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(path.read_bytes(), before)

    def test_approve_design_revision_rejects_unpaired_surrogate_identity_without_overwriting_or_traceback(self):
        valid = self.task_contract([{"id": "T1"}])
        for side in ("old", "new"):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as tmp:
                old = json.loads(json.dumps(valid))
                new = json.loads(json.dumps(valid))
                malformed = old if side == "old" else new
                malformed["tasks"][0]["acceptance"] = ["unpaired surrogate \ud800"]
                if side == "old":
                    new["tasks"][0]["acceptance"] = ["changed acceptance"]
                path = pathlib.Path(tmp) / f"surrogate-{side}.json"
                path.write_text(json.dumps(self.revision_state(old)), encoding="utf-8")
                before = path.read_bytes()

                result = self.run_contract_revision(path, new, ["T1"])

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_contract_mode_rejects_unchanged_identity_preflight_and_approval_without_overwriting(self):
        contract = self.task_contract([{"id": "T1"}, {"id": "T2", "depends_on": ["T1"]}])
        blocker = self.canonical_blocker("design_revision", "T1", reason="context changed")
        state = self.revision_state(
            contract,
            tasks={
                "T1": {"status": "blocked", "attempts": 1, "blocker": blocker, "reason": "context changed"},
                "T2": {"status": "pending", "attempts": 0, "design_revision_authorization": "sha256:" + "b" * 64},
            },
        )
        for mode in ("preflight", "approve"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "state.json"
                self.write_json(path, state)
                before = path.read_bytes()

                if mode == "preflight":
                    result = self.run_design_revision_preflight(path, contract, [])
                else:
                    result = self.run_contract_revision(path, contract, [])

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"])
                self.assertIn("--unblock-tasks", payload["error"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)
                preserved = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(preserved["gates"]["design"], "pending")
                self.assertEqual(preserved["tasks"]["T1"]["status"], "blocked")
                self.assertEqual(preserved["tasks"]["T1"]["blocker"], blocker)
                self.assertIsNotNone(preserved["tasks"]["T2"]["design_revision_authorization"])

    def test_contract_mode_identity_change_preflight_and_approval_remain_in_parity(self):
        old = self.task_contract([{"id": "T1"}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old))
            preflight = self.run_design_revision_preflight(path, new, ["T1"])
            approval = self.run_contract_revision(path, new, ["T1"])
            self.assertEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
            self.assertEqual(approval.returncode, 0, approval.stdout + approval.stderr)
            preflight_payload = self.read_stdout_json(preflight)
            audit = json.loads(path.read_text(encoding="utf-8"))["implementation"]["design_revisions"][-1]
            self.assertNotEqual(preflight_payload["old_contract_identity"], preflight_payload["new_contract_identity"])
            self.assertEqual(preflight_payload["old_contract_identity"], audit["old_contract_identity"])
            self.assertEqual(preflight_payload["new_contract_identity"], audit["new_contract_identity"])

    def test_contract_revision_rejects_malformed_per_path_snapshot_refs_in_preflight_and_approval(self):
        old = self.task_contract([
            {"id": "T1", "mutation_targets": ["src/a.py", "src/b.py"]},
            {
                "id": "T2", "depends_on": ["T1"], "mutation_targets": ["src/b.py"],
                "ownership_handoffs": [{"path": "src/b.py", "from_task": "T1", "to_task": "T2"}],
            },
        ])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        valid_completion = self.snapshot_ref("completion", "T1", "src/a.py")
        valid_dependency = self.snapshot_ref("dependency", "T2", "src/b.py", from_task="T1")
        malformed_cases = []
        for value in ("bad", {}, None):
            malformed_cases.append((f"entry_{type(value).__name__}", "completion_snapshot_refs", [value]))
        for field in ("evidence_path", "record_hash", "path", "path_id"):
            ref = dict(valid_completion); ref.pop(field)
            malformed_cases.append((f"missing_{field}", "completion_snapshot_refs", [ref]))
        ref = dict(valid_completion); ref["extra"] = True
        malformed_cases.append(("extra_field", "completion_snapshot_refs", [ref]))
        for name, field, value in (
            ("wrong_evidence_type", "evidence_path", 1),
            ("wrong_path_type", "path", []),
            ("bad_evidence_path", "evidence_path", "../snapshot.json"),
            ("bad_filename_kind", "evidence_path", valid_completion["evidence_path"].replace("completion-", "live-")),
            ("bad_path", "path", "src/../a.py"),
            ("bad_path_id", "path_id", "A" * 64),
            ("path_id_mismatch", "path_id", "0" * 64),
            ("bad_record_hash", "record_hash", "a" * 64),
        ):
            ref = dict(valid_completion); ref[field] = value
            malformed_cases.append((name, "completion_snapshot_refs", [ref]))
        for name, edge in (
            ("missing_edge", None),
            ("edge_extra", {**valid_dependency["incoming_edge"], "extra": True}),
            ("edge_path_mismatch", {**valid_dependency["incoming_edge"], "path": "src/a.py"}),
            ("edge_from_mismatch", {**valid_dependency["incoming_edge"], "from": "T2"}),
            ("edge_to_mismatch", {**valid_dependency["incoming_edge"], "to": "T1"}),
        ):
            ref = dict(valid_dependency)
            if edge is None:
                ref.pop("incoming_edge")
            else:
                ref["incoming_edge"] = edge
            malformed_cases.append((name, "dependency_handoff_snapshot_refs", [ref]))
        second = self.snapshot_ref("completion", "T1", "src/b.py", hash_char="b")
        malformed_cases.extend((
            ("noncanonical_order", "completion_snapshot_refs", [second, valid_completion]),
            ("duplicate_path", "completion_snapshot_refs", [valid_completion, valid_completion]),
            ("duplicate_evidence_path", "completion_snapshot_refs", [valid_completion, {**valid_completion, "path": "src/b.py", "path_id": second["path_id"]}]),
        ))

        for name, field, refs in malformed_cases:
            for mode in ("preflight", "approve"):
                with self.subTest(name=name, field=field, mode=mode), tempfile.TemporaryDirectory() as tmp:
                    path = pathlib.Path(tmp) / "state.json"
                    state = self.revision_state(old)
                    state["tasks"]["T1" if field != "dependency_handoff_snapshot_refs" else "T2"][field] = refs
                    self.write_json(path, state)
                    before = path.read_bytes()
                    runner = self.run_design_revision_preflight if mode == "preflight" else self.run_contract_revision
                    result = runner(path, new, ["T1", "T2"])
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertFalse(self.read_stdout_json(result)["ok"])
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(path.read_bytes(), before)

    def test_contract_revision_accepts_valid_per_path_snapshot_refs_and_audits_them(self):
        old = self.task_contract([
            {"id": "T1", "mutation_targets": ["src/a.py", "src/b.py"]},
            {
                "id": "T2", "depends_on": ["T1"], "mutation_targets": ["src/b.py"],
                "ownership_handoffs": [{"path": "src/b.py", "from_task": "T1", "to_task": "T2"}],
            },
        ])
        new = json.loads(json.dumps(old)); new["tasks"][0]["acceptance"] = ["changed"]
        refs = {
            "completion_snapshot_refs": [
                self.snapshot_ref("completion", "T1", "src/a.py", hash_char="a"),
                self.snapshot_ref("completion", "T1", "src/b.py", hash_char="b"),
            ],
            "live_snapshot_refs": [
                self.snapshot_ref("live", "T1", "src/a.py", hash_char="c"),
                self.snapshot_ref("live", "T1", "src/b.py", hash_char="d"),
            ],
        }
        dependency_refs = [self.snapshot_ref("dependency", "T2", "src/b.py", from_task="T1", hash_char="e")]
        tasks = {
            "T1": {"status": "completed", "attempts": 1, **refs},
            "T2": {"status": "completed", "attempts": 1, "dependency_handoff_snapshot_refs": dependency_refs},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old, tasks=tasks, implementation={"completed_tasks": ["T1", "T2"]}))
            preflight = self.run_design_revision_preflight(path, new, ["T1", "T2"])
            self.assertEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
            approval = self.run_contract_revision(path, new, ["T1", "T2"])
            self.assertEqual(approval.returncode, 0, approval.stdout + approval.stderr)
            audit = json.loads(path.read_text(encoding="utf-8"))["implementation"]["design_revisions"][-1]["invalidated_evidence"]
            self.assertEqual(audit["T1"]["completion_snapshot_refs"], refs["completion_snapshot_refs"])
            self.assertEqual(audit["T1"]["live_snapshot_refs"], refs["live_snapshot_refs"])
            self.assertEqual(audit["T2"]["dependency_handoff_snapshot_refs"], dependency_refs)

    def test_contract_revision_dependency_snapshot_refs_use_incoming_edge_from_to_schema_in_preflight_and_approval(self):
        old = self.task_contract([
            {"id": "T1", "mutation_targets": ["src/b.py"]},
            {
                "id": "T2", "depends_on": ["T1"], "mutation_targets": ["src/b.py"],
                "ownership_handoffs": [{"path": "src/b.py", "from_task": "T1", "to_task": "T2"}],
            },
        ])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        dependency_ref = self.snapshot_ref("dependency", "T2", "src/b.py", from_task="T1", hash_char="e")
        dependency_ref["incoming_edge"] = {"path": "src/b.py", "from": "T1", "to": "T2"}
        tasks = {
            "T1": {"status": "completed", "attempts": 1},
            "T2": {"status": "completed", "attempts": 1, "dependency_handoff_snapshot_refs": [dependency_ref]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old, tasks=tasks, implementation={"completed_tasks": ["T1", "T2"]}))

            preflight = self.run_design_revision_preflight(path, new, ["T1", "T2"])
            self.assertEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
            approval = self.run_contract_revision(path, new, ["T1", "T2"])

            self.assertEqual(approval.returncode, 0, approval.stdout + approval.stderr)
            audit = json.loads(path.read_text(encoding="utf-8"))["implementation"]["design_revisions"][-1]["invalidated_evidence"]
            self.assertEqual(audit["T2"]["dependency_handoff_snapshot_refs"], [dependency_ref])

    def test_contract_revision_rejects_legacy_dependency_snapshot_incoming_edge_from_task_to_task_schema_without_overwriting_or_traceback(self):
        old = self.task_contract([
            {"id": "T1", "mutation_targets": ["src/b.py"]},
            {
                "id": "T2", "depends_on": ["T1"], "mutation_targets": ["src/b.py"],
                "ownership_handoffs": [{"path": "src/b.py", "from_task": "T1", "to_task": "T2"}],
            },
        ])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        legacy_dependency_ref = self.snapshot_ref("dependency", "T2", "src/b.py", from_task="T1", hash_char="e")
        legacy_dependency_ref["incoming_edge"] = {"path": "src/b.py", "from_task": "T1", "to_task": "T2"}
        for mode in ("preflight", "approve"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "state.json"
                tasks = {
                    "T1": {"status": "completed", "attempts": 1},
                    "T2": {
                        "status": "completed", "attempts": 1,
                        "dependency_handoff_snapshot_refs": [legacy_dependency_ref],
                    },
                }
                self.write_json(path, self.revision_state(old, tasks=tasks, implementation={"completed_tasks": ["T1", "T2"]}))
                before = path.read_bytes()
                runner = self.run_design_revision_preflight if mode == "preflight" else self.run_contract_revision

                result = runner(path, new, ["T1", "T2"])

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                payload = self.read_stdout_json(result)
                self.assertFalse(payload["ok"])
                self.assertIn("incoming_edge", payload["error"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_validate_design_revision_succeeds_without_writing_or_approving_gate(self):
        old = self.task_contract([{"id": "T1"}, {"id": "T2", "depends_on": ["T1"]}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old))
            before = path.read_bytes()

            result = self.run_design_revision_preflight(path, new, ["T1", "T2"])

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertEqual(payload["ok"], True)
            self.assertEqual(payload["required_affected_tasks"], ["T1", "T2"])
            self.assertEqual(payload["declared_affected_tasks"], ["T1", "T2"])
            self.assertRegex(payload["old_contract_identity"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(payload["new_contract_identity"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(payload["approved_control_plane_identity"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["gates"]["design"], "pending")

    def test_validate_design_revision_rejects_missing_and_extra_affected_tasks_without_writing(self):
        old = self.task_contract([{"id": "T1"}, {"id": "T2", "depends_on": ["T1"]}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        for name, affected in (("missing", ["T1"]), ("extra", ["T1", "T2", "T9"])):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / f"{name}.json"
                self.write_json(path, self.revision_state(old))
                before = path.read_bytes()

                result = self.run_design_revision_preflight(path, new, affected)

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertFalse(self.read_stdout_json(result)["ok"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_validate_design_revision_rejects_malformed_contract_blocker_and_snapshot_refs_without_writing(self):
        old = self.task_contract([{"id": "T1"}])
        changed = json.loads(json.dumps(old))
        changed["tasks"][0]["acceptance"] = ["changed"]
        malformed_contract = json.loads(json.dumps(changed))
        malformed_contract["tasks"][0]["acceptance"] = []
        blocker = self.canonical_blocker("design_revision", "T1", reason="changed")
        malformed_blocker_state = self.revision_state(
            old,
            tasks={"T1": {"status": "blocked", "attempts": 1, "blocker": {**blocker, "blocker_record_id": "bad"}, "reason": "changed"}},
        )
        malformed_snapshot_state = self.revision_state(
            old,
            tasks={"T1": {"status": "completed", "attempts": 1, "completion_snapshot_refs": {}}},
            implementation={"completed_tasks": ["T1"]},
        )
        cases = (
            ("contract", self.revision_state(old), malformed_contract),
            ("blocker", malformed_blocker_state, changed),
            ("snapshot", malformed_snapshot_state, changed),
        )
        for name, state, contract in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / f"{name}.json"
                self.write_json(path, state)
                before = path.read_bytes()

                result = self.run_design_revision_preflight(path, contract, ["T1"])

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertFalse(self.read_stdout_json(result)["ok"])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_validate_and_approve_design_revision_report_same_required_set(self):
        old = self.task_contract([{"id": "T1"}, {"id": "T2", "depends_on": ["T1"]}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["verification"] = {"commands": ["changed"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old))

            preflight = self.run_design_revision_preflight(path, new, ["T1", "T2"])
            approve = self.run_contract_revision(path, new, ["T1", "T2"])

            self.assertEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
            self.assertEqual(approve.returncode, 0, approve.stdout + approve.stderr)
            self.assertEqual(
                self.read_stdout_json(preflight)["required_affected_tasks"],
                self.read_stdout_json(approve)["required_affected_tasks"],
            )

    def test_approve_design_revision_revalidates_state_after_preflight(self):
        old = self.task_contract([{"id": "T1"}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            state = self.revision_state(old)
            self.write_json(path, state)
            preflight = self.run_design_revision_preflight(path, new, ["T1"])
            self.assertEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
            state["gates"]["design"] = "approved"
            self.write_json(path, state)
            before_approve = path.read_bytes()

            approve = self.run_contract_revision(path, new, ["T1"])

            self.assertEqual(approve.returncode, 1, approve.stdout + approve.stderr)
            self.assertIn("pending", self.read_stdout_json(approve)["error"])
            self.assertEqual(path.read_bytes(), before_approve)

    def test_validate_design_revision_parser_rejects_allow_approval_without_writing(self):
        old = self.task_contract([{"id": "T1"}])
        new = json.loads(json.dumps(old))
        new["tasks"][0]["acceptance"] = ["changed"]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            self.write_json(path, self.revision_state(old))
            before = path.read_bytes()

            result = self.run_design_revision_preflight(path, new, ["T1"], "changed", "--allow-approval")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = self.read_stdout_json(result)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"], "parse error")
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_non_object_and_missing_state_fail_closed_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            invalid_state = tmp_path / "invalid.json"
            invalid_state.write_text("{not json", encoding="utf-8")
            original_invalid = invalid_state.read_text(encoding="utf-8")
            non_object_state = tmp_path / "array.json"
            non_object_state.write_text("[]", encoding="utf-8")
            missing_state = tmp_path / "missing.json"

            invalid_result = self.run_helper(
                "merge-state", "--state", str(invalid_state), "--patch", json.dumps({"status": "x"})
            )
            non_object_result = self.run_helper(
                "merge-state", "--state", str(non_object_state), "--patch", json.dumps({"status": "x"})
            )
            missing_result = self.run_helper(
                "merge-state", "--state", str(missing_state), "--patch", json.dumps({"status": "x"})
            )

            for result in (invalid_result, non_object_result, missing_result):
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertFalse(self.read_stdout_json(result)["ok"])
            self.assertEqual(invalid_state.read_text(encoding="utf-8"), original_invalid)
            self.assertEqual(non_object_state.read_text(encoding="utf-8"), "[]")
            self.assertFalse(missing_state.exists())


if __name__ == "__main__":
    unittest.main()
