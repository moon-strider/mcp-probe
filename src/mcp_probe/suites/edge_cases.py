from __future__ import annotations

from mcp_probe.protocol import result_object
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity


class EdgeCasesSuite(BaseSuite):
    name = "edge_cases"

    def __init__(self, *args, tools: list[dict] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tools = tools or []

    def _method(self):
        return "server/discover" if self._client.modern else "ping"

    @check("EDGE-001", "Request accepts empty application parameters", Severity.ERROR)
    async def check_edge_001(self):
        result_object(await self._client._send_request(self._method(), {}))
        return self.pass_check("Empty application parameters accepted")

    @check("EDGE-002", "Legacy request accepts omitted params", Severity.ERROR)
    async def check_edge_002(self):
        if self._client.modern:
            self.skip("Modern requests carry required metadata in params")
        response = await self._client.send_raw({"jsonrpc": "2.0", "id": 9002, "method": "ping"})
        if response is None:
            return self.fail_check("No response within deadline")
        result_object(response)
        return self.pass_check("Omitted params accepted")

    @check("EDGE-003", "Observe handling of a large metadata payload", Severity.INFO)
    async def check_edge_003(self):
        if not self._client.active:
            self.skip("Large-payload probe requires --active")
        response = await self._client._send_request(self._method(), {"_meta": {"probe/payload": "x" * 102400}})
        if "error" in response:
            return self.info_check("Server explicitly rejected a large request")
        return self.pass_check("Server answered a large request without invoking tools")

    @check("EDGE-004", "Response arrives within the check deadline", Severity.ERROR)
    async def check_edge_004(self):
        result_object(await self._client._send_request(self._method()))
        return self.pass_check("Response arrived within the enforced deadline")

    @check("EDGE-005", "Transport shutdown is managed by the runner", Severity.INFO)
    async def check_edge_005(self):
        return self.info_check("Process and HTTP session cleanup run after reporting; no server is killed mid-suite")
