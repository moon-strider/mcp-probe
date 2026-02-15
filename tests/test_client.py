from __future__ import annotations

import sys

import pytest

from mcp_probe.client import MCPClient
from mcp_probe.transport.stdio import StdioTransport
from tests.conftest import MOCK_VALID


@pytest.fixture
async def client_on_valid():
    t = StdioTransport(f"{sys.executable} {MOCK_VALID}")
    await t.start()
    c = MCPClient(t, timeout=5.0)
    yield c
    await t.stop()


async def test_initialize(client_on_valid):
    resp = await client_on_valid.initialize()
    assert "result" in resp
    assert client_on_valid.capabilities.get("tools") is not None
    assert client_on_valid.capabilities.get("resources") is not None
    assert client_on_valid.capabilities.get("prompts") is not None
    assert client_on_valid.server_info["name"] == "mock-valid"


async def test_list_tools(client_on_valid):
    await client_on_valid.initialize()
    tools = await client_on_valid.list_tools()
    assert len(tools) == 2
    names = {t["name"] for t in tools}
    assert names == {"echo", "add"}


async def test_call_tool(client_on_valid):
    await client_on_valid.initialize()
    resp = await client_on_valid.call_tool("echo", {"message": "hello"})
    assert "result" in resp
    assert resp["result"]["content"][0]["text"] == "hello"


async def test_list_resources(client_on_valid):
    await client_on_valid.initialize()
    resources = await client_on_valid.list_resources()
    assert len(resources) == 1
    assert resources[0]["uri"] == "test://data"


async def test_read_resource(client_on_valid):
    await client_on_valid.initialize()
    resp = await client_on_valid.read_resource("test://data")
    assert "result" in resp
    assert resp["result"]["contents"][0]["text"] == "hello world"


async def test_list_prompts(client_on_valid):
    await client_on_valid.initialize()
    prompts = await client_on_valid.list_prompts()
    assert len(prompts) == 1
    assert prompts[0]["name"] == "greeting"


async def test_get_prompt(client_on_valid):
    await client_on_valid.initialize()
    resp = await client_on_valid.get_prompt("greeting", {"name": "Test"})
    assert "result" in resp
    assert resp["result"]["messages"][0]["content"]["text"] == "Hello, Test!"


async def test_send_raw(client_on_valid):
    await client_on_valid.initialize()
    resp = await client_on_valid.send_raw(
        {
            "jsonrpc": "2.0",
            "id": 9999,
            "method": "tools/list",
            "params": {},
        }
    )
    assert resp is not None
    assert "result" in resp


async def test_send_raw_notification(client_on_valid):
    await client_on_valid.initialize()
    resp = await client_on_valid.send_raw(
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
    )
    assert resp is None
