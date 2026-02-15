#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


SERVER_INFO = {"name": "mock-valid", "version": "1.0.0"}
CAPABILITIES = {
    "tools": {},
    "resources": {"subscribe": True, "listChanged": True},
    "prompts": {},
}

TOOLS = [
    {
        "name": "echo",
        "description": "Echoes back the input message",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to echo"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "add",
        "description": "Adds two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "First number"},
                "b": {"type": "integer", "description": "Second number"},
            },
            "required": ["a", "b"],
        },
    },
]

RESOURCES = [
    {
        "uri": "test://data",
        "name": "Test Data",
        "mimeType": "text/plain",
    },
]

PROMPTS = [
    {
        "name": "greeting",
        "description": "A friendly greeting prompt",
        "arguments": [
            {"name": "name", "description": "Name to greet", "required": False},
        ],
    },
]


def _response(id_val, result):
    return {"jsonrpc": "2.0", "id": id_val, "result": result}


def _error(id_val, code, message):
    return {"jsonrpc": "2.0", "id": id_val, "error": {"code": code, "message": message}}


def _handle_request(msg):
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params", {})

    if msg_id is None:
        return None

    if method == "initialize":
        return _response(msg_id, {
            "protocolVersion": "2025-11-25",
            "capabilities": CAPABILITIES,
            "serverInfo": SERVER_INFO,
        })

    if method == "ping":
        return _response(msg_id, {})

    if method == "tools/list":
        return _response(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        if name == "echo":
            message = arguments.get("message")
            if message is None:
                return _error(msg_id, -32602, "Missing required argument: message")
            return _response(msg_id, {
                "content": [{"type": "text", "text": str(message)}],
            })
        if name == "add":
            a = arguments.get("a")
            b = arguments.get("b")
            if a is None or b is None:
                return _error(msg_id, -32602, "Missing required arguments: a, b")
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                return _error(msg_id, -32602, "Arguments a and b must be numbers")
            return _response(msg_id, {
                "content": [{"type": "text", "text": str(a + b)}],
            })
        return _error(msg_id, -32602, f"Unknown tool: {name}")

    if method == "resources/list":
        return _response(msg_id, {"resources": RESOURCES})

    if method == "resources/read":
        uri = params.get("uri", "")
        if uri == "test://data":
            return _response(msg_id, {
                "contents": [{"uri": uri, "text": "hello world", "mimeType": "text/plain"}],
            })
        return _error(msg_id, -32602, f"Unknown resource: {uri}")

    if method == "resources/subscribe":
        return _response(msg_id, {})

    if method == "resources/unsubscribe":
        return _response(msg_id, {})

    if method == "prompts/list":
        return _response(msg_id, {"prompts": PROMPTS})

    if method == "prompts/get":
        name = params.get("name", "")
        if name == "greeting":
            greeting_name = params.get("arguments", {}).get("name", "World")
            return _response(msg_id, {
                "messages": [{
                    "role": "user",
                    "content": {"type": "text", "text": f"Hello, {greeting_name}!"},
                }],
            })
        return _error(msg_id, -32602, f"Unknown prompt: {name}")

    return _error(msg_id, -32601, f"Method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()
            continue

        response = _handle_request(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
