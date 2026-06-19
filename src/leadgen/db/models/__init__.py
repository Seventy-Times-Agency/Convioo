"""Re-export all ORM models from domain modules.

Existing code that does ``from leadgen.db.models import Lead`` keeps
working without any changes.
"""

from .base import _JSONB, _UUID, Base, _utcnow
from .integration import (
    AffiliateCode,
    AssistantMemory,
    OAuthConsumedNonce,
    OAuthCredential,
    Referral,
    StripeEvent,
    UserIntegrationCredential,
    Webhook,
)
from .lead import (
    Lead,
    LeadActivity,
    LeadCustomField,
    LeadMark,
    LeadSegment,
    LeadStatus,
    LeadTag,
    LeadTagAssignment,
    LeadTask,
    UserSeenLead,
)
from .outreach import (
    EmailDailySend,
    EmailMessage,
    EmailSequence,
    OutreachTemplate,
    SequenceEnrollment,
)
from .search import SavedSearch, SearchQuery
from .team import Team, TeamInvite, TeamMembership, TeamSeenLead
from .user import (
    EmailVerificationToken,
    PasswordResetToken,
    User,
    UserApiKey,
    UserAuditLog,
    UserSession,
)

__all__ = [
    # base
    "Base",
    "_JSONB",
    "_UUID",
    "_utcnow",
    # user
    "User",
    "UserSession",
    "UserApiKey",
    "EmailVerificationToken",
    "PasswordResetToken",
    "UserAuditLog",
    # search
    "SearchQuery",
    "SavedSearch",
    # lead
    "Lead",
    "LeadMark",
    "LeadTag",
    "LeadTagAssignment",
    "LeadStatus",
    "LeadCustomField",
    "LeadActivity",
    "LeadTask",
    "LeadSegment",
    "UserSeenLead",
    # team
    "Team",
    "TeamMembership",
    "TeamInvite",
    "TeamSeenLead",
    # outreach
    "OutreachTemplate",
    "EmailDailySend",
    "EmailMessage",
    "EmailSequence",
    "SequenceEnrollment",
    # integration
    "OAuthCredential",
    "OAuthConsumedNonce",
    "UserIntegrationCredential",
    "Webhook",
    "StripeEvent",
    "AffiliateCode",
    "Referral",
    "AssistantMemory",
]
