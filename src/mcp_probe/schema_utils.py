"""Conservative fixture generation with offline, optional JSON Schema validation."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Any

_COMPLEX_KEYWORDS = frozenset({"$ref", "$dynamicRef", "anyOf", "oneOf", "allOf", "if", "not"})


def is_complex_schema(schema: dict) -> bool:
    return bool(_COMPLEX_KEYWORDS & schema.keys())


def _validator(schema: dict):
    try:
        import jsonschema  # type: ignore[import-untyped]
        from referencing import Registry
        from referencing.exceptions import NoSuchResource
    except ImportError:
        return None

    def no_remote(uri):
        raise NoSuchResource(uri)

    cls = jsonschema.validators.validator_for(schema, default=jsonschema.Draft202012Validator)
    cls.check_schema(schema)
    registry_factory: Any = Registry
    return cls(schema, registry=registry_factory(retrieve=no_remote))


def schema_error(schema: Any) -> str | None:
    if not isinstance(schema, dict):
        return "Schema must be an object"
    if len(json.dumps(schema)) > 65536:
        return "Schema exceeds the validation size limit"
    try:
        validator = _validator(schema)
    except Exception:
        return "Invalid JSON Schema"
    if validator is None:
        return None
    return None


def matches_schema(value: Any, schema: dict) -> bool | None:
    """None means validation is unavailable; remote references are never fetched."""
    try:
        validator = _validator(schema)
        return None if validator is None else validator.is_valid(value)
    except Exception:
        return None


def generate_valid_args(schema: dict) -> dict | None:
    try:
        value = _generate_value(schema, 0)
        if not isinstance(value, dict):
            return None
        verdict = matches_schema(value, schema)
        if verdict is False:
            return None
        return value
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
        return None


def generate_invalid_args(schema: dict) -> dict | None:
    required = schema.get("required", [])
    if required:
        return {} if matches_schema({}, schema) is not True else None
    if schema.get("additionalProperties") is False:
        key = "__invalid_field__"
        while key in schema.get("properties", {}):
            key += "_"
        candidate = {key: "invalid"}
        verdict = matches_schema(candidate, schema)
        if verdict is False or (verdict is None and not schema.get("patternProperties")):
            return candidate
    for name, prop in schema.get("properties", {}).items():
        if not isinstance(prop, dict):
            continue
        candidates: list[Any] = [None, [], {}, True, 1, "invalid"]
        for candidate in candidates:
            args = {name: candidate}
            if matches_schema(args, schema) is False:
                return args
    return None


def _generate_value(schema: dict, depth: int) -> Any:
    if depth > 8 or not isinstance(schema, dict) or is_complex_schema(schema):
        raise ValueError("Fixture needs an explicit case")
    supported = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "enum",
        "const",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "title",
        "description",
        "default",
        "examples",
        "$schema",
        "deprecated",
        "readOnly",
        "writeOnly",
        "x-mcp-header",
    }
    if set(schema) - supported:
        raise ValueError("Unsupported generation constraint")
    if "const" in schema:
        return deepcopy(schema["const"])
    if "enum" in schema:
        return deepcopy(schema["enum"][0])
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {name: _generate_value(props[name], depth + 1) for name in schema.get("required", [])}
    if kind == "string":
        minimum = max(0, schema.get("minLength", 0))
        maximum = schema.get("maxLength", 4096)
        if minimum > min(maximum, 4096):
            raise ValueError("String bounds")
        return "test"[:maximum] if minimum <= 4 else "x" * minimum
    if kind in ("integer", "number"):
        lower = schema.get("minimum", -1e6)
        upper = schema.get("maximum", 1e6)
        if "exclusiveMinimum" in schema:
            lower = max(lower, math.floor(schema["exclusiveMinimum"]) + 1)
        if "exclusiveMaximum" in schema:
            upper = min(upper, math.ceil(schema["exclusiveMaximum"]) - 1)
        value = max(lower, min(1, upper))
        if kind == "integer":
            value = math.ceil(value)
        if value > upper or not math.isfinite(value):
            raise ValueError("Numeric bounds")
        return value
    if kind == "boolean":
        return True
    if kind == "null":
        return None
    if kind == "array":
        count = schema.get("minItems", 0)
        if count > min(64, schema.get("maxItems", 64)) or count < 0:
            raise ValueError("Array bounds")
        return [_generate_value(schema.get("items", {}), depth + 1) for _ in range(count)]
    raise ValueError("Schema needs an explicit case")
