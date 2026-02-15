from __future__ import annotations

import asyncio
import logging

from mcp_probe.schema_utils import generate_valid_args
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity

logger = logging.getLogger(__name__)

_VALID_TASK_STATUSES = {"working", "input_required", "completed", "failed", "cancelled"}
_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class TasksSuite(BaseSuite):
    name = "tasks"

    def __init__(self, *args, tools: list[dict] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tools = tools or []
        self._tasks: list[dict] = []

    @check("TASK-001", "tasks/list returns a list of tasks", Severity.CRITICAL)
    async def check_task_001(self):
        resp = await self._client._send_request("tasks/list")
        result = resp.get("result", {})
        tasks = result.get("tasks")
        if tasks is None:
            return self.fail_check(f"No 'tasks' key in result: {list(result.keys())}")
        if not isinstance(tasks, list):
            return self.fail_check(f"'tasks' is not a list: {type(tasks).__name__}")
        self._tasks = tasks
        return self.pass_check(f"Found {len(tasks)} tasks")

    @check("TASK-002", "Each task has taskId, status, createdAt", Severity.ERROR)
    async def check_task_002(self):
        if not self._tasks:
            self.skip("No tasks discovered")
        issues: list[str] = []
        for t in self._tasks:
            tid = t.get("taskId")
            if not isinstance(tid, str) or not tid:
                issues.append(f"task missing 'taskId': {t}")
            status = t.get("status")
            if status not in _VALID_TASK_STATUSES:
                issues.append(f"task '{tid}' has invalid status: {status!r}")
            created = t.get("createdAt")
            if not isinstance(created, str) or not created:
                issues.append(f"task '{tid}' missing 'createdAt'")
        if issues:
            return self.fail_check("; ".join(issues[:5]))
        return self.pass_check(f"All {len(self._tasks)} tasks have required fields")

    @check("TASK-003", "tasks/get returns task status", Severity.ERROR)
    async def check_task_003(self):
        if not self._tasks:
            self.skip("No tasks to get")
        task_id = self._tasks[0]["taskId"]
        resp = await self._client.get_task(task_id)
        if "error" in resp:
            return self.fail_check(f"get_task error: {resp['error']}")
        result = resp.get("result", {})
        if "taskId" not in result or "status" not in result:
            return self.fail_check(f"Response missing taskId or status: {list(result.keys())}")
        return self.pass_check(f"Task '{task_id}' status: {result['status']}")

    @check("TASK-004", "Nonexistent taskId returns error", Severity.WARNING)
    async def check_task_004(self):
        try:
            resp = await self._client.get_task("nonexistent-task-id-00000")
        except Exception as exc:
            return self.fail_check(f"Server crashed: {exc}")
        if "error" in resp:
            return self.pass_check("Server returned error for nonexistent taskId")
        return self.fail_check("Server did not return error for nonexistent taskId")

    @check("TASK-005", "tasks/cancel cancels a working task", Severity.ERROR)
    async def check_task_005(self):
        working = [t for t in self._tasks if t.get("status") == "working"]
        if not working:
            self.skip("No tasks in 'working' status")
        task_id = working[0]["taskId"]
        resp = await self._client.cancel_task(task_id)
        if "error" in resp:
            return self.fail_check(f"cancel error: {resp['error']}")
        result = resp.get("result", {})
        if result.get("status") == "cancelled":
            return self.pass_check(f"Task '{task_id}' cancelled")
        return self.warn_check(f"Task '{task_id}' status after cancel: {result.get('status')}")

    @check("TASK-006", "tasks/cancel on terminal task returns error", Severity.WARNING)
    async def check_task_006(self):
        terminal = [t for t in self._tasks if t.get("status") in _TERMINAL_STATUSES]
        if not terminal:
            self.skip("No tasks in terminal status")
        task_id = terminal[0]["taskId"]
        resp = await self._client.cancel_task(task_id)
        if "error" in resp:
            code = resp["error"].get("code")
            return self.pass_check(f"Server returned error (code={code}) for cancel on terminal task")
        return self.warn_check("Server did not return error for cancel on terminal task")

    @check("TASK-007", "tasks/result returns completed task result", Severity.ERROR)
    async def check_task_007(self):
        completed = [t for t in self._tasks if t.get("status") == "completed"]
        if not completed:
            self.skip("No completed tasks")
        task_id = completed[0]["taskId"]
        resp = await self._client.get_task_result(task_id)
        if "error" in resp:
            return self.fail_check(f"get_task_result error: {resp['error']}")
        return self.pass_check(f"Got result for completed task '{task_id}'")

    @check("TASK-008", "Task-augmented tools/call returns task handle", Severity.ERROR)
    async def check_task_008(self):
        caps = self._client.capabilities
        tasks_caps = caps.get("tasks", {})
        if not isinstance(tasks_caps, dict) or not tasks_caps.get("tools"):
            self.skip("Server does not advertise tasks.tools capability")
        if not self._tools:
            self.skip("No tools available for task-augmented call")
        tool = None
        args = None
        for t in self._tools:
            schema = t.get("inputSchema", {})
            a = generate_valid_args(schema)
            if a is not None:
                tool = t
                args = a
                break
        if tool is None or args is None:
            self.skip("No tool with simple enough schema for task-augmented call")
        resp = await self._client.call_tool_with_task(tool["name"], args, ttl=30000)
        if "error" in resp:
            return self.fail_check(f"Task-augmented call error: {resp['error']}")
        result = resp.get("result", {})
        if result.get("type") != "task":
            return self.fail_check(f"Response type is {result.get('type')!r}, expected 'task'")
        task_id = result.get("taskId")
        status = result.get("status")
        if not task_id:
            return self.fail_check("Response missing taskId")
        details = f"Task '{task_id}' created with status '{status}'"
        if status == "working":
            poll_interval = result.get("pollInterval", 1000) / 1000.0
            for _ in range(3):
                await asyncio.sleep(poll_interval)
                poll_resp = await self._client.get_task(task_id)
                poll_result = poll_resp.get("result", {})
                if poll_result.get("status") in _TERMINAL_STATUSES:
                    details += f" -> {poll_result['status']}"
                    if poll_result["status"] == "completed":
                        await self._client.get_task_result(task_id)
                        details += " (result fetched)"
                    break
        return self.pass_check(details)
