from __future__ import annotations

import asyncio
import logging
import signal
import time

from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.transport.stdio import StdioTransport
from mcp_probe.types import Severity

logger = logging.getLogger(__name__)


class EdgeCasesSuite(BaseSuite):
    name = "edge_cases"

    def __init__(self, *args, tools: list[dict] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tools = tools or []

    def _find_string_param_tool(self) -> tuple[str, str] | None:
        for t in self._tools:
            schema = t.get("inputSchema", {})
            props = schema.get("properties", {})
            for param_name, param_schema in props.items():
                if param_schema.get("type") == "string":
                    return t["name"], param_name
        return None

    @check("EDGE-001", "tools/list accepts empty params object", Severity.WARNING)
    async def check_edge_001(self):
        resp = await self._client.send_raw({
            "jsonrpc": "2.0",
            "id": 9001,
            "method": "tools/list",
            "params": {},
        })
        if resp is None:
            return self.fail_check("No response (timeout)")
        if "error" in resp:
            return self.fail_check(f"Server returned error for empty params: {resp['error']}")
        return self.pass_check("Server accepted empty params object")

    @check("EDGE-002", "tools/list accepts missing params field", Severity.WARNING)
    async def check_edge_002(self):
        resp = await self._client.send_raw({
            "jsonrpc": "2.0",
            "id": 9002,
            "method": "tools/list",
        })
        if resp is None:
            return self.fail_check("No response (timeout)")
        if "error" in resp:
            return self.fail_check(f"Server returned error for missing params: {resp['error']}")
        return self.pass_check("Server accepted request without params field")

    @check("EDGE-003", "Server handles 100KB+ payload", Severity.INFO)
    async def check_edge_003(self):
        result = self._find_string_param_tool()
        if result is None:
            self.skip("No tool with string parameter found")
        tool_name, param_name = result
        huge_string = "x" * 102400
        try:
            resp = await self._client.call_tool(tool_name, {param_name: huge_string})
        except asyncio.TimeoutError:
            return self.fail_check("Server timed out on 100KB+ payload")
        except Exception as exc:
            return self.pass_check(f"Server responded with exception: {type(exc).__name__}: {exc}")
        if "error" in resp:
            return self.pass_check(f"Server returned error for large payload: {resp['error'].get('message', '')[:100]}")
        return self.pass_check("Server handled 100KB+ payload successfully")

    @check("EDGE-004", "Response time within timeout", Severity.WARNING)
    async def check_edge_004(self):
        start = time.perf_counter()
        resp = await self._client.send_raw({
            "jsonrpc": "2.0",
            "id": 9004,
            "method": "tools/list",
            "params": {},
        })
        elapsed = time.perf_counter() - start
        if resp is None:
            return self.fail_check("No response (timeout)")
        threshold_80 = self._timeout * 0.8
        if elapsed > self._timeout:
            return self.fail_check(f"Response took {elapsed:.2f}s (timeout={self._timeout}s)")
        if elapsed > threshold_80:
            return self.warn_check(f"Response took {elapsed:.2f}s (>{threshold_80:.1f}s = 80% of timeout)")
        return self.pass_check(f"Response in {elapsed:.3f}s")

    @check("EDGE-005", "Server graceful shutdown on SIGTERM", Severity.INFO)
    async def check_edge_005(self):
        transport = self._client._transport
        if not isinstance(transport, StdioTransport):
            self.skip("SIGTERM test only applicable to stdio transport")
        process = transport._process
        if process is None:
            self.skip("No subprocess available")
        try:
            process.send_signal(signal.SIGTERM)
        except (ProcessLookupError, OSError) as exc:
            return self.fail_check(f"Could not send SIGTERM: {exc}")
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            return self.fail_check("Process did not terminate within 5s after SIGTERM (required SIGKILL)")
        code = process.returncode
        if code == 0:
            return self.pass_check("Process exited with code 0 after SIGTERM")
        return self.warn_check(f"Process exited with code {code} after SIGTERM")
