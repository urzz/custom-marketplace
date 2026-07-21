"""
JSON Schema helper tests.

## Contents

- [Fixture loading](#fixture-loading)
- [Synthetic schema coverage](#synthetic-schema-coverage)
- [Canonical packet schema coverage](#canonical-packet-schema-coverage)
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "plugins" / "nuclio-plugin" / "scripts" / "json-schema-helper.py"
PACKET_SCHEMA = ROOT / "plugins" / "nuclio-plugin" / "schemas" / "packet.schema.json"
A_HASH = "a" * 64
B_HASH = "b" * 64


def load_helper():
    spec = importlib.util.spec_from_file_location("json_schema_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker_packet(**overrides):
    packet = {
        "schema_version": 1,
        "role": "worker",
        "change_id": "change-alpha",
        "contract_sha256": A_HASH,
        "context_fingerprint": B_HASH,
        "state_version": 2,
        "output_language": "zh-CN",
        "task_id": "T1",
        "ownership": [{"path": "plugins/nuclio-plugin/scripts/a.py", "mode": "create"}],
        "range": {"base_head": "abcdef1", "expected_dirty_state": "clean"},
        "snapshots": [],
        "checks": {"focused": [], "full": []},
        "handoffs": [],
        "packet_id": A_HASH,
    }
    packet.update(overrides)
    return packet


class JsonSchemaHelperTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def schema_file(self, schema):
        path = Path(self.temp.name) / "schema.json"
        path.write_text(json.dumps(schema), encoding="utf-8")
        return path

    def assert_valid(self, schema, instance):
        self.helper.validate_instance(self.schema_file(schema), instance)

    def assert_invalid(self, schema, instance, code="VALIDATION_ERROR"):
        with self.assertRaises(self.helper.SchemaValidationError) as ctx:
            self.helper.validate_instance(self.schema_file(schema), instance)
        self.assertEqual(ctx.exception.code, code)
        self.assertIn("schema_path", ctx.exception.details())
        self.assertIn("instance_path", ctx.exception.details())

    def test_type_integer_excludes_bool_and_annotation_keywords_are_allowed(self):
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "ints", "description": "annotation", "type": "integer", "minimum": 1}
        self.assert_valid(schema, 1)
        self.assert_invalid(schema, True)

    def test_local_ref_required_additional_and_pattern_properties(self):
        schema = {
            "$defs": {"non_empty": {"type": "string", "minLength": 1}},
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"$ref": "#/$defs/non_empty"}},
            "patternProperties": {"^x-": {"type": "integer"}},
            "additionalProperties": False,
        }
        self.assert_valid(schema, {"name": "ok", "x-count": 2})
        self.assert_invalid(schema, {"name": "ok", "extra": 1})
        self.assert_invalid(schema, {"x-count": 2})
        self.assert_invalid(schema, {"name": "ok", "x-count": True})

    def test_allof_anyof_not_if_then_and_constraints(self):
        schema = {
            "allOf": [
                {"type": "object", "minProperties": 2},
                {
                    "type": "object",
                    "required": ["kind", "items", "name", "count"],
                    "properties": {
                        "kind": {"enum": ["a", "b"]},
                        "name": {"type": "string", "pattern": "^[a-z]+$", "minLength": 2},
                        "count": {"type": "number", "minimum": 0},
                        "items": {"type": "array", "minItems": 1, "items": {"anyOf": [{"const": "x"}, {"type": "integer"}]}},
                    },
                    "if": {"properties": {"kind": {"const": "a"}}, "required": ["kind"]},
                    "then": {"not": {"required": ["forbidden"]}},
                },
            ]
        }
        self.assert_valid(schema, {"kind": "a", "name": "ab", "count": 0.5, "items": ["x", 3]})
        self.assert_invalid(schema, {"kind": "a", "name": "ab", "count": 0, "items": ["y"]})
        self.assert_invalid(schema, {"kind": "a", "name": "ab", "count": 0, "items": [1], "forbidden": True})
        self.assert_invalid(schema, {"kind": "b", "name": "A", "count": -1, "items": [1]})

    def test_applicators_propagate_invalid_refs_fail_closed(self):
        cases = [
            {"$ref": "#/$defs/missing"},
            {"allOf": [{"$ref": "#/$defs/missing"}]},
            {"anyOf": [{"$ref": "#/$defs/missing"}, True]},
            {"not": {"$ref": "#/$defs/missing"}},
            {"if": {"$ref": "#/$defs/missing"}, "then": False},
            {"if": True, "then": {"$ref": "#/$defs/missing"}},
        ]
        for schema in cases:
            with self.subTest(schema=schema):
                self.assert_invalid(schema, "x", "INVALID_SCHEMA_REF")

    def test_preflight_rejects_dormant_conditional_and_defs_invalid_refs(self):
        dormant_conditional = {
            "type": "object",
            "properties": {"role": {"enum": ["worker", "reviewer"]}},
            "allOf": [
                {
                    "if": {"properties": {"role": {"const": "reviewer"}}, "required": ["role"]},
                    "then": {"properties": {"review_targets": {"items": {"$ref": "#/$defs/missing"}}}},
                }
            ],
        }
        self.assert_invalid(dormant_conditional, {"role": "worker"}, "INVALID_SCHEMA_REF")

        dormant_defs = {
            "$defs": {"unused": {"properties": {"value": {"$ref": "#/$defs/missing"}}}},
            "type": "string",
        }
        self.assert_invalid(dormant_defs, "ok", "INVALID_SCHEMA_REF")

    def test_preflight_allows_repeated_and_recursive_local_refs_without_looping(self):
        repeated = {
            "$defs": {"name": {"type": "string", "minLength": 1}},
            "type": "object",
            "required": ["a", "b"],
            "properties": {
                "a": {"$ref": "#/$defs/name"},
                "b": {"anyOf": [{"$ref": "#/$defs/name"}, {"$ref": "#/$defs/name"}]},
            },
        }
        self.assert_valid(repeated, {"a": "one", "b": "two"})
        self.assert_invalid(repeated, {"a": "one", "b": ""})

        recursive = {
            "$defs": {
                "node": {
                    "anyOf": [
                        {"type": "null"},
                        {"type": "object", "properties": {"next": {"$ref": "#/$defs/node"}}},
                    ]
                }
            },
            "$ref": "#/$defs/node",
        }
        self.assert_valid(recursive, {"next": {"next": None}})
        self.assert_invalid(recursive, {"next": {"next": 1}})

    def test_applicators_preserve_plain_validation_mismatch_control_flow(self):
        self.assert_valid({"anyOf": [{"type": "integer"}, True]}, "x")
        self.assert_valid({"not": {"type": "integer"}}, "x")
        self.assert_valid({"if": {"type": "integer"}, "then": False}, "x")
        self.assert_invalid({"if": {"type": "integer"}, "then": False}, 1)

    def test_unknown_validation_keyword_fails_closed(self):
        self.assert_invalid({"type": "object", "dependentRequired": {"a": ["b"]}}, {}, "UNSUPPORTED_SCHEMA_KEYWORD")

    def test_enum_and_const_use_strict_json_value_equality_for_bool_number(self):
        cases = [
            ({"const": True}, 1),
            ({"const": 1}, True),
            ({"enum": [True]}, 1),
            ({"enum": [1]}, True),
            ({"const": False}, 0),
            ({"const": 0}, False),
            ({"enum": [False]}, 0),
            ({"enum": [0]}, False),
        ]
        for schema, instance in cases:
            with self.subTest(schema=schema, instance=instance):
                self.assert_invalid(schema, instance)

    def test_enum_and_const_preserve_json_number_mathematical_equality(self):
        self.assert_valid({"const": 1}, 1.0)
        self.assert_valid({"const": 1.0}, 1)
        self.assert_valid({"enum": [1]}, 1.0)
        self.assert_valid({"enum": [1.0]}, 1)

    def test_enum_and_const_apply_json_value_equality_recursively(self):
        self.assert_invalid({"const": [True, {"count": 1}]}, [1, {"count": True}])
        self.assert_invalid({"enum": [[False, {"count": 0}]]}, [[0, {"count": False}]])
        self.assert_valid({"const": {"a": [1, True], "b": {"nested": False}}}, {"b": {"nested": False}, "a": [1.0, True]})
        self.assert_valid({"enum": [{"a": [1, {"x": False}], "b": "ok"}]}, {"b": "ok", "a": [1.0, {"x": False}]})

    def test_canonical_packet_schema_accepts_valid_worker_and_rejects_bool_integer(self):
        self.helper.validate_instance(PACKET_SCHEMA, worker_packet())
        bad = worker_packet(schema_version=True)
        with self.assertRaises(self.helper.SchemaValidationError) as ctx:
            self.helper.validate_instance(PACKET_SCHEMA, bad)
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")
        self.assertEqual(ctx.exception.instance_path, "#/schema_version")


if __name__ == "__main__":
    unittest.main()
