"""In-process cache fallback (no Redis)."""

from __future__ import annotations

import pytest

from leadgen.utils import cache


@pytest.mark.asyncio
async def test_cache_set_and_get_roundtrip() -> None:
    await cache.reset_for_tests()
    await cache.set_json("test", "key1", {"a": 1, "b": [2, 3]}, ttl_sec=60)
    got = await cache.get_json("test", "key1")
    assert got == {"a": 1, "b": [2, 3]}


@pytest.mark.asyncio
async def test_cache_miss_returns_none() -> None:
    await cache.reset_for_tests()
    assert await cache.get_json("test", "missing") is None


@pytest.mark.asyncio
async def test_cache_zero_ttl_is_noop() -> None:
    await cache.reset_for_tests()
    await cache.set_json("test", "k", "v", ttl_sec=0)
    assert await cache.get_json("test", "k") is None


@pytest.mark.asyncio
async def test_cache_namespace_isolation() -> None:
    await cache.reset_for_tests()
    await cache.set_json("ns_a", "k", "from-a", ttl_sec=60)
    await cache.set_json("ns_b", "k", "from-b", ttl_sec=60)
    assert await cache.get_json("ns_a", "k") == "from-a"
    assert await cache.get_json("ns_b", "k") == "from-b"
