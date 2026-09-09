from __future__ import annotations

import httpx
import pytest

from mcp_probe.auth import discover_oauth_metadata, discover_protected_resource
from mcp_probe.suites.auth import AuthSuite
from mcp_probe.types import Status


@pytest.fixture
def fake_http(monkeypatch):
    original = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(
            httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)
        )

    return install


async def test_metadata_uses_resource_path_then_root(fake_http):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        assert "authorization" not in request.headers
        if request.url.path.endswith("/mcp"):
            return httpx.Response(404)
        return httpx.Response(200, json={"authorization_servers": ["https://issuer.example"]})

    fake_http(handler)
    value = await discover_protected_resource("https://service.example/mcp")
    assert value["authorization_servers"] == ["https://issuer.example"]
    assert seen == ["/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-protected-resource"]


async def test_issuer_path_discovery(fake_http):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"issuer": "https://issuer.example/tenant"})

    fake_http(handler)
    assert await discover_oauth_metadata("https://issuer.example/tenant")
    assert seen == ["/.well-known/oauth-authorization-server/tenant"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json=[]),
        httpx.Response(200, text="not json"),
        httpx.Response(200, content=b"x" * 65537),
        httpx.Response(302, headers={"Location": "https://other.example"}),
    ],
)
async def test_invalid_metadata_is_not_accepted(fake_http, response):
    fake_http(lambda request: response)
    assert await discover_protected_resource("https://service.example/mcp") is None


async def test_auth_suite_checks_metadata_without_logging_in(fake_http):
    def handler(request):
        assert "authorization" not in request.headers
        if request.method == "POST":
            return httpx.Response(401, headers={"WWW-Authenticate": "bearer realm=mcp"})
        if "oauth-protected-resource" in request.url.path:
            return httpx.Response(200, json={"authorization_servers": ["https://issuer.example"]})
        return httpx.Response(
            200,
            json={
                "issuer": "https://issuer.example",
                "authorization_endpoint": "https://issuer.example/auth",
                "token_endpoint": "https://issuer.example/token",
            },
        )

    fake_http(handler)
    result = await AuthSuite("https://service.example/mcp").run()
    assert [c.status for c in result.checks] == [Status.PASS] * 3


async def test_non_auth_errors_do_not_prove_public_access(fake_http):
    fake_http(lambda request: httpx.Response(500))
    result = await AuthSuite("https://service.example/mcp").run()
    assert result.checks[0].status is Status.INFO
    assert "undetermined" in result.checks[0].details
    assert result.checks[1].status is Status.SKIP
