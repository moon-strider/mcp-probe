from __future__ import annotations

import pathlib

import pytest

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
MOCK_VALID = str(FIXTURES_DIR / "mock_server_valid.py")
MOCK_BROKEN = str(FIXTURES_DIR / "mock_server_broken.py")
MOCK_MINIMAL = str(FIXTURES_DIR / "mock_server_minimal.py")


@pytest.fixture
def mock_valid_cmd():
    return f"python {MOCK_VALID}"


@pytest.fixture
def mock_broken_cmd():
    return f"python {MOCK_BROKEN}"


@pytest.fixture
def mock_minimal_cmd():
    return f"python {MOCK_MINIMAL}"


@pytest.fixture(autouse=True)
def isolate_http_environment(monkeypatch):
    # Loopback/mock tests must not inherit a developer's external proxy.
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
