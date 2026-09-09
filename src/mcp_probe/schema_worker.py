"""Run untrusted JSON Schema work in a cancellable, time-limited subprocess."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from typing import Any, cast

from mcp_probe import schema_utils


class SchemaBudgetError(RuntimeError):
    """Validation was not completed within the probe's resource budget."""


async def _evaluate(operation: str, *args: Any) -> Any:
    payload = json.dumps([operation, args], allow_nan=False).encode()
    if len(payload) > 5 * 1024 * 1024:
        raise SchemaBudgetError("Schema input exceeds the worker byte budget")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "mcp_probe.schema_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        try:
            output, _ = await asyncio.wait_for(process.communicate(payload), 2.0)
        except asyncio.TimeoutError as exc:
            raise SchemaBudgetError("Schema evaluation exceeded its two-second worker deadline") from exc
        if process.returncode or len(output) > 65536:
            raise SchemaBudgetError("Schema worker could not complete validation")
        return json.loads(output)
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


async def schema_error(schema: dict) -> str | None:
    return cast(str | None, await _evaluate("schema_error", schema))


async def matches_schema(value: Any, schema: dict) -> bool | None:
    return cast(bool | None, await _evaluate("matches_schema", value, schema))


async def generate_valid_args(schema: dict) -> dict | None:
    return cast(dict | None, await _evaluate("generate_valid_args", schema))


async def generate_invalid_args(schema: dict) -> dict | None:
    return cast(dict | None, await _evaluate("generate_invalid_args", schema))


def _main() -> None:
    # This process has no network schema resolver. Its parent enforces the wall
    # deadline and reaps it on cancellation, including catastrophic regexes.
    operation, args = json.loads(sys.stdin.buffer.read(5 * 1024 * 1024 + 1))
    functions: dict[str, Callable[..., Any]] = {
        "schema_error": schema_utils.schema_error,
        "matches_schema": schema_utils.matches_schema,
        "generate_valid_args": schema_utils.generate_valid_args,
        "generate_invalid_args": schema_utils.generate_invalid_args,
    }
    result = functions[operation](*args)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    _main()
