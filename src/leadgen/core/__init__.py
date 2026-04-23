"""Business logic that is client-agnostic.

Anything in ``core`` must not import from ``leadgen.bot`` or any
aiogram/FastAPI-specific code. That way the same services are reused
by the Telegram adapter, by a future web adapter, and by anything else
(CLI, CRON, background workers).

Currently exposes service facades. Low-level building blocks
(collectors, DB models, AI analyzer) still live at the package root;
they're already framework-neutral.
"""

from leadgen.core.services.billing_service import (
    BillingError,
    BillingService,
    QuotaCheck,
)

__all__ = ["BillingError", "BillingService", "QuotaCheck"]
