from __future__ import annotations

import os

import pytest

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("GOOGLE_PLACES_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic")


@pytest.fixture
def anyio_backend() -> str:
    """Pin anyio tests to asyncio so they don't try to run on trio too."""
    return "asyncio"
