"""Verify fresh base/full wheel installations outside the source checkout."""

from __future__ import annotations

import json
import os
import pathlib
import shlex
import subprocess
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(*args: str, cwd: pathlib.Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True, timeout=120).stdout


def main() -> None:
    wheel = next((ROOT / "dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "mcp_probe/schema_worker.py" in names
        assert not any(n.startswith(("tests/", "examples/", "dist/", ".venv/")) for n in names)
    with tempfile.TemporaryDirectory(prefix="mcp-probe-package-") as directory:
        work = pathlib.Path(directory)
        for extra in ("", "full"):
            environment = work / (extra or "base")
            run("uv", "venv", str(environment), cwd=work)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            requirement = str(wheel) + ("[full]" if extra else "")
            run("uv", "pip", "install", "--python", str(python), requirement, cwd=work)
            version = run(str(python), "-m", "mcp_probe", "--version", cwd=work).strip()
            command = shlex.join([str(python), str(ROOT / "tests/fixtures/mock_server_valid.py")])
            output = run(str(python), "-m", "mcp_probe", command, "--tool", "echo", "--format", "json", cwd=work)
            report = json.loads(output)
            assert report["exit_code"] == 0 and not report["incomplete"]
            check = next(c for s in report["suites"] for c in s["checks"] if c["id"] == "TOOL-003")
            assert check["status"] == ("PASS" if extra else "INFO")
            print(f"{version}: clean {extra or 'base'} installation passed")


if __name__ == "__main__":
    main()
