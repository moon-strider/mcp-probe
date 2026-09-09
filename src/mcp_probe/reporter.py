from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET

from mcp_probe.runner import compute_exit_code
from mcp_probe.types import ProbeReport, Severity, Status

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

    lines.append(f"mcp-probe v{report.probe_version} — MCP server checks")
    lines.append(f"Target: {report.target}")
    lines.append(f"Transport: {report.transport}")
    lines.append(f"Spec: MCP {report.spec_version}")
    lines.append(f"Mode: {report.mode}")
    if report.incomplete:
        lines.append("Run incomplete: transport failure or deadline exceeded")
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


def report_junit(report: ProbeReport, strict: bool = False) -> str:
    root = ET.Element("testsuites", name="mcp-probe")
    failures = errors = skipped = 0
    for suite in report.suites:
        node = ET.SubElement(root, "testsuite", name=suite.name, tests=str(len(suite.checks)))
        before = (failures, errors, skipped)
        for check in suite.checks:
            case = ET.SubElement(
                node,
                "testcase",
                classname=suite.name,
                name=f"{check.check_id}: {check.description}",
                time=f"{check.duration_ms / 1000:.6f}",
            )
            if check.error_kind == "transport":
                ET.SubElement(case, "error", message=check.details or "Transport failure")
                errors += 1
            elif (check.status is Status.FAIL and check.severity in (Severity.CRITICAL, Severity.ERROR)) or (
                strict and check.status in (Status.FAIL, Status.WARN) and check.severity is not Severity.INFO
            ):
                ET.SubElement(case, "failure", message=check.details or check.status.value)
                failures += 1
            elif check.status is Status.SKIP:
                ET.SubElement(case, "skipped", message=check.details or "Not exercised")
                skipped += 1
            elif check.details:
                ET.SubElement(case, "system-out").text = check.details
        for name, count, previous in zip(("failures", "errors", "skipped"), (failures, errors, skipped), before):
            node.set(name, str(count - previous))
        node.set("time", f"{sum(c.duration_ms for c in suite.checks) / 1000:.6f}")
    root.set("tests", str(report.summary["total"]))
    root.set("failures", str(failures))
    root.set("errors", str(errors))
    root.set("skipped", str(skipped))
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def redact_report(report: ProbeReport, secrets: list[str]) -> None:
    """Strip terminal controls and known credentials from every report surface."""

    def clean(value):
        if isinstance(value, str):
            for secret in sorted(set(secrets), key=len, reverse=True):
                if secret:
                    value = value.replace(secret, "[redacted]")
            value = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [redacted]", value)
            return "".join(
                c
                for c in value
                if (
                    32 <= ord(c) <= 0x10FFFF
                    and not (127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF)
                    and ord(c) not in (0xFFFE, 0xFFFF)
                )
                or c in "\n\t"
            )[:4096]
        if isinstance(value, dict):
            return {clean(str(k)): clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    report.target = clean(report.target)
    report.server_info = clean(report.server_info)
    report.capabilities = clean(report.capabilities)
    for suite in report.suites:
        for check in suite.checks:
            check.details = clean(check.details)


def format_report(
    report: ProbeReport, fmt: str = "console", verbose: bool = False, color: bool = True, strict: bool = False
) -> str:
    if fmt == "json":
        payload = report.to_dict()
        payload["exit_code"] = compute_exit_code(report, strict)
        return json.dumps(payload, indent=2, ensure_ascii=False)
    if fmt == "junit":
        return report_junit(report, strict)
    if fmt != "console":
        raise ValueError("Unsupported report format")
    return report_console(report, color=color, verbose=verbose)
