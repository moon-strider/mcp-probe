from __future__ import annotations

import asyncio
import time

import pytest

from mcp_probe.schema_worker import SchemaBudgetError, matches_schema


async def test_worker_checks_local_references_without_network():
    schema = {"$defs": {"n": {"type": "integer"}}, "$ref": "#/$defs/n"}
    assert await matches_schema(3, schema) is True
    assert await matches_schema("three", schema) is False
    assert await matches_schema({}, {"$ref": "https://not-contacted.invalid/schema"}) is None


async def test_pathological_regex_does_not_block_event_loop():
    schema = {"type": "string", "pattern": "^(a+)+$"}
    started = time.monotonic()
    task = asyncio.create_task(matches_schema("a" * 100 + "!", schema))
    await asyncio.sleep(0.05)
    assert not task.done()
    with pytest.raises(SchemaBudgetError, match="deadline"):
        await task
    assert time.monotonic() - started < 4


async def test_cancellation_reaps_worker(monkeypatch):
    import mcp_probe.schema_worker as worker

    original = asyncio.create_subprocess_exec
    spawned = []

    async def create(*args, **kwargs):
        process = await original(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(worker.asyncio, "create_subprocess_exec", create)
    task = asyncio.create_task(matches_schema("a" * 100 + "!", {"pattern": "^(a+)+$"}))
    while not spawned:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert spawned[0].returncode is not None
