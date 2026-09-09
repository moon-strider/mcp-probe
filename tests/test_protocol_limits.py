from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from mcp_probe.client import MCPClient
from mcp_probe.protocol import MODERN_VERSION, ProtocolError, loads_message, validate_content, validate_tool_result
from mcp_probe.runner import Runner, compute_exit_code
from mcp_probe.suites.notifications import NotificationsSuite
from mcp_probe.types import Status


@pytest.mark.parametrize(
    "item",
    [
        {"type": "image", "mimeType": "image/png", "data": "aGk="},
        {"type": "audio", "mimeType": "audio/wav", "data": "aGk="},
        {"type": "resource_link", "name": "x", "uri": "demo://x"},
        {"type": "resource", "resource": {"uri": "demo://x", "blob": "aGk="}},
    ],
)
def test_supported_content_variants(item):
    validate_content(item)


@pytest.mark.parametrize(
    "item",
    [
        None,
        [],
        {"type": "unknown"},
        {"type": "image", "data": "not base64"},
        {"type": "audio", "mimeType": "audio/wav", "data": "!"},
        {"type": "resource_link", "uri": "demo://x"},
        {"type": "resource", "resource": {"uri": "demo://x", "blob": 7}},
    ],
)
def test_malformed_content_variants(item):
    with pytest.raises(ProtocolError):
        validate_content(item)


def test_structured_content_rules_are_revision_specific():
    result = {"content": [], "structuredContent": [1, 2]}
    validate_tool_result(result, modern=True)
    with pytest.raises(ProtocolError):
        validate_tool_result(result)


@pytest.mark.parametrize("raw", [b"NaN", b"[]", b"null", b'{"x":Infinity}', b"\xff", b'{"x":' + b"[" * 2000])
def test_invalid_finite_json(raw):
    with pytest.raises(ProtocolError):
        loads_message(raw)


@pytest.mark.parametrize(
    "override", [{"ttlMs": -1}, {"cacheScope": "wrong"}, {"supportedVersions": []}, {"_meta": []}, {"capabilities": []}]
)
async def test_discovery_metadata_is_validated(override):
    transport = AsyncMock()
    transport.receive.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "resultType": "complete",
            "ttlMs": 0,
            "cacheScope": "public",
            "supportedVersions": [MODERN_VERSION],
            "capabilities": {},
            **override,
        },
    }
    with pytest.raises(ProtocolError):
        await MCPClient(transport, protocol_version=MODERN_VERSION).initialize()


async def test_run_timeout_returns_incomplete_report():
    client = MCPClient(AsyncMock(), timeout=1)
    runner = Runner(client, AsyncMock(), run_timeout=0.02)

    async def stuck(report):
        await asyncio.Event().wait()

    runner._run_suites = stuck
    report = await runner.run()
    assert report.incomplete and compute_exit_code(report) == 2
    assert report.suites[-1].checks[0].check_id == "RUN-001"


@pytest.mark.parametrize(
    "values,expected",
    [
        ([0, 1, 2], Status.PASS),
        ([0, 2, 1], Status.FAIL),
        ([True], Status.FAIL),
        ([-1], Status.FAIL),
        ([float("nan")], Status.FAIL),
    ],
)
async def test_progress_validation(values, expected):
    client = MCPClient(AsyncMock())
    client.received_notifications = [
        {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progressToken": "x", "progress": value}}
        for value in values
    ]
    assert (await NotificationsSuite(client).check_notif_005()).status is expected


async def test_progress_tokens_keep_string_and_integer_separate():
    client = MCPClient(AsyncMock())
    client.received_notifications = [
        {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progressToken": token, "progress": value}}
        for token, value in [(1, 10), ("1", 0), (1, 11), ("1", 1)]
    ]
    assert (await NotificationsSuite(client).check_notif_005()).status is Status.PASS
