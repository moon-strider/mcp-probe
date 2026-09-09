from __future__ import annotations

import httpx

from mcp_probe.auth import discover_oauth_metadata, discover_protected_resource
from mcp_probe.suites.base import BaseSuite, check
from mcp_probe.types import Severity


class AuthSuite(BaseSuite):
    name = "auth"

    def __init__(self, server_url: str, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._server_url = server_url
        self._auth_server: str | None = None
        self._requires_auth = False

    @check("AUTH-001", "Observe unauthenticated endpoint response", Severity.INFO)
    async def check_auth_001(self):
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
            async with client.stream(
                "POST", self._server_url, content=b"{}", headers={"Content-Type": "application/json"}
            ) as response:
                status = response.status_code
                challenge = response.headers.get("www-authenticate", "")
        self._requires_auth = status == 401
        if not self._requires_auth:
            return self.info_check(
                f"Unauthenticated malformed request returned HTTP {status}; auth requirement undetermined"
            )
        if not challenge.lower().startswith("bearer"):
            return self.warn_check("Unauthorized response has no Bearer challenge")
        return self.pass_check("Bearer challenge observed; credentials were not sent")

    @check("AUTH-002", "Protected Resource Metadata is discoverable", Severity.WARNING)
    async def check_auth_002(self):
        if not self._requires_auth:
            self.skip("No authentication challenge observed")
        metadata = await discover_protected_resource(self._server_url, self._timeout)
        if metadata is None:
            return self.warn_check("Well-known metadata unavailable; challenge-specific discovery may be required")
        issuers = metadata.get("authorization_servers")
        if not isinstance(issuers, list) or not issuers or any(not isinstance(x, str) for x in issuers):
            return self.fail_check("Metadata requires authorization_servers")
        self._auth_server = issuers[0]
        return self.pass_check("Authorization server metadata location discovered")

    @check("AUTH-003", "Authorization server advertises endpoints", Severity.WARNING)
    async def check_auth_003(self):
        if self._auth_server is None:
            self.skip("No authorization server discovered")
        metadata = await discover_oauth_metadata(self._auth_server, self._timeout)
        if metadata is None:
            return self.warn_check("Authorization metadata unavailable")
        if metadata.get("issuer") != self._auth_server:
            return self.fail_check("Authorization metadata issuer mismatch")
        if not all(
            isinstance(metadata.get(k), str) and metadata[k] for k in ("authorization_endpoint", "token_endpoint")
        ):
            return self.fail_check("Authorization metadata is missing endpoints")
        return self.pass_check("Issuer and endpoint metadata present; login flow is outside this probe")
