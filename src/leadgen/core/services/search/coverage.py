"""Память о прочёсанном и досбор до заказанного.

Один запрос к карте отдаёт не больше 60 компаний (3 страницы по 20).
Чтобы набрать заказанное, когда часть найденного — дубли, запуск
делится на срезы: город — на четыре части, ниша — на варианты
формулировки («стоматологии», «Dentists», «Стоматології»). Срезы,
которые команда уже прошла за последние ``COVERAGE_TTL_DAYS`` дней,
пропускаются: там почти одни дубли, а страница карты стоит денег.

Отсюда же — прогноз до запуска: сколько уже получено, сколько срезов
осталось и сколько свежих компаний ожидать.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from leadgen.data.niches import NicheEntry, match_niche
from leadgen.db.models import SearchCoverage

#: Через столько дней срез снова считается нетронутым — появляются
#: новые компании, а старые меняют телефоны и сайты.
COVERAGE_TTL_DAYS = 30
#: Сколько вариантов формулировки ниши пробовать сверх исходной.
MAX_VARIANTS = 2
#: Досбор останавливается, когда столько срезов подряд дали меньше
#: ``LOW_YIELD`` свежих: ниша в этом городе исчерпана.
LOW_YIELD_STREAK = 2
LOW_YIELD = 3
#: Радиус для деления города на части, если поиск идёт без границ.
DEFAULT_TILE_RADIUS_M = 15_000
#: Метка «исчерпано» — служебная строка памяти, не срез.
EXHAUSTED_KEY = "_exhausted"

BBox = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class Slice:
    key: str
    query: str
    bbox: BBox | None


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())[:160]


def niche_key(niche: str) -> str:
    entry = match_niche(niche)
    return entry.id if entry is not None else norm(niche)[:120]


def scope_key(team_id: Any, user_id: Any) -> str:
    return str(team_id) if team_id is not None else f"u{user_id}"


def tiles(bbox: BBox) -> list[BBox]:
    """Четыре части прямоугольника (south, west, north, east)."""
    s, w, n, e = bbox
    mid_lat, mid_lon = (s + n) / 2, (w + e) / 2
    return [
        (s, w, mid_lat, mid_lon),
        (s, mid_lon, mid_lat, e),
        (mid_lat, w, n, mid_lon),
        (mid_lat, mid_lon, n, e),
    ]


def niche_variants(niche: str, entry: NicheEntry | None, language: str | None) -> list[str]:
    """Другие формулировки той же ниши из таксономии: подпись на языке
    поиска, английская, украинская, затем синонимы."""
    if entry is None:
        return []
    seen = {norm(niche)}
    out: list[str] = []
    candidates = [
        entry.labels.get(language or ""),
        entry.labels.get("en"),
        entry.labels.get("uk"),
        *entry.aliases,
    ]
    for c in candidates:
        if not c or norm(c) in seen:
            continue
        seen.add(norm(c))
        out.append(c.strip())
        if len(out) >= MAX_VARIANTS:
            break
    return out


def _sig(bbox: BBox | None) -> str:
    return ",".join(f"{v:.2f}" for v in bbox) if bbox else "-"


def build_slices(
    niche: str,
    entry: NicheEntry | None,
    language: str | None,
    bbox: BBox | None,
    tile_bbox: BBox | None = None,
) -> list[Slice]:
    """Срезы в порядке «от самого урожайного»: весь город, его части,
    другие формулировки по всему городу, первая из них по частям.

    ``tile_bbox`` — границы для деления на части, когда сам поиск идёт
    без жёстких границ (город из справочника без радиуса)."""
    area = bbox or tile_bbox
    sig = _sig(area)
    out = [Slice(f"base@{sig}", niche, bbox)]
    parts = tiles(area) if area else []
    out += [Slice(f"t{i}@{sig}", niche, tb) for i, tb in enumerate(parts, 1)]
    variants = niche_variants(niche, entry, language)
    out += [Slice(f"v:{norm(v)}@{sig}", v, bbox) for v in variants]
    if variants and parts:
        first = variants[0]
        out += [Slice(f"v:{norm(first)}|t{i}@{sig}", first, tb) for i, tb in enumerate(parts, 1)]
    return out


async def covered(
    session: AsyncSession, scope: str, nkey: str, rkey: str
) -> dict[str, int]:
    """Срезы, пройденные за последние ``COVERAGE_TTL_DAYS``: ключ → свежих."""
    since = datetime.now(timezone.utc) - timedelta(days=COVERAGE_TTL_DAYS)
    rows = (
        await session.execute(
            select(SearchCoverage.slice_key, SearchCoverage.fresh, SearchCoverage.last_run_at)
            .where(SearchCoverage.scope_key == scope)
            .where(SearchCoverage.niche_key == nkey)
            .where(SearchCoverage.region_key == rkey)
        )
    ).all()
    out: dict[str, int] = {}
    for key, fresh, at in rows:
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if at is not None and at >= since:
            out[key] = int(fresh or 0)
    return out


async def record(
    session: AsyncSession,
    scope: str,
    nkey: str,
    rkey: str,
    slice_key: str,
    *,
    found: int,
    fresh: int,
) -> None:
    row = (
        await session.execute(
            select(SearchCoverage)
            .where(SearchCoverage.scope_key == scope)
            .where(SearchCoverage.niche_key == nkey)
            .where(SearchCoverage.region_key == rkey)
            .where(SearchCoverage.slice_key == slice_key)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None:
        session.add(
            SearchCoverage(
                scope_key=scope,
                niche_key=nkey,
                region_key=rkey,
                slice_key=slice_key,
                found=found,
                fresh=fresh,
                last_run_at=now,
            )
        )
    else:
        row.runs = (row.runs or 0) + 1
        row.found = found
        row.fresh = fresh
        row.last_run_at = now


async def clear_exhausted(session: AsyncSession, scope: str, nkey: str, rkey: str) -> None:
    """Запуск набрал своё — снять метку «исчерпано», если была."""
    await session.execute(
        delete(SearchCoverage)
        .where(SearchCoverage.scope_key == scope)
        .where(SearchCoverage.niche_key == nkey)
        .where(SearchCoverage.region_key == rkey)
        .where(SearchCoverage.slice_key == EXHAUSTED_KEY)
    )


async def forecast(
    session: AsyncSession,
    *,
    scope: str,
    niche: str,
    region: str,
    requested: int,
    already_have: int,
) -> dict[str, Any]:
    """Что ждать от запуска: сколько срезов прочёсано, сколько осталось,
    сколько свежих компаний примерно даст досбор."""
    entry = match_niche(niche)
    # Срезов на город с известными границами — прогноз до геокодинга.
    total = len(build_slices(niche, entry, None, (0.0, 0.0, 1.0, 1.0)))
    done = await covered(session, scope, niche_key(niche), norm(region))
    exhausted_mark = any(k.startswith(EXHAUSTED_KEY) for k in done)
    slices = {k.split("@", 1)[0]: v for k, v in done.items() if not k.startswith("_")}
    remaining = max(0, total - len(slices))
    expected: int | None = None
    if slices:
        avg = sum(slices.values()) / len(slices)
        expected = min(requested, int(round(avg * remaining)))
    # Метка ставится, когда досбор упёрся в одни дубли или срезы
    # кончились, — средним по прошлым срезам это уже не исправить.
    exhausted = remaining == 0 or exhausted_mark
    return {
        "already_have": int(already_have),
        "covered": len(slices),
        "total": total,
        "expected_new": 0 if exhausted else expected,
        "exhausted": exhausted,
    }
