from __future__ import annotations

import base64
import hashlib

from mcp_probe.auth import _base64url_encode, _generate_pkce


def test_base64url_encode_no_padding():
    data = b"test data"
    encoded = _base64url_encode(data)
    assert "=" not in encoded
    assert isinstance(encoded, str)


def test_generate_pkce_verifier_and_challenge():
    verifier, challenge = _generate_pkce()
    assert isinstance(verifier, str)
    assert isinstance(challenge, str)
    assert len(verifier) > 20
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert challenge == expected


def test_generate_pkce_unique():
    v1, c1 = _generate_pkce()
    v2, c2 = _generate_pkce()
    assert v1 != v2
    assert c1 != c2
