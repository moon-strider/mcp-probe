from __future__ import annotations

import json
import os
import sys

from mcp_probe.types import PROBE_VERSION, SPEC_VERSION, ProbeReport, Status

_SEPARATOR = "─" * 60

_ANSI = {
    Status.PASS: "\033[32m",
    Status.FAIL: "\033[31m",
    Status.WARN: "\033[33m",
    Status.SKIP: "\033[90m",
    Status.INFO: "\033[34m",
}
_RESET = "\033[0m"

_SUITE_TITLES: dict[str, str] = {
    "lifecycle": "Lifecycle & Handshake",
    "jsonrpc": "JSON-RPC Protocol",
    "tools": "Tools",
    "resources": "Resources",
    "prompts": "Prompts",
    "notifications": "Notifications & Subscriptions",
    "tasks": "Tasks",
    "auth": "Authentication (OAuth)",
    "edge_cases": "Edge Cases",
}


def _colorize(text: str, status: Status, color: bool) -> str:
    if not color:
        return text
    code = _ANSI.get(status, "")
    if not code:
        return text
    return f"{code}{text}{_RESET}"


def _resolve_color(color: bool) -> bool:
    if not color:
        return False
    if "NO_COLOR" in os.environ:
        return False
    if not sys.stdout.isatty():
        return False
    return True


def report_console(report: ProbeReport, color: bool = True, verbose: bool = False) -> str:
    color = _resolve_color(color)
    lines: list[str] = []

    lines.append(f"mcp-probe v{PROBE_VERSION} — MCP Server Protocol Compliance Validator")
    lines.append(f"Target: {report.target}")
    lines.append(f"Transport: {report.transport}")
    lines.append(f"Spec: MCP {SPEC_VERSION}")
    lines.append("")

    for suite_result in report.suites:
        title = _SUITE_TITLES.get(suite_result.name, suite_result.name)
        lines.append(_SEPARATOR)
        lines.append(f" {title}")
        lines.append(_SEPARATOR)

        for check in suite_result.checks:
            status_str = _colorize(f"{check.status.value:5s}", check.status, color)
            duration_str = f"{check.duration_ms:.0f}ms"
            lines.append(f" {status_str}  {check.check_id:10s} {check.description:40s} {duration_str}")

            if check.details and (verbose or check.status in (Status.FAIL, Status.WARN)):
                lines.append(f"       → {check.details}")

        lines.append("")

    summary = report.summary
    lines.append(_SEPARATOR)

    parts: list[str] = []
    if summary["passed"]:
        parts.append(_colorize(f"{summary['passed']} passed", Status.PASS, color))
    if summary["failed"]:
        parts.append(_colorize(f"{summary['failed']} failed", Status.FAIL, color))
    if summary["warnings"]:
        parts.append(_colorize(f"{summary['warnings']} warnings", Status.WARN, color))
    if summary["skipped"]:
        parts.append(_colorize(f"{summary['skipped']} skipped", Status.SKIP, color))

    lines.append(f" Summary: {', '.join(parts)}")

    total_seconds = report.duration_ms / 1000
    lines.append(f" Duration: {total_seconds:.1f}s")

    return "\n".join(lines)


def report_json(report: ProbeReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def format_report(report: ProbeReport, fmt: str = "console", verbose: bool = False, color: bool = True) -> str:
    if fmt == "json":
        return report_json(report)
    return report_console(report, color=color, verbose=verbose)
