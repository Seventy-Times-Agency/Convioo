"""Оценка настройки запуска — до того, как потрачены деньги.

Светофор и отчёт для формы нового поиска. Источники:

* **разведка Google** — бесплатный поиск «только идентификаторы» по
  нетронутым срезам каждого города: сколько компаний свежие, а сколько
  уже есть у команды (верхняя граница — закрытые и дубли по телефону
  видны только после платного шага);
* **история команды по нише** — сколько отсекут фильтры, доля горячих,
  как часто находится руководитель, сколько стоил лид;
* **правила** — настройки, которые противоречат друг другу.

Тексты не здесь: наружу уходят коды и числа, форма переводит их сама.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.core.services.search import coverage
from leadgen.data.cities import match_city
from leadgen.data.niches import match_niche
from leadgen.db.models import Lead, SearchQuery, TeamSeenLead, UserSeenLead
from leadgen.utils.dedup import domain_root
from leadgen.utils.geocode import bbox_from_circle, geocode_region_dedup

logger = logging.getLogger(__name__)

#: Сколько истории брать для оценки ниши.
HISTORY_DAYS = 180
#: Себестоимость лида, если по нише ещё нет своих данных (новая схема).
DEFAULT_COST_PER_LEAD_USD = 0.012
DEFAULT_WASTED_SHARE = 0.12
HOT_SCORE = 75
DM_MIN_SCORE = 50
SCOUT_TIMEOUT_SEC = 25.0
#: Языки на латинице и на кириллице — для проверки «язык против страны».
LATIN_LANGS = {"en", "de", "es", "fr", "pl", "it", "pt", "nl"}
CYRILLIC_LANGS = {"uk", "ru", "kk"}
CYRILLIC_COUNTRIES = {"UA", "KZ"}


@dataclass
class CityIn:
    region: str
    radius_km: int = 0
    country_code: str | None = None


@dataclass
class SetupIn:
    niche: str
    cities: list[CityIn]
    limit: int = 50
    team_id: Any = None
    user_id: int | None = None
    website_filter: str | None = None
    min_rating: float | None = None
    min_reviews: int | None = None
    target_languages: list[str] = field(default_factory=list)
    find_decision_makers: bool = False


def _level(ratio: float | None, bad: float, fair: float) -> str:
    if ratio is None:
        return "unknown"
    if ratio < bad:
        return "bad"
    if ratio < fair:
        return "fair"
    return "good"


async def _geo(city: CityIn) -> tuple[tuple[float, float, float, float] | None, tuple | None]:
    """Границы поиска и границы для деления на части — как в запуске."""
    radius_m = city.radius_km * 1000 if city.radius_km else None
    curated = match_city(city.region)
    if curated is not None:
        bbox = bbox_from_circle(curated.lat, curated.lon, radius_m) if radius_m else None
        tile = None if bbox else bbox_from_circle(curated.lat, curated.lon, coverage.DEFAULT_TILE_RADIUS_M)
        return bbox, tile
    geo = await geocode_region_dedup(city.region)
    if geo is None:
        return None, None
    if radius_m:
        return bbox_from_circle(geo.lat, geo.lon, radius_m), None
    return geo.bbox_tuple(), None


async def _scout_city(
    session: AsyncSession, inp: SetupIn, city: CityIn, collector: Any, sem: asyncio.Semaphore
) -> dict[str, Any]:
    """Свежие и уже известные компании в нетронутых срезах города."""
    entry = match_niche(inp.niche)
    bbox, tile = await _geo(city)
    slices = coverage.build_slices(inp.niche, entry, None, bbox, tile)
    scope = coverage.scope_key(inp.team_id, inp.user_id)
    done = await coverage.covered(session, scope, coverage.niche_key(inp.niche), coverage.norm(city.region))
    pending = [s for s in slices if s.key not in done]

    async def one(sl: coverage.Slice) -> list[str]:
        async with sem:
            try:
                return await collector.scout_ids(sl.query, city.region, location_restriction_bbox=sl.bbox)
            except Exception:  # noqa: BLE001 — разведка необязательна
                logger.warning("scout slice %s failed", sl.key, exc_info=True)
                return []

    ids: list[str] = []
    for found in await asyncio.gather(*[one(s) for s in pending]):
        ids.extend(x for x in found if x not in ids)
    seen: set[str] = set()
    if ids:
        model = TeamSeenLead if inp.team_id is not None else UserSeenLead
        owner = (
            TeamSeenLead.team_id == inp.team_id
            if inp.team_id is not None
            else UserSeenLead.user_id == inp.user_id
        )
        rows = await session.execute(
            select(model.source_id).where(owner).where(model.source_id.in_(ids))
        )
        seen = {r[0] for r in rows.all()}
    return {
        "fresh": len(ids) - len(seen),
        "already": len(seen),
        "covered": len(slices) - len(pending),
        "total": len(slices),
    }


async def _history(session: AsyncSession, inp: SetupIn) -> dict[str, Any]:
    """Что команда уже знает о нише: фильтры, качество, ЛПР, цена."""
    since = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
    owner = (
        SearchQuery.team_id == inp.team_id
        if inp.team_id is not None
        else SearchQuery.user_id == inp.user_id
    )
    searches = (
        await session.execute(
            select(SearchQuery.id, SearchQuery.niche, SearchQuery.find_decision_makers, SearchQuery.economics)
            .where(owner)
            .where(SearchQuery.status == "done")
            .where(SearchQuery.created_at >= since)
            .order_by(SearchQuery.created_at.desc())
            .limit(300)
        )
    ).all()
    nkey = coverage.niche_key(inp.niche)
    same = [s for s in searches if coverage.niche_key(s.niche) == nkey]
    pool = same or list(searches)
    out: dict[str, Any] = {"same_niche": bool(same), "leads": 0}
    if not pool:
        return out
    dm_searches = {s.id for s in pool if s.find_decision_makers is True}
    leads = (
        await session.execute(
            select(Lead.query_id, Lead.website, Lead.rating, Lead.reviews_count, Lead.score_ai, Lead.website_meta)
            .where(Lead.query_id.in_([s.id for s in pool]))
            .limit(5000)
        )
    ).all()
    out["leads"] = len(leads)
    if leads:
        def passes(r: Any) -> bool:
            site = (r.website or "").strip()
            if inp.website_filter == "with" and not site:
                return False
            if inp.website_filter == "without" and site:
                return False
            if inp.min_rating and r.rating is not None and r.rating < float(inp.min_rating):
                return False
            return not (inp.min_reviews and r.reviews_count is not None and r.reviews_count < int(inp.min_reviews))

        out["filter_pass"] = sum(1 for r in leads if passes(r)) / len(leads)
        scored = [r.score_ai for r in leads if r.score_ai is not None]
        if same and scored:
            out["hot_share"] = sum(1 for s in scored if s >= HOT_SCORE) / len(scored)
            out["avg_score"] = sum(scored) / len(scored)
        eligible = [
            r for r in leads
            if r.query_id in dm_searches and (r.score_ai or 0) >= DM_MIN_SCORE and domain_root(r.website)
        ]
        if same and eligible:
            found = sum(1 for r in eligible if (r.website_meta or {}).get("contact_person"))
            # Доля от всех лидов, а не от подходящих: токен берётся за найденного.
            dm_pool = [r for r in leads if r.query_id in dm_searches]
            out["dm_rate"] = found / max(1, len(dm_pool))
    cost = sum(float((s.economics or {}).get("cost_usd") or 0) for s in same)
    wasted = sum(float((s.economics or {}).get("wasted_usd") or 0) for s in same)
    delivered = sum(int((s.economics or {}).get("delivered") or 0) for s in same)
    if delivered >= 10:
        out["cost_per_lead"] = cost / delivered
    if cost > 0:
        out["wasted_share"] = wasted / cost
    return out


def _conflicts(inp: SetupIn) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if inp.website_filter == "without" and inp.find_decision_makers:
        out.append({"key": "conflict_dm_no_site", "level": "bad", "params": {}})
    langs = {x.lower() for x in inp.target_languages}
    countries = {(c.country_code or "").upper() for c in inp.cities if c.country_code}
    if langs and langs <= LATIN_LANGS and countries & CYRILLIC_COUNTRIES:
        out.append({"key": "conflict_lang_latin", "level": "fair", "params": {}})
    if langs and langs <= CYRILLIC_LANGS and countries and not (countries & CYRILLIC_COUNTRIES):
        out.append({"key": "conflict_lang_cyrillic", "level": "fair", "params": {}})
    return out


async def check_setup(
    session: AsyncSession, inp: SetupIn, *, collector: Any | None
) -> dict[str, Any]:
    from leadgen.core.services.account.tokens import quote

    limit = max(1, min(int(inp.limit), 100))
    history = await _history(session, inp)
    filters_on = bool(inp.website_filter or inp.min_rating or inp.min_reviews)
    pass_rate = history.get("filter_pass") if filters_on else 1.0

    sem = asyncio.Semaphore(6)
    cities_out: list[dict[str, Any]] = []
    for city in inp.cities[:10]:
        fc = await coverage.forecast(
            session,
            scope=coverage.scope_key(inp.team_id, inp.user_id),
            niche=inp.niche,
            region=city.region,
            requested=limit,
            already_have=0,
        )
        row: dict[str, Any] = {
            "region": city.region,
            "covered": fc["covered"],
            "total": fc["total"],
            "exhausted": fc["exhausted"],
            "scouted": False,
            "fresh": None,
            "already": None,
        }
        if collector is not None:
            try:
                scout = await asyncio.wait_for(
                    _scout_city(session, inp, city, collector, sem), timeout=SCOUT_TIMEOUT_SEC
                )
                row.update(scout, scouted=True)
            except Exception:  # noqa: BLE001
                logger.warning("scout failed for %s", city.region, exc_info=True)
        supply = row["fresh"] if row["scouted"] else fc["expected_new"]
        if supply is None:
            row["expected"] = None
            row["level"] = "bad" if fc["exhausted"] else "unknown"
        else:
            eff = int(supply * (pass_rate if pass_rate is not None else 1.0))
            row["expected"] = min(limit, eff)
            row["level"] = "bad" if fc["exhausted"] and not row["scouted"] else _level(row["expected"] / limit, 0.3, 0.8)
        fixes: list[dict[str, Any]] = []
        if row["level"] in ("bad", "fair"):
            if city.radius_km < 50:
                fixes.append({"kind": "radius", "city": city.region, "value": 25 if city.radius_km < 25 else 50})
            if row["expected"] is not None and 0 < row["expected"] < limit:
                fixes.append({"kind": "limit", "city": city.region, "value": max(10, row["expected"])})
        row["fixes"] = fixes
        cities_out.append(row)

    checks: list[dict[str, Any]] = []
    entry = match_niche(inp.niche)
    checks.append({"key": "niche_known" if entry else "niche_free_text", "level": "good" if entry else "fair", "params": {}})
    if filters_on:
        if pass_rate is None:
            checks.append({"key": "filters_unknown", "level": "unknown", "params": {}})
        else:
            fixes = []
            if inp.min_rating and float(inp.min_rating) > 4.0 and pass_rate < 0.5:
                fixes.append({"kind": "min_rating", "value": 4})
            checks.append({
                "key": "filters_cut",
                "level": _level(pass_rate, 0.25, 0.5),
                "params": {"cut": round((1 - pass_rate) * 100), "n": history.get("leads", 0), "same": history.get("same_niche")},
                "fixes": fixes,
            })
    if "hot_share" in history:
        checks.append({
            "key": "quality",
            "level": "good" if history["hot_share"] >= 0.2 else "fair",
            "params": {"hot": round(history["hot_share"] * 100), "avg": round(history["avg_score"])},
        })
    else:
        checks.append({"key": "quality_unknown", "level": "unknown", "params": {}})
    total_expected = sum(c["expected"] or 0 for c in cities_out)
    if inp.find_decision_makers:
        rate = history.get("dm_rate")
        checks.append({
            "key": "dm_rate" if rate is not None else "dm_unknown",
            "level": "unknown" if rate is None else _level(rate, 0.1, 0.33),
            "params": {"rate": round((rate or 0) * 100), "tokens": round(total_expected * (rate or 0))},
        })
    conflicts = _conflicts(inp)
    checks += conflicts or [{"key": "no_conflicts", "level": "good", "params": {}}]

    cpl = history.get("cost_per_lead", DEFAULT_COST_PER_LEAD_USD)
    cost = total_expected * cpl
    burned = cost * history.get("wasted_share", DEFAULT_WASTED_SHARE)
    dm_expected = round(total_expected * history.get("dm_rate", 0.3)) if inp.find_decision_makers else 0
    tokens_max = quote(total_expected, find_decision_makers=inp.find_decision_makers).total
    checks.append({
        "key": "cost",
        "level": "good",
        "params": {"usd": round(cost, 2), "burned": round(burned, 2), "tokens": tokens_max},
    })

    # Общий балл: запас свежих важнее всего, затем противоречия и фильтры.
    requested = limit * max(1, len(cities_out))
    known = [c for c in cities_out if c["expected"] is not None]
    supply_ratio = (
        sum(c["expected"] for c in known) / (limit * len(known)) if known else None
    )
    score = 100.0
    if supply_ratio is not None:
        score -= (1 - supply_ratio) * 55
    for c in checks:
        score -= {"bad": 25, "fair": 8}.get(c["level"], 0)
    score = max(0, min(100, round(score)))
    levels = [c["level"] for c in cities_out] + [c["level"] for c in checks]
    level = "bad" if "bad" in levels or score < 45 else "fair" if "fair" in levels or score < 75 else "good"

    # Главная причина — первое самое тяжёлое.
    order = {"bad": 0, "fair": 1}
    worst_city = min(cities_out, key=lambda c: order.get(c["level"], 9), default=None)
    worst_check = min(checks, key=lambda c: order.get(c["level"], 9), default=None)
    headline: dict[str, Any] = {"key": "all_good", "params": {}}
    if worst_city and order.get(worst_city["level"], 9) <= order.get(worst_check["level"] if worst_check else "", 9):
        if worst_city["level"] in order:
            headline = {
                "key": "city_exhausted" if worst_city["exhausted"] and not worst_city["scouted"] else "city_low",
                "params": {"city": worst_city["region"], "n": worst_city["expected"] or 0},
            }
    elif worst_check and worst_check["level"] in order:
        headline = {"key": worst_check["key"], "params": worst_check["params"]}

    return {
        "level": level,
        "score": score,
        "headline": headline,
        "cities": cities_out,
        "checks": checks,
        "totals": {
            "requested": requested,
            "expected": total_expected,
            "hot": round(total_expected * history["hot_share"]) if "hot_share" in history else None,
            "dm": dm_expected,
            "tokens_max": tokens_max,
            "cost_usd": round(cost, 2),
            "burned_usd": round(burned, 2),
        },
        "scouted": any(c["scouted"] for c in cities_out),
    }
