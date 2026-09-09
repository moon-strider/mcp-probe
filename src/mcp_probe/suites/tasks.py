from __future__ import annotations

from datetime import datetime

from mcp_probe.protocol import ProtocolError, result_object, validate_tool_result
from mcp_probe.schema_utils import generate_valid_args, matches_schema
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
_VALID_TASK_STATUSES = _TERMINAL_STATUSES | {"working", "input_required"}


def validate_task(task: dict) -> None:
    if not isinstance(task, dict) or not isinstance(task.get("taskId"), str) or not task["taskId"]:
        raise ProtocolError("Task requires a nonempty taskId")
    if task.get("status") not in _VALID_TASK_STATUSES:
        raise ProtocolError("Task has an invalid status")
    for field in ("createdAt", "lastUpdatedAt"):
        try:
            value = datetime.fromisoformat(task[field].replace("Z", "+00:00"))
            if value.tzinfo is None:
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProtocolError("Task requires timezone-aware createdAt and lastUpdatedAt") from exc
    if "ttl" not in task or (task["ttl"] is not None and (type(task["ttl"]) is not int or task["ttl"] < 0)):
        raise ProtocolError("Task ttl must be null or a nonnegative integer")
    if "pollInterval" in task and (type(task["pollInterval"]) is not int or task["pollInterval"] < 0):
        raise ProtocolError("Task pollInterval must be a nonnegative integer")


class TasksSuite(BaseSuite):
    """Legacy task checks only ever mutate task handles created by this suite."""

    name = "tasks"

    def __init__(self, *args, tools: list[dict] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tools = tools or []
        self._tasks: list[dict] = []
        self._owned: dict | None = None

    def _caps(self) -> dict:
        value = self._client.capabilities.get("tasks", {})
        return value if isinstance(value, dict) else {}

    async def _ensure_owned(self) -> dict:
        if self._owned is not None:
            return self._owned
        if not self._client.active:
            self.skip("Task execution requires --active and explicit tool selection")
        if "call" not in self._caps().get("requests", {}).get("tools", {}):
            self.skip("Server does not advertise tasks.requests.tools.call")
        for tool in self._tools:
            if tool.get("name") not in self._client.allowed_tools:
                continue
            if tool.get("execution", {}).get("taskSupport") not in ("required", "optional"):
                continue
            args = self._client.tool_cases.get(tool["name"])
            if args is None:
                args = generate_valid_args(tool.get("inputSchema", {}))
            if args is None:
                continue
            if matches_schema(args, tool["inputSchema"]) is False:
                raise ProtocolError("Task case does not match inputSchema")
            result = result_object(await self._client.call_tool_with_task(tool["name"], args))
            owned = result.get("task")
            if not isinstance(owned, dict):
                raise ProtocolError("CreateTaskResult requires a task object")
            validate_task(owned)
            self._owned = owned
            return owned
        self.skip("No selected task-capable tool with usable arguments")

    @check("TASK-001", "Advertised tasks/list returns a bounded list", Severity.ERROR)
    async def check_task_001(self):
        if "list" not in self._caps():
            self.skip("Server does not advertise tasks.list")
        self._tasks = await self._client.list_tasks()
        return self.pass_check(f"Found {len(self._tasks)} tasks; these handles will not be cancelled")

    @check("TASK-002", "Listed task metadata is well formed", Severity.ERROR)
    async def check_task_002(self):
        if not self._tasks:
            self.skip("No tasks listed")
        seen: set[str] = set()
        for task in self._tasks:
            validate_task(task)
            if task["taskId"] in seen:
                return self.fail_check("Duplicate task ids in listing")
            seen.add(task["taskId"])
        return self.pass_check("Task ids, statuses, timestamps and lifetime fields are valid")

    @check("TASK-003", "tasks/get returns the probe-created task", Severity.ERROR)
    async def check_task_003(self):
        owned = await self._ensure_owned()
        result = result_object(await self._client.get_task(owned["taskId"]))
        validate_task(result)
        if result["taskId"] != owned["taskId"]:
            return self.fail_check("tasks/get returned a different task id")
        self._owned = result
        return self.pass_check("Probe-created task retrieved")

    @check("TASK-004", "Unknown task id returns an error", Severity.WARNING)
    async def check_task_004(self):
        if not self._client.active:
            self.skip("Negative task probe requires --active")
        response = await self._client.get_task("__mcp_probe_nonexistent_task__")
        if "error" not in response:
            return self.fail_check("Unknown task id accepted")
        return self.pass_check("Unknown task id rejected")

    @check("TASK-005", "Only a probe-created working task is cancelled", Severity.ERROR)
    async def check_task_005(self):
        if "cancel" not in self._caps():
            self.skip("Server does not advertise tasks.cancel")
        owned = await self._ensure_owned()
        if owned["status"] not in ("working", "input_required"):
            self.skip("Probe-created task is already terminal")
        response = await self._client.cancel_task(owned["taskId"])
        if "error" in response:
            # Completion may win the race between get and cancel.
            state = result_object(await self._client.get_task(owned["taskId"]))
            validate_task(state)
            if state["taskId"] == owned["taskId"] and state["status"] in _TERMINAL_STATUSES:
                self._owned = state
                return self.info_check("Task completed before cancellation")
            return self.fail_check("Cancellation failed for a nonterminal task")
        result = result_object(response)
        validate_task(result)
        if result["taskId"] != owned["taskId"] or result["status"] != "cancelled":
            return self.fail_check("Cancellation returned an inconsistent task")
        self._owned = result
        return self.pass_check("Probe-created task cancelled")

    @check("TASK-006", "Terminal task rejects cancellation", Severity.WARNING)
    async def check_task_006(self):
        if "cancel" not in self._caps():
            self.skip("Server does not advertise tasks.cancel")
        owned = await self._ensure_owned()
        if owned["status"] not in _TERMINAL_STATUSES:
            self.skip("Probe-created task is not terminal")
        response = await self._client.cancel_task(owned["taskId"])
        if response.get("error", {}).get("code") != -32602:
            return self.warn_check("Expected invalid-params rejection; task may have expired")
        return self.pass_check("Terminal task cancellation rejected")

    @check("TASK-007", "Completed probe task returns its tool result", Severity.ERROR)
    async def check_task_007(self):
        owned = await self._ensure_owned()
        if owned["status"] != "completed":
            self.skip("Probe-created task is not completed")
        result = result_object(await self._client.get_task_result(owned["taskId"]))
        validate_tool_result(result)
        if result.get("_meta", {}).get("io.modelcontextprotocol/related-task", {}).get("taskId") != owned["taskId"]:
            return self.fail_check("Task result is missing matching related-task metadata")
        return self.pass_check("tasks/result returned valid content for the probe task")

    @check("TASK-008", "Task-augmented call returns a task object", Severity.ERROR)
    async def check_task_008(self):
        await self._ensure_owned()
        return self.pass_check("CreateTaskResult contains valid task metadata")
