from __future__ import annotations

import pytest

from mcp_probe.runner import Runner, _VALID_SUITE_NAMES, compute_exit_code
from mcp_probe.types import CheckResult, ProbeReport, Severity, Status, SuiteResult


def test_valid_suite_names():
    expected = {"lifecycle", "tools", "resources", "prompts", "jsonrpc", "notifications", "tasks", "auth", "edge"}
    assert _VALID_SUITE_NAMES == expected


def test_invalid_suite_name_raises():
    with pytest.raises(ValueError, match="Unknown suite"):
        Runner(None, None, suites_to_run=["bogus"])


def test_should_run_all_by_default():
    runner = Runner.__new__(Runner)
    runner._explicitly_requested = set()
    for name in _VALID_SUITE_NAMES:
        assert runner._should_run_suite(name) is True


def test_should_run_filtered():
    runner = Runner.__new__(Runner)
    runner._explicitly_requested = {"tools", "resources"}
    assert runner._should_run_suite("lifecycle") is True
    assert runner._should_run_suite("tools") is True
    assert runner._should_run_suite("resources") is True
    assert runner._should_run_suite("jsonrpc") is False
    assert runner._should_run_suite("edge") is False


def test_exit_code_no_failures():
    report = ProbeReport(
        probe_version="0.1.0", spec_version="2025-11-25",
        target="test", transport="stdio", timestamp="", duration_ms=0,
        server_info=None, capabilities={},
        suites=[SuiteResult(name="lifecycle", checks=[
            CheckResult("INIT-001", "test", Status.PASS, Severity.CRITICAL, 0),
        ])],
    )
    assert compute_exit_code(report) == 0


def test_exit_code_with_critical_failure():
    report = ProbeReport(
        probe_version="0.1.0", spec_version="2025-11-25",
        target="test", transport="stdio", timestamp="", duration_ms=0,
        server_info=None, capabilities={},
        suites=[SuiteResult(name="lifecycle", checks=[
            CheckResult("INIT-001", "test", Status.FAIL, Severity.CRITICAL, 0),
        ])],
    )
    assert compute_exit_code(report) == 1


def test_exit_code_strict_mode():
    report = ProbeReport(
        probe_version="0.1.0", spec_version="2025-11-25",
        target="test", transport="stdio", timestamp="", duration_ms=0,
        server_info=None, capabilities={},
        suites=[SuiteResult(name="edge", checks=[
            CheckResult("EDGE-001", "test", Status.WARN, Severity.WARNING, 0),
        ])],
    )
    assert compute_exit_code(report, strict=False) == 0
    assert compute_exit_code(report, strict=True) == 1


def test_exit_code_info_fail_ignored():
    report = ProbeReport(
        probe_version="0.1.0", spec_version="2025-11-25",
        target="test", transport="stdio", timestamp="", duration_ms=0,
        server_info=None, capabilities={},
        suites=[SuiteResult(name="auth", checks=[
            CheckResult("AUTH-001", "test", Status.FAIL, Severity.INFO, 0),
        ])],
    )
    assert compute_exit_code(report) == 0
