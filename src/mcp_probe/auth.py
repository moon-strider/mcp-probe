from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    pass


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _generate_pkce() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = _base64url_encode(digest)
    return code_verifier, code_challenge


def discover_protected_resource(url: str) -> dict[str, Any] | None:
    parsed = urllib.parse.urlparse(url)
    well_known = f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource"
    req = urllib.request.Request(well_known, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result: dict[str, Any] = json.loads(resp.read())
        return result
    except Exception:
        logger.debug("Failed to discover protected resource metadata at %s", well_known)
        return None


def discover_oauth_metadata(auth_server_url: str) -> dict[str, Any] | None:
    url = auth_server_url.rstrip("/") + "/.well-known/oauth-authorization-server"
    req = urllib.request.Request(url, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result: dict[str, Any] = json.loads(resp.read())
        return result
    except Exception:
        logger.debug("Failed to discover OAuth metadata at %s", url)
        return None


def _start_callback_server(port: int, timeout: float = 120.0) -> tuple[str, str]:
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            if code:
                result["code"] = code
            if state:
                result["state"] = state
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            body = b"<html><body><h1>Authorization complete.</h1><p>You can close this tab.</p></body></html>"
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    server.timeout = timeout
    server.handle_request()
    server.server_close()

    if not result.get("code"):
        raise OAuthError("No authorization code received in callback")

    return result["code"], result.get("state", "")


def perform_oauth_flow(
    server_url: str,
    client_id: str,
    redirect_port: int = 8765,
) -> str:
    pr_meta = discover_protected_resource(server_url)
    if pr_meta is None:
        raise OAuthError(f"Could not discover Protected Resource Metadata for {server_url}")

    auth_servers = pr_meta.get("authorization_servers", [])
    if not auth_servers:
        raise OAuthError("No authorization_servers in Protected Resource Metadata")

    oauth_meta = discover_oauth_metadata(auth_servers[0])
    if oauth_meta is None:
        raise OAuthError(f"Could not discover OAuth Server Metadata for {auth_servers[0]}")

    authorization_endpoint = oauth_meta.get("authorization_endpoint")
    token_endpoint = oauth_meta.get("token_endpoint")
    if not authorization_endpoint or not token_endpoint:
        raise OAuthError("OAuth metadata missing authorization_endpoint or token_endpoint")

    code_verifier, code_challenge = _generate_pkce()
    state = secrets.token_urlsafe(16)
    redirect_uri = f"http://localhost:{redirect_port}/callback"

    auth_params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": server_url,
        "scope": "mcp",
    }
    auth_url = authorization_endpoint + "?" + urllib.parse.urlencode(auth_params)

    webbrowser.open(auth_url)

    code, callback_state = _start_callback_server(redirect_port)

    if callback_state != state:
        raise OAuthError(f"State mismatch: expected {state}, got {callback_state}")

    token_data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "resource": server_url,
        }
    ).encode()
    token_req = urllib.request.Request(
        token_endpoint,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        token_resp = urllib.request.urlopen(token_req, timeout=30)
        token_json = json.loads(token_resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise OAuthError(f"Token exchange failed: HTTP {exc.code} — {body}") from exc
    except Exception as exc:
        raise OAuthError(f"Token exchange failed: {exc}") from exc

    access_token = token_json.get("access_token")
    if not access_token:
        raise OAuthError("No access_token in token response")

    return str(access_token)
