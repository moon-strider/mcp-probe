"""Read-only OAuth metadata discovery. Tokens are supplied by the caller."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx


async def _get_json(url: str, timeout: float = 10.0) -> dict | None:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            async with client.stream("GET", url, headers={"Accept": "application/json"}) as response:
                if response.status_code != 200:
                    return None
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 65536:
                        return None
                import json

                value = json.loads(content)
                return value if isinstance(value, dict) else None
    except (httpx.HTTPError, ValueError):
        return None


async def discover_protected_resource(url: str, timeout: float = 10.0) -> dict | None:
    parsed = urlsplit(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    paths = [
        f"{origin}/.well-known/oauth-protected-resource{parsed.path.rstrip('/')}",
        f"{origin}/.well-known/oauth-protected-resource",
    ]
    for candidate in dict.fromkeys(paths):
        result = await _get_json(candidate, timeout)
        if result is not None:
            return result
    return None


async def discover_oauth_metadata(issuer: str, timeout: float = 10.0) -> dict | None:
    parsed = urlsplit(issuer)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    for url in (
        f"{origin}/.well-known/oauth-authorization-server{path}",
        f"{issuer.rstrip('/')}/.well-known/openid-configuration",
    ):
        value = await _get_json(url, timeout)
        if value is not None:
            return value
    return None
