"""Safe wrappers around ``asyncio.create_task`` for fire-and-forget work.

Plain ``asyncio.create_task(coro)`` with no awaiter swallows exceptions
silently — they only surface as a Python warning when the task is
garbage-collected, which may be long after the request that scheduled
it has returned. This module exposes ``spawn`` which attaches a
done-callback that logs the traceback and forwards it to Sentry so the
failure becomes visible.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# Keep strong references to detached tasks so they cannot be GC'd
# mid-flight (https://docs.python.org/3/library/asyncio-task.html
# #asyncio.create_task — "important: save a reference"). Removed in
# the done-callback once the task settles.
_pending: set[asyncio.Task[Any]] = set()


def _on_done(task: asyncio.Task[Any]) -> None:
    _pending.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is None:
        return
    name = task.get_name()
    logger.exception(
        "background task %s failed", name, exc_info=exc
    )
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        # Sentry not configured / not installed in this context.
        pass


def spawn(
    coro: Coroutine[Any, Any, Any], *, name: str | None = None
) -> asyncio.Task[Any]:
    """Schedule ``coro`` and log/Sentry-report any unhandled exception.

    Returns the underlying ``asyncio.Task`` so callers that still want
    to ``cancel()`` it on shutdown can keep a reference. The task is
    also tracked module-internally so it cannot be GC'd prematurely.
    """
    task = asyncio.create_task(coro, name=name)
    _pending.add(task)
    task.add_done_callback(_on_done)
    return task
