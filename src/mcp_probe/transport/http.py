from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request

from mcp_probe.transport.base import BaseTransport
from mcp_probe.transport.sse import parse_sse_json_stream

logger = logging.getLogger(__name__)


class AuthRequiredError(Exception):
    pass


class HttpTransport(BaseTransport):
    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._url = url
        self._custom_headers = headers or {}
        self._timeout = timeout
        self.session_id: str | None = None
        self._pending_messages: asyncio.Queue[dict] = asyncio.Queue()

    async def start(self) -> None:
        self._running = True

    async def send(self, message: dict) -> None:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id is not None:
            headers["Mcp-Session-Id"] = self.session_id
        headers.update(self._custom_headers)

        data = json.dumps(message).encode()
        req = urllib.request.Request(self._url, data=data, headers=headers, method="POST")

        try:
            response = await asyncio.to_thread(urllib.request.urlopen, req, timeout=self._timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise AuthRequiredError(f"Server returned 401 Unauthorized: {self._url}") from exc
            raise ConnectionError(f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Connection failed: {exc.reason}") from exc

        new_session_id = response.headers.get("Mcp-Session-Id")
        if new_session_id is not None:
            self.session_id = new_session_id

        content_type = response.headers.get("Content-Type", "")
        body = response.read()

        if "text/event-stream" in content_type:
            lines = body.decode().splitlines(keepends=True)
            for msg in parse_sse_json_stream(lines):
                await self._pending_messages.put(msg)
        elif "application/json" in content_type:
            try:
                parsed = json.loads(body)
                await self._pending_messages.put(parsed)
            except json.JSONDecodeError as exc:
                raise ConnectionError(f"Invalid JSON in response: {exc}") from exc
        elif body:
            try:
                parsed = json.loads(body)
                await self._pending_messages.put(parsed)
            except json.JSONDecodeError:
                logger.debug("Unhandled content-type %s, body: %s", content_type, body[:200])

    async def receive(self, timeout: float) -> dict:
        return await asyncio.wait_for(self._pending_messages.get(), timeout)

    async def stop(self) -> None:
        self._running = False
        if self.session_id is None:
            return
        headers = {"Mcp-Session-Id": self.session_id}
        headers.update(self._custom_headers)
        req = urllib.request.Request(self._url, headers=headers, method="DELETE")
        try:
            await asyncio.to_thread(urllib.request.urlopen, req, timeout=self._timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 405:
                logger.debug("Server does not support DELETE (405), ignoring")
            else:
                logger.debug("DELETE session failed: HTTP %s", exc.code)
        except Exception:
            logger.debug("DELETE session failed", exc_info=True)
