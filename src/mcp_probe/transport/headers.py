"""Metadata headers for the stateless Streamable HTTP revision."""

from __future__ import annotations

import base64
import re
from typing import Any

from mcp_probe.protocol import ProtocolError

_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


def encode_value(value: str | int | bool) -> str:
    if isinstance(value, bool):
        text = str(value).lower()
    elif isinstance(value, int):
        if abs(value) > 2**53 - 1:
            raise ProtocolError("Header integer exceeds the safe integer range")
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise ProtocolError("Header value must be a string, integer or boolean")
    if (
        text != text.strip()
        or any(not (32 <= ord(c) <= 126 or c == "\t") for c in text)
        or (text.startswith("=?base64?") and text.endswith("?="))
    ):
        return "=?base64?" + base64.b64encode(text.encode()).decode("ascii") + "?="
    return text


def parameter_headers(schema: dict, arguments: dict) -> dict[str, str]:
    """Validate annotations and extract values only along static property paths."""
    headers: dict[str, str] = {}
    names: set[str] = set()
    count = 0

    def visit(node: Any, path: tuple[str, ...] | None, depth: int) -> None:
        nonlocal count
        count += 1
        if depth > 32 or count > 10000:
            raise ProtocolError("Header schema traversal limit exceeded")
        if isinstance(node, list):
            for child in node:
                visit(child, None, depth + 1)
        if not isinstance(node, dict):
            return
        if "x-mcp-header" in node:
            name = node["x-mcp-header"]
            if (
                not isinstance(name, str)
                or _TOKEN.fullmatch(name) is None
                or name.lower() in names
                or node.get("type") not in ("string", "integer", "boolean")
                or not path
            ):
                raise ProtocolError("Invalid or duplicate x-mcp-header annotation")
            names.add(name.lower())
            value: Any = arguments
            for part in path:
                value = value.get(part) if isinstance(value, dict) else None
            if value is not None:
                headers["Mcp-Param-" + name] = encode_value(value)
        for key, child in node.items():
            if key == "properties" and isinstance(child, dict) and path is not None:
                for prop, definition in child.items():
                    visit(definition, (*path, prop), depth + 1)
            elif isinstance(child, (dict, list)):
                # Annotation data (examples/defaults) are not subschemas.
                if key not in ("default", "const", "enum", "examples"):
                    visit(child, None, depth + 1)

    visit(schema, (), 0)
    return headers
