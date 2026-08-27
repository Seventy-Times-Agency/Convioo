from __future__ import annotations

import pytest

from leadgen.utils.retry import retry_async


@pytest.mark.anyio
async def test_retry_async_succeeds_after_failures() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("temporary")
        return "ok"

    result = await retry_async(flaky, retries=3, base_delay=0.01, retry_on=(RuntimeError,))

    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.anyio
async def test_retry_async_raises_when_exhausted() -> None:
    async def always_fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await retry_async(always_fail, retries=1, base_delay=0.01, retry_on=(ValueError,))


@pytest.mark.anyio
async def test_retry_async_does_not_retry_unmatched_exception() -> None:
    calls = {"n": 0}

    async def boom() -> None:
        calls["n"] += 1
        raise KeyError("nope")

    with pytest.raises(KeyError):
        await retry_async(
            boom, retries=3, base_delay=0.0, retry_on=(ValueError,)
        )
    assert calls["n"] == 1


@pytest.mark.anyio
async def test_retry_async_source_tag_does_not_break() -> None:
    async def ok() -> int:
        return 42

    assert await retry_async(ok, retries=1, base_delay=0.0, source="probe") == 42
