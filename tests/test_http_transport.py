from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from mcp_probe.transport.http import AuthRequired, HttpTransport


class MockMCPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        msg = json.loads(body)

        session_id = self.headers.get("Mcp-Session-Id")

        response = {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "result": {"echo": msg.get("method")},
        }

        resp_bytes = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Mcp-Session-Id", "test-session-123")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)

    def do_DELETE(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


class MockAuthHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", "Bearer")
        self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def mock_http_server():
    server = HTTPServer(("127.0.0.1", 0), MockMCPHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def mock_auth_server():
    server = HTTPServer(("127.0.0.1", 0), MockAuthHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


async def test_send_receive_json(mock_http_server):
    t = HttpTransport(mock_http_server, timeout=5.0)
    await t.start()
    try:
        await t.send({"jsonrpc": "2.0", "id": 1, "method": "test"})
        resp = await t.receive(5.0)
        assert resp["id"] == 1
        assert resp["result"]["echo"] == "test"
    finally:
        await t.stop()


async def test_session_id_saved(mock_http_server):
    t = HttpTransport(mock_http_server, timeout=5.0)
    await t.start()
    try:
        assert t.session_id is None
        await t.send({"jsonrpc": "2.0", "id": 1, "method": "test"})
        await t.receive(5.0)
        assert t.session_id == "test-session-123"
    finally:
        await t.stop()


async def test_auth_required(mock_auth_server):
    t = HttpTransport(mock_auth_server, timeout=5.0)
    await t.start()
    try:
        with pytest.raises(AuthRequired):
            await t.send({"jsonrpc": "2.0", "id": 1, "method": "test"})
    finally:
        await t.stop()
