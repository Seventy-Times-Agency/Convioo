"""Team and invite schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: str
    description: str | None = None
    initials: str
    color: str
    email: str | None = None
    last_active: str | None = None
    #: Сколько лидов сейчас закреплено за участником — колонка «Лидов»
    #: на экране Команды.
    leads_count: int = 0
    #: Команда внутри компании; NULL — общий пул.
    squad_id: uuid.UUID | None = None
    avatar_url: str | None = None
    target_calls_day: int | None = None
    target_goals_week: int | None = None


class TeamSummary(BaseModel):
    """One team a user belongs to, with their role on it."""

    id: uuid.UUID
    name: str
    plan: str
    role: str
    member_count: int
    created_at: datetime


class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    # Kept for backwards compat with the existing frontend client; the
    # backend now derives the owner from the session and ignores it.
    owner_user_id: int | None = None


class TeamDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    plan: str
    created_at: datetime
    role: str  # the caller's role on this team
    #: Автораспределение Базы (см. Team.auto_distribute).
    auto_distribute: bool = False
    members: list[TeamMemberResponse]
    #: Отправленные и ещё не принятые приглашения — карточка
    #: «Приглашения» на экране Команды.
    pending_invites: int = 0


class TeamUpdateRequest(BaseModel):
    """Owner-only PATCH for the team's editable fields.

    The acting user comes from the session; a legacy ``by_user_id``
    field in the payload is ignored.
    """

    name: str | None = Field(default=None, min_length=2, max_length=120)
    # Справка о компании целиком — 4000 знаков, чтобы не резать её.
    description: str | None = Field(default=None, max_length=4000)
    auto_distribute: bool | None = None


class MembershipUpdateRequest(BaseModel):
    """Owner-only PATCH for one teammate's description / role.

    Sets the short note Henry uses to introduce the member to the
    rest of the team ("Анна — закрывает стоматологии в EU"). The
    acting user comes from the session; a legacy ``by_user_id``
    field in the payload is ignored.
    """

    description: str | None = Field(default=None, max_length=1000)
    role: str | None = Field(default=None, max_length=32)
    #: План на человека; 0 — снять план.
    target_calls_day: int | None = Field(default=None, ge=0, le=1000)
    target_goals_week: int | None = Field(default=None, ge=0, le=1000)
    #: Перемещение между командами компании. Пустая строка — в общий
    #: пул (None в JSON означал бы «не менять»).
    squad_id: uuid.UUID | Literal[""] | None = None


class InviteCreateRequest(BaseModel):
    # The inviter is the authenticated session — a legacy
    # ``by_user_id`` field in the payload is ignored.
    role: str = Field(default="member", max_length=32)
    ttl_seconds: int = Field(default=600, ge=60, le=86400)


class InviteResponse(BaseModel):
    """Invite payload shown to the owner who just generated it."""

    token: str
    team_id: uuid.UUID
    team_name: str
    role: str
    expires_at: datetime


class InvitePreview(BaseModel):
    """Limited preview a non-member sees before accepting."""

    team_id: uuid.UUID
    team_name: str
    role: str
    expires_at: datetime
    expired: bool
    accepted: bool


class TeamMemberSummary(BaseModel):
    """Owner-facing roll-up of one teammate's activity.

    Powers the "see each member's CRM" panel on the owner's team
    page; click a row and the workspace switches to viewing that
    member's data via ``member_user_id`` on the list endpoints.
    """

    user_id: int
    name: str
    role: str
    sessions_total: int
    leads_total: int
    hot_total: int


class TeamAnalyticsStatusBucket(BaseModel):
    status: str
    leads_count: int


class TeamAnalyticsSourceBucket(BaseModel):
    source: str
    leads_count: int


class TeamAnalyticsMemberBucket(BaseModel):
    user_id: int
    name: str
    searches_total: int
    leads_total: int
    hot_leads: int
    avg_score: float | None


class TeamAnalyticsNicheBucket(BaseModel):
    niche: str
    searches_total: int


class TeamAnalyticsTimepoint(BaseModel):
    date: str  # ISO YYYY-MM-DD
    searches_total: int
    leads_total: int


class TeamAnalytics(BaseModel):
    """``GET /api/v1/teams/{team_id}/analytics`` payload."""

    team_id: str
    period_from: datetime
    period_to: datetime
    searches_total: int
    leads_total: int
    avg_lead_score: float | None
    avg_lead_cost_usd: float | None
    status_breakdown: list[TeamAnalyticsStatusBucket]
    top_source: TeamAnalyticsSourceBucket | None
    top_member: TeamAnalyticsMemberBucket | None
    top_niche: TeamAnalyticsNicheBucket | None
    members: list[TeamAnalyticsMemberBucket]
    sources: list[TeamAnalyticsSourceBucket]
    niches: list[TeamAnalyticsNicheBucket]
    timeseries: list[TeamAnalyticsTimepoint]


class MemberTelephony(BaseModel):
    extension: str | None = None
    #: True/False для SIP-логина, None — номер телефона или проверка
    #: недоступна.
    online: bool | None = None


class OverviewMember(BaseModel):
    id: int
    name: str
    role: str
    description: str | None = None
    initials: str
    color: str
    avatar_url: str | None = None
    squad_id: uuid.UUID | None = None
    leads_count: int = 0
    hot_count: int = 0
    calls_today: int = 0
    talks_today: int = 0
    calls_7d: int = 0
    talks_7d: int = 0
    goals_7d: int = 0
    target_calls_day: int | None = None
    target_goals_week: int | None = None
    telephony: MemberTelephony
    #: Что может делать вызывающий с этой строкой.
    can_edit: bool = False
    can_change_role: bool = False
    can_set_targets: bool = False
    can_view_as: bool = False
    can_remove: bool = False


class TeamOverview(BaseModel):
    team_id: uuid.UUID
    name: str
    description: str | None
    role: str
    created_at: str | None = None
    people: int
    people_by_role: dict[str, int]
    leads_in_work: int
    leads_total: int
    free_pool: int
    calls_today: int
    talks_today: int
    goals_7d: int
    pending_invites: int
    members: list[OverviewMember]
