from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from mcp_probe import __version__
from mcp_probe.reporter import format_report
from mcp_probe.runner import Runner, compute_exit_code


def _parse_header(raw: str) -> tuple[str, str]:
    if ":" not in raw:
        raise argparse.ArgumentTypeError(f"Invalid header format (expected 'Name: Value'): {raw}")
    name, value = raw.split(":", 1)
    return name.strip(), value.strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-probe",
        description="CLI validator for Model Context Protocol (MCP) server compliance",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"mcp-probe {__version__}",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help="Shell command to launch MCP server (stdio transport)",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="URL of remote MCP server (HTTP transport)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default=None,
        help="Explicit transport type (default: auto-detect from command/url)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds per check (default: 30)",
    )
    parser.add_argument(
        "--suite",
        default=None,
        help="Comma-separated list of suites to run (default: all)",
    )
    parser.add_argument(
        "--format",
        choices=["console", "json"],
        default="console",
        dest="fmt",
        help="Output format (default: console)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write report to file instead of stdout",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Show details and payloads for all checks",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Treat warnings as failures (exit code 1)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable ANSI colors in console output",
    )
    parser.add_argument(
        "-H", "--header",
        action="append",
        default=[],
        dest="headers",
        help="Custom HTTP header (format: 'Name: Value', repeatable)",
    )
    parser.add_argument(
        "--oauth",
        action="store_true",
        default=False,
        help="Enable OAuth 2.1 flow for HTTP authentication",
    )
    parser.add_argument(
        "--client-id",
        default=None,
        help="OAuth client_id",
    )
    parser.add_argument(
        "--redirect-port",
        type=int,
        default=8765,
        help="Port for OAuth localhost callback (default: 8765)",
    )
    return parser


def _error(msg: str) -> None:
    print(f"mcp-probe: error: {msg}", file=sys.stderr)
    sys.exit(2)


async def _run(args: argparse.Namespace) -> int:
    from mcp_probe.client import MCPClient
    from mcp_probe.transport.base import BaseTransport

    command = args.command
    url = args.url
    timeout = float(args.timeout)

    if command and url:
        _error("Cannot specify both a command and --url")
    if not command and not url:
        _error("Must specify either a command or --url")

    if args.oauth and not url:
        _error("--oauth requires --url (HTTP transport)")

    suites_to_run: list[str] | None = None
    if args.suite:
        suites_to_run = [s.strip() for s in args.suite.split(",") if s.strip()]

    parsed_headers: dict[str, str] = {}
    for h in args.headers:
        try:
            name, value = _parse_header(h)
            parsed_headers[name] = value
        except argparse.ArgumentTypeError as exc:
            _error(str(exc))

    transport_name: str
    transport: BaseTransport

    if command:
        transport_name = "stdio"
        if parsed_headers:
            logging.getLogger("mcp_probe").warning("--header ignored for stdio transport")

        from mcp_probe.transport.stdio import StdioTransport

        transport = StdioTransport(command)

        def transport_factory() -> BaseTransport:
            return StdioTransport(command)

        target = command
    else:
        transport_name = args.transport or "http"
        if transport_name == "sse":
            _error("Legacy SSE transport is not supported. Use --transport http for Streamable HTTP.")

        from mcp_probe.transport.http import HttpTransport

        transport = HttpTransport(url, headers=parsed_headers, timeout=timeout)

        def transport_factory() -> BaseTransport:
            return HttpTransport(url, headers=parsed_headers, timeout=timeout)

        target = url

    await transport.start()
    try:
        client = MCPClient(transport, timeout=timeout)
        runner = Runner(
            client=client,
            transport_factory=transport_factory,
            suites_to_run=suites_to_run,
            timeout=timeout,
            server_url=url,
            oauth_enabled=args.oauth,
            target=target,
            transport_name=transport_name,
        )
        report = await runner.run()
    finally:
        await transport.stop()

    output = format_report(
        report,
        fmt=args.fmt,
        verbose=args.verbose,
        color=not args.no_color,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
            f.write("\n")
    else:
        print(output)

    return compute_exit_code(report, strict=args.strict)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command and not args.url:
        parser.print_help()
        sys.exit(2)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(name)s: %(message)s",
    )

    try:
        exit_code = asyncio.run(_run(args))
    except ValueError as exc:
        _error(str(exc))
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        logging.getLogger("mcp_probe").debug("Unexpected error", exc_info=True)
        _error(f"Unexpected error: {exc}")

    sys.exit(exit_code)
