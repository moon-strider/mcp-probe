from __future__ import annotations

import logging

from mcp_probe.protocol import ProtocolError, validate_content
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
        self._prompts = await self._client.list_prompts()
        self._first_page_had_cursor = self._client.page_counts.get("prompts/list", 0) > 1
        return self.pass_check(f"Found {len(self._prompts)} prompts")

    @check("PROMPT-002", "Prompt names and optional descriptions are valid", Severity.ERROR)
    async def check_prompt_002(self):
        if not self._prompts:
            self.skip("No prompts discovered")
        issues: list[str] = []
        identifiers = [item.get("name") for item in self._prompts]
        if len(set(str(x) for x in identifiers)) != len(identifiers):
            issues.append("Duplicate names in listing")
        for p in self._prompts:
            if not isinstance(p.get("name"), str) or not p["name"]:
                issues.append(f"prompt missing 'name': {p}")
        if issues:
            return self.fail_check("; ".join(issues[:5]))
        return self.pass_check(f"All {len(self._prompts)} prompts have required fields")

    @check("PROMPT-003", "prompts/get returns messages", Severity.ERROR)
    async def check_prompt_003(self):
        if not self._client.active:
            self.skip("Content retrieval requires --active")
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
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
                raise ProtocolError("Prompt message requires a valid role")
            validate_content(message.get("content"))
        return self.pass_check(f"Prompt '{name}' returned {len(messages)} message(s)")

    @check("PROMPT-004", "prompts/list pagination works", Severity.WARNING)
    async def check_prompt_004(self):
        if not self._first_page_had_cursor:
            self.skip("Server returned all prompts in a single page")
        return self.pass_check("Pagination verified during PROMPT-001")
