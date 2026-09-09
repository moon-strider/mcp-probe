from __future__ import annotations

from collections.abc import Callable

from mcp_probe.client import MCPClient
from mcp_probe.protocol import result_object
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.transport.base import BaseTransport
from mcp_probe.transport.stdio import StdioTransport
from mcp_probe.types import JSONRPC_ERROR_CODES, Severity


class JsonRpcSuite(BaseSuite):
    name = "jsonrpc"

    def __init__(self, *args, transport_factory: Callable[[], BaseTransport] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._transport_factory = transport_factory
        self._error_codes_seen: list[int] = []

    def _health_method(self):
        return "server/discover" if self._client.modern else "ping"

    @check("RPC-001", "Response has a valid JSON-RPC envelope", Severity.CRITICAL)
    async def check_rpc_001(self):
        result_object(await self._client._send_request(self._health_method()))
        return self.pass_check("Validated envelope, result and JSON-RPC version")

    @check("RPC-002", "Response id matches request id", Severity.CRITICAL)
    async def check_rpc_002(self):
        result_object(await self._client._send_request(self._health_method()))
        return self.pass_check("Request and response ids match, including their types")

    @check("RPC-003", "Unknown method produces a structured error", Severity.ERROR)
    async def check_rpc_003(self):
        if not self._client.active:
            self.skip("Negative protocol probes require --active")
        response = await self._client._send_request("__mcp_probe_unknown_method__")
        if "error" not in response:
            return self.fail_check("Unknown method did not return an error")
        self._error_codes_seen.append(response["error"]["code"])
        return self.pass_check("Error envelope is well formed")

    @check("RPC-004", "Isolated server survives malformed stdio input", Severity.ERROR)
    async def check_rpc_004(self):
        if not self._client.active or self._transport_factory is None:
            self.skip("Isolated malformed-input probe requires --active")
        async with self._transport_factory() as transport:
            if not isinstance(transport, StdioTransport):
                self.skip("Malformed framing probe applies to stdio")
            client = MCPClient(transport, self._timeout, protocol_version=self._client.protocol_version)
            await client.initialize()
            await transport.send_bytes(b"not json\n")
            response = await client.send_raw({"jsonrpc": "2.0", "id": 8004, "method": self._health_method()})
            if response is None or "error" in response:
                return self.fail_check("Server did not recover after malformed input")
            return self.pass_check("Fresh server recovered after malformed input")

    @check("RPC-005", "Unknown method returns method-not-found", Severity.ERROR)
    async def check_rpc_005(self):
        if not self._client.active:
            self.skip("Negative protocol probes require --active")
        response = await self._client._send_request("__mcp_probe_unknown_method__")
        if response.get("error", {}).get("code") != -32601:
            return self.fail_check("Expected JSON-RPC error code -32601")
        return self.pass_check("Correct method-not-found error")

    @check("RPC-006", "Legacy server tolerates unknown notification", Severity.INFO)
    async def check_rpc_006(self):
        if self._client.modern or not self._client.active:
            self.skip("Legacy notification probe requires --active")
        await self._client._send_notification("notifications/__mcp_probe_unknown__")
        result_object(await self._client._send_request("ping"))
        return self.info_check("Server remains responsive; unsolicited response handling is limited")

    @check("RPC-007", "Observed protocol error codes", Severity.INFO)
    async def check_rpc_007(self):
        values = [f"{c}: {JSONRPC_ERROR_CODES.get(c, 'custom')}" for c in sorted(set(self._error_codes_seen))]
        return self.info_check("; ".join(values) or "No negative probes were observed")
