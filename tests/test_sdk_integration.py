"""Run against an independently installed official SDK, never a mock transport."""

from __future__ import annotations

import json
import os
import pathlib
import socket
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SDK_PYTHON = os.environ.get("MCP_PROBE_SDK_PYTHON")
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not SDK_PYTHON, reason="Set MCP_PROBE_SDK_PYTHON")]


@pytest.mark.parametrize("version", ["2025-11-25", "2026-07-28"])
@pytest.mark.parametrize("transport", ["stdio", "http-json", "http-sse"])
def test_official_sdk(version, transport, tmp_path):
    server_args = [str(SDK_PYTHON), str(ROOT / "examples/server.py")]
    server = None
    with (tmp_path / "server.log").open("w+") as log:
        try:
            if transport == "stdio":
                import shlex

                target = [shlex.join(server_args)]
            else:
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    port = listener.getsockname()[1]
                server_args += ["--port", str(port)]
                if transport == "http-json":
                    server_args.append("--json")
                server = subprocess.Popen(server_args, stdout=log, stderr=log, cwd=ROOT)
                deadline = time.monotonic() + 15
                while True:
                    assert server.poll() is None, "SDK server failed to start"
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        assert time.monotonic() < deadline, "SDK server startup deadline exceeded"
                        time.sleep(0.05)
                target = ["--url", f"http://127.0.0.1:{port}/mcp"]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mcp_probe",
                    *target,
                    "--active",
                    "--cases",
                    str(ROOT / "examples/cases.json"),
                    "--protocol-version",
                    version,
                    "--format",
                    "json",
                    "--timeout",
                    "8",
                    "--run-timeout",
                    "50",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=ROOT,
            )
            assert result.stdout, result.stderr
            report = json.loads(result.stdout)
            problems = [c for s in report["suites"] for c in s["checks"] if c["status"] in ("FAIL", "WARN")]
            assert result.returncode == 0, (problems, result.stderr)
            assert report["summary"]["failed"] == 0, report
            assert not report["incomplete"]
            checks = {c["id"]: c for s in report["suites"] for c in s["checks"]}
            assert checks["TOOL-004"]["status"] == "PASS"
            assert checks["RES-003"]["status"] == "PASS"
            assert checks["PROMPT-003"]["status"] == "PASS"
        finally:
            if server is not None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
