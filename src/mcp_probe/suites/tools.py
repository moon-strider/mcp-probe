from __future__ import annotations

import re

from mcp_probe.protocol import ProtocolError, result_object, validate_tool_result
from mcp_probe.schema_utils import generate_invalid_args, generate_valid_args, matches_schema, schema_error
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity

_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class ToolsSuite(BaseSuite):
    name = "tools"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tools: list[dict] = []
        self._first_page_had_cursor = False

    def _selected(self) -> list[dict]:
        selected = [t for t in self._tools if t.get("name") in self._client.allowed_tools]
        if not selected:
            self.skip("No tool selected; use --tool or --cases to enable calls")
        return selected

    def _arguments(self, tool: dict) -> dict | None:
        if tool["name"] in self._client.tool_cases:
            return self._client.tool_cases[tool["name"]]
        return generate_valid_args(tool.get("inputSchema", {}))

    @check("TOOL-001", "tools/list returns a bounded list", Severity.CRITICAL)
    async def check_tool_001(self):
        self._tools = await self._client.list_tools()
        self._first_page_had_cursor = self._client.page_counts.get("tools/list", 0) > 1
        missing = self._client.allowed_tools - {t.get("name") for t in self._tools}
        if missing:
            return self.fail_check("Selected tools were not advertised: " + ", ".join(sorted(missing)))
        return self.pass_check(f"Found {len(self._tools)} tools")

    @check("TOOL-002", "Tool metadata has valid required fields", Severity.CRITICAL)
    async def check_tool_002(self):
        if not self._tools:
            self.skip("No tools discovered")
        names: set[str] = set()
        for tool in self._tools:
            name = tool.get("name")
            if not isinstance(name, str) or not name or name in names:
                return self.fail_check("Tool names must be nonempty and unique")
            names.add(name)
            if not isinstance(tool.get("inputSchema"), dict):
                return self.fail_check(f"Tool {name!r} requires an inputSchema object")
            if "description" in tool and not isinstance(tool["description"], str):
                return self.fail_check(f"Tool {name!r} description must be a string")
            execution = tool.get("execution", {})
            if not isinstance(execution, dict) or execution.get("taskSupport", "forbidden") not in (
                "required",
                "optional",
                "forbidden",
            ):
                return self.fail_check(f"Tool {name!r} has invalid execution metadata")
        return self.pass_check(f"Validated {len(names)} tool definitions")

    @check("TOOL-003", "Tool input and output schemas are valid", Severity.ERROR)
    async def check_tool_003(self):
        if not self._tools:
            self.skip("No tools discovered")
        for tool in self._tools:
            for key in ("inputSchema", "outputSchema"):
                if key not in tool:
                    continue
                error = schema_error(tool[key])
                if error:
                    return self.fail_check(f"{tool.get('name')!r} {key}: {error}")
                if not self._client.modern and tool[key].get("type") != "object":
                    return self.fail_check("Legacy tool schemas require type=object")
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            return self.info_check("Basic schema shape checked; install the full extra for JSON Schema validation")
        return self.pass_check("Schemas validated offline")

    @check("TOOL-004", "Selected tool calls return valid content", Severity.ERROR)
    async def check_tool_004(self):
        checked = 0
        application_errors = 0
        for tool in self._selected():
            if tool.get("execution", {}).get("taskSupport") == "required":
                continue
            args = self._arguments(tool)
            if args is None:
                continue
            if matches_schema(args, tool["inputSchema"]) is False:
                return self.fail_check(f"Case arguments do not match {tool['name']!r} inputSchema")
            response = await self._client.call_tool(tool["name"], args)
            if "error" in response:
                return self.fail_check(f"Selected tool returned a protocol error: {tool['name']!r}")
            result = response.get("result")
            try:
                validate_tool_result(result, modern=self._client.modern is True)
            except ProtocolError as exc:
                return self.fail_check(str(exc))
            if result.get("isError"):
                application_errors += 1
            elif "outputSchema" in tool:
                if "structuredContent" not in result:
                    return self.fail_check("Tool with outputSchema omitted structuredContent")
                valid = matches_schema(result["structuredContent"], tool["outputSchema"])
                if valid is False:
                    return self.fail_check("structuredContent does not match outputSchema")
                if valid is None:
                    return self.warn_check(
                        "Could not validate outputSchema offline; install full or resolve local references"
                    )
            checked += 1
        if not checked:
            self.skip("Selected schemas need explicit --cases or require task execution")
        if application_errors:
            return self.warn_check(
                f"{checked} results are well formed; {application_errors} tools reported application errors"
            )
        return self.pass_check(f"Validated {checked} selected tool result(s)")

    @check("TOOL-005", "Selected tools reject schema-invalid arguments", Severity.ERROR)
    async def check_tool_005(self):
        if not self._client.active:
            self.skip("Requires --active and explicit tool selection")
        checked = 0
        for tool in self._selected():
            if tool.get("execution", {}).get("taskSupport") == "required":
                continue
            args = generate_invalid_args(tool.get("inputSchema", {}))
            if args is None:
                continue
            response = await self._client.call_tool(tool["name"], args)
            if "error" not in response:
                result = result_object(response)
                validate_tool_result(result, modern=self._client.modern)
                if result.get("isError") is not True:
                    return self.fail_check(f"Tool {tool['name']!r} accepted schema-invalid arguments")
            checked += 1
        if not checked:
            self.skip("Could not construct a provably invalid argument object")
        return self.pass_check(f"Validated argument rejection for {checked} tool(s)")

    @check("TOOL-006", "Nonexistent tool returns an error", Severity.WARNING)
    async def check_tool_006(self):
        if not self._client.active:
            self.skip("Requires --active")
        name = "__mcp_probe_nonexistent_tool__"
        if any(t.get("name") == name for t in self._tools):
            self.skip("Reserved probe name is advertised by the server")
        response = await self._client.call_tool(name, {})
        if "error" in response or result_object(response).get("isError") is True:
            return self.pass_check("Server rejected unknown tool")
        return self.fail_check("Server accepted an unknown tool")

    @check("TOOL-007", "Tool names follow the naming recommendation", Severity.WARNING)
    async def check_tool_007(self):
        invalid = [t.get("name") for t in self._tools if not _TOOL_NAME_RE.fullmatch(str(t.get("name", "")))]
        if invalid:
            return self.warn_check("Names should use letters, digits, underscore, hyphen or dot, within 128 characters")
        return self.pass_check("Tool names follow the naming recommendation")

    @check("TOOL-008", "tools/list pagination terminates", Severity.WARNING)
    async def check_tool_008(self):
        if not self._first_page_had_cursor:
            self.skip("Only one page was returned")
        return self.pass_check("Pagination completed without repeated cursors")
