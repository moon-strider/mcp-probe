"""Bounded validation shared by transports, the client, and feature checks."""

from __future__ import annotations

import base64
import binascii
import json
import math
from typing import Any

LEGACY_VERSION = "2025-11-25"
MODERN_VERSION = "2026-07-28"
SUPPORTED_VERSIONS = (LEGACY_VERSION, MODERN_VERSION)
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
MAX_MESSAGES = 1000
MAX_PAGES = 100
MAX_ITEMS = 10000


class ProtocolError(ValueError):
    """The peer returned a malformed or inconsistent protocol message."""


def loads_message(raw: bytes | str) -> dict:
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Message exceeds the byte limit")

    def reject_constant(value: str) -> None:
        raise ProtocolError("Non-finite numbers are not JSON")

    def finite_float(raw_number: str) -> float:
        number = float(raw_number)
        if not math.isfinite(number):
            raise ProtocolError("Number exceeds the finite float range")
        return number

    def bounded_integer(raw_number: str) -> int:
        if len(raw_number) > 256:
            raise ProtocolError("Integer exceeds the digit budget")
        return int(raw_number)

    try:
        value = json.loads(raw, parse_constant=reject_constant, parse_float=finite_float, parse_int=bounded_integer)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("Invalid UTF-8 JSON message") from exc
    if not isinstance(value, dict):
        raise ProtocolError("A JSON-RPC message must be an object")
    return value


def validate_envelope(message: Any) -> None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise ProtocolError("Expected a JSON-RPC object with jsonrpc='2.0'")
    if "method" in message:
        if not isinstance(message["method"], str) or not message["method"]:
            raise ProtocolError("Message method must be a nonempty string")
        if "result" in message or "error" in message:
            raise ProtocolError("A request or notification cannot contain a result or error")
        if "params" in message and not isinstance(message["params"], dict):
            raise ProtocolError("MCP params must be an object")
        if "id" in message and type(message["id"]) not in (str, int):
            raise ProtocolError("Request id must be a string or integer")
        return
    if "id" not in message or type(message["id"]) not in (str, int, type(None)):
        raise ProtocolError("Response id must be a string, integer, or null error id")
    if ("result" in message) == ("error" in message):
        raise ProtocolError("Response must contain exactly one of result and error")
    if "error" in message:
        err = message["error"]
        if not isinstance(err, dict) or type(err.get("code")) is not int or not isinstance(err.get("message"), str):
            raise ProtocolError("Error must contain an integer code and string message")
    elif message["id"] is None or not isinstance(message["result"], dict):
        raise ProtocolError("MCP success response requires an id and object result")


def result_object(response: dict) -> dict:
    if "error" in response:
        code = response["error"].get("code") if isinstance(response["error"], dict) else None
        raise ProtocolError(f"Server returned a protocol error (code={code})")
    result = response.get("result")
    if not isinstance(result, dict):
        raise ProtocolError("Missing object result")
    return result


def validate_content(item: Any) -> None:
    if not isinstance(item, dict):
        raise ProtocolError("Content item must be an object")
    kind = item.get("type")
    if kind == "text":
        if not isinstance(item.get("text"), str):
            raise ProtocolError("Text content requires a string text field")
    elif kind in ("image", "audio"):
        if not isinstance(item.get("mimeType"), str) or not item["mimeType"]:
            raise ProtocolError("Media content requires mimeType")
        try:
            base64.b64decode(item["data"], validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            raise ProtocolError("Media content requires base64 data") from exc
    elif kind == "resource_link":
        if not all(isinstance(item.get(k), str) and item[k] for k in ("uri", "name")):
            raise ProtocolError("Resource link requires uri and name")
    elif kind == "resource":
        validate_resource_content(item.get("resource"))
    else:
        raise ProtocolError("Unknown content type")


def validate_resource_content(item: Any) -> None:
    if not isinstance(item, dict) or not isinstance(item.get("uri"), str) or not item["uri"]:
        raise ProtocolError("Resource content requires a uri")
    if isinstance(item.get("text"), str):
        return
    try:
        base64.b64decode(item["blob"], validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error) as exc:
        raise ProtocolError("Resource content requires text or base64 blob") from exc


def validate_tool_result(result: Any, modern: bool = False) -> None:
    if not isinstance(result, dict) or not isinstance(result.get("content"), list):
        raise ProtocolError("Tool result requires a content array")
    for item in result["content"]:
        validate_content(item)
    if "isError" in result and type(result["isError"]) is not bool:
        raise ProtocolError("isError must be a boolean")
    if not modern and "structuredContent" in result and not isinstance(result["structuredContent"], dict):
        raise ProtocolError("Legacy structuredContent must be an object")


def validate_cache_metadata(result: dict) -> None:
    ttl = result.get("ttlMs")
    if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or not math.isfinite(ttl) or ttl < 0:
        raise ProtocolError("Cacheable result requires nonnegative finite ttlMs")
    if result.get("cacheScope") not in ("public", "private"):
        raise ProtocolError("Cacheable result requires public or private cacheScope")
