#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


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
        return _response(
            msg_id,
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mock-minimal", "version": "1.0.0"},
            },
        )

    if method == "ping":
        return _response(msg_id, {})

    if method == "tools/list":
        return _response(
            msg_id,
            {
                "tools": [
                    {
                        "name": "ping",
                        "description": "Returns pong",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ],
            },
        )

    if method == "tools/call":
        name = params.get("name", "")
        if name == "ping":
            return _response(
                msg_id,
                {
                    "content": [{"type": "text", "text": "pong"}],
                },
            )
        return _error(msg_id, -32602, f"Unknown tool: {name}")

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
