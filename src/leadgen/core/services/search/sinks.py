"""Client-side observability protocols for a long-running search.

The pipeline talks to the outside world only through these two
protocols:

- ``ProgressSink`` — receives phase transitions and progress bar
  updates. The web adapter pushes JSON events over SSE; a CLI could
  just print.
- ``DeliverySink`` — receives the final stats card, insights, top
  leads and Excel bytes. The web adapter persists them so the
  dashboard can render the session.

Both protocols are ``runtime_checkable`` Protocols, so callers can
``isinstance()``-check a sink without worrying about nominal typing.
``NullSink`` is a no-op default for CLI / batch use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from leadgen.analysis.aggregator import BaseStats
    from leadgen.db.models import Lead


@runtime_checkable
class ProgressSink(Protocol):
    async def phase(self, title: str, subtitle: str = "") -> None: ...
    async def update(self, done: int, total: int) -> None: ...
    async def finish(self, text: str) -> None: ...


@runtime_checkable
class DeliverySink(Protocol):
    async def deliver_stats(
        self, niche: str, region: str, stats: BaseStats
    ) -> None: ...
    async def deliver_insights(self, insights: str) -> None: ...
    async def deliver_top_leads(self, leads: list[Lead]) -> None: ...
    async def deliver_excel(
        self, leads: list[Lead], niche: str, region: str
    ) -> None: ...


class NullSink:
    """Silently absorbs all progress + delivery calls.

    Useful for CLI runs, batch jobs and tests that just want to know
    whether the search completed without needing to inspect the UI
    side effects.
    """

    async def phase(self, title: str, subtitle: str = "") -> None:
        return None

    async def update(self, done: int, total: int) -> None:
        return None

    async def finish(self, text: str) -> None:
        return None

    async def deliver_stats(
        self, niche: str, region: str, stats: Any
    ) -> None:
        return None

    async def deliver_insights(self, insights: str) -> None:
        return None

    async def deliver_top_leads(self, leads: Any) -> None:
        return None

    async def deliver_excel(
        self, leads: Any, niche: str, region: str
    ) -> None:
        return None
