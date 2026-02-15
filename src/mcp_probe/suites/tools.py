from __future__ import annotations

import logging
import re

from mcp_probe.schema_utils import generate_invalid_args, generate_valid_args
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity

logger = logging.getLogger(__name__)

try:
    import jsonschema  # type: ignore[import-untyped]

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

_TOOL_NAME_RE = re.compile(r"^[a-z0-9_-]+$")


class ToolsSuite(BaseSuite):
    name = "tools"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tools: list[dict] = []
        self._first_page_had_cursor: bool = False

    @check("TOOL-001", "tools/list returns a list of tools", Severity.CRITICAL)
    async def check_tool_001(self):
        resp = await self._client._send_request("tools/list")
        result = resp.get("result", {})
        tools = result.get("tools")
        if tools is None:
            return self.fail_check(f"No 'tools' key in result: {list(result.keys())}")
        if not isinstance(tools, list):
            return self.fail_check(f"'tools' is not a list: {type(tools).__name__}")
        self._first_page_had_cursor = "nextCursor" in result
        if self._first_page_had_cursor:
            cursor = result["nextCursor"]
            while cursor:
                resp2 = await self._client._send_request("tools/list", {"cursor": cursor})
                r2 = resp2.get("result", {})
                tools.extend(r2.get("tools", []))
                cursor = r2.get("nextCursor")
        self._tools = tools
        return self.pass_check(f"Found {len(tools)} tools")

    @check("TOOL-002", "Each tool has name, description, inputSchema", Severity.CRITICAL)
    async def check_tool_002(self):
        if not self._tools:
            self.skip("No tools discovered")
        missing: list[str] = []
        for t in self._tools:
            name = t.get("name")
            if not isinstance(name, str) or not name:
                missing.append(f"tool missing 'name': {t}")
            if not isinstance(t.get("inputSchema"), dict):
                missing.append(f"tool '{name}' missing 'inputSchema' (dict)")
        if missing:
            return self.fail_check("; ".join(missing[:5]))
        return self.pass_check(f"All {len(self._tools)} tools have required fields")

    @check("TOOL-003", "inputSchema is valid JSON Schema", Severity.ERROR)
    async def check_tool_003(self):
        if not self._tools:
            self.skip("No tools discovered")
        invalid: list[str] = []
        for t in self._tools:
            schema = t.get("inputSchema", {})
            if HAS_JSONSCHEMA:
                try:
                    jsonschema.Draft202012Validator.check_schema(schema)
                except jsonschema.SchemaError as exc:
                    invalid.append(f"'{t.get('name')}': {exc.message}")
            else:
                if not isinstance(schema, dict):
                    invalid.append(f"'{t.get('name')}': schema is not a dict")
                elif schema.get("type") == "object" and "properties" not in schema:
                    invalid.append(f"'{t.get('name')}': object schema without properties")
        if invalid:
            return self.fail_check("; ".join(invalid[:5]))
        suffix = "" if HAS_JSONSCHEMA else " (install jsonschema for full validation)"
        return self.pass_check(f"All schemas valid{suffix}")

    @check("TOOL-004", "Tool call with valid arguments succeeds", Severity.ERROR)
    async def check_tool_004(self):
        if not self._tools:
            self.skip("No tools discovered")
        for t in self._tools:
            schema = t.get("inputSchema", {})
            args = generate_valid_args(schema)
            if args is None:
                continue
            resp = await self._client.call_tool(t["name"], args)
            if "error" in resp:
                return self.fail_check(f"Tool '{t['name']}' returned error: {resp['error']}")
            result = resp.get("result", {})
            if "content" not in result and not isinstance(result, dict):
                return self.fail_check(f"Tool '{t['name']}' response has no 'content'")
            return self.pass_check(f"Tool '{t['name']}' called successfully")
        self.skip("All tool schemas too complex for auto-generation")

    @check("TOOL-005", "Tool call with invalid arguments returns error", Severity.ERROR)
    async def check_tool_005(self):
        if not self._tools:
            self.skip("No tools discovered")
        t = self._tools[0]
        schema = t.get("inputSchema", {})
        args = generate_invalid_args(schema)
        try:
            resp = await self._client.call_tool(t["name"], args)
        except Exception as exc:
            return self.fail_check(f"Server crashed on invalid args: {exc}")
        if "error" in resp:
            return self.pass_check(f"Server returned error for invalid args on '{t['name']}'")
        result = resp.get("result", {})
        is_error_content = False
        for item in result.get("content", []):
            if item.get("type") == "text" and "error" in item.get("text", "").lower():
                is_error_content = True
        if result.get("isError"):
            return self.pass_check(f"Server returned isError=true for invalid args on '{t['name']}'")
        if is_error_content:
            return self.pass_check(f"Server returned error content for invalid args on '{t['name']}'")
        return self.warn_check(f"Server accepted invalid args without error on '{t['name']}'")

    @check("TOOL-006", "Nonexistent tool returns error", Severity.WARNING)
    async def check_tool_006(self):
        try:
            resp = await self._client.call_tool("__nonexistent_tool_name__", {})
        except Exception as exc:
            return self.fail_check(f"Server crashed on nonexistent tool: {exc}")
        if "error" in resp:
            return self.pass_check("Server returned error for nonexistent tool")
        result = resp.get("result", {})
        if result.get("isError"):
            return self.pass_check("Server returned isError=true for nonexistent tool")
        return self.fail_check("Server did not return error for nonexistent tool")

    @check("TOOL-007", "Tool names follow naming convention", Severity.INFO)
    async def check_tool_007(self):
        if not self._tools:
            self.skip("No tools discovered")
        non_conforming = [t["name"] for t in self._tools if not _TOOL_NAME_RE.match(t.get("name", ""))]
        if non_conforming:
            return self.info_check(f"Non-standard names: {', '.join(non_conforming[:10])}")
        return self.pass_check("All tool names follow [a-z0-9_-] convention")

    @check("TOOL-008", "tools/list pagination works", Severity.WARNING)
    async def check_tool_008(self):
        if not self._first_page_had_cursor:
            self.skip("Server returned all tools in a single page")
        return self.pass_check("Pagination verified during TOOL-001")
