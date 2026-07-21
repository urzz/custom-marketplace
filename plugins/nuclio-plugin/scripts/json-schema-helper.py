#!/usr/bin/env python3
"""
Nuclio deterministic JSON Schema subset evaluator.

## Contents

- [Exceptions and public API](#exceptions-and-public-api)
- [Schema support scanning](#schema-support-scanning)
- [Reference and path helpers](#reference-and-path-helpers)
- [Validation helpers](#validation-helpers)
- [Keyword evaluation](#keyword-evaluation)

The evaluator intentionally implements only the Draft 2020-12 keywords used by
Nuclio's canonical packet schema and focused regression tests. It uses only the
Python standard library and fails closed when a schema contains an unsupported
validation or applicator keyword.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ANNOTATION_KEYWORDS = {
    "$comment",
    "$id",
    "$schema",
    "default",
    "deprecated",
    "description",
    "examples",
    "readOnly",
    "title",
    "writeOnly",
}
SCHEMA_CONTAINER_KEYWORDS = {"$defs", "properties", "patternProperties"}
KNOWN_KEYWORDS = ANNOTATION_KEYWORDS | SCHEMA_CONTAINER_KEYWORDS | {
    "$ref",
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "enum",
    "if",
    "items",
    "minItems",
    "minLength",
    "minimum",
    "minProperties",
    "not",
    "pattern",
    "required",
    "then",
    "type",
}
JSON_TYPES = {"array", "boolean", "integer", "null", "number", "object", "string"}


class SchemaValidationError(Exception):
    def __init__(self, code: str, reason: str, schema_path: str = "#", instance_path: str = "#"):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.schema_path = schema_path
        self.instance_path = instance_path

    def details(self) -> dict[str, str]:
        return {
            "code": self.code,
            "reason": self.reason,
            "schema_path": self.schema_path,
            "instance_path": self.instance_path,
        }


def validate_instance(schema_path: str | Path, instance: Any) -> None:
    """Validate instance against schema_path or raise SchemaValidationError."""
    path = Path(schema_path)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SchemaValidationError("SCHEMA_LOAD_ERROR", f"schema is not readable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaValidationError("SCHEMA_LOAD_ERROR", f"schema is not valid JSON: {exc.msg}") from exc
    _check_schema_supported(schema, "#", schema)
    _validate(schema, instance, schema, "#", "#")


def _check_schema_supported(schema: Any, schema_path: str, root_schema: Any) -> None:
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise SchemaValidationError("INVALID_SCHEMA", "schema node must be an object or boolean", schema_path)
    for keyword, value in schema.items():
        keyword_path = _join_schema_path(schema_path, keyword)
        if keyword not in KNOWN_KEYWORDS:
            raise SchemaValidationError("UNSUPPORTED_SCHEMA_KEYWORD", f"unsupported schema keyword: {keyword}", keyword_path)
        if keyword in ANNOTATION_KEYWORDS:
            continue
        if keyword == "$defs":
            if not isinstance(value, dict):
                raise SchemaValidationError("INVALID_SCHEMA", "$defs must be an object", keyword_path)
            for name, subschema in value.items():
                _check_schema_supported(subschema, _join_schema_path(keyword_path, name), root_schema)
        elif keyword == "properties":
            if not isinstance(value, dict):
                raise SchemaValidationError("INVALID_SCHEMA", "properties must be an object", keyword_path)
            for name, subschema in value.items():
                _check_schema_supported(subschema, _join_schema_path(keyword_path, name), root_schema)
        elif keyword == "patternProperties":
            if not isinstance(value, dict):
                raise SchemaValidationError("INVALID_SCHEMA", "patternProperties must be an object", keyword_path)
            for pattern, subschema in value.items():
                _compile_pattern(pattern, _join_schema_path(keyword_path, pattern))
                _check_schema_supported(subschema, _join_schema_path(keyword_path, pattern), root_schema)
        elif keyword in {"additionalProperties", "items", "not", "if", "then"}:
            if keyword == "additionalProperties" and isinstance(value, bool):
                continue
            _check_schema_supported(value, keyword_path, root_schema)
        elif keyword in {"allOf", "anyOf"}:
            if not isinstance(value, list):
                raise SchemaValidationError("INVALID_SCHEMA", f"{keyword} must be an array", keyword_path)
            for index, subschema in enumerate(value):
                _check_schema_supported(subschema, _join_schema_path(keyword_path, str(index)), root_schema)
        elif keyword == "$ref":
            if not isinstance(value, str) or not value.startswith("#"):
                raise SchemaValidationError("INVALID_SCHEMA_REF", "$ref must be a local JSON pointer", keyword_path)
            _resolve_ref(root_schema, value, keyword_path)
        elif keyword == "type":
            types = value if isinstance(value, list) else [value]
            if not types or any(item not in JSON_TYPES for item in types):
                raise SchemaValidationError("INVALID_SCHEMA", "type must name supported JSON types", keyword_path)
        elif keyword == "required":
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise SchemaValidationError("INVALID_SCHEMA", "required must be an array of strings", keyword_path)
        elif keyword in {"pattern"}:
            if not isinstance(value, str):
                raise SchemaValidationError("INVALID_SCHEMA", f"{keyword} must be a string", keyword_path)
            _compile_pattern(value, keyword_path)
        elif keyword in {"minLength", "minimum", "minItems", "minProperties"}:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise SchemaValidationError("INVALID_SCHEMA", f"{keyword} must be numeric", keyword_path)


def _resolve_ref(root_schema: Any, ref: str, schema_path: str) -> tuple[Any, str]:
    if ref == "#":
        return root_schema, "#"
    if not ref.startswith("#/"):
        raise SchemaValidationError("INVALID_SCHEMA_REF", "$ref must be a local JSON pointer", schema_path)
    current = root_schema
    current_path = "#"
    for raw_part in ref[2:].split("/"):
        part = _unescape_pointer(raw_part, schema_path)
        if isinstance(current, dict) and part in current:
            current = current[part]
            current_path = _join_schema_path(current_path, part)
            continue
        if isinstance(current, list) and part.isdecimal():
            index = int(part)
            if index < len(current):
                current = current[index]
                current_path = _join_schema_path(current_path, part)
                continue
        raise SchemaValidationError("INVALID_SCHEMA_REF", f"unresolvable $ref: {ref}", schema_path)
    return current, current_path


def _unescape_pointer(token: str, schema_path: str) -> str:
    if re.search(r"~(?![01])", token):
        raise SchemaValidationError("INVALID_SCHEMA_REF", "invalid JSON pointer escape in $ref", schema_path)
    return token.replace("~1", "/").replace("~0", "~")


def _join_schema_path(base: str, token: str) -> str:
    return f"{base}/{_escape_pointer(token)}" if base != "#" else f"#/{_escape_pointer(token)}"


def _join_instance_path(base: str, token: str) -> str:
    return f"{base}/{_escape_pointer(token)}" if base != "#" else f"#/{_escape_pointer(token)}"


def _escape_pointer(token: str) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def _compile_pattern(pattern: str, schema_path: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise SchemaValidationError("INVALID_SCHEMA", f"invalid regex pattern: {exc}", schema_path) from exc


def _validation_error(reason: str, schema_path: str, instance_path: str) -> None:
    raise SchemaValidationError("VALIDATION_ERROR", reason, schema_path, instance_path)


def _is_validation_mismatch(error: SchemaValidationError) -> bool:
    return error.code == "VALIDATION_ERROR"


def _json_values_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if _is_number(left) or _is_number(right):
        return _is_number(left) and _is_number(right) and left == right
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_values_equal(left_item, right_item) for left_item, right_item in zip(left, right))
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and left.keys() == right.keys()
            and all(_json_values_equal(left[key], right[key]) for key in left)
        )
    return False


def _validate(schema: Any, instance: Any, root_schema: Any, schema_path: str, instance_path: str) -> None:
    if schema is True:
        return
    if schema is False:
        _validation_error("boolean false schema rejects all instances", schema_path, instance_path)
    if not isinstance(schema, dict):
        raise SchemaValidationError("INVALID_SCHEMA", "schema node must be an object or boolean", schema_path, instance_path)

    if "$ref" in schema:
        target, target_path = _resolve_ref(root_schema, schema["$ref"], _join_schema_path(schema_path, "$ref"))
        _validate(target, instance, root_schema, target_path, instance_path)

    if "type" in schema:
        _validate_type(schema["type"], instance, _join_schema_path(schema_path, "type"), instance_path)
    if "enum" in schema and not any(_json_values_equal(instance, candidate) for candidate in schema["enum"]):
        _validation_error("value is not one of the allowed enum values", _join_schema_path(schema_path, "enum"), instance_path)
    if "const" in schema and not _json_values_equal(instance, schema["const"]):
        _validation_error("value does not equal const", _join_schema_path(schema_path, "const"), instance_path)

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            _validation_error("string is shorter than minLength", _join_schema_path(schema_path, "minLength"), instance_path)
        if "pattern" in schema and not _compile_pattern(schema["pattern"], _join_schema_path(schema_path, "pattern")).search(instance):
            _validation_error("string does not match pattern", _join_schema_path(schema_path, "pattern"), instance_path)

    if _is_number(instance) and "minimum" in schema and instance < schema["minimum"]:
        _validation_error("number is less than minimum", _join_schema_path(schema_path, "minimum"), instance_path)

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            _validation_error("array has fewer items than minItems", _join_schema_path(schema_path, "minItems"), instance_path)
        if "items" in schema:
            for index, item in enumerate(instance):
                _validate(schema["items"], item, root_schema, _join_schema_path(schema_path, "items"), _join_instance_path(instance_path, str(index)))

    if isinstance(instance, dict):
        _validate_object_keywords(schema, instance, root_schema, schema_path, instance_path)

    for keyword in ("allOf", "anyOf", "not", "if"):
        if keyword in schema:
            _validate_applicator(keyword, schema, instance, root_schema, schema_path, instance_path)


def _validate_type(raw_type: Any, instance: Any, schema_path: str, instance_path: str) -> None:
    types = raw_type if isinstance(raw_type, list) else [raw_type]
    if not any(_matches_type(type_name, instance) for type_name in types):
        _validation_error(f"value is not of type {types}", schema_path, instance_path)


def _matches_type(type_name: str, instance: Any) -> bool:
    if type_name == "object":
        return isinstance(instance, dict)
    if type_name == "array":
        return isinstance(instance, list)
    if type_name == "string":
        return isinstance(instance, str)
    if type_name == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if type_name == "number":
        return _is_number(instance)
    if type_name == "boolean":
        return isinstance(instance, bool)
    if type_name == "null":
        return instance is None
    return False


def _is_number(instance: Any) -> bool:
    return isinstance(instance, (int, float)) and not isinstance(instance, bool)


def _validate_object_keywords(schema: dict[str, Any], instance: dict[str, Any], root_schema: Any, schema_path: str, instance_path: str) -> None:
    if "minProperties" in schema and len(instance) < schema["minProperties"]:
        _validation_error("object has fewer properties than minProperties", _join_schema_path(schema_path, "minProperties"), instance_path)
    for field in schema.get("required", []):
        if field not in instance:
            _validation_error(f"required property is missing: {field}", _join_schema_path(schema_path, "required"), instance_path)

    properties = schema.get("properties", {}) if isinstance(schema.get("properties", {}), dict) else {}
    matched: set[str] = set()
    for field, subschema in properties.items():
        if field in instance:
            matched.add(field)
            _validate(subschema, instance[field], root_schema, _join_schema_path(_join_schema_path(schema_path, "properties"), field), _join_instance_path(instance_path, field))

    pattern_properties = schema.get("patternProperties", {}) if isinstance(schema.get("patternProperties", {}), dict) else {}
    for pattern, subschema in pattern_properties.items():
        compiled = _compile_pattern(pattern, _join_schema_path(_join_schema_path(schema_path, "patternProperties"), pattern))
        for field, value in instance.items():
            if compiled.search(field):
                matched.add(field)
                _validate(subschema, value, root_schema, _join_schema_path(_join_schema_path(schema_path, "patternProperties"), pattern), _join_instance_path(instance_path, field))

    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        extra = [field for field in instance if field not in matched]
        if additional is False and extra:
            _validation_error(f"additional properties are not allowed: {sorted(extra)}", _join_schema_path(schema_path, "additionalProperties"), instance_path)
        if isinstance(additional, dict) or additional is True:
            if additional is not True:
                for field in extra:
                    _validate(additional, instance[field], root_schema, _join_schema_path(schema_path, "additionalProperties"), _join_instance_path(instance_path, field))


def _validate_applicator(keyword: str, schema: dict[str, Any], instance: Any, root_schema: Any, schema_path: str, instance_path: str) -> None:
    if keyword == "allOf":
        for index, subschema in enumerate(schema["allOf"]):
            _validate(subschema, instance, root_schema, _join_schema_path(_join_schema_path(schema_path, "allOf"), str(index)), instance_path)
    elif keyword == "anyOf":
        errors = []
        for index, subschema in enumerate(schema["anyOf"]):
            try:
                _validate(subschema, instance, root_schema, _join_schema_path(_join_schema_path(schema_path, "anyOf"), str(index)), instance_path)
                return
            except SchemaValidationError as exc:
                if not _is_validation_mismatch(exc):
                    raise
                errors.append(exc.reason)
        _validation_error(f"value does not match anyOf: {errors}", _join_schema_path(schema_path, "anyOf"), instance_path)
    elif keyword == "not":
        try:
            _validate(schema["not"], instance, root_schema, _join_schema_path(schema_path, "not"), instance_path)
        except SchemaValidationError as exc:
            if not _is_validation_mismatch(exc):
                raise
            return
        _validation_error("value matches forbidden not schema", _join_schema_path(schema_path, "not"), instance_path)
    elif keyword == "if":
        try:
            _validate(schema["if"], instance, root_schema, _join_schema_path(schema_path, "if"), instance_path)
        except SchemaValidationError as exc:
            if not _is_validation_mismatch(exc):
                raise
            return
        if "then" in schema:
            _validate(schema["then"], instance, root_schema, _join_schema_path(schema_path, "then"), instance_path)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit("json-schema-helper.py is import-only")
