from __future__ import annotations

import asyncio
import logging

from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import JSONRPC_ERROR_CODES, Severity

logger = logging.getLogger(__name__)


class JsonRpcSuite(BaseSuite):
    name = "jsonrpc"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._error_codes_seen: list[int] = []

    def _record_error(self, resp: dict) -> None:
        error = resp.get("error", {})
        code = error.get("code")
        if isinstance(code, int):
            self._error_codes_seen.append(code)

    @check("RPC-001", "Response contains jsonrpc 2.0 field", Severity.CRITICAL)
    async def check_rpc_001(self):
        resp = await self._client.send_raw({
            "jsonrpc": "2.0",
            "id": 8001,
            "method": "tools/list",
            "params": {},
        })
        if resp is None:
            return self.fail_check("No response received")
        version = resp.get("jsonrpc")
        if version != "2.0":
            return self.fail_check(f"jsonrpc field is {version!r}, expected '2.0'")
        return self.pass_check()

    @check("RPC-002", "Response id matches request id", Severity.CRITICAL)
    async def check_rpc_002(self):
        resp = await self._client.send_raw({
            "jsonrpc": "2.0",
            "id": 8042,
            "method": "tools/list",
            "params": {},
        })
        if resp is None:
            return self.fail_check("No response received")
        if resp.get("id") != 8042:
            return self.fail_check(f"Response id is {resp.get('id')!r}, expected 8042")
        return self.pass_check()

    @check("RPC-003", "Error response has valid structure", Severity.ERROR)
    async def check_rpc_003(self):
        resp = await self._client.send_raw({
            "jsonrpc": "2.0",
            "id": 8003,
            "method": "nonexistent/method_for_rpc003",
            "params": {},
        })
        if resp is None:
            return self.fail_check("No response received")
        self._record_error(resp)
        error = resp.get("error")
        if error is None:
            return self.fail_check("Server did not return an error for unknown method")
        if not isinstance(error.get("code"), int):
            return self.fail_check(f"error.code is not an integer: {error.get('code')!r}")
        if not isinstance(error.get("message"), str):
            return self.fail_check(f"error.message is not a string: {error.get('message')!r}")
        return self.pass_check(f"code={error['code']}, message={error['message']!r}")

    @check("RPC-004", "Server survives invalid JSON input", Severity.ERROR)
    async def check_rpc_004(self):
        transport = self._client._transport
        try:
            if hasattr(transport, '_process') and transport._process and transport._process.stdin:
                transport._process.stdin.write(b"not json at all\n")
                await transport._process.stdin.drain()
            else:
                await transport.send({"__raw_invalid__": True})
        except Exception:
            pass

        await asyncio.sleep(0.3)

        try:
            resp = await self._client.send_raw({
                "jsonrpc": "2.0",
                "id": 8004,
                "method": "tools/list",
                "params": {},
            })
            if resp is not None:
                return self.pass_check("Server still responds after invalid JSON")
            return self.fail_check("Server stopped responding after invalid JSON")
        except Exception as exc:
            return self.fail_check(f"Server crashed after invalid JSON: {exc}")

    @check("RPC-005", "Unknown method returns -32601", Severity.WARNING)
    async def check_rpc_005(self):
        resp = await self._client.send_raw({
            "jsonrpc": "2.0",
            "id": 8005,
            "method": "nonexistent/method_for_rpc005",
            "params": {},
        })
        if resp is None:
            return self.fail_check("No response received")
        self._record_error(resp)
        error = resp.get("error")
        if error is None:
            return self.fail_check("Server did not return an error for unknown method")
        code = error.get("code")
        if code == -32601:
            return self.pass_check("Correct error code -32601 (Method not found)")
        return self.warn_check(f"Error returned but code is {code}, expected -32601")

    @check("RPC-006", "Server ignores unknown notification", Severity.INFO)
    async def check_rpc_006(self):
        await self._client._transport.send({
            "jsonrpc": "2.0",
            "method": "nonexistent/notification_for_rpc006",
        })
        await asyncio.sleep(0.3)
        try:
            resp = await self._client.send_raw({
                "jsonrpc": "2.0",
                "id": 8006,
                "method": "tools/list",
                "params": {},
            })
            if resp is not None:
                return self.pass_check("Server still responds after unknown notification")
            return self.fail_check("Server stopped responding after unknown notification")
        except Exception as exc:
            return self.fail_check(f"Server crashed after unknown notification: {exc}")

    @check("RPC-007", "Error codes summary", Severity.INFO)
    async def check_rpc_007(self):
        if not self._error_codes_seen:
            return self.info_check("No error codes observed during testing")
        summary_parts: list[str] = []
        for code in sorted(set(self._error_codes_seen)):
            label = JSONRPC_ERROR_CODES.get(code, "custom")
            summary_parts.append(f"{code} ({label})")
        return self.info_check(f"Error codes seen: {', '.join(summary_parts)}")
