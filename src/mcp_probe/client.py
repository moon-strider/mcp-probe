from __future__ import annotations

import asyncio
from copy import deepcopy

from mcp_probe.protocol import (
    MAX_ITEMS,
    MAX_MESSAGES,
    MAX_PAGES,
    MODERN_VERSION,
    SUPPORTED_VERSIONS,
    ProtocolError,
    result_object,
    validate_cache_metadata,
    validate_envelope,
)
from mcp_probe.transport.base import BaseTransport
from mcp_probe.types import PROBE_VERSION, SPEC_VERSION


class MCPClient:
    """Serial request client with a total deadline and bounded peer input."""

    def __init__(
        self,
        transport: BaseTransport,
        timeout: float = 30.0,
        *,
        protocol_version: str = SPEC_VERSION,
        active: bool = False,
        allowed_tools: set[str] | None = None,
        tool_cases: dict[str, dict] | None = None,
        max_pages: int = MAX_PAGES,
    ) -> None:
        if timeout <= 0 or max_pages < 1:
            raise ValueError("Timeout and page limit must be positive")
        if protocol_version not in SUPPORTED_VERSIONS:
            raise ValueError("Unsupported protocol version")
        self._transport = transport
        self._timeout = timeout
        self._next_id = 1
        self._lock = asyncio.Lock()
        self.protocol_version = protocol_version
        self.active = active
        self.allowed_tools = set(allowed_tools or ())
        self.tool_cases = deepcopy(tool_cases or {})
        self.max_pages = max_pages
        self.page_counts: dict[str, int] = {}
        self.server_info: dict | None = None
        self.capabilities: dict = {}
        self.received_notifications: list[dict] = []
        self.protocol_events: list[str] = []
        self.initialized = False
        self._transport.protocol_version = protocol_version if self.modern else None

    @property
    def modern(self) -> bool:
        return self.protocol_version == MODERN_VERSION

    def _params(self, params: dict | None) -> dict:
        result = deepcopy(params or {})
        if self.modern:
            result.setdefault("_meta", {}).update(
                {
                    "io.modelcontextprotocol/protocolVersion": self.protocol_version,
                    "io.modelcontextprotocol/clientCapabilities": {},
                    "io.modelcontextprotocol/clientInfo": {"name": "mcp-probe", "version": PROBE_VERSION},
                }
            )
        return result

    async def _send_request(self, method: str, params: dict | None = None) -> dict:
        msg_id = self._next_id
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": self._params(params)}
        return await asyncio.wait_for(self._exchange(message), self._timeout)

    async def _exchange(self, message: dict, *, raw: bool = False) -> dict:
        async with self._lock:
            await self._transport.send(message)
            return await self._receive_response(message["id"], raw=raw)

    async def _receive_response(self, expected_id: int | str, *, raw: bool = False) -> dict:
        # This inner deadline also protects callers of send_raw and this method.
        deadline = asyncio.get_running_loop().time() + self._timeout
        for _ in range(MAX_MESSAGES):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            msg = await asyncio.wait_for(self._transport.receive(remaining), remaining)
            validate_envelope(msg)
            if "method" in msg:
                if "id" in msg:
                    reply = {"jsonrpc": "2.0", "id": msg["id"]}
                    if msg["method"] == "ping" and not self.modern:
                        reply["result"] = {}
                    else:
                        reply["error"] = {"code": -32601, "message": "Client capability not supported"}
                    await self._transport.send(reply)
                else:
                    if len(self.received_notifications) >= MAX_MESSAGES:
                        raise ProtocolError("Notification limit exceeded")
                    self.received_notifications.append(msg)
                continue
            if msg.get("id") is None and "error" in msg and raw:
                self.protocol_events.append("Uncorrelated error response")
                continue
            if not raw and (type(msg["id"]) is not type(expected_id) or msg["id"] != expected_id):
                raise ProtocolError("Response id does not match the request")
            if self.modern and "result" in msg:
                result = msg["result"]
                if result.get("resultType") not in ("complete", "input_required"):
                    raise ProtocolError("Modern results require resultType")
                if result["resultType"] == "input_required":
                    raise ProtocolError("Peer requested unadvertised client interaction")
            return msg
        raise ProtocolError("Message limit exceeded while waiting for a response")

    async def _send_notification(self, method: str, params: dict | None = None) -> None:
        message: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        await asyncio.wait_for(self._transport.send(message), self._timeout)

    async def initialize(self) -> dict:
        if self.modern:
            response = await self._send_request("server/discover")
            result = result_object(response)
            versions = result.get("supportedVersions")
            if not isinstance(versions, list) or self.protocol_version not in versions:
                raise ProtocolError("Server does not advertise the requested protocol version")
            self.server_info = result.get("_meta", {}).get("io.modelcontextprotocol/serverInfo")
        else:
            response = await self._send_request(
                "initialize",
                {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-probe", "version": PROBE_VERSION},
                },
            )
            result = result_object(response)
            if result.get("protocolVersion") != self.protocol_version:
                raise ProtocolError("Server did not negotiate the requested protocol version")
            self.server_info = result.get("serverInfo")
            if not isinstance(self.server_info, dict) or not all(
                isinstance(self.server_info.get(k), str) and self.server_info[k] for k in ("name", "version")
            ):
                raise ProtocolError("Initialize result requires serverInfo name and version")
        caps = result.get("capabilities")
        if not isinstance(caps, dict) or any(not isinstance(v, dict) for v in caps.values()):
            raise ProtocolError("Capabilities must contain objects")
        self.capabilities = caps
        self._transport.protocol_version = self.protocol_version
        if not self.modern:
            await self._send_notification("notifications/initialized")
        self.initialized = True
        return response

    async def _paginated_list(self, method: str, key: str) -> list[dict]:
        items: list[dict] = []
        seen: set[str] = set()
        cursor: str | None = None
        deadline = asyncio.get_running_loop().time() + self._timeout
        for page in range(1, self.max_pages + 1):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            params = {} if cursor is None else {"cursor": cursor}
            response = await asyncio.wait_for(self._send_request(method, params), remaining)
            result = result_object(response)
            if self.modern:
                validate_cache_metadata(result)
            values = result.get(key)
            if not isinstance(values, list) or any(not isinstance(x, dict) for x in values):
                raise ProtocolError(f"{method} must return an array of objects in {key}")
            items.extend(values)
            if len(items) > MAX_ITEMS:
                raise ProtocolError("Listing item limit exceeded")
            self.page_counts[method] = page
            if "nextCursor" not in result:
                return items
            cursor = result["nextCursor"]
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise ProtocolError("Invalid or repeated pagination cursor")
            seen.add(cursor)
        raise ProtocolError("Pagination page limit exceeded")

    async def list_tools(self) -> list[dict]:
        return await self._paginated_list("tools/list", "tools")

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return await self._send_request("tools/call", {"name": name, "arguments": arguments})

    async def list_resources(self) -> list[dict]:
        return await self._paginated_list("resources/list", "resources")

    async def read_resource(self, uri: str) -> dict:
        return await self._send_request("resources/read", {"uri": uri})

    async def subscribe_resource(self, uri: str) -> dict:
        return await self._send_request("resources/subscribe", {"uri": uri})

    async def unsubscribe_resource(self, uri: str) -> dict:
        return await self._send_request("resources/unsubscribe", {"uri": uri})

    async def list_prompts(self) -> list[dict]:
        return await self._paginated_list("prompts/list", "prompts")

    async def get_prompt(self, name: str, arguments: dict | None = None) -> dict:
        params: dict = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        return await self._send_request("prompts/get", params)

    async def list_tasks(self) -> list[dict]:
        return await self._paginated_list("tasks/list", "tasks")

    async def get_task(self, task_id: str) -> dict:
        return await self._send_request("tasks/get", {"taskId": task_id})

    async def cancel_task(self, task_id: str) -> dict:
        return await self._send_request("tasks/cancel", {"taskId": task_id})

    async def get_task_result(self, task_id: str) -> dict:
        return await self._send_request("tasks/result", {"taskId": task_id})

    async def call_tool_with_task(self, name: str, arguments: dict, ttl: int = 30000) -> dict:
        return await self._send_request("tools/call", {"name": name, "arguments": arguments, "task": {"ttl": ttl}})

    async def send_raw(self, message: dict) -> dict | None:
        if "id" not in message:
            await asyncio.wait_for(self._transport.send(message), self._timeout)
            return None
        self._next_id = max(self._next_id, message["id"] + 1) if type(message["id"]) is int else self._next_id
        if self.modern and "method" in message:
            message = {**message, "params": self._params(message.get("params"))}
        try:
            return await asyncio.wait_for(self._exchange(message, raw=True), self._timeout)
        except asyncio.TimeoutError:
            return None
