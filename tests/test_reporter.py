from __future__ import annotations

import json
import os

from mcp_probe.reporter import format_report, report_console, report_json
from mcp_probe.types import CheckResult, ProbeReport, Severity, Status, SuiteResult


def _make_report():
    return ProbeReport(
        probe_version="0.1.0",
        spec_version="2025-11-25",
        target="python test.py",
        transport="stdio",
        timestamp="2026-02-15T12:00:00Z",
        duration_ms=1234.5,
        server_info={"name": "test-server", "version": "1.0.0"},
        capabilities={"tools": True, "resources": False},
        suites=[
            SuiteResult(name="lifecycle", checks=[
                CheckResult("INIT-001", "Server responds", Status.PASS, Severity.CRITICAL, 45.0),
            ]),
            SuiteResult(name="tools", checks=[
                CheckResult("TOOL-001", "List tools", Status.PASS, Severity.CRITICAL, 30.0),
                CheckResult("TOOL-003", "Schema check", Status.FAIL, Severity.ERROR, 15.0, "invalid"),
                CheckResult("EDGE-001", "Empty params", Status.WARN, Severity.WARNING, 5.0, "slow"),
            ]),
        ],
    )


def test_console_no_color():
    report = _make_report()
    output = report_console(report, color=False)
    assert "mcp-probe v0.1.0" in output
    assert "Target: python test.py" in output
    assert "Transport: stdio" in output
    assert "INIT-001" in output
    assert "TOOL-003" in output
    assert "→ invalid" in output
    assert "→ slow" in output
    assert "2 passed" in output
    assert "1 failed" in output
    assert "1 warnings" in output


def test_console_verbose():
    report = _make_report()
    output = report_console(report, color=False, verbose=True)
    assert "→ invalid" in output
    assert "→ slow" in output


def test_console_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    report = _make_report()
    output = report_console(report, color=True)
    assert "\033[" not in output


def test_json_report():
    report = _make_report()
    output = report_json(report)
    data = json.loads(output)
    assert data["mcp_probe_version"] == "0.1.0"
    assert data["spec_version"] == "2025-11-25"
    assert data["target"] == "python test.py"
    assert data["transport"] == "stdio"
    assert data["timestamp"] == "2026-02-15T12:00:00Z"
    assert data["duration_ms"] == 1234.5
    assert data["server_info"]["name"] == "test-server"
    assert data["capabilities"]["tools"] is True
    assert data["capabilities"]["resources"] is False
    assert data["summary"]["total"] == 4
    assert data["summary"]["passed"] == 2
    assert data["summary"]["failed"] == 1
    assert data["summary"]["warnings"] == 1
    assert len(data["suites"]) == 2
    assert data["suites"][0]["checks"][0]["id"] == "INIT-001"


def test_json_null_server_info():
    report = ProbeReport(
        probe_version="0.1.0",
        spec_version="2025-11-25",
        target="test",
        transport="stdio",
        timestamp="2026-02-15T12:00:00Z",
        duration_ms=100,
        server_info=None,
        capabilities={},
        suites=[],
    )
    data = json.loads(report_json(report))
    assert data["server_info"] is None


def test_format_report_router():
    report = _make_report()
    json_out = format_report(report, "json")
    data = json.loads(json_out)
    assert "suites" in data

    console_out = format_report(report, "console", color=False)
    assert "mcp-probe" in console_out


def test_summary_counts():
    report = _make_report()
    s = report.summary
    assert s["total"] == 4
    assert s["passed"] == 2
    assert s["failed"] == 1
    assert s["warnings"] == 1
    assert s["skipped"] == 0
    assert s["info"] == 0
