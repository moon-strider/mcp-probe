#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


def _response(id_val, result):
    return {"jsonrpc": "2.0", "id": id_val, "result": result}


def _handle_request(msg):
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params", {})

    if msg_id is None:
        return None

    if method == "initialize":
        return _response(msg_id, {
            "serverInfo": {"name": "mock-broken", "version": "0.0.1"},
        })

    if method == "ping":
        return _response(msg_id, {})

    if method == "tools/list":
        return _response(msg_id, {
            "tools": [
                {
                    "name": "no_desc_tool",
                    "inputSchema": {"type": "object", "properties": {}},
                },
                {
                    "name": "bad_schema_tool",
                    "description": "Tool with invalid schema",
                    "inputSchema": "not-a-dict",
                },
            ],
        })

    if method == "tools/call":
        return _response(msg_id, {
            "content": [{"type": "text", "text": "ok"}],
        })

    if method == "resources/list":
        return {
            "id": msg_id,
            "result": {"resources": []},
        }

    if method == "resources/read":
        return _response(msg_id, {
            "contents": [{"uri": params.get("uri", ""), "text": "data"}],
        })

    if method == "prompts/list":
        return _response(msg_id, {"prompts": []})

    if method == "prompts/get":
        return _response(msg_id, {"messages": []})

    return {"jsonrpc": "2.0", "id": msg_id, "error": {"message": f"Not found: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        response = _handle_request(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
