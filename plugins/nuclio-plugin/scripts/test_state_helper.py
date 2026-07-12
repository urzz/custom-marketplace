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
