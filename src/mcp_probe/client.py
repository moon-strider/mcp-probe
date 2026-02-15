from __future__ import annotations

import asyncio
import logging

from mcp_probe.transport.base import BaseTransport
from mcp_probe.types import PROBE_VERSION, SPEC_VERSION

logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self, transport: BaseTransport, timeout: float = 30.0) -> None:
        self._transport = transport
        self._timeout = timeout
        self._next_id: int = 1
        self.server_info: dict | None = None
        self.capabilities: dict = {}
        self.received_notifications: list[dict] = []

    async def _send_request(self, method: str, params: dict | None = None) -> dict:
        msg_id = self._next_id
        self._next_id += 1
        message: dict = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        else:
            message["params"] = {}
        await self._transport.send(message)
        return await self._receive_response(msg_id)

    async def _receive_response(self, expected_id: int) -> dict:
        while True:
            msg = await self._transport.receive(self._timeout)
            if "id" not in msg:
                self.received_notifications.append(msg)
                continue
            if msg["id"] == expected_id:
                return msg
            logger.debug("Unexpected id %s (expected %s), skipping", msg.get("id"), expected_id)

    async def _send_notification(self, method: str, params: dict | None = None) -> None:
        message: dict = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            message["params"] = params
        await self._transport.send(message)

    async def initialize(self) -> dict:
        result = await self._send_request("initialize", {
            "protocolVersion": SPEC_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "mcp-probe",
                "version": PROBE_VERSION,
            },
        })
        if "result" in result:
            self.server_info = result["result"].get("serverInfo")
            self.capabilities = result["result"].get("capabilities", {})
        await self._send_notification("notifications/initialized")
        return result

    async def _paginated_list(self, method: str, key: str) -> list[dict]:
        items: list[dict] = []
        cursor: str | None = None
        while True:
            params: dict = {}
            if cursor is not None:
                params["cursor"] = cursor
            resp = await self._send_request(method, params)
            result = resp.get("result", {})
            items.extend(result.get(key, []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return items

    async def list_tools(self) -> list[dict]:
        return await self._paginated_list("tools/list", "tools")

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })

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
        return await self._send_request("tasks/get_result", {"taskId": task_id})

    async def call_tool_with_task(self, name: str, arguments: dict, ttl: int = 30000) -> dict:
        return await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
            "task": {"ttl": ttl},
        })

    async def send_raw(self, message: dict) -> dict | None:
        await self._transport.send(message)
        if "id" not in message:
            return None
        try:
            return await self._receive_response(message["id"])
        except asyncio.TimeoutError:
            return None
