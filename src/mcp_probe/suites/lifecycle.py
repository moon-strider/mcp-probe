from __future__ import annotations

import asyncio
from collections.abc import Callable

from mcp_probe.client import MCPClient
from mcp_probe.protocol import result_object
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.transport.base import BaseTransport
from mcp_probe.types import Severity


class LifecycleSuite(BaseSuite):
    name = "lifecycle"

    def __init__(
        self, client: MCPClient, transport_factory: Callable[[], BaseTransport], timeout: float = 30.0
    ) -> None:
        super().__init__(client, timeout)
        self._transport_factory = transport_factory
        self._init_response: dict | None = None

    @check("INIT-001", "Protocol handshake or discovery succeeds", Severity.CRITICAL)
    async def check_init_001(self):
        self._init_response = await self._client.initialize()
        return self.pass_check("Discovery complete" if self._client.modern else "Handshake complete")

    @check("INIT-002", "Requested protocol version is supported", Severity.CRITICAL)
    async def check_init_002(self):
        if self._init_response is None:
            self.skip("Handshake/discovery failed")
        return self.pass_check(self._client.protocol_version)

    @check("INIT-003", "Capabilities and server identity are well formed", Severity.CRITICAL)
    async def check_init_003(self):
        if self._init_response is None:
            self.skip("Handshake/discovery failed")
        info = self._client.server_info
        if info is not None and (
            not isinstance(info, dict) or not all(isinstance(info.get(k), str) and info[k] for k in ("name", "version"))
        ):
            return self.fail_check("Server identity requires string name and version")
        return self.pass_check("Validated capability objects and server identity")

    @check("INIT-004", "Server responds after handshake or discovery", Severity.CRITICAL)
    async def check_init_004(self):
        if self._init_response is None:
            self.skip("Handshake/discovery failed")
        method = "server/discover" if self._client.modern else "ping"
        result_object(await self._client._send_request(method))
        return self.pass_check("Server responded successfully")

    @check("INIT-005", "Observe requests before legacy initialization", Severity.INFO)
    async def check_init_005(self):
        if self._client.modern or not self._client.active:
            self.skip("Legacy isolated probe; requires --active")
        async with self._transport_factory() as transport:
            client = MCPClient(transport, self._timeout)
            try:
                response = await client._send_request("tools/list")
            except (ConnectionError, asyncio.TimeoutError):
                return self.info_check("Isolated peer rejected or did not answer a pre-initialize request")
            behavior = "rejected" if "error" in response else "accepted"
            return self.info_check(f"Request before initialize was {behavior}; this is an observation")

    @check("INIT-006", "Observe repeated legacy initialization", Severity.INFO)
    async def check_init_006(self):
        if self._client.modern or not self._client.active:
            self.skip("Legacy isolated probe; requires --active")
        async with self._transport_factory() as transport:
            client = MCPClient(transport, self._timeout)
            await client.initialize()
            response = await client._send_request(
                "initialize",
                {
                    "protocolVersion": client.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-probe", "version": "probe"},
                },
            )
            behavior = "rejected" if "error" in response else "accepted"
            return self.info_check(f"Repeated initialize was {behavior}; this is an observation")
