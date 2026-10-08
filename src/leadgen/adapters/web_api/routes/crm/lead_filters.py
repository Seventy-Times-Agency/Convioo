"""Фильтры и сортировка списка лидов + счётчики для панели «Базы».

Один набор условий на всё: список лидов (``GET /api/v1/leads``) и
счётчики панели слева (``GET /api/v1/leads/facets``). Счётчики
«разъединённые»: у каждой группы (ниша, город, кто ведёт…) количество
считается с учётом всех остальных выбранных фильтров, но без своего —
иначе, выбрав одну нишу, человек видел бы нули у всех остальных.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import membership
from leadgen.core.services.account.team_permissions import is_sales
from leadgen.db.models import Lead, SearchQuery, User
from leadgen.db.session import session_factory

router = APIRouter(tags=["leads"])

HOT = 75
WARM = 50


@dataclass(slots=True)
class LeadFilters:
    q: str | None = None
    niches: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    owners: list[int] = field(default_factory=list)
    free: bool = False
    temps: list[str] = field(default_factory=list)
    has_phone: bool = False
    has_email: bool = False
    no_website: bool = False
    added_after: datetime | None = None


def parse_filters(
    q: str | None,
    niche: list[str] | None,
    region: list[str] | None,
    owner: list[str] | None,
    temps: str | None,
    has_phone: bool,
    has_email: bool,
    no_website: bool,
    added_after: datetime | None,
) -> LeadFilters:
    owners: list[int] = []
    free = False
    for raw in owner or []:
        if raw == "free":
            free = True
        else:
            try:
                owners.append(int(raw))
            except ValueError:
                continue
    return LeadFilters(
        q=(q or "").strip() or None,
        niches=[n for n in (niche or []) if n],
        regions=[r for r in (region or []) if r],
        owners=owners,
        free=free,
        temps=[t for t in (temps or "").split(",") if t in ("hot", "warm", "cold")],
        has_phone=has_phone,
        has_email=has_email,
        no_website=no_website,
        added_after=added_after,
    )


def _temp_clause(temp: str):
    if temp == "hot":
        return Lead.score_ai >= HOT
    if temp == "warm":
        return (Lead.score_ai >= WARM) & (Lead.score_ai < HOT)
    return (Lead.score_ai < WARM) | Lead.score_ai.is_(None)


def filter_clauses(f: LeadFilters, *, skip: str | None = None) -> list[Any]:
    """Условия WHERE. ``skip`` — группа, которую не применять (для её
    же счётчиков). Запрос должен уже содержать JOIN на SearchQuery."""
    out: list[Any] = []
    if f.q:
        like = f"%{f.q.lower()}%"
        out.append(
            func.lower(func.coalesce(Lead.name, "")).like(like)
            | func.lower(func.coalesce(Lead.address, "")).like(like)
            | func.lower(func.coalesce(Lead.category, "")).like(like)
        )
    if f.niches and skip != "niche":
        out.append(SearchQuery.niche.in_(f.niches))
    if f.regions and skip != "region":
        out.append(SearchQuery.region.in_(f.regions))
    if (f.owners or f.free) and skip != "owner":
        cond = Lead.owner_user_id.in_(f.owners) if f.owners else None
        if f.free:
            cond = Lead.owner_user_id.is_(None) if cond is None else (cond | Lead.owner_user_id.is_(None))
        out.append(cond)
    if f.temps and skip != "temp":
        cond = None
        for t in f.temps:
            c = _temp_clause(t)
            cond = c if cond is None else (cond | c)
        out.append(cond)
    if skip != "contacts":
        if f.has_phone:
            out.append(func.coalesce(Lead.phone, "") != "")
        if f.has_email:
            out.append(func.coalesce(Lead.contact_email, "") != "")
        if f.no_website:
            out.append(func.coalesce(Lead.website, "") == "")
    if f.added_after is not None:
        out.append(Lead.created_at >= f.added_after)
    return out


SORTS = ("score", "name", "region", "owner", "created")


def apply_sort(stmt, sort: str | None, order: str | None):
    """Сортировка списка. По «кто ведёт» — по имени продажника."""
    desc = (order or "").lower() != "asc"
    key = sort if sort in SORTS else "score"

    def o(col):
        return col.desc().nullslast() if desc else col.asc().nullslast()

    if key == "name":
        return stmt.order_by(o(func.lower(Lead.name)))
    if key == "region":
        return stmt.order_by(o(SearchQuery.region), Lead.score_ai.desc().nullslast())
    if key == "owner":
        owner_name = (
            select(func.coalesce(User.display_name, User.first_name, User.email))
            .where(User.id == Lead.owner_user_id)
            .scalar_subquery()
        )
        return stmt.order_by(o(owner_name), Lead.score_ai.desc().nullslast())
    if key == "created":
        return stmt.order_by(o(Lead.created_at))
    return stmt.order_by(o(Lead.score_ai), Lead.created_at.desc())


async def _base_scope(session, team_id: uuid.UUID | None, user_id: int) -> list[Any]:
    """Те же границы, что у «Базы» в списке: нетронутые лиды команды
    (тимлид группы — своя группа и свободные) или свои личные."""
    clauses: list[Any] = [
        SearchQuery.source == "web",
        Lead.deleted_at.is_(None),
        Lead.archived_at.is_(None),
        Lead.lead_status == "new",
    ]
    if team_id is None:
        clauses += [SearchQuery.user_id == user_id, SearchQuery.team_id.is_(None)]
        return clauses
    ms = await membership(session, team_id, user_id)
    if ms is None:
        raise HTTPException(status_code=403, detail="not a team member")
    if is_sales(ms.role):
        raise HTTPException(status_code=403, detail="the base is a manager's tool")
    clauses.append(SearchQuery.team_id == team_id)
    from leadgen.core.services.account.squads import visible_member_ids

    scope_ids = await visible_member_ids(session, team_id, user_id)
    if scope_ids is not None:
        clauses.append(Lead.owner_user_id.in_(scope_ids) | Lead.owner_user_id.is_(None))
    return clauses


@router.get("/api/v1/leads/facets")
async def base_facets(
    team_id: uuid.UUID | None = None,
    q: str | None = None,
    niche: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    owner: list[str] | None = Query(default=None),
    temps: str | None = None,
    has_phone: bool = False,
    has_email: bool = False,
    no_website: bool = False,
    added_after: datetime | None = None,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Счётчики для панели фильтров «Базы»."""
    f = parse_filters(q, niche, region, owner, temps, has_phone, has_email, no_website, added_after)
    async with session_factory() as session:
        scope = await _base_scope(session, team_id, current_user.id)

        def base(skip: str | None = None):
            return (
                select(func.count(Lead.id))
                .select_from(Lead)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(*scope, *filter_clauses(f, skip=skip))
            )

        async def grouped(col, skip: str) -> list[tuple[Any, int]]:
            stmt = (
                select(col, func.count(Lead.id))
                .select_from(Lead)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(*scope, *filter_clauses(f, skip=skip))
                .group_by(col)
                .order_by(func.count(Lead.id).desc())
            )
            return [(k, int(n)) for k, n in (await session.execute(stmt)).all()]

        total = int((await session.execute(base())).scalar() or 0)
        niches = await grouped(SearchQuery.niche, "niche")
        regions = await grouped(SearchQuery.region, "region")
        owners_raw = await grouped(Lead.owner_user_id, "owner")
        temp_counts = {}
        for t in ("hot", "warm", "cold"):
            temp_counts[t] = int(
                (await session.execute(base("temp").where(_temp_clause(t)))).scalar() or 0
            )
        contacts = {
            "phone": int((await session.execute(base("contacts").where(func.coalesce(Lead.phone, "") != ""))).scalar() or 0),
            "email": int(
                (await session.execute(base("contacts").where(func.coalesce(Lead.contact_email, "") != ""))).scalar() or 0
            ),
            "no_website": int(
                (await session.execute(base("contacts").where(func.coalesce(Lead.website, "") == ""))).scalar() or 0
            ),
        }
        ids = [k for k, _ in owners_raw if k is not None]
        names: dict[int, str] = {}
        if ids:
            for u in (await session.execute(select(User).where(User.id.in_(ids)))).scalars():
                names[u.id] = (
                    u.display_name or " ".join(filter(None, [u.first_name, u.last_name])) or u.email or f"#{u.id}"
                )
    return {
        "total": total,
        "free": next((n for k, n in owners_raw if k is None), 0),
        "owners": [{"id": k, "name": names.get(k, f"#{k}"), "count": n} for k, n in owners_raw if k is not None],
        "niches": [{"value": k, "count": n} for k, n in niches if k],
        "regions": [{"value": k, "count": n} for k, n in regions if k],
        "temps": temp_counts,
        "contacts": contacts,
    }
