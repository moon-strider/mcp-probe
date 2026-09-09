from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from mcp_probe.protocol import ProtocolError
from mcp_probe.suites.tasks import TasksSuite, validate_task
from mcp_probe.types import Status

TASK = {
    "taskId": "owned",
    "status": "working",
    "createdAt": "2026-08-01T00:00:00Z",
    "lastUpdatedAt": "2026-08-01T00:00:00Z",
    "ttl": 30000,
    "pollInterval": 10,
}
TOOL = {"name": "compute", "inputSchema": {"type": "object"}, "execution": {"taskSupport": "required"}}


def make_client(active=True, selected=True, status="working"):
    client = AsyncMock()
    client.active = active
    client.allowed_tools = {"compute"} if selected else set()
    client.tool_cases = {"compute": {}}
    client.capabilities = {"tasks": {"list": {}, "cancel": {}, "requests": {"tools": {"call": {}}}}}
    client.list_tasks.return_value = [{**TASK, "taskId": "someone-elses-task"}]
    client.list_tools.return_value = [TOOL]
    owned = {**TASK, "status": status}
    client.call_tool_with_task.return_value = {"result": {"task": owned}}
    client.get_task.side_effect = lambda task_id: (
        {"result": owned} if task_id == "owned" else {"error": {"code": -32602, "message": "missing"}}
    )
    client.cancel_task.side_effect = [
        {"result": {**TASK, "status": "cancelled"}},
        {"error": {"code": -32602, "message": "terminal"}},
    ]
    return client


async def test_task_suite_never_cancels_listed_foreign_tasks():
    client = make_client()
    report = await TasksSuite(client).run()
    assert all(c.status is not Status.FAIL for c in report.checks), report
    assert client.call_tool_with_task.await_count == 1
    assert [c.args[0] for c in client.cancel_task.await_args_list] == ["owned", "owned"]
    client.get_task_result.assert_not_awaited()


@pytest.mark.parametrize("active,selected", [(False, False), (False, True), (True, False)])
async def test_task_execution_requires_both_active_and_selection(active, selected):
    client = make_client(active, selected)
    await TasksSuite(client).run()
    client.call_tool_with_task.assert_not_awaited()
    client.cancel_task.assert_not_awaited()


async def test_completed_task_uses_underlying_result_and_related_metadata():
    client = make_client(status="completed")
    client.cancel_task.side_effect = None
    client.cancel_task.return_value = {"error": {"code": -32602, "message": "terminal"}}
    client.get_task_result.return_value = {
        "result": {
            "content": [{"type": "text", "text": "done"}],
            "_meta": {"io.modelcontextprotocol/related-task": {"taskId": "owned"}},
        }
    }
    report = await TasksSuite(client).run()
    checks = {c.check_id: c for c in report.checks}
    assert checks["TASK-007"].status is Status.PASS
    client.get_task_result.assert_awaited_once_with("owned")
    assert client.cancel_task.await_count == 1  # Only the terminal rejection probe.


async def test_completion_winning_cancel_race_is_not_a_failure():
    client = make_client()
    client.cancel_task.side_effect = None
    client.cancel_task.return_value = {"error": {"code": -32602, "message": "terminal"}}
    client.get_task.side_effect = None
    client.get_task.return_value = {"result": {**TASK, "status": "completed"}}
    suite = TasksSuite(client, tools=[TOOL])
    result = await suite.check_task_005()
    assert result.status is Status.INFO


@pytest.mark.parametrize(
    "field,value",
    [
        ("taskId", ""),
        ("status", "pending"),
        ("ttl", True),
        ("createdAt", "yesterday"),
        ("lastUpdatedAt", "2026-01-01"),
        ("pollInterval", -1),
    ],
)
def test_invalid_task_metadata(field, value):
    task = deepcopy(TASK)
    task[field] = value
    with pytest.raises(ProtocolError):
        validate_task(task)
