from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlsplit

import httpx

from mcp_probe.protocol import MAX_MESSAGE_BYTES, MAX_MESSAGES, MODERN_VERSION, ProtocolError, loads_message
from mcp_probe.transport.base import BaseTransport
from mcp_probe.transport.headers import encode_value, parameter_headers
from mcp_probe.transport.sse import parse_sse_json_stream


class AuthRequiredError(ConnectionError):
    pass


class HttpTransport(BaseTransport):
    """Streamable HTTP with bounded asynchronous JSON/SSE response readers."""

    def __init__(self, url: str, headers: dict[str, str] | None = None, timeout: float = 30.0) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError("Expected an http(s) URL without credentials or fragment")
        self._url = url
        self._custom_headers = headers or {}
        self._timeout = timeout
        self.session_id: str | None = None
        self._pending_messages: asyncio.Queue[dict | Exception] = asyncio.Queue(maxsize=MAX_MESSAGES)
        self._jobs: set[asyncio.Task] = set()
        self._http: httpx.AsyncClient | None = None
        self._schemas: dict[str, dict] = {}

    def set_tool_schemas(self, tools: list[dict]) -> None:
        self._schemas = {
            t["name"]: t["inputSchema"]
            for t in tools
            if isinstance(t.get("name"), str) and isinstance(t.get("inputSchema"), dict)
        }
        if self.protocol_version == MODERN_VERSION:
            for schema in self._schemas.values():
                parameter_headers(schema, {})

    async def start(self) -> None:
        if self._running:
            raise RuntimeError("Transport already started")
        self._http = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        self._running = True
        self.session_id = None

    def _headers(self, message: dict | None = None) -> dict[str, str]:
        headers = {
            **self._custom_headers,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        if self.session_id is not None and self.protocol_version != MODERN_VERSION:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol_version == MODERN_VERSION and message and "method" in message:
            headers["Mcp-Method"] = message["method"]
            params = message.get("params", {})
            if message["method"] in ("tools/call", "prompts/get", "resources/read"):
                name = params.get("uri" if message["method"] == "resources/read" else "name")
                if name is not None:
                    headers["Mcp-Name"] = encode_value(name)
            if message["method"] == "tools/call":
                headers.update(
                    parameter_headers(self._schemas.get(params.get("name"), {}), params.get("arguments", {}))
                )
        return headers

    async def send(self, message: dict) -> None:
        if not self._running or self._http is None:
            raise ConnectionError("Transport not started")
        if "id" not in message or "method" not in message:
            await asyncio.wait_for(self._exchange(message), self._timeout)
            return
        task = asyncio.create_task(self._deliver(message))
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    async def _deliver(self, message: dict) -> None:
        try:
            await asyncio.wait_for(self._exchange(message), self._timeout)
        except (asyncio.TimeoutError, httpx.HTTPError) as exc:
            await self._pending_messages.put(ConnectionError(f"HTTP exchange failed: {type(exc).__name__}"))
        except Exception as exc:
            await self._pending_messages.put(exc)

    async def _exchange(self, message: dict) -> None:
        if self._http is None:
            raise ConnectionError("Transport not started")
        data = json.dumps(message, allow_nan=False).encode()
        if len(data) > MAX_MESSAGE_BYTES:
            raise ProtocolError("Outgoing message exceeds the byte limit")
        expects_response = "id" in message and "method" in message
        async with self._http.stream("POST", self._url, content=data, headers=self._headers(message)) as response:
            if response.status_code == 401:
                raise AuthRequiredError("Server requires authentication; supply a header or token environment variable")
            protocol_error_status = (
                expects_response
                and self.protocol_version == MODERN_VERSION
                and response.status_code in (400, 404)
                and response.headers.get("content-type", "").split(";", 1)[0] == "application/json"
            )
            if response.status_code >= 300 and not protocol_error_status:
                raise ConnectionError(f"Server returned HTTP {response.status_code}")
            if not expects_response:
                if response.status_code != 202:
                    raise ProtocolError("HTTP notifications and client responses require status 202")
                return
            if response.status_code != 200 and not protocol_error_status:
                raise ProtocolError("HTTP request did not return a response body with status 200")
            session = response.headers.get("Mcp-Session-Id")
            if session is not None and self.protocol_version != MODERN_VERSION:
                if not session or any(ord(c) < 33 or ord(c) > 126 for c in session):
                    raise ProtocolError("Invalid session id header")
                if self.session_id is not None and session != self.session_id:
                    raise ProtocolError("Session id changed during an active session")
                self.session_id = session
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in ("application/json", "text/event-stream"):
                raise ProtocolError("Expected application/json or text/event-stream")
            size = 0
            count = 0
            buffer = bytearray()
            event_lines: list[str] = []
            skip_lf = False
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_MESSAGE_BYTES:
                    raise ProtocolError("HTTP response exceeds the byte limit")
                if skip_lf and chunk:
                    if chunk.startswith(b"\n"):
                        chunk = chunk[1:]
                    skip_lf = False
                buffer.extend(chunk)
                if content_type == "application/json":
                    continue
                while match := re.search(b"[\r\n]", buffer):
                    index = match.start()
                    line = buffer[:index]
                    is_cr = buffer[index] == 13
                    buffer = buffer[index + 1 :]
                    if is_cr:
                        if buffer.startswith(b"\n"):
                            del buffer[0]
                        elif not buffer:
                            skip_lf = True
                    try:
                        decoded = line.decode("utf-8").rstrip("\r")
                    except UnicodeError as exc:
                        raise ProtocolError("SSE is not valid UTF-8") from exc
                    event_lines.append(decoded)
                    if decoded:
                        continue
                    for msg in parse_sse_json_stream(event_lines):
                        count += 1
                        if count > MAX_MESSAGES:
                            raise ProtocolError("SSE message limit exceeded")
                        await self._pending_messages.put(msg)
                        if "method" not in msg and msg.get("id") == message["id"]:
                            return
                    event_lines = []
            if content_type == "application/json":
                parsed = loads_message(bytes(buffer))
                if protocol_error_status and "error" not in parsed:
                    raise ProtocolError("HTTP error status requires a JSON-RPC error body")
                await self._pending_messages.put(parsed)
                return
            raise ConnectionError("SSE stream ended before the request response")

    async def receive(self, timeout: float) -> dict:
        message = await asyncio.wait_for(self._pending_messages.get(), timeout)
        if isinstance(message, Exception):
            raise message
        return message

    async def stop(self) -> None:
        self._running = False
        jobs = list(self._jobs)
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        if self._http is not None:
            try:
                if self.session_id and self.protocol_version != MODERN_VERSION:
                    try:
                        await self._http.delete(self._url, headers=self._headers(), timeout=min(self._timeout, 2.0))
                    except httpx.HTTPError:
                        pass
            finally:
                await self._http.aclose()
                self._http = None
        self.session_id = None
        while not self._pending_messages.empty():
            self._pending_messages.get_nowait()
