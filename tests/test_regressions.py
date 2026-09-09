"""Failures reproduced against the original public implementation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from mcp_probe.client import MCPClient
from mcp_probe.schema_utils import generate_invalid_args, generate_valid_args
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.suites.tools import ToolsSuite
from mcp_probe.types import Severity, Status


def client_with_response(payload):
    transport = AsyncMock()
    transport.receive.return_value = payload
    return MCPClient(transport, timeout=0.02)


@pytest.mark.parametrize(
    "payload",
    [
        {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {"code": -1, "message": "bad"}},
        {"jsonrpc": "1.0", "id": 1, "result": {}},
        {"jsonrpc": "2.0", "id": True, "result": {}},
        {"jsonrpc": "2.0", "id": 1, "error": {"code": True, "message": "bad"}},
    ],
)
async def test_reject_malformed_response_envelopes(payload):
    with pytest.raises((ValueError, ConnectionError)):
        await client_with_response(payload)._send_request("ping")


async def test_notifications_cannot_extend_request_deadline():
    client = client_with_response({"jsonrpc": "2.0", "method": "notifications/message"})

    async def notification(*args):
        await asyncio.sleep(0.004)
        return {"jsonrpc": "2.0", "method": "notifications/message"}

    client._transport.receive.side_effect = notification
    request = asyncio.create_task(client._send_request("ping"))
    await asyncio.sleep(0.08)
    completed = request.done()
    request.cancel()
    await asyncio.gather(request, return_exceptions=True)
    assert completed, "Notifications reset the request timeout indefinitely"


async def test_pagination_rejects_repeated_cursor():
    client = client_with_response({})
    calls = 0

    async def page(*args):
        nonlocal calls
        calls += 1
        if calls > 3:
            raise RuntimeError("pagination never stopped")
        return {"result": {"tools": [], "nextCursor": "same"}}

    client._send_request = page
    with pytest.raises(ValueError, match="cursor"):
        await client.list_tools()


async def test_pagination_does_not_turn_errors_into_empty_lists():
    client = client_with_response({})
    client._send_request = AsyncMock(return_value={"error": {"code": -32601, "message": "unsupported"}})
    with pytest.raises(ValueError):
        await client.list_tools()


async def test_task_result_uses_specified_method():
    client = client_with_response({})
    client._send_request = AsyncMock(return_value={"result": {"content": []}})
    await client.get_task_result("owned-task")
    client._send_request.assert_awaited_once_with("tasks/result", {"taskId": "owned-task"})


def test_parameterless_object_schema_generates_object():
    assert generate_valid_args({"type": "object"}) == {}


def test_unconstrained_schema_has_no_invalid_object():
    assert generate_invalid_args({"type": "object"}) is None


def test_generated_numbers_respect_upper_bound():
    schema = {"type": "object", "properties": {"x": {"type": "integer", "maximum": -5}}, "required": ["x"]}
    args = generate_valid_args(schema)
    assert args is None or args["x"] <= -5


@pytest.mark.parametrize("result", [{}, {"content": "not a list"}, {"content": [{"type": "text"}]}])
async def test_tool_check_rejects_malformed_content(result):
    client = AsyncMock()
    client.call_tool.return_value = {"result": result}
    # Explicit selection will become required by the audit; assign it here so
    # this regression also exercises the same call after that change.
    client.allowed_tools = {"echo"}
    client.tool_cases = {"echo": {"message": "hello"}}
    suite = ToolsSuite(client)
    suite._tools = [{"name": "echo", "inputSchema": {"type": "object"}}]
    outcome = await suite.check_tool_004()
    assert outcome.status is Status.FAIL


async def test_each_check_has_a_total_deadline():
    class HangingSuite(BaseSuite):
        name = "hanging"

        @check("HANG-001", "bounded wait", Severity.ERROR)
        async def check_hang(self):
            await asyncio.sleep(1)
            return self.pass_check()

    task = asyncio.create_task(HangingSuite(client_with_response({}), timeout=0.01).run())
    await asyncio.sleep(0.08)
    completed = task.done()
    task.cancel()
    results = await asyncio.gather(task, return_exceptions=True)
    assert completed, "A check exceeded its configured deadline"
    assert results[0].checks[0].status is Status.FAIL
