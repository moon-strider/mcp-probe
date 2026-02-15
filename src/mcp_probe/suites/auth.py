from __future__ import annotations

import asyncio
import logging
import sys
import urllib.error
import urllib.request

from mcp_probe.auth import OAuthError, discover_oauth_metadata, discover_protected_resource, perform_oauth_flow
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity

logger = logging.getLogger(__name__)


class AuthSuite(BaseSuite):
    name = "auth"

    def __init__(self, server_url: str, timeout: float = 30.0) -> None:
        self._client = None  # type: ignore[assignment]
        self._timeout = timeout
        self._server_url = server_url
        self._pr_meta: dict | None = None
        self._auth_server: str | None = None

    async def _post_no_auth(self) -> tuple[int, dict[str, str]]:
        req = urllib.request.Request(self._server_url, data=b"{}", method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=self._timeout)
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers
        except urllib.error.HTTPError as exc:
            headers = {k.lower(): v for k, v in exc.headers.items()}
            return exc.code, headers

    @check("AUTH-001", "Server returns 401 with WWW-Authenticate", Severity.INFO)
    async def check_auth_001(self):
        status_code, headers = await self._post_no_auth()
        if status_code != 401:
            return self.info_check(f"Server returned {status_code}, not 401 (no auth required)")
        www_auth = headers.get("www-authenticate", "")
        if "Bearer" in www_auth:
            return self.pass_check(f"401 with WWW-Authenticate: {www_auth[:100]}")
        if www_auth:
            return self.info_check(f"401 with WWW-Authenticate but no Bearer: {www_auth[:100]}")
        return self.info_check("401 without WWW-Authenticate header")

    @check("AUTH-002", "Protected Resource Metadata discovery", Severity.INFO)
    async def check_auth_002(self):
        meta = await asyncio.to_thread(discover_protected_resource, self._server_url)
        if meta is None:
            return self.fail_check("Protected Resource Metadata endpoint unavailable or invalid JSON")
        auth_servers = meta.get("authorization_servers")
        if not isinstance(auth_servers, list) or not auth_servers:
            return self.fail_check(f"authorization_servers missing or empty: {meta.keys()}")
        self._pr_meta = meta
        self._auth_server = auth_servers[0]
        return self.pass_check(f"Found {len(auth_servers)} authorization server(s): {auth_servers[0]}")

    @check("AUTH-003", "OAuth Authorization Server Metadata discovery", Severity.INFO)
    async def check_auth_003(self):
        if self._auth_server is None:
            self.skip("No authorization server discovered (AUTH-002 did not run or failed)")
        meta = await asyncio.to_thread(discover_oauth_metadata, self._auth_server)
        if meta is None:
            return self.fail_check(f"OAuth metadata unavailable for {self._auth_server}")
        auth_ep = meta.get("authorization_endpoint")
        token_ep = meta.get("token_endpoint")
        if not isinstance(auth_ep, str) or not auth_ep:
            return self.fail_check("Missing authorization_endpoint in OAuth metadata")
        if not isinstance(token_ep, str) or not token_ep:
            return self.fail_check("Missing token_endpoint in OAuth metadata")
        return self.pass_check(f"authorization_endpoint={auth_ep}, token_endpoint={token_ep}")

    @check("AUTH-004", "Full OAuth flow with Bearer token", Severity.ERROR)
    async def check_auth_004(self):
        if not sys.stdin.isatty():
            self.skip("Non-interactive terminal, cannot perform OAuth flow")
        if self._auth_server is None:
            self.skip("No authorization server discovered")
        try:
            token = await asyncio.to_thread(
                perform_oauth_flow, self._server_url, "mcp-probe"
            )
        except OAuthError as exc:
            return self.fail_check(f"OAuth flow failed: {exc}")
        req = urllib.request.Request(self._server_url, data=b"{}", method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {token}")
        try:
            resp = await asyncio.to_thread(urllib.request.urlopen, req, timeout=self._timeout)
            return self.pass_check(f"Authenticated request returned {resp.status}")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return self.fail_check("Still 401 after OAuth flow — token not accepted")
            return self.pass_check(f"Authenticated request returned HTTP {exc.code} (not 401)")
