from __future__ import annotations

import json
import subprocess
import sys
import tempfile

import pytest

from tests.conftest import MOCK_BROKEN, MOCK_MINIMAL, MOCK_VALID


def _run_probe(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mcp_probe", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestValidServer:
    def test_exit_code_0(self):
        r = _run_probe(f"{sys.executable} {MOCK_VALID}")
        assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"

    def test_stdout_contains_passed(self):
        r = _run_probe(f"{sys.executable} {MOCK_VALID}")
        assert "passed" in r.stdout.lower()


class TestBrokenServer:
    def test_exit_code_1(self):
        r = _run_probe(f"{sys.executable} {MOCK_BROKEN}")
        assert r.returncode == 1, f"stdout={r.stdout}\nstderr={r.stderr}"

    def test_stdout_contains_failed(self):
        r = _run_probe(f"{sys.executable} {MOCK_BROKEN}")
        assert "failed" in r.stdout.lower()


class TestJsonOutput:
    def test_valid_json(self):
        r = _run_probe(f"{sys.executable} {MOCK_VALID}", "--format", "json")
        data = json.loads(r.stdout)
        assert "mcp_probe_version" in data
        assert "suites" in data
        assert "summary" in data
        assert isinstance(data["suites"], list)
        assert data["summary"]["total"] > 0


class TestSuiteFilter:
    def test_only_lifecycle(self):
        r = _run_probe(f"{sys.executable} {MOCK_VALID}", "--suite", "lifecycle", "--format", "json")
        data = json.loads(r.stdout)
        suite_names = [s["name"] for s in data["suites"]]
        assert "lifecycle" in suite_names
        assert len(suite_names) == 1


class TestStrictMode:
    def test_strict_elevates_warnings(self):
        r_normal = _run_probe(f"{sys.executable} {MOCK_VALID}")
        r_strict = _run_probe(f"{sys.executable} {MOCK_VALID}", "--strict")
        assert r_normal.returncode == 0


class TestOutputFile:
    def test_output_to_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        r = _run_probe(
            f"{sys.executable} {MOCK_VALID}",
            "--format", "json",
            "--output", path,
        )
        assert r.returncode == 0
        with open(path) as f:
            data = json.loads(f.read())
        assert "suites" in data


class TestInvalidArgs:
    def test_no_args(self):
        r = _run_probe()
        assert r.returncode == 2

    def test_command_and_url(self):
        r = _run_probe("python test.py", "--url", "http://localhost:8080")
        assert r.returncode == 2

    def test_invalid_suite(self):
        r = _run_probe(f"{sys.executable} {MOCK_VALID}", "--suite", "nonexistent")
        assert r.returncode == 2


class TestMinimalServer:
    def test_exit_code_0(self):
        r = _run_probe(f"{sys.executable} {MOCK_MINIMAL}")
        assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"

    def test_has_skipped(self):
        r = _run_probe(f"{sys.executable} {MOCK_MINIMAL}", "--format", "json")
        data = json.loads(r.stdout)
        assert data["summary"]["skipped"] >= 0
