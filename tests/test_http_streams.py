from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from mcp_probe.client import MCPClient
from mcp_probe.protocol import MODERN_VERSION, ProtocolError
from mcp_probe.transport.headers import encode_value, parameter_headers
from mcp_probe.transport.http import HttpTransport


@pytest.fixture
def http_mock(monkeypatch):
    original = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))

    return install


class OpenStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("newline", [b"\n", b"\r", b"\r\n"])
async def test_sse_response_finishes_without_eof(http_mock, newline):
    notification = {"jsonrpc": "2.0", "method": "notifications/message", "params": {"data": "café"}}
    response = {"jsonrpc": "2.0", "id": 1, "result": {}}
    payload = b": heartbeat" + newline * 2
    for value in (notification, response):
        payload += b"data: " + json.dumps(value, ensure_ascii=False).encode() + newline * 2
    # Deliberately split UTF-8 and CRLF across network chunks.
    stream = OpenStream([payload[i : i + 1] for i in range(len(payload))])
    http_mock(lambda r: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream))
    async with HttpTransport("http://example.test/mcp", timeout=0.5) as transport:
        client = MCPClient(transport, timeout=0.5)
        assert await client._send_request("ping") == response
        assert client.received_notifications == [notification]
    assert stream.closed


async def test_server_ping_is_answered_while_response_stream_is_open(http_mock):
    replied = asyncio.Event()

    class InteractiveStream(OpenStream):
        async def __aiter__(self):
            yield b'data: {"jsonrpc":"2.0","id":"peer","method":"ping"}\n\n'
            await replied.wait()
            yield b'data: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
            await asyncio.Event().wait()

    stream = InteractiveStream([])

    def handler(request):
        body = json.loads(request.content)
        if body.get("id") == "peer":
            assert body == {"jsonrpc": "2.0", "id": "peer", "result": {}}
            replied.set()
            return httpx.Response(202)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    http_mock(handler)
    async with HttpTransport("http://example.test/mcp", timeout=1) as transport:
        assert "result" in await MCPClient(transport, timeout=1)._send_request("ping")
    assert replied.is_set() and stream.closed


async def test_stalled_body_is_bounded_and_closed(http_mock):
    stream = OpenStream([b"{"])
    http_mock(lambda r: httpx.Response(200, headers={"content-type": "application/json"}, stream=stream))
    async with HttpTransport("http://example.test/mcp", timeout=0.03) as transport:
        with pytest.raises((ConnectionError, asyncio.TimeoutError)):
            await MCPClient(transport, timeout=0.1)._send_request("ping")
    assert stream.closed


@pytest.mark.parametrize(
    "status,body,kind",
    [
        (200, b"[]", "application/json"),
        (200, b'{"jsonrpc":"2.0","id":1,"result":NaN}', "application/json"),
        (200, b"<html>error</html>", "text/html"),
        (202, b"", "application/json"),
        (200, b"x" * (4 * 1024 * 1024 + 1), "application/json"),
    ],
)
async def test_invalid_http_responses_are_rejected(http_mock, status, body, kind):
    http_mock(lambda r: httpx.Response(status, content=body, headers={"content-type": kind}))
    async with HttpTransport("http://example.test/mcp") as transport:
        with pytest.raises(ProtocolError):
            await MCPClient(transport)._send_request("ping")


async def test_redirect_does_not_forward_credentials(http_mock):
    visited = []

    def handler(request):
        visited.append(str(request.url))
        return httpx.Response(307, headers={"location": "https://other.test/private"})

    http_mock(handler)
    async with HttpTransport("https://example.test/mcp", headers={"Authorization": "Bearer secret"}) as transport:
        with pytest.raises(ConnectionError, match="307"):
            await MCPClient(transport)._send_request("ping")
    assert visited == ["https://example.test/mcp"]


@pytest.mark.parametrize("status,code", [(400, -32020), (404, -32601)])
async def test_modern_http_errors_preserve_protocol_envelope(http_mock, status, code):
    http_mock(
        lambda r: httpx.Response(
            status, json={"jsonrpc": "2.0", "id": 1, "error": {"code": code, "message": "invalid"}}
        )
    )
    async with HttpTransport("https://example.test/mcp") as transport:
        client = MCPClient(transport, protocol_version=MODERN_VERSION)
        assert (await client._send_request("unknown"))["error"]["code"] == code


async def test_modern_headers_match_body_and_omit_sessions(http_mock):
    seen = []

    def handler(request):
        seen.append(request)
        body = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"Mcp-Session-Id": "ignored"},
            json={"jsonrpc": "2.0", "id": body["id"], "result": {"resultType": "complete"}},
        )

    http_mock(handler)
    async with HttpTransport("https://example.test/mcp") as transport:
        client = MCPClient(transport, protocol_version=MODERN_VERSION)
        transport.set_tool_schemas(
            [
                {
                    "name": "echo",
                    "inputSchema": {
                        "properties": {
                            "config": {
                                "type": "object",
                                "properties": {"region": {"type": "string", "x-mcp-header": "Region"}},
                            }
                        }
                    },
                }
            ]
        )
        await client.call_tool("echo", {"config": {"region": "мир"}})
        await client.read_resource("demo://привет")
    assert len(seen) == 2  # No legacy DELETE session request.
    first = seen[0]
    assert first.headers["mcp-method"] == "tools/call"
    assert first.headers["mcp-name"] == "echo"
    assert first.headers["mcp-param-region"] == encode_value("мир")
    assert "mcp-session-id" not in first.headers
    assert first.headers["mcp-protocol-version"] == MODERN_VERSION
    assert seen[1].headers["mcp-name"] == encode_value("demo://привет")
    meta = json.loads(first.content)["params"]["_meta"]
    assert meta["io.modelcontextprotocol/protocolVersion"] == MODERN_VERSION


@pytest.mark.parametrize("value", [" padded ", "hello\nworld", "世界", "=?base64?literal?="])
def test_header_encoding_is_reversible(value):
    import base64

    encoded = encode_value(value)
    assert encoded.startswith("=?base64?")
    assert base64.b64decode(encoded[9:-2]).decode() == value


@pytest.mark.parametrize(
    "schema",
    [
        {"properties": {"x": {"type": "string", "x-mcp-header": "a\nb"}}},
        {"properties": {"x": {"type": "number", "x-mcp-header": "x"}}},
        {"items": {"properties": {"x": {"type": "string", "x-mcp-header": "x"}}}},
        {"properties": {"x": {"type": "string", "x-mcp-header": "X"}, "y": {"type": "string", "x-mcp-header": "x"}}},
    ],
)
def test_invalid_header_annotations_are_rejected(schema):
    with pytest.raises(ProtocolError):
        parameter_headers(schema, {})
