from __future__ import annotations

import json
import shlex
import sys
import xml.etree.ElementTree as ET

import pytest

from mcp_probe.cli import _build_parser, _headers, _write_output, main
from mcp_probe.reporter import format_report, redact_report
from mcp_probe.types import CheckResult, ProbeReport, Severity, Status, SuiteResult
from tests.conftest import MOCK_MINIMAL, MOCK_VALID


def run_cli(capsys, *args):
    with pytest.raises(SystemExit) as exit_info:
        main(list(args))
    output = capsys.readouterr()
    return exit_info.value.code, output


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["python server.py", "--url", "https://example.test"],
        ["python server.py", "--transport", "http"],
        ["python server.py", "--timeout", "nan"],
        ["python server.py", "--timeout", "0"],
        ["python server.py", "--run-timeout", "inf"],
        ["python server.py", "--max-pages", "0"],
        ["python server.py", "--suite", "tools,,edge"],
        ["python server.py", "--tool", "echo", "--suite", "lifecycle"],
        ["python server.py", "--header", "Authorization: secret"],
        ["--url", "https://example.test", "--cwd", "."],
        ["--url", "https://example.test", "-H", "Mcp-Method: ping"],
    ],
)
def test_invalid_options_fail_before_starting_a_server(capsys, args):
    code, output = run_cli(capsys, *args)
    assert code == 2 and output.err
    assert "Traceback" not in output.err


def test_catalog_needs_no_target(capsys):
    code, output = run_cli(capsys, "--list-checks")
    catalog = json.loads(output.out)
    assert code == 0 and len(catalog) >= 50
    assert len({c["id"] for c in catalog}) == len(catalog)


def test_discovery_skips_calls_and_selected_mode_executes_exact_tools(capsys):
    command = shlex.join([sys.executable, MOCK_VALID])
    code, output = run_cli(capsys, command, "--format", "json")
    report = json.loads(output.out)
    checks = {c["id"]: c for s in report["suites"] for c in s["checks"]}
    assert code == report["exit_code"] == 0
    assert report["mode"] == "discovery"
    assert checks["TOOL-004"]["status"] == "SKIP"
    assert checks["RES-003"]["status"] == "SKIP"
    code, output = run_cli(capsys, command, "--tool", "echo", "--format", "json")
    report = json.loads(output.out)
    checks = {c["id"]: c for s in report["suites"] for c in s["checks"]}
    assert code == 0 and report["mode"] == "selected-tools"
    assert checks["TOOL-004"]["status"] == "PASS"
    assert checks["TOOL-005"]["status"] == "SKIP"


def test_selected_missing_tool_is_not_silently_skipped(capsys):
    code, output = run_cli(capsys, shlex.join([sys.executable, MOCK_MINIMAL]), "--tool", "missing", "--format", "json")
    assert code == 1
    assert json.loads(output.out)["summary"]["failed"] >= 1


def test_json_cases_select_tools_and_report_can_be_written(capsys, tmp_path):
    cases = tmp_path / "cases.json"
    cases.write_text('{"echo":{"message":"hello"}}')
    report_file = tmp_path / "report.json"
    code, output = run_cli(
        capsys,
        shlex.join([sys.executable, MOCK_VALID]),
        "--cases",
        str(cases),
        "--format",
        "json",
        "--output",
        str(report_file),
    )
    assert code == 0 and not output.out
    assert json.loads(report_file.read_text())["mode"] == "selected-tools"


@pytest.mark.parametrize("contents", ["[]", "{}", '{"echo":[]}', '{"echo":{"x":NaN}}', "{"])
def test_bad_cases(capsys, tmp_path, contents):
    cases = tmp_path / "cases.json"
    cases.write_text(contents)
    assert run_cli(capsys, "not-started", "--cases", str(cases))[0] == 2


def test_environment_headers_and_duplicate_rejection(monkeypatch):
    monkeypatch.setenv("PROBE_TEST_TOKEN", "sensitive")
    args = _build_parser().parse_args(["--url", "https://example.test", "--bearer-token-env", "PROBE_TEST_TOKEN"])
    assert _headers(args) == {"authorization": "Bearer sensitive"}
    args.header = ["AUTHORIZATION: duplicate"]
    with pytest.raises(ValueError, match="Duplicate"):
        _headers(args)


def test_failed_atomic_write_keeps_existing_report(monkeypatch, tmp_path):
    destination = tmp_path / "report.json"
    destination.write_text("previous report")

    def failed_replace(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr("mcp_probe.cli.os.replace", failed_replace)
    with pytest.raises(OSError):
        _write_output("new report", str(destination))
    assert destination.read_text() == "previous report"
    assert list(tmp_path.iterdir()) == [destination]


def test_junit_matches_exit_semantics_and_redacts_credentials():
    report = ProbeReport(
        "test",
        "2025-11-25",
        "test",
        "http",
        "now",
        10,
        {"name": "secret\x1b"},
        {},
        [
            SuiteResult(
                "suite",
                [
                    CheckResult("ONE", "failure", Status.FAIL, Severity.ERROR, 1, "Bearer abc secret\x00"),
                    CheckResult("TWO", "warning", Status.WARN, Severity.WARNING, 1, "warn"),
                    CheckResult("THREE", "transport", Status.FAIL, Severity.CRITICAL, 1, "disconnected", "transport"),
                    CheckResult("FOUR", "skip", Status.SKIP, Severity.INFO, 0, "not exercised"),
                ],
            )
        ],
    )
    redact_report(report, ["secret"])
    for fmt in ("json", "junit", "console"):
        output = format_report(report, fmt, strict=True)
        assert "secret" not in output and "abc" not in output and "\x00" not in output and "\x1b" not in output
    xml = ET.fromstring(format_report(report, "junit", strict=True))
    assert xml.attrib["failures"] == "2"
    assert xml.attrib["errors"] == "1"
    assert xml.attrib["skipped"] == "1"
