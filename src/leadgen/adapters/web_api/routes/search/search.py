"""``/api/v1/searches/*`` — search creation, listing, search-leads."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update

from leadgen.adapters.web_api.auth import (
    enforce_rate_limit,
    get_current_user,
    request_ip,
)
from leadgen.adapters.web_api.routes._helpers import (
    ACTIVE_SEARCH_STATUSES,
    has_active_search,
    launch_search,
    marks_for_user,
    membership,
    money_hidden_for,
    resolve_team_view,
    search_access,
    start_next_queued_search,
    tags_by_lead,
    team_prior_searches,
    to_lead_response,
    to_summary,
)
from leadgen.adapters.web_api.routes._helpers import (
    temp as compute_temp,
)
from leadgen.adapters.web_api.schemas import (
    LeadResponse,
    SearchCreate,
    SearchCreateResponse,
    SearchPreflightResponse,
    SearchSummary,
)
from leadgen.config import get_settings
from leadgen.core.services import BillingService, default_broker
from leadgen.core.services.account.team_permissions import (
    ROLE_ADMIN,
    ROLE_OWNER,
    can_run_search,
    can_view_all_leads,
    is_sales,
    normalize_role,
)
from leadgen.db.models import (
    Lead,
    SearchQuery,
    Team,
    User,
)
from leadgen.db.session import session_factory
from leadgen.utils.locale_text import pick
from leadgen.utils.rate_limit import (
    search_ip_limiter,
    search_team_limiter,
    search_user_limiter,
)

router = APIRouter(tags=["search"])


@router.get(
    "/api/v1/searches/preflight",
    response_model=SearchPreflightResponse,
)
async def search_preflight(
    niche: str,
    region: str,
    team_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
) -> SearchPreflightResponse:
    """Tell the UI whether this niche+region combo is safe to run."""
    if team_id is None:
        return SearchPreflightResponse(blocked=False, matches=[])
    async with session_factory() as session:
        m = await membership(session, team_id, current_user.id)
        if m is None:
            raise HTTPException(status_code=403, detail="not a team member")
        matches = await team_prior_searches(session, team_id, niche, region)
    return SearchPreflightResponse(blocked=bool(matches), matches=matches)


@router.get("/api/v1/searches/estimate")
async def search_estimate(
    leads: int = 50,
    find_decision_makers: bool = False,
    current_user: User = Depends(get_current_user),  # noqa: ARG001 — auth gate
) -> dict:
    """Оценка запуска до нажатия кнопки.

    Наружу идут токены — их пользователь и тратит. Доллары остаются
    в ответе для админки платформы и потому, что цену токена ещё
    предстоит назначить, сравнив одно с другим.
    """
    from leadgen.core.services.account.tokens import quote
    from leadgen.core.services.search.cost_control import (
        COST_PER_ENRICHED_LEAD_USD,
        estimate_search_cost,
    )

    n = max(1, min(int(leads), 500))
    q = quote(n, find_decision_makers=find_decision_makers)
    return {
        "leads": n,
        "tokens": q.total,
        "tokens_per_lead": q.per_lead,
        "tokens_breakdown": q.breakdown,
        "cost_usd": estimate_search_cost(n),
        "cost_per_lead_usd": COST_PER_ENRICHED_LEAD_USD,
    }


@router.get("/api/v1/searches/channels")
async def search_channels(
    current_user: User = Depends(get_current_user),  # noqa: ARG001 — auth gate
) -> dict:
    """Каналы для расширенного поиска.

    Тексты живут на сервере, а не в форме: описание канала — часть
    продукта, а не вёрстки, и меняется вместе с набором коллекторов.
    Имён вендоров здесь нет намеренно.
    """
    from leadgen.core.services.search.search_channels import CHANNELS

    return {
        "channels": [
            {
                "key": c.key,
                "title": c.title,
                "what": c.what,
                "limit": c.limit,
                "required": c.required,
            }
            for c in CHANNELS
        ]
    }


async def _launch_profile(
    session,
    user: User | None,
    body: SearchCreate,
    team_id: uuid.UUID | None,
    user_id: int,
) -> dict[str, Any]:
    """Профиль для оценки ИИ: кто запускает, что продаёт, «кто мы»."""
    profile: dict[str, Any] = {}
    if user is not None:
        profile = {
            "display_name": user.display_name or user.first_name,
            "age_range": user.age_range,
            "gender": user.gender,
            "business_size": user.business_size,
            "profession": user.profession,
            "service_description": user.service_description,
            "home_region": user.home_region,
            "niches": list(user.niches or []),
            "language_code": user.language_code,
        }
    if body.language_code:
        profile["language_code"] = body.language_code
    if body.profession:
        profile["profession"] = body.profession
    # Командный контекст для скоринга и советов: «кто мы» из профиля
    # команды и роль запускающего. Продукт не зашит под одно
    # агентство — ИИ читает то, что владелец написал о своей команде.
    if team_id is not None:
        team = await session.get(Team, team_id)
        ms = await membership(session, team_id, user_id)
        if team is not None and team.description:
            profile["team_about"] = team.description
        if ms is not None and ms.description:
            profile["member_note"] = ms.description
    return profile


@router.post("/api/v1/searches", response_model=SearchCreateResponse)
async def create_search(
    body: SearchCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> SearchCreateResponse:
    """Create a SearchQuery row + launch the pipeline.

    The search owner is always the authenticated caller — a
    ``user_id`` in the body (legacy clients) is ignored.
    """
    ip = request_ip(request)
    enforce_rate_limit(
        search_user_limiter, f"user:{current_user.id}", retry_hint=300
    )
    if body.team_id is not None:
        enforce_rate_limit(
            search_team_limiter, f"team:{body.team_id}", retry_hint=300
        )
    enforce_rate_limit(
        search_ip_limiter, f"ip:{ip or '?'}", retry_hint=300
    )
    return await start_search(current_user, body)


async def start_search(
    current_user: User, body: SearchCreate, *, repeat: bool = False
) -> SearchCreateResponse:
    """Единственный путь запуска поиска: квота, подтверждение почты,
    роль в команде, лимит расходов, резерв токенов, очередь городов.

    Им пользуются кнопка «Найти», сохранённые поиски (вручную и по
    расписанию) и Henry — раньше у каждого были свои, разные проверки.
    ``repeat`` — повтор сохранённого поиска: та же ниша и город в
    команде здесь ожидаемы, а не повод для отказа.
    """
    async with session_factory() as session:
        billing = BillingService(session)
        quota = await billing.try_consume(current_user.id)
        if not quota.allowed:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"Quota exhausted ({quota.queries_used}/{quota.queries_limit})."
                ),
            )
        user = await session.get(User, current_user.id)
        if (
            get_settings().require_email_verification
            and user is not None
            and user.id < 0
            and user.email is not None
            and user.email_verified_at is None
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=pick(
                    user.language_code,
                    ru=(
                        "Подтвердите email чтобы запускать поиски. "
                        "Ссылка отправлена на " + (user.email or "ваш ящик") + "."
                    ),
                    uk=(
                        "Підтвердьте email, щоб запускати пошуки. "
                        "Посилання надіслано на "
                        + (user.email or "вашу скриньку")
                        + "."
                    ),
                    en=(
                        "Verify your email to launch searches. "
                        "The link was sent to "
                        + (user.email or "your inbox")
                        + "."
                    ),
                ),
            )

        team_id = body.team_id
        if team_id is not None:
            m = await membership(session, team_id, current_user.id)
            if m is None:
                raise HTTPException(
                    status_code=403,
                    detail="user is not a member of this team",
                )
            # Prospecting is a manager+ capability — sales reps work
            # assigned leads only and never see the parsing surface.
            if not can_run_search(m.role):
                raise HTTPException(
                    status_code=403,
                    detail="your role can't launch searches in this team",
                )
            # Бюджет команды — это токены: запуск останавливает только
            # «стоп на нуле» (ниже, при резерве). Доллары остаются
            # отчётом о себестоимости; на 80% — одно предупреждение
            # владельцу в день.
            from leadgen.core.services.search.cost_control import (
                get_team_cost_status,
                maybe_warn_owner,
            )

            cost_status = await get_team_cost_status(session, team_id)
            if cost_status.warning:
                await maybe_warn_owner(session, team_id, cost_status)
            prior = (
                []
                if repeat
                else await team_prior_searches(
                    session, team_id, body.niche, body.region
                )
            )
            if prior:
                first = prior[0]
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"This niche+region was already searched in this "
                        f"team by {first.user_name} on "
                        f"{first.created_at:%Y-%m-%d} "
                        f"({first.leads_count} leads). Pick a different "
                        f"angle so two members don't chase the same companies."
                    ),
                )
        else:
            # Личное пространство не обходит контроль затрат: без
            # команды нет владельческого потолка, поэтому действует
            # лимит платформы (PERSONAL_MONTHLY_COST_CAP_USD).
            from leadgen.core.services.search.cost_control import (
                get_personal_cost_status,
            )

            personal = await get_personal_cost_status(current_user.id)
            if personal.blocked:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=(
                        "Месячный лимит затрат личного пространства "
                        f"исчерпан: ${personal.month_cost_usd:.2f} из "
                        f"${personal.cap_usd:.2f}. Лимит обновится в "
                        "новом месяце; для больших объёмов работайте "
                        "в командном пространстве."
                    ),
                )

        scope = (body.scope or "city").strip().lower()
        if scope not in {"city", "metro", "state", "country"}:
            scope = "city"
        radius_m_value: int | None = None
        if scope in {"city", "metro"} and body.radius_km is not None:
            radius_m_value = max(0, min(int(body.radius_km), 100)) * 1000

        allowed_sources = {"google", "osm", "yelp", "foursquare"}
        enabled_sources_value: list[str] | None = None
        if body.enabled_sources:
            enabled_sources_value = sorted(
                {
                    s.strip().lower()
                    for s in body.enabled_sources
                    if s.strip().lower() in allowed_sources
                }
            ) or None
        # Расширенный поиск присылает каналы, а не источники. Каналы
        # выигрывают: enabled_sources остаётся для старых клиентов и
        # внутренних вызовов.
        if body.channels:
            from leadgen.core.services.search.search_channels import sources_for

            enabled_sources_value = sources_for(body.channels)

        from leadgen.core.services.account import tokens as _tokens

        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(minutes=15)
        stale_rows = (
            await session.execute(
                select(SearchQuery).where(
                    SearchQuery.user_id == current_user.id,
                    SearchQuery.status.in_(ACTIVE_SEARCH_STATUSES),
                    SearchQuery.created_at < stale_cutoff,
                )
            )
        ).scalars().all()
        for stale in stale_rows:
            stale.status = "failed"
            stale.error = "auto-failed: stale active search reclaimed"
            stale.finished_at = now
            # Зависший поиск не должен держать токены команды.
            await _tokens.close_search_hold(session, stale)
        await session.flush()
        # Уже идёт поиск — новый (следующий город) встаёт в очередь и
        # стартует сам, когда предыдущий закончится.
        queue_it = await has_active_search(session, current_user.id)
        user_profile = await _launch_profile(
            session, user, body, team_id, current_user.id
        )

        prefilters: dict[str, Any] = {}
        if body.website_filter and body.website_filter != "any":
            prefilters["website"] = body.website_filter
        if body.min_rating:
            prefilters["min_rating"] = float(body.min_rating)
        if body.min_reviews:
            prefilters["min_reviews"] = int(body.min_reviews)
        if body.exclusions and body.exclusions.strip():
            # Не фильтр до оценки: ИИ отмечает подпавших при оценке,
            # пайплайн их убирает и не списывает за них токены.
            prefilters["exclude"] = body.exclusions.strip()
        query = SearchQuery(
            user_id=current_user.id,
            team_id=team_id,
            niche=body.niche,
            region=body.region,
            country_code=body.country_code.upper() if body.country_code else None,
            target_languages=(
                list(body.target_languages)
                if body.target_languages
                else None
            ),
            max_results=(
                int(body.limit) if body.limit is not None else None
            ),
            scope=scope,
            radius_m=radius_m_value,
            enabled_sources=enabled_sources_value,
            find_decision_makers=body.find_decision_makers,
            prefilters=prefilters or None,
            source="web",
            status="queued" if queue_it else "pending",
            launch_profile=(user_profile or None) if queue_it else None,
        )
        session.add(query)
        # Резерв токенов под запуск. Пишется всегда — журнал должен
        # отражать реальность и до включения продаж; запрещает запуск
        # только TOKENS_ENFORCED. Резерв и сам поиск коммитятся одной
        # транзакцией: иначе при сбое остался бы либо занятый резерв
        # без поиска, либо поиск без учёта.
        if team_id is not None:
            await session.flush()
            q = _tokens.quote(
                int(body.limit or 50),
                find_decision_makers=body.find_decision_makers,
            )
            from leadgen.core.services.account import budget as _budget

            _team = await session.get(Team, team_id)
            if _team is not None:
                await _budget.ensure_refill(session, _team)
            if get_settings().tokens_enforced or (
                _team is not None and _team.token_stop_at_zero
            ):
                have = await _tokens.balance(session, team_id)
                if have < q.total:
                    await session.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail=(
                            f"Не хватает токенов: нужно {q.total}, "
                            f"на балансе {have}. Добавить может владелец "
                            "в Настройки → Деньги и токены."
                        ),
                    )
            await _tokens.hold(
                session,
                team_id,
                query.id,
                q.total,
                user_id=current_user.id,
                reason=f"запуск: {body.niche}, {body.region}",
            )
        try:
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Another search is already running for this user, "
                    "or the row couldn't be created."
                ),
            ) from exc
        await session.refresh(query)

    if queue_it:
        # Если предыдущий поиск успел закончиться между проверкой и
        # коммитом, очередь иначе ждала бы следующего финала.
        await start_next_queued_search(current_user.id)
        return SearchCreateResponse(id=query.id, queued=True)

    queued = await launch_search(query.id, user_profile or None)
    return SearchCreateResponse(id=query.id, queued=queued)


@router.get("/api/v1/searches", response_model=list[SearchSummary])
async def list_searches(
    team_id: uuid.UUID | None = None,
    member_user_id: int | None = None,
    limit: int = 50,
    archived: bool = False,
    current_user: User = Depends(get_current_user),
) -> list[SearchSummary]:
    """List searches for a workspace.

    By default the active workspace is returned. Pass ``archived=true``
    to fetch only soft-archived sessions (the dedicated archive zone).
    """
    user_id = current_user.id
    limit = max(1, min(limit, 200))
    async with session_factory() as session:
        stmt = (
            select(SearchQuery)
            .order_by(SearchQuery.created_at.desc())
            .limit(limit)
        )
        if archived:
            stmt = stmt.where(SearchQuery.archived_at.is_not(None))
        else:
            stmt = stmt.where(SearchQuery.archived_at.is_(None))
        if team_id is not None:
            target_user = await resolve_team_view(
                session, team_id, user_id, member_user_id
            )
            stmt = stmt.where(SearchQuery.team_id == team_id).where(
                SearchQuery.user_id == target_user
            )
        else:
            stmt = stmt.where(SearchQuery.user_id == user_id).where(
                SearchQuery.team_id.is_(None)
            )
        result = await session.execute(stmt)
        return [to_summary(row) for row in result.scalars().all()]


async def _authorise_search_read(
    session, search_id: uuid.UUID, current_user: User
) -> SearchQuery:
    """Load a search the caller may read, or raise 404.

    Readable when the caller owns it or is a member of its team.
    Cross-user access answers 404 (not 403) so search ids can't be
    probed for existence.
    """
    query = await session.get(SearchQuery, search_id)
    allowed, _ms = await search_access(session, query, current_user.id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="search not found"
        )
    assert query is not None
    return query


@router.get("/api/v1/searches/{search_id}", response_model=SearchSummary)
async def get_search(
    search_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> SearchSummary:
    async with session_factory() as session:
        query = await _authorise_search_read(session, search_id, current_user)
        return to_summary(query)


@router.get(
    "/api/v1/searches/{search_id}/leads", response_model=list[LeadResponse]
)
async def list_search_leads(
    search_id: uuid.UUID,
    temp: str | None = None,
    current_user: User = Depends(get_current_user),
) -> list[LeadResponse]:
    """All leads for one search."""
    user_id = current_user.id
    async with session_factory() as session:
        query = await _authorise_search_read(session, search_id, current_user)
        _ok, ms = await search_access(session, query, user_id)
        stmt = (
            select(Lead)
            .where(Lead.query_id == search_id)
            .where(Lead.deleted_at.is_(None))
            .order_by(Lead.score_ai.desc().nullslast(), Lead.rating.desc().nullslast())
        )
        # Линза роли — та же, что в общем списке: селз видит только
        # свои лиды и без сумм.
        if ms is not None and is_sales(ms.role):
            stmt = stmt.where(Lead.owner_user_id == user_id)
        result = await session.execute(stmt)
        leads = list(result.scalars().all())
        lead_ids = [lead.id for lead in leads]
        marks = await marks_for_user(session, user_id, lead_ids)
        tags_map = await tags_by_lead(session, lead_ids)
    hide_money = money_hidden_for(ms)

    if temp in {"hot", "warm", "cold"}:
        leads = [lead for lead in leads if compute_temp(lead.score_ai) == temp]
    out: list[LeadResponse] = []
    for lead in leads:
        payload = to_lead_response(lead, marks.get(lead.id), tags_map.get(lead.id))
        if hide_money:
            payload.deal_value = None
        out.append(payload)
    return out


# ── Session archive / restore / delete ────────────────────────────────
#
# Archive softly hides a session and its leads from the workspace
# (CRM, kanban, sessions list). Leads stay in user_seen_leads /
# team_seen_leads so a future search won't surface the same companies
# again — that's the explicit requirement from the user.
#
# Permission matrix:
#   personal session     → only the owner (search.user_id) can archive
#                          or hard-delete
#   team session         → any team member can archive
#                          → only Owner / Admin can hard-delete
#
# Hard delete cascades through the search_queries → leads FK so the
# row vanishes for good.


async def _load_search_for_mutation(
    session, search_id: uuid.UUID, current_user: User
) -> SearchQuery:
    query = await session.get(SearchQuery, search_id)
    if query is None:
        raise HTTPException(status_code=404, detail="search not found")
    if query.team_id is None:
        if query.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="forbidden")
    else:
        m = await membership(session, query.team_id, current_user.id)
        if m is None:
            raise HTTPException(status_code=403, detail="forbidden")
        # Архив прячет весь поиск у всей команды — это не для селза.
        if not can_view_all_leads(m.role):
            raise HTTPException(
                status_code=403, detail="your role can't archive team sessions"
            )
    return query


def _can_hard_delete(query: SearchQuery, current_user: User, member_role: str | None) -> bool:
    if query.team_id is None:
        return query.user_id == current_user.id
    role = normalize_role(member_role)
    return role in {ROLE_OWNER, ROLE_ADMIN}


@router.post("/api/v1/searches/{search_id}/archive")
async def archive_search(
    search_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Soft-archive a session + all its leads."""
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        query = await _load_search_for_mutation(session, search_id, current_user)
        if query.archived_at is None:
            query.archived_at = now
        # Mirror the archive flag onto the leads so the existing
        # active-CRM filters keep working without a join.
        await session.execute(
            update(Lead)
            .where(Lead.query_id == query.id)
            .where(Lead.archived_at.is_(None))
            .values(archived_at=now)
        )
        await session.commit()
    return {"ok": True, "archived_at": now.isoformat()}


@router.post("/api/v1/searches/{search_id}/restore")
async def restore_search(
    search_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Restore a previously-archived session + its leads."""
    async with session_factory() as session:
        query = await _load_search_for_mutation(session, search_id, current_user)
        query.archived_at = None
        await session.execute(
            update(Lead)
            .where(Lead.query_id == query.id)
            .values(archived_at=None)
        )
        await session.commit()
    return {"ok": True}


@router.delete("/api/v1/searches/{search_id}")
async def delete_search(
    search_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Hard-delete a session.

    For team sessions only Owner / Admin pass. For personal sessions
    only the search owner. Cascade removes leads via the FK.
    """
    async with session_factory() as session:
        query = await _load_search_for_mutation(session, search_id, current_user)
        member_role: str | None = None
        if query.team_id is not None:
            m = await membership(session, query.team_id, current_user.id)
            member_role = m.role if m else None
        if not _can_hard_delete(query, current_user, member_role):
            raise HTTPException(
                status_code=403,
                detail="only owner or admin can delete this session",
            )
        await session.delete(query)
        await session.commit()
    return {"ok": True}


@router.get("/api/v1/searches/{search_id}/progress")
async def search_progress(
    search_id: uuid.UUID,
    api_key: str | None = Query(default=None, alias="api_key"),
) -> StreamingResponse:
    """Server-Sent Events stream of progress beats.

    Auth: if WEB_API_KEY is configured, require it as ``?api_key=``.
    Otherwise (open-demo mode), stream unauthenticated.
    """
    expected = get_settings().web_api_key
    if expected and api_key != expected:
        raise HTTPException(status_code=401, detail="invalid api_key")

    stream_max_seconds = 600.0
    heartbeat_interval = 15.0

    async def event_stream() -> asyncio.AsyncIterator[bytes]:
        yield b"retry: 5000\n\n"
        sub = default_broker.subscribe(search_id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + stream_max_seconds
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    yield b"event: timeout\ndata: {}\n\n"
                    return
                try:
                    event = await asyncio.wait_for(
                        sub.__anext__(),
                        timeout=min(heartbeat_interval, remaining),
                    )
                except TimeoutError:
                    yield b": heartbeat\n\n"
                    continue
                except StopAsyncIteration:
                    break
                payload = json.dumps({"kind": event.kind, **event.data})
                yield f"event: {event.kind}\ndata: {payload}\n\n".encode()
            yield b"event: done\ndata: {}\n\n"
        finally:
            await sub.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
