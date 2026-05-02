"""Client-agnostic application services.

Each service encapsulates one piece of domain logic (billing, search,
profile, team…) behind a narrow interface. Adapters (Telegram, web
API) call these services instead of reimplementing the same rules.
"""

from leadgen.core.services.billing_service import (
    BillingError,
    BillingService,
    QuotaCheck,
)
from leadgen.core.services.email_sender import (
    mask_email,
    render_account_locked_email,
    render_email_changed_alert,
    render_email_recovery_email,
    render_new_device_login_email,
    render_password_changed_email,
    render_password_reset_email,
    render_verification_email,
    send_email,
)
from leadgen.core.services.profile_service import ProfileService, ProfileUpdate
from leadgen.core.services.progress_broker import (
    BrokerProgressSink,
    ProgressBroker,
    ProgressEvent,
    default_broker,
)
from leadgen.core.services.sinks import DeliverySink, NullSink, ProgressSink

__all__ = [
    "BillingError",
    "BillingService",
    "BrokerProgressSink",
    "DeliverySink",
    "NullSink",
    "ProfileService",
    "ProfileUpdate",
    "ProgressBroker",
    "ProgressEvent",
    "ProgressSink",
    "QuotaCheck",
    "default_broker",
    "mask_email",
    "render_account_locked_email",
    "render_email_changed_alert",
    "render_email_recovery_email",
    "render_new_device_login_email",
    "render_password_changed_email",
    "render_password_reset_email",
    "render_verification_email",
    "send_email",
]
