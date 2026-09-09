"""Small offline MCP server for trying the probe with the official Python SDK."""

from __future__ import annotations

import argparse

from mcp.server import MCPServer

server = MCPServer("probe-demo", version="1.0.0")


@server.tool()
def add(a: int, b: int) -> dict[str, int]:
    """Add two integers without external services or side effects."""
    return {"sum": a + b}


@server.tool()
def echo(text: str) -> str:
    """Return the supplied text."""
    return text


@server.resource("demo://welcome")
def welcome() -> str:
    """Read a static greeting."""
    return "Welcome to mcp-probe."


@server.prompt()
def greet(name: str = "world") -> str:
    """Create a greeting prompt."""
    return f"Say hello to {name}."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, help="Serve Streamable HTTP on loopback instead of stdio")
    parser.add_argument("--json", action="store_true", help="Use JSON HTTP responses instead of SSE")
    args = parser.parse_args()
    if args.port:
        server.run("streamable-http", host="127.0.0.1", port=args.port, json_response=args.json)
    else:
        server.run()


if __name__ == "__main__":
    main()
