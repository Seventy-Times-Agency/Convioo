"""Web adapter implementations of ProgressSink + DeliverySink.

Progress is already handled by ``BrokerProgressSink`` (it publishes
phase/update/finish events to the in-process ``default_broker``; the
``/api/v1/searches/{id}/progress`` SSE endpoint subscribes). This
module is only the **delivery** side.

Unlike the Telegram sink — which has to send messages and an Excel
file over HTTP to a client that can't come back later — the web path
is pull-based: the frontend will hit
``GET /api/v1/searches/{id}/leads`` whenever the user opens the
session. So ``WebDeliverySink`` doesn't need to do anything with the
leads themselves (they were already persisted in ``search.py`` step
3). Its one real job is to stop ``_cleanup_leads`` from wiping them,
which is achieved by gating on ``SearchQuery.source == "web"`` — this
sink exists as an explicit marker for that flow and to log delivery
for debugging.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from leadgen.analysis.aggregator import BaseStats
    from leadgen.db.models import Lead

logger = logging.getLogger(__name__)


class WebDeliverySink:
    """No-op delivery sink for web-initiated searches.

    The frontend fetches leads + analysis via REST after the search
    completes, so there's nothing to push here. We still log each
    callback so production issues are easy to trace in Railway logs.
    """

    def __init__(self, search_id: Any) -> None:
        self.search_id = search_id
        self.any_delivered = False

    async def deliver_stats(
        self, niche: str, region: str, stats: BaseStats
    ) -> None:
        logger.info(
            "web_delivery: stats ready search_id=%s niche=%s region=%s leads=%s",
            self.search_id,
            niche,
            region,
            getattr(stats, "total", "?"),
        )
        self.any_delivered = True

    async def deliver_insights(self, insights: str) -> None:
        logger.info(
            "web_delivery: insights ready search_id=%s len=%d",
            self.search_id,
            len(insights or ""),
        )
        self.any_delivered = True

    async def deliver_top_leads(self, leads: list[Lead]) -> None:
        logger.info(
            "web_delivery: top leads ready search_id=%s count=%d",
            self.search_id,
            len(leads),
        )
        self.any_delivered = True

    async def deliver_excel(
        self, leads: list[Lead], niche: str, region: str
    ) -> None:
        # Web users download Excel on demand via a REST endpoint; the
        # pipeline-generated buffer isn't needed here. No-op by design.
        logger.info(
            "web_delivery: excel generation skipped (web path) search_id=%s",
            self.search_id,
        )
