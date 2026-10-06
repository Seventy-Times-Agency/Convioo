"""``/api/v1/teams/{id}/connections`` — вкладка «Подключения».

Два уровня: общие для команды (бот Telegram компании, Agency OS) и
личные у каждого сотрудника (его почта, его Telegram). Личные человек
подключает сам в профиле; здесь руководитель только видит, у кого что
подключено.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import _DEMO_TEAM_COLORS, membership
from leadgen.config import get_settings
from leadgen.core.services.account.team_permissions import ROLE_ADMIN, ROLE_OWNER, normalize_role
from leadgen.db.models import OAuthCredential, TeamMembership, TelegramConnection, User
from leadgen.db.session import session_factory

router = APIRouter(tags=["connections"])


class MemberConnections(BaseModel):
    user_id: int
    name: str
    role: str
    color: str
    avatar_url: str | None = None
    mail_provider: str | None = None
    mail_address: str | None = None
    telegram: bool = False


class TeamConnections(BaseModel):
    telegram_bot: bool
    members: list[MemberConnections]


@router.get("/api/v1/teams/{team_id}/connections", response_model=TeamConnections)
async def team_connections(
    team_id: uuid.UUID, current_user: User = Depends(get_current_user)
) -> TeamConnections:
    async with session_factory() as session:
        ms = await membership(session, team_id, current_user.id)
        if ms is None or normalize_role(ms.role) not in {ROLE_OWNER, ROLE_ADMIN}:
            raise HTTPException(status_code=403, detail="owner or head of sales only")
        rows = (
            await session.execute(
                select(TeamMembership, User)
                .join(User, User.id == TeamMembership.user_id)
                .where(TeamMembership.team_id == team_id)
                .order_by(TeamMembership.created_at)
            )
        ).all()
        ids = [u.id for _m, u in rows]
        creds = (
            await session.execute(
                select(OAuthCredential)
                .where(OAuthCredential.user_id.in_(ids))
                .where(OAuthCredential.provider.in_(["gmail", "outlook"]))
            )
        ).scalars().all()
        tg = set(
            (
                await session.execute(
                    select(TelegramConnection.user_id).where(TelegramConnection.user_id.in_(ids))
                )
            ).scalars()
        )
    mail: dict[int, OAuthCredential] = {}
    for c in creds:
        mail.setdefault(c.user_id, c)
    members = []
    for i, (m, u) in enumerate(rows):
        c = mail.get(u.id)
        members.append(
            MemberConnections(
                user_id=u.id,
                name=u.display_name or " ".join(filter(None, [u.first_name, u.last_name])) or f"User {u.id}",
                role=m.role,
                color=_DEMO_TEAM_COLORS[i % len(_DEMO_TEAM_COLORS)],
                avatar_url=u.avatar_url,
                mail_provider=c.provider if c else None,
                mail_address=getattr(c, "account_email", None) if c else None,
                telegram=u.id in tg,
            )
        )
    return TeamConnections(telegram_bot=bool(get_settings().telegram_bot_token), members=members)
