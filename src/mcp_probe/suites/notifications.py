from __future__ import annotations

import asyncio
import logging

from mcp_probe.client import MCPClient
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity

logger = logging.getLogger(__name__)

_VALID_NOTIFICATION_METHODS = {
    "notifications/tools/list_changed",
    "notifications/resources/list_changed",
    "notifications/resources/updated",
    "notifications/prompts/list_changed",
    "notifications/progress",
}


def _validate_notification_format(notif: dict) -> str | None:
    if notif.get("jsonrpc") != "2.0":
        return f"jsonrpc is {notif.get('jsonrpc')!r}, expected '2.0'"
    if "method" not in notif:
        return "missing 'method' field"
    if "id" in notif:
        return "notification should not have 'id' field"
    params = notif.get("params")
    if params is not None and not isinstance(params, dict):
        return f"params is {type(params).__name__}, expected object or absent"
    return None


class NotificationsSuite(BaseSuite):
    name = "notifications"

    def __init__(self, client: MCPClient, timeout: float = 30.0, resources: list[dict] | None = None) -> None:
        super().__init__(client, timeout)
        self._resources = resources or []
        self._subscribed_uri: str | None = None

    def _find_notifications(self, method: str) -> list[dict]:
        return [n for n in self._client.received_notifications if n.get("method") == method]

    @check("NOTIF-001", "Server accepts notifications/initialized", Severity.CRITICAL)
    async def check_notif_001(self):
        try:
            resp = await self._client.send_raw(
                {
                    "jsonrpc": "2.0",
                    "id": 7001,
                    "method": "ping",
                }
            )
            if resp is not None:
                return self.pass_check("Server responds after notifications/initialized")
        except asyncio.TimeoutError:
            pass
        resp = await self._client._send_request("tools/list")
        if "result" in resp or "error" in resp:
            return self.pass_check("Server still operational after notifications/initialized")
        return self.fail_check("Server not responding after notifications/initialized")

    @check("NOTIF-002", "notifications/tools/list_changed format", Severity.ERROR)
    async def check_notif_002(self):
        notifs = self._find_notifications("notifications/tools/list_changed")
        if not notifs:
            self.skip("No tools/list_changed notifications received")
        for n in notifs:
            err = _validate_notification_format(n)
            if err:
                return self.fail_check(f"Invalid format: {err}")
        return self.pass_check(f"Validated {len(notifs)} notification(s)")

    @check("NOTIF-003", "notifications/resources/list_changed format", Severity.ERROR)
    async def check_notif_003(self):
        notifs = self._find_notifications("notifications/resources/list_changed")
        if not notifs:
            self.skip("No resources/list_changed notifications received")
        for n in notifs:
            err = _validate_notification_format(n)
            if err:
                return self.fail_check(f"Invalid format: {err}")
        return self.pass_check(f"Validated {len(notifs)} notification(s)")

    @check("NOTIF-004", "notifications/prompts/list_changed format", Severity.ERROR)
    async def check_notif_004(self):
        notifs = self._find_notifications("notifications/prompts/list_changed")
        if not notifs:
            self.skip("No prompts/list_changed notifications received")
        for n in notifs:
            err = _validate_notification_format(n)
            if err:
                return self.fail_check(f"Invalid format: {err}")
        return self.pass_check(f"Validated {len(notifs)} notification(s)")

    @check("NOTIF-005", "notifications/progress format and monotonicity", Severity.WARNING)
    async def check_notif_005(self):
        notifs = self._find_notifications("notifications/progress")
        if not notifs:
            self.skip("No progress notifications received")
        issues: list[str] = []
        by_token: dict[str, list[dict]] = {}
        for n in notifs:
            err = _validate_notification_format(n)
            if err:
                issues.append(err)
                continue
            params = n.get("params", {})
            token = params.get("progressToken")
            if token is None:
                issues.append("progress notification missing progressToken")
                continue
            progress = params.get("progress")
            if not isinstance(progress, (int, float)) or progress < 0:
                issues.append(f"progress is {progress!r}, expected number >= 0")
                continue
            total = params.get("total")
            if total is not None:
                if not isinstance(total, (int, float)) or total <= 0:
                    issues.append(f"total is {total!r}, expected number > 0")
                elif progress > total:
                    issues.append(f"progress {progress} > total {total}")
            by_token.setdefault(str(token), []).append(params)
        for token, entries in by_token.items():
            values = [e.get("progress", 0) for e in entries]
            for i in range(1, len(values)):
                if values[i] < values[i - 1]:
                    issues.append(f"token {token}: progress not monotonic ({values[i-1]} -> {values[i]})")
        if issues:
            return self.fail_check("; ".join(issues[:5]))
        return self.pass_check(f"Validated {len(notifs)} progress notification(s)")

    @check("SUB-001", "resources/subscribe returns success", Severity.ERROR)
    async def check_sub_001(self):
        caps = self._client.capabilities
        res_caps = caps.get("resources", {})
        if not isinstance(res_caps, dict) or not res_caps.get("subscribe"):
            self.skip("Server does not advertise resources.subscribe capability")
        if not self._resources:
            self.skip("No resources available for subscribe test")
        uri = self._resources[0].get("uri", "")
        resp = await self._client.subscribe_resource(uri)
        if "error" in resp:
            return self.fail_check(f"subscribe error: {resp['error']}")
        self._subscribed_uri = uri
        return self.pass_check(f"Subscribed to '{uri}'")

    @check("SUB-002", "resources/unsubscribe returns success", Severity.ERROR)
    async def check_sub_002(self):
        if self._subscribed_uri is None:
            self.skip("No active subscription (SUB-001 did not run or failed)")
        resp = await self._client.unsubscribe_resource(self._subscribed_uri)
        if "error" in resp:
            return self.fail_check(f"unsubscribe error: {resp['error']}")
        return self.pass_check(f"Unsubscribed from '{self._subscribed_uri}'")

    @check("SUB-003", "Resource update triggers notification", Severity.WARNING)
    async def check_sub_003(self):
        self.skip("No automatic way to trigger resource update (requires server-specific tool)")
