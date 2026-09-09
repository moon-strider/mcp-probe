from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from mcp_probe import __version__
from mcp_probe.client import MCPClient
from mcp_probe.protocol import MAX_PAGES, SUPPORTED_VERSIONS
from mcp_probe.reporter import format_report, redact_report
from mcp_probe.runner import _VALID_SUITE_NAMES, Runner, compute_exit_code
from mcp_probe.transport.http import HttpTransport
from mcp_probe.transport.stdio import StdioTransport


def _positive_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return result


def _positive_int(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def _parse_header(raw: str) -> tuple[str, str]:
    if ":" not in raw:
        raise argparse.ArgumentTypeError("Header must use 'Name: Value'")
    name, value = (part.strip() for part in raw.split(":", 1))
    if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise argparse.ArgumentTypeError("Invalid HTTP header name or value")
    if name.lower() in {
        "host",
        "content-length",
        "content-type",
        "accept",
        "mcp-session-id",
        "mcp-protocol-version",
        "mcp-method",
        "mcp-name",
    }:
        raise argparse.ArgumentTypeError("Transport-owned headers cannot be overridden")
    return name, value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-probe", description="Bounded MCP server checks over stdio and Streamable HTTP"
    )
    parser.add_argument("-V", "--version", action="version", version=f"mcp-probe {__version__}")
    parser.add_argument("command", nargs="?", help="Quoted program and arguments, executed without a shell")
    parser.add_argument("--url", help="MCP Streamable HTTP endpoint")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], help="Optional consistency check for the chosen target"
    )
    parser.add_argument("--cwd", help="Working directory for the stdio server")
    parser.add_argument(
        "--protocol-version",
        choices=SUPPORTED_VERSIONS,
        default=SUPPORTED_VERSIONS[0],
        help="Protocol revision to test (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout", type=_positive_float, default=10.0, help="Total deadline per check, seconds (default: %(default)s)"
    )
    parser.add_argument(
        "--run-timeout",
        type=_positive_float,
        default=120.0,
        help="Total suite run deadline, seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--max-pages", type=_positive_int, default=MAX_PAGES, help="Maximum pages per listing (default: %(default)s)"
    )
    parser.add_argument("--suite", help="Comma-separated suites: " + ", ".join(sorted(_VALID_SUITE_NAMES)))
    parser.add_argument(
        "--list-checks", action="store_true", help="Print the check catalog without contacting a server"
    )
    parser.add_argument(
        "--active", action="store_true", help="Enable negative probes, content reads and selected task execution"
    )
    parser.add_argument(
        "--tool", action="append", default=[], help="Permit this exact tool name to be called; repeatable"
    )
    parser.add_argument("--cases", help="JSON file mapping selected tool names to explicit argument objects")
    parser.add_argument(
        "--check-auth", action="store_true", help="Inspect unauthenticated HTTP responses and OAuth metadata"
    )
    parser.add_argument("--bearer-token-env", help="Read a Bearer token from this environment variable")
    parser.add_argument("-H", "--header", action="append", default=[], help="Custom HTTP header as 'Name: Value'")
    parser.add_argument("--header-env", action="append", default=[], help="Read a header value as 'Name=ENV_VAR'")
    parser.add_argument("--format", choices=["console", "json", "junit"], default="console", dest="fmt")
    parser.add_argument("--output", help="Atomically write a report to this file")
    parser.add_argument("--strict", action="store_true", help="Warnings also fail the run")
    parser.add_argument("-v", "--verbose", action="store_true", help="Include check details in console reports")
    parser.add_argument("--no-color", action="store_true")
    return parser


def check_catalog() -> list[dict]:
    from mcp_probe.suites.auth import AuthSuite
    from mcp_probe.suites.edge_cases import EdgeCasesSuite
    from mcp_probe.suites.jsonrpc import JsonRpcSuite
    from mcp_probe.suites.lifecycle import LifecycleSuite
    from mcp_probe.suites.notifications import NotificationsSuite
    from mcp_probe.suites.prompts import PromptsSuite
    from mcp_probe.suites.resources import ResourcesSuite
    from mcp_probe.suites.tasks import TasksSuite
    from mcp_probe.suites.tools import ToolsSuite

    dummy = MCPClient(StdioTransport(["catalog-only"]))
    instances = [
        LifecycleSuite(dummy, lambda: StdioTransport(["catalog-only"])),
        JsonRpcSuite(None),
        ToolsSuite(None),
        ResourcesSuite(None),
        PromptsSuite(None),
        NotificationsSuite(dummy),
        TasksSuite(None),
        AuthSuite(""),
        EdgeCasesSuite(None),
    ]
    return [
        {
            "suite": suite.name,
            "id": meta["check_id"],
            "description": meta["description"],
            "severity": meta["severity"].value,
        }
        for suite in instances
        for meta, _ in suite._get_checks()
    ]


def _cases(path: str | None) -> dict[str, dict]:
    if path is None:
        return {}
    file = Path(path)
    if file.stat().st_size > 65536:
        raise ValueError("Case file exceeds 64 KiB")
    try:
        value = json.loads(file.read_text(encoding="utf-8"))
        json.dumps(value, allow_nan=False)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Case file must contain valid finite JSON") from exc
    if (
        not isinstance(value, dict)
        or not value
        or not all(isinstance(k, str) and k and isinstance(v, dict) for k, v in value.items())
    ):
        raise ValueError("Case file must map nonempty tool names to argument objects")
    return value


def _headers(args: argparse.Namespace) -> dict[str, str]:
    raw = list(args.header)
    for item in args.header_env:
        name, sep, variable = item.partition("=")
        if not sep or not variable or variable not in os.environ:
            raise ValueError("Header environment variable is missing")
        raw.append(f"{name}: {os.environ[variable]}")
    if args.bearer_token_env:
        value = os.environ.get(args.bearer_token_env)
        if not value:
            raise ValueError("Bearer token environment variable is empty or missing")
        raw.append(f"Authorization: Bearer {value}")
    result: dict[str, str] = {}
    for item in raw:
        name, value = _parse_header(item)
        if name.lower() in result:
            raise ValueError("Duplicate HTTP header")
        result[name.lower()] = value
    return result


def _write_output(output: str, path: str | None) -> None:
    if path is None:
        print(output)
        return
    destination = Path(path)
    name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as file:
            name = file.name
            file.write(output + "\n")
        os.replace(name, destination)
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


async def _run(args: argparse.Namespace) -> int:
    if bool(args.command) == bool(args.url):
        raise ValueError("Specify exactly one command or --url")
    transport_name = "stdio" if args.command else "http"
    if args.transport and args.transport != transport_name:
        raise ValueError("Transport does not match the target")
    if (args.check_auth or args.header or args.header_env or args.bearer_token_env) and not args.url:
        raise ValueError("Authentication and HTTP headers require --url")
    if args.cwd and not args.command:
        raise ValueError("--cwd requires a stdio command")
    suites = [s.strip() for s in args.suite.split(",")] if args.suite else None
    if suites is not None and (not all(suites) or set(suites) - _VALID_SUITE_NAMES):
        raise ValueError("Unknown or empty suite name")
    if suites and "auth" in suites and not args.url:
        raise ValueError("Auth suite requires --url")
    if suites and "tasks" in suites and args.protocol_version != SUPPORTED_VERSIONS[0]:
        raise ValueError("Tasks suite targets the legacy core protocol only")
    cases = _cases(args.cases)
    selected = set(args.tool) | set(cases)
    if any(not name for name in selected):
        raise ValueError("Tool names cannot be empty")
    if selected and suites and not ({"tools", "tasks"} & set(suites)):
        raise ValueError("Selected tools require the tools or tasks suite")
    headers = _headers(args)
    if args.command:
        command = shlex.split(args.command)
        if not command:
            raise ValueError("Server command is empty")

        def factory():
            return StdioTransport(command, cwd=args.cwd)

        target = "stdio: " + Path(command[0]).name
    else:

        def factory():
            return HttpTransport(args.url, headers=headers, timeout=args.timeout)

        parts = urlsplit(args.url)
        target = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    transport = factory()
    client = MCPClient(
        transport,
        args.timeout,
        protocol_version=args.protocol_version,
        active=args.active,
        allowed_tools=selected,
        tool_cases=cases,
        max_pages=args.max_pages,
    )
    runner = Runner(
        client,
        factory,
        suites_to_run=suites,
        timeout=args.timeout,
        server_url=args.url,
        check_auth=args.check_auth or bool(suites and "auth" in suites),
        target=target,
        transport_name=transport_name,
        run_timeout=args.run_timeout,
    )
    async with transport:
        report = await runner.run()
    secrets = [v for v in headers.values() if v]
    if args.bearer_token_env:
        secrets.append(os.environ[args.bearer_token_env])
    redact_report(report, secrets)
    output = format_report(report, fmt=args.fmt, verbose=args.verbose, color=not args.no_color, strict=args.strict)
    _write_output(output, args.output)
    return compute_exit_code(report, strict=args.strict)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    # Debug logs from HTTP libraries can contain URLs and headers; reports are
    # the supported diagnostic surface, including in verbose mode.
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    try:
        if args.list_checks:
            _write_output(json.dumps(check_catalog(), indent=2), args.output)
            raise SystemExit(0)
        code = asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130) from None
    except (ValueError, OSError, argparse.ArgumentTypeError) as exc:
        print(f"mcp-probe: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except Exception as exc:
        print(f"mcp-probe: operation failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(2) from None
    raise SystemExit(code)
