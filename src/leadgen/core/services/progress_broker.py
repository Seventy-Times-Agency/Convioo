"""In-process progress broker: search workers publish, SSE consumers subscribe.

Designed to work without Redis — a simple asyncio ``Queue`` per search
id, kept in a module-level dict, cleared when the search completes.
Fine for a single-process deploy (bot + FastAPI sharing an event loop,
which is what we have today).

When we move to a multi-worker setup (arq workers in one container, a
web API in another), swap this for Redis pub/sub keyed on search id;
the ``publish``/``subscribe`` contract stays identical.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ProgressEvent:
    kind: str  # "phase" | "update" | "finish"
    data: dict[str, Any]


class ProgressBroker:
    """Lets many SSE clients tail progress for one search at once.

    Each ``subscribe`` call gets its own async queue; ``publish`` fans
    out to every live subscriber. When the search finishes, ``close``
    sends a sentinel so every subscriber loop can exit cleanly.
    """

    def __init__(self) -> None:
        # search_id -> list of per-subscriber queues
        self._subs: dict[uuid.UUID, list[asyncio.Queue[ProgressEvent | None]]] = {}

    async def publish(self, search_id: uuid.UUID, event: ProgressEvent) -> None:
        for q in list(self._subs.get(search_id, [])):
            # Non-blocking: drop events if a subscriber can't keep up.
            # Progress is advisory, not authoritative — losing one phase
            # beat is better than stalling the search worker.
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)

    async def close(self, search_id: uuid.UUID) -> None:
        for q in list(self._subs.get(search_id, [])):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(None)
        self._subs.pop(search_id, None)

    async def subscribe(self, search_id: uuid.UUID) -> AsyncIterator[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent | None] = asyncio.Queue(maxsize=64)
        self._subs.setdefault(search_id, []).append(q)
        try:
            while True:
                event = await q.get()
                if event is None:
                    return
                yield event
        finally:
            subs = self._subs.get(search_id, [])
            with contextlib.suppress(ValueError):
                subs.remove(q)
            if not subs:
                self._subs.pop(search_id, None)


# Module-level singleton — both the web sink (publisher) and the SSE
# endpoint (subscriber) import this.
default_broker = ProgressBroker()


class BrokerProgressSink:
    """ProgressSink implementation that publishes to a ``ProgressBroker``.

    Used by the web adapter: the search worker writes beats here, any
    number of SSE clients watching the same search id receive them.
    """

    def __init__(self, broker: ProgressBroker, search_id: uuid.UUID) -> None:
        self._broker = broker
        self._search_id = search_id

    async def phase(self, title: str, subtitle: str = "") -> None:
        await self._broker.publish(
            self._search_id,
            ProgressEvent("phase", {"title": title, "subtitle": subtitle}),
        )

    async def update(self, done: int, total: int) -> None:
        await self._broker.publish(
            self._search_id,
            ProgressEvent("update", {"done": done, "total": total}),
        )

    async def finish(self, text: str) -> None:
        await self._broker.publish(
            self._search_id, ProgressEvent("finish", {"text": text})
        )
        await self._broker.close(self._search_id)
