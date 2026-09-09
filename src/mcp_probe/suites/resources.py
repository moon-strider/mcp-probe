from __future__ import annotations

import logging

from mcp_probe.protocol import validate_cache_metadata, validate_resource_content
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity

logger = logging.getLogger(__name__)


class ResourcesSuite(BaseSuite):
    name = "resources"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._resources: list[dict] = []
        self._first_page_had_cursor: bool = False

    @check("RES-001", "resources/list returns a list of resources", Severity.CRITICAL)
    async def check_res_001(self):
        self._resources = await self._client.list_resources()
        self._first_page_had_cursor = self._client.page_counts.get("resources/list", 0) > 1
        return self.pass_check(f"Found {len(self._resources)} resources")

    @check("RES-002", "Each resource has uri and name", Severity.ERROR)
    async def check_res_002(self):
        if not self._resources:
            self.skip("No resources discovered")
        issues: list[str] = []
        identifiers = [item.get("name") for item in self._resources]
        if len(set(str(x) for x in identifiers)) != len(identifiers):
            issues.append("Duplicate names in listing")
        for r in self._resources:
            if not isinstance(r.get("uri"), str) or not r["uri"]:
                issues.append(f"resource missing 'uri': {r}")
            if not isinstance(r.get("name"), str) or not r["name"]:
                issues.append(f"resource missing 'name': {r}")
            mime = r.get("mimeType")
            if mime is not None and not isinstance(mime, str):
                issues.append(f"resource '{r.get('name')}' mimeType is not a string: {mime!r}")
        if issues:
            return self.fail_check("; ".join(issues[:5]))
        return self.pass_check(f"All {len(self._resources)} resources have required fields")

    @check("RES-003", "resources/read returns content", Severity.ERROR)
    async def check_res_003(self):
        if not self._client.active:
            self.skip("Content retrieval requires --active")
        if not self._resources:
            self.skip("No resources discovered")
        uri = self._resources[0]["uri"]
        resp = await self._client.read_resource(uri)
        if "error" in resp:
            return self.fail_check(f"Error reading '{uri}': {resp['error']}")
        result = resp.get("result", {})
        contents = result.get("contents")
        if not isinstance(contents, list):
            return self.fail_check(f"No 'contents' in read response for '{uri}'")
        for item in contents:
            validate_resource_content(item)
        if self._client.modern:
            validate_cache_metadata(result)
        return self.pass_check(f"Read '{uri}' returned {len(contents)} content item(s)")

    @check("RES-004", "Nonexistent resource returns error", Severity.WARNING)
    async def check_res_004(self):
        if not self._client.active:
            self.skip("Negative resource probe requires --active")
        try:
            resp = await self._client.read_resource("nonexistent://fake-resource-uri")
        except Exception as exc:
            return self.fail_check(f"Server crashed on nonexistent resource: {exc}")
        if "error" in resp:
            return self.pass_check("Server returned error for nonexistent resource")
        return self.fail_check("Server did not return error for nonexistent resource")

    @check("RES-005", "resources/list pagination works", Severity.WARNING)
    async def check_res_005(self):
        if not self._first_page_had_cursor:
            self.skip("Server returned all resources in a single page")
        return self.pass_check("Pagination verified during RES-001")
