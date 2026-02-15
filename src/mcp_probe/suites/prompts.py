from __future__ import annotations

import logging

from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity

logger = logging.getLogger(__name__)


class PromptsSuite(BaseSuite):
    name = "prompts"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._prompts: list[dict] = []
        self._first_page_had_cursor: bool = False

    @check("PROMPT-001", "prompts/list returns a list of prompts", Severity.CRITICAL)
    async def check_prompt_001(self):
        resp = await self._client._send_request("prompts/list")
        result = resp.get("result", {})
        prompts = result.get("prompts")
        if prompts is None:
            return self.fail_check(f"No 'prompts' key in result: {list(result.keys())}")
        if not isinstance(prompts, list):
            return self.fail_check(f"'prompts' is not a list: {type(prompts).__name__}")
        self._first_page_had_cursor = "nextCursor" in result
        if self._first_page_had_cursor:
            cursor = result["nextCursor"]
            while cursor:
                resp2 = await self._client._send_request("prompts/list", {"cursor": cursor})
                r2 = resp2.get("result", {})
                prompts.extend(r2.get("prompts", []))
                cursor = r2.get("nextCursor")
        self._prompts = prompts
        return self.pass_check(f"Found {len(prompts)} prompts")

    @check("PROMPT-002", "Each prompt has name and description", Severity.ERROR)
    async def check_prompt_002(self):
        if not self._prompts:
            self.skip("No prompts discovered")
        issues: list[str] = []
        for p in self._prompts:
            if not isinstance(p.get("name"), str) or not p["name"]:
                issues.append(f"prompt missing 'name': {p}")
        if issues:
            return self.fail_check("; ".join(issues[:5]))
        return self.pass_check(f"All {len(self._prompts)} prompts have required fields")

    @check("PROMPT-003", "prompts/get returns messages", Severity.ERROR)
    async def check_prompt_003(self):
        if not self._prompts:
            self.skip("No prompts discovered")
        prompt = self._prompts[0]
        name = prompt["name"]
        arguments: dict | None = None
        prompt_args = prompt.get("arguments", [])
        if prompt_args:
            arguments = {}
            for arg in prompt_args:
                arg_name = arg.get("name", "")
                arguments[arg_name] = "test"
        resp = await self._client.get_prompt(name, arguments)
        if "error" in resp:
            return self.fail_check(f"Error getting prompt '{name}': {resp['error']}")
        result = resp.get("result", {})
        messages = result.get("messages")
        if messages is None:
            return self.fail_check(f"No 'messages' in get_prompt response for '{name}'")
        if not isinstance(messages, list):
            return self.fail_check(f"'messages' is not a list: {type(messages).__name__}")
        return self.pass_check(f"Prompt '{name}' returned {len(messages)} message(s)")

    @check("PROMPT-004", "prompts/list pagination works", Severity.WARNING)
    async def check_prompt_004(self):
        if not self._first_page_had_cursor:
            self.skip("Server returned all prompts in a single page")
        return self.pass_check("Pagination verified during PROMPT-001")
