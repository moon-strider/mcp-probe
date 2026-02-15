from __future__ import annotations

from mcp_probe.schema_utils import generate_invalid_args, generate_valid_args, is_complex_schema


def test_valid_args_string():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    args = generate_valid_args(schema)
    assert args is not None
    assert isinstance(args["name"], str)


def test_valid_args_integer():
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}
    args = generate_valid_args(schema)
    assert args is not None
    assert isinstance(args["count"], int)


def test_valid_args_number():
    schema = {"type": "object", "properties": {"val": {"type": "number"}}, "required": ["val"]}
    args = generate_valid_args(schema)
    assert args is not None
    assert isinstance(args["val"], (int, float))


def test_valid_args_boolean():
    schema = {"type": "object", "properties": {"flag": {"type": "boolean"}}, "required": ["flag"]}
    args = generate_valid_args(schema)
    assert args is not None
    assert isinstance(args["flag"], bool)


def test_valid_args_array():
    schema = {"type": "object", "properties": {"items": {"type": "array"}}, "required": ["items"]}
    args = generate_valid_args(schema)
    assert args is not None
    assert isinstance(args["items"], list)


def test_valid_args_enum():
    schema = {"type": "object", "properties": {"color": {"enum": ["red", "blue"]}}, "required": ["color"]}
    args = generate_valid_args(schema)
    assert args is not None
    assert args["color"] == "red"


def test_valid_args_nested_object():
    schema = {
        "type": "object",
        "properties": {
            "config": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
            },
        },
        "required": ["config"],
    }
    args = generate_valid_args(schema)
    assert args is not None
    assert isinstance(args["config"], dict)


def test_valid_args_complex_returns_none():
    schema = {"type": "object", "properties": {"x": {"$ref": "#/defs/Foo"}}, "required": ["x"]}
    assert generate_valid_args(schema) is None


def test_valid_args_complex_top_level():
    schema = {"$ref": "#/defs/Foo"}
    assert generate_valid_args(schema) is None


def test_invalid_args_with_required():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    args = generate_invalid_args(schema)
    assert args == {}


def test_invalid_args_without_required():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    args = generate_invalid_args(schema)
    assert "__invalid_field__" in args


def test_is_complex_schema():
    assert is_complex_schema({"$ref": "#/defs/Foo"}) is True
    assert is_complex_schema({"anyOf": [{"type": "string"}]}) is True
    assert is_complex_schema({"oneOf": [{"type": "string"}]}) is True
    assert is_complex_schema({"allOf": [{"type": "string"}]}) is True
    assert is_complex_schema({"if": {"type": "string"}}) is True
    assert is_complex_schema({"type": "object", "properties": {}}) is False


def test_valid_args_optional_skipped():
    schema = {
        "type": "object",
        "properties": {
            "required_field": {"type": "string"},
            "optional_field": {"type": "integer"},
        },
        "required": ["required_field"],
    }
    args = generate_valid_args(schema)
    assert args is not None
    assert "required_field" in args
