from __future__ import annotations

import argparse
import sys

from mcp_probe import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-probe",
        description="CLI validator for Model Context Protocol (MCP) server compliance",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"mcp-probe {__version__}",
    )
    parser.parse_args(argv)

    print(f"mcp-probe v{__version__}")
    sys.exit(0)
