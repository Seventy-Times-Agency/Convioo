from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Run an async callable with exponential backoff retries."""
    attempt = 0
    while True:
        try:
            return await fn()
        except retry_on:
            attempt += 1
            if attempt > retries:
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            await asyncio.sleep(delay)
