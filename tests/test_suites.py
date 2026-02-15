from __future__ import annotations

import sys

import pytest

from mcp_probe.client import MCPClient
from mcp_probe.transport.stdio import StdioTransport
from mcp_probe.types import Status
from tests.conftest import MOCK_BROKEN, MOCK_MINIMAL, MOCK_VALID


async def _make_client(cmd: str, timeout: float = 5.0):
    t = StdioTransport(cmd)
    await t.start()
    c = MCPClient(t, timeout=timeout)
    return c, t


def _status_map(suite_result):
    return {check.check_id: check.status for check in suite_result.checks}


class TestLifecycleSuiteValid:
    async def test_all_pass(self):
        cmd = f"{sys.executable} {MOCK_VALID}"
        c, t = await _make_client(cmd)
        try:
            from mcp_probe.suites.lifecycle import LifecycleSuite
            suite = LifecycleSuite(c, lambda: StdioTransport(cmd), timeout=5.0)
            result = await suite.run()
            sm = _status_map(result)
            assert sm["INIT-001"] == Status.PASS
            assert sm["INIT-002"] == Status.PASS
            assert sm["INIT-003"] == Status.PASS
            assert sm["INIT-004"] == Status.PASS
        finally:
            await t.stop()


class TestLifecycleSuiteBroken:
    async def test_missing_fields(self):
        cmd = f"{sys.executable} {MOCK_BROKEN}"
        c, t = await _make_client(cmd)
        try:
            from mcp_probe.suites.lifecycle import LifecycleSuite
            suite = LifecycleSuite(c, lambda: StdioTransport(cmd), timeout=5.0)
            result = await suite.run()
            sm = _status_map(result)
            assert sm["INIT-001"] == Status.PASS
            assert sm["INIT-002"] == Status.FAIL
            assert sm["INIT-003"] == Status.FAIL
        finally:
            await t.stop()


class TestJsonRpcSuiteValid:
    async def test_all_pass(self):
        cmd = f"{sys.executable} {MOCK_VALID}"
        c, t = await _make_client(cmd)
        try:
            await c.initialize()
            from mcp_probe.suites.jsonrpc import JsonRpcSuite
            suite = JsonRpcSuite(c, 5.0)
            result = await suite.run()
            sm = _status_map(result)
            assert sm["RPC-001"] == Status.PASS
            assert sm["RPC-002"] == Status.PASS
            assert sm["RPC-005"] == Status.PASS
        finally:
            await t.stop()


class TestToolsSuiteValid:
    async def test_basic_checks_pass(self):
        cmd = f"{sys.executable} {MOCK_VALID}"
        c, t = await _make_client(cmd)
        try:
            await c.initialize()
            from mcp_probe.suites.tools import ToolsSuite
            suite = ToolsSuite(c, 5.0)
            result = await suite.run()
            sm = _status_map(result)
            assert sm["TOOL-001"] == Status.PASS
            assert sm["TOOL-002"] == Status.PASS
        finally:
            await t.stop()


class TestToolsSuiteBroken:
    async def test_detects_issues(self):
        cmd = f"{sys.executable} {MOCK_BROKEN}"
        c, t = await _make_client(cmd)
        try:
            await c.initialize()
            from mcp_probe.suites.tools import ToolsSuite
            suite = ToolsSuite(c, 5.0)
            result = await suite.run()
            sm = _status_map(result)
            has_fail = any(s == Status.FAIL for s in sm.values())
            assert has_fail, f"Expected at least one FAIL, got {sm}"
        finally:
            await t.stop()


class TestResourcesSuiteValid:
    async def test_basic_pass(self):
        cmd = f"{sys.executable} {MOCK_VALID}"
        c, t = await _make_client(cmd)
        try:
            await c.initialize()
            from mcp_probe.suites.resources import ResourcesSuite
            suite = ResourcesSuite(c, 5.0)
            result = await suite.run()
            sm = _status_map(result)
            assert sm["RES-001"] == Status.PASS
            assert sm["RES-002"] == Status.PASS
        finally:
            await t.stop()


class TestPromptsSuiteValid:
    async def test_basic_pass(self):
        cmd = f"{sys.executable} {MOCK_VALID}"
        c, t = await _make_client(cmd)
        try:
            await c.initialize()
            from mcp_probe.suites.prompts import PromptsSuite
            suite = PromptsSuite(c, 5.0)
            result = await suite.run()
            sm = _status_map(result)
            assert sm["PROMPT-001"] == Status.PASS
            assert sm["PROMPT-002"] == Status.PASS
        finally:
            await t.stop()


class TestEdgeCasesSuiteValid:
    async def test_empty_params_pass(self):
        cmd = f"{sys.executable} {MOCK_VALID}"
        c, t = await _make_client(cmd)
        try:
            await c.initialize()
            tools = await c.list_tools()
            from mcp_probe.suites.edge_cases import EdgeCasesSuite
            suite = EdgeCasesSuite(c, tools=tools, timeout=5.0)
            result = await suite.run()
            sm = _status_map(result)
            assert sm["EDGE-001"] == Status.PASS
            assert sm["EDGE-002"] == Status.PASS
            assert sm["EDGE-003"] == Status.PASS
            assert sm["EDGE-004"] == Status.PASS
        finally:
            await t.stop()


class TestNotificationsSuiteValid:
    async def test_initialized_pass(self):
        cmd = f"{sys.executable} {MOCK_VALID}"
        c, t = await _make_client(cmd)
        try:
            await c.initialize()
            from mcp_probe.suites.notifications import NotificationsSuite
            suite = NotificationsSuite(c, 5.0)
            result = await suite.run()
            sm = _status_map(result)
            assert sm["NOTIF-001"] == Status.PASS
        finally:
            await t.stop()
