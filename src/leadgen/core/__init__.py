"""Business logic that is client-agnostic.

Anything in ``core`` must not import from ``leadgen.adapters`` or any
FastAPI-specific code. That way the same services are reused by the
web adapter, by background workers, and by anything else (CLI, CRON).

Currently exposes service facades. Low-level building blocks
(collectors, DB models, AI analyzer) still live at the package root;
they're already framework-neutral.
"""

from leadgen.core.services.billing_service import (
    BillingError,
    BillingService,
    QuotaCheck,
)
from leadgen.core.services.profile_service import ProfileService, ProfileUpdate
from leadgen.core.services.sinks import DeliverySink, NullSink, ProgressSink

__all__ = [
    "BillingError",
    "BillingService",
    "DeliverySink",
    "NullSink",
    "ProfileService",
    "ProfileUpdate",
    "ProgressSink",
    "QuotaCheck",
]
