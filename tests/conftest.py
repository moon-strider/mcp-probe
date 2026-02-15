from __future__ import annotations

import os
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
