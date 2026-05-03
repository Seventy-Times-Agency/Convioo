from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    jitter: float = 0.25,
    source: str | None = None,
) -> T:
    """Run an async callable with exponential backoff retries.

    Sleeps ``base_delay * 2**(attempt-1)`` (capped at ``max_delay``)
    between attempts, plus a random jitter window so a thundering
    herd of retries doesn't re-synchronise on every external blip.

    ``source`` tags retry log lines (e.g. ``yelp``, ``overpass``) so
    Railway log search can pinpoint which collector is flapping.
    """
    attempt = 0
    while True:
        try:
            return await fn()
        except retry_on as exc:
            attempt += 1
            if attempt > retries:
                logger.warning(
                    "retry_async: giving up source=%s attempts=%d error=%s",
                    source or "?",
                    attempt,
                    exc,
                )
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if jitter > 0:
                delay = delay + random.uniform(0, jitter * delay)
            logger.info(
                "retry_async: source=%s attempt=%d/%d delay=%.2fs error=%s",
                source or "?",
                attempt,
                retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
