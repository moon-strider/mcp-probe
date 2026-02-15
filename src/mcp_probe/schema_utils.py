from __future__ import annotations

_COMPLEX_KEYWORDS = frozenset({"$ref", "anyOf", "oneOf", "allOf", "if"})


def is_complex_schema(schema: dict) -> bool:
    return bool(_COMPLEX_KEYWORDS & schema.keys())


def generate_valid_args(schema: dict) -> dict | None:
    if is_complex_schema(schema):
        return None
    return _generate_value(schema)  # type: ignore[return-value]


def generate_invalid_args(schema: dict) -> dict:
    required = schema.get("required", [])
    if required:
        return {}
    return {"__invalid_field__": "should_not_be_accepted"}


def _generate_value(schema: dict) -> object:
    if is_complex_schema(schema):
        return None

    if "enum" in schema:
        return schema["enum"][0]

    typ = schema.get("type")

    if typ == "string":
        return "test"

    if typ == "integer":
        return schema.get("minimum", 1)

    if typ == "number":
        return schema.get("minimum", 1)

    if typ == "boolean":
        return True

    if typ == "array":
        min_items = schema.get("minItems", 0)
        if min_items > 0 and "items" in schema:
            item = _generate_value(schema["items"])
            return [item] * min_items
        return []

    if typ == "object" or "properties" in schema:
        return _generate_object(schema)

    return "test"


def _generate_object(schema: dict) -> dict | None:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    result: dict = {}
    for name, prop_schema in properties.items():
        if name not in required:
            continue
        if is_complex_schema(prop_schema):
            return None
        result[name] = _generate_value(prop_schema)
    return result
