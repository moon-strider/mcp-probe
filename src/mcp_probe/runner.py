from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from mcp_probe.client import MCPClient
from mcp_probe.transport.base import BaseTransport
from mcp_probe.types import PROBE_VERSION, SPEC_VERSION, ProbeReport, Severity, Status

logger = logging.getLogger(__name__)

_VALID_SUITE_NAMES = frozenset(
    {
        "lifecycle",
        "tools",
        "resources",
        "prompts",
        "jsonrpc",
        "notifications",
        "tasks",
        "auth",
        "edge",
    }
)

_SUITE_ORDER = [
    "auth",
    "lifecycle",
    "jsonrpc",
    "tools",
    "resources",
    "prompts",
    "notifications",
    "tasks",
    "edge",
]


class AbortRunError(Exception):
    pass


class Runner:
    def __init__(
        self,
        client: MCPClient,
        transport_factory: Callable[[], BaseTransport],
        suites_to_run: list[str] | None = None,
        timeout: float = 30.0,
        server_url: str | None = None,
        oauth_enabled: bool = False,
        target: str = "",
        transport_name: str = "stdio",
    ) -> None:
        self._client = client
        self._transport_factory = transport_factory
        self._timeout = timeout
        self._server_url = server_url
        self._oauth_enabled = oauth_enabled
        self._target = target
        self._transport_name = transport_name
        self._explicitly_requested: set[str] = set()

        if suites_to_run is not None:
            for name in suites_to_run:
                if name not in _VALID_SUITE_NAMES:
                    raise ValueError(
                        f"Unknown suite '{name}'. " f"Valid suites: {', '.join(sorted(_VALID_SUITE_NAMES))}"
                    )
            self._explicitly_requested = set(suites_to_run)

        self._tools: list[dict] = []
        self._resources: list[dict] = []

    def _should_run_suite(self, name: str) -> bool:
        if self._explicitly_requested:
            if name == "lifecycle":
                return True
            return name in self._explicitly_requested
        return True

    def _is_http(self) -> bool:
        return self._transport_name in ("http", "sse")

    async def run(self) -> ProbeReport:
        start = time.perf_counter()
        report = ProbeReport(
            probe_version=PROBE_VERSION,
            spec_version=SPEC_VERSION,
            target=self._target,
            transport=self._transport_name,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            duration_ms=0,
            server_info=self._client.server_info,
            capabilities={},
            suites=[],
        )

        try:
            await self._run_auth(report)
            await self._run_lifecycle(report)
            caps = self._client.capabilities
            report.capabilities = {
                "tools": "tools" in caps,
                "resources": "resources" in caps,
                "prompts": "prompts" in caps,
                "tasks": "tasks" in caps,
            }
            report.server_info = self._client.server_info

            has_tools = "tools" in caps
            has_resources = "resources" in caps
            has_prompts = "prompts" in caps
            has_tasks = "tasks" in caps
            has_subscribe = isinstance(caps.get("resources"), dict) and caps["resources"].get("subscribe", False)

            await self._run_jsonrpc(report)
            await self._run_tools(report, has_tools)
            await self._run_resources(report, has_resources)
            await self._run_prompts(report, has_prompts)
            await self._run_notifications(report, has_subscribe)
            await self._run_tasks(report, has_tasks)
            await self._run_edge(report)

        except AbortRunError:
            logger.info("Run aborted due to critical failure")

        report.duration_ms = (time.perf_counter() - start) * 1000
        return report

    async def _run_auth(self, report: ProbeReport) -> None:
        if not self._should_run_suite("auth"):
            return
        if not self._is_http() or not self._oauth_enabled or not self._server_url:
            return

        from mcp_probe.suites.auth import AuthSuite

        suite = AuthSuite(self._server_url, timeout=self._timeout)
        result = await suite.run()
        report.suites.append(result)

    async def _run_lifecycle(self, report: ProbeReport) -> None:
        from mcp_probe.suites.lifecycle import LifecycleSuite

        suite = LifecycleSuite(
            self._client,
            self._transport_factory,
            timeout=self._timeout,
        )
        result = await suite.run()
        report.suites.append(result)

        for check in result.checks:
            if check.check_id == "INIT-001" and check.status is Status.FAIL:
                raise AbortRunError("INIT-001 failed — server handshake broken")

    async def _run_jsonrpc(self, report: ProbeReport) -> None:
        if not self._should_run_suite("jsonrpc"):
            return

        from mcp_probe.suites.jsonrpc import JsonRpcSuite

        suite = JsonRpcSuite(self._client, self._timeout)
        result = await suite.run()
        report.suites.append(result)

    async def _run_tools(self, report: ProbeReport, has_capability: bool) -> None:
        if not self._should_run_suite("tools"):
            return
        if not has_capability and "tools" not in self._explicitly_requested:
            return

        from mcp_probe.suites.tools import ToolsSuite

        suite = ToolsSuite(self._client, self._timeout)
        result = await suite.run()
        report.suites.append(result)

        for check in result.checks:
            if check.check_id == "TOOL-001" and check.status is Status.PASS:
                self._tools = getattr(suite, "_tools", [])
                break

    async def _run_resources(self, report: ProbeReport, has_capability: bool) -> None:
        if not self._should_run_suite("resources"):
            return
        if not has_capability and "resources" not in self._explicitly_requested:
            return

        from mcp_probe.suites.resources import ResourcesSuite

        suite = ResourcesSuite(self._client, self._timeout)
        result = await suite.run()
        report.suites.append(result)

        for check in result.checks:
            if check.check_id == "RES-001" and check.status is Status.PASS:
                self._resources = getattr(suite, "_resources", [])
                break

    async def _run_prompts(self, report: ProbeReport, has_capability: bool) -> None:
        if not self._should_run_suite("prompts"):
            return
        if not has_capability and "prompts" not in self._explicitly_requested:
            return

        from mcp_probe.suites.prompts import PromptsSuite

        suite = PromptsSuite(self._client, self._timeout)
        result = await suite.run()
        report.suites.append(result)

    async def _run_notifications(self, report: ProbeReport, has_subscribe: bool) -> None:
        if not self._should_run_suite("notifications"):
            return

        from mcp_probe.suites.notifications import NotificationsSuite

        resources_for_sub = self._resources if has_subscribe else []
        suite = NotificationsSuite(self._client, self._timeout, resources=resources_for_sub)
        result = await suite.run()
        report.suites.append(result)

    async def _run_tasks(self, report: ProbeReport, has_capability: bool) -> None:
        if not self._should_run_suite("tasks"):
            return
        if not has_capability and "tasks" not in self._explicitly_requested:
            return

        from mcp_probe.suites.tasks import TasksSuite

        suite = TasksSuite(self._client, tools=self._tools, timeout=self._timeout)
        result = await suite.run()
        report.suites.append(result)

    async def _run_edge(self, report: ProbeReport) -> None:
        if not self._should_run_suite("edge"):
            return

        from mcp_probe.suites.edge_cases import EdgeCasesSuite

        suite = EdgeCasesSuite(self._client, tools=self._tools, timeout=self._timeout)
        result = await suite.run()
        report.suites.append(result)


def compute_exit_code(report: ProbeReport, strict: bool = False) -> int:
    for suite in report.suites:
        for check in suite.checks:
            if check.status is Status.FAIL:
                if check.severity in (Severity.CRITICAL, Severity.ERROR):
                    return 1
                if strict and check.severity is Severity.WARNING:
                    return 1
            if strict and check.status is Status.WARN:
                if check.severity in (Severity.CRITICAL, Severity.ERROR, Severity.WARNING):
                    return 1
    return 0
