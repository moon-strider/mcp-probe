from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from mcp_probe.client import MCPClient
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.transport.base import BaseTransport
from mcp_probe.types import Severity, SPEC_VERSION, PROBE_VERSION

logger = logging.getLogger(__name__)


class LifecycleSuite(BaseSuite):
    name = "lifecycle"

    def __init__(
        self,
        client: MCPClient,
        transport_factory: Callable[[], BaseTransport],
        timeout: float = 30.0,
    ) -> None:
        super().__init__(client, timeout)
        self._transport_factory = transport_factory
        self._init_response: dict | None = None

    @check("INIT-005", "Request before initialize is rejected", Severity.WARNING)
    async def check_init_005(self):
        transport = self._transport_factory()
        try:
            await transport.start()
            raw_msg = {
                "jsonrpc": "2.0",
                "id": 9990,
                "method": "tools/list",
                "params": {},
            }
            await transport.send(raw_msg)
            try:
                resp = await transport.receive(self._timeout)
            except (asyncio.TimeoutError, ConnectionError):
                return self.pass_check("Server did not respond (acceptable)")
            if "error" in resp:
                return self.pass_check(f"Server rejected with error: {resp['error'].get('message', '')}")
            return self.warn_check("Server accepted request without prior initialize")
        finally:
            await transport.stop()

    @check("INIT-006", "Double initialize is rejected", Severity.WARNING)
    async def check_init_006(self):
        transport = self._transport_factory()
        try:
            await transport.start()
            temp_client = MCPClient(transport, self._timeout)
            await temp_client.initialize()
            second_init = {
                "jsonrpc": "2.0",
                "id": 9991,
                "method": "initialize",
                "params": {
                    "protocolVersion": SPEC_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-probe", "version": PROBE_VERSION},
                },
            }
            await transport.send(second_init)
            try:
                resp = await transport.receive(self._timeout)
                while "id" not in resp:
                    resp = await transport.receive(self._timeout)
            except (asyncio.TimeoutError, ConnectionError):
                return self.pass_check("Server did not respond to second initialize")
            if "error" in resp:
                return self.pass_check(f"Server rejected double init: {resp['error'].get('message', '')}")
            return self.warn_check("Server accepted double initialize")
        finally:
            await transport.stop()

    @check("INIT-001", "Server responds to initialize", Severity.CRITICAL)
    async def check_init_001(self):
        resp = await self._client.initialize()
        self._init_response = resp
        if "result" not in resp:
            return self.fail_check(f"No 'result' in response: {resp}")
        return self.pass_check()

    @check("INIT-002", "protocolVersion is present and valid", Severity.CRITICAL)
    async def check_init_002(self):
        if self._init_response is None:
            self.skip("INIT-001 did not complete")
        result = self._init_response.get("result", {})
        version = result.get("protocolVersion")
        if not version or not isinstance(version, str):
            return self.fail_check(f"protocolVersion missing or not a string: {version!r}")
        return self.pass_check(f"protocolVersion={version}")

    @check("INIT-003", "capabilities object is present", Severity.CRITICAL)
    async def check_init_003(self):
        if self._init_response is None:
            self.skip("INIT-001 did not complete")
        result = self._init_response.get("result", {})
        caps = result.get("capabilities")
        if not isinstance(caps, dict):
            return self.fail_check(f"capabilities missing or not an object: {caps!r}")
        return self.pass_check(f"capabilities keys: {list(caps.keys())}")

    @check("INIT-004", "notifications/initialized does not crash server", Severity.CRITICAL)
    async def check_init_004(self):
        if self._init_response is None:
            self.skip("INIT-001 did not complete")
        try:
            resp = await self._client.send_raw({
                "jsonrpc": "2.0",
                "id": 9992,
                "method": "ping",
            })
        except asyncio.TimeoutError:
            resp = None
        if resp is None:
            try:
                resp = await self._client._send_request("tools/list")
            except Exception:
                return self.fail_check("Server stopped responding after notifications/initialized")
        return self.pass_check("Server still responds after notifications/initialized")
