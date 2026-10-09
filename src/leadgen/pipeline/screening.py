"""Отбор найденного: бесплатные проверки → дубли → быстрый отсев ИИ.

Каждая порция компаний (первый поиск и каждый срез досбора) проходит
одни и те же шаги, от бесплатного к платному. Результат копится в
``fresh`` — свежие кандидаты, ещё не обрезанные по лимиту. Счётчики
воронки пишутся в ``funnel`` по ходу.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import or_, select

from leadgen.collectors.google_places import RawLead
from leadgen.db.models import TeamSeenLead, UserSeenLead
from leadgen.db.session import session_factory
from leadgen.utils.dedup import domain_root, normalize_phone

Keyed = tuple[RawLead, str | None, str | None]
Triage = Callable[[list[RawLead]], Awaitable[set[int]]]

#: Источники-карты: у компании должен быть способ связаться.
CONTACT_SOURCES = {"google_places", "osm", "yelp", "foursquare"}


def has_contact(lead: RawLead) -> bool:
    if lead.source not in CONTACT_SOURCES:
        return True
    return bool((lead.phone or "").strip() or (lead.website or "").strip())


def name_addr_key(lead: RawLead) -> str | None:
    """«Название + адрес» — ключ дубля для компаний без телефона и
    сайта, найденных двумя источниками. Нормализуется грубо: регистр,
    пунктуация, первая часть адреса (улица и дом)."""
    name = re.sub(r"[^\w]+", "", (lead.name or "").lower())
    street = re.sub(r"[^\w]+", "", (lead.address or "").split(",")[0].lower())
    if len(name) < 3 or len(street) < 3:
        return None
    return f"{name}|{street}"


class Screen:
    def __init__(
        self,
        *,
        funnel: dict[str, int],
        user_id: int | None,
        team_id: uuid.UUID | None,
        skip_dedup: bool,
        passes_prefilters: Callable[[RawLead], bool] | None = None,
        passes_language: Callable[[RawLead], bool] | None = None,
        triage: Triage | None = None,
    ) -> None:
        self.funnel = funnel
        self.user_id = user_id
        self.team_id = team_id
        self.skip_dedup = skip_dedup
        self.passes_prefilters = passes_prefilters
        self.passes_language = passes_language
        self.triage = triage
        self.fresh: list[Keyed] = []
        #: Отсеянные быстрым ИИ — помечаются «уже видели», чтобы не
        #: платить за них снова.
        self.rejected: list[Keyed] = []
        self._ids: set[str] = set()
        self._phones: set[str] = set()
        self._domains: set[str] = set()
        self._name_addr: set[str] = set()

    def _bump(self, key: str, n: int) -> None:
        if n:
            self.funnel[key] = self.funnel.get(key, 0) + n

    async def add(self, leads: list[RawLead]) -> int:
        """Пропустить порцию через все проверки; вернуть, сколько
        свежих она дала."""
        self._bump("found", len(leads))
        if self.passes_prefilters is not None:
            kept = [r for r in leads if self.passes_prefilters(r)]
            self._bump("prefiltered", len(leads) - len(kept))
            leads = kept
        if self.passes_language is not None:
            kept = [r for r in leads if self.passes_language(r)]
            self._bump("language", len(leads) - len(kept))
            leads = kept
        kept = [r for r in leads if has_contact(r)]
        self._bump("no_contact", len(leads) - len(kept))
        leads = kept
        if not leads:
            return 0

        keyed: list[Keyed] = [(r, normalize_phone(r.phone), domain_root(r.website)) for r in leads]
        seen_ids, seen_phones, seen_domains = await self._load_seen(keyed)
        candidates: list[Keyed] = []
        duplicates = 0
        for r, phone, domain in keyed:
            if not r.source_id or r.source_id in self._ids:
                continue
            # Уже были у команды — каким бы источником ни нашлись.
            if (
                r.source_id in seen_ids
                or (phone and phone in seen_phones)
                or (domain and domain in seen_domains)
            ):
                duplicates += 1
                continue
            # Одна компания из двух источников в этом же запуске.
            na = name_addr_key(r)
            if (
                (phone and phone in self._phones)
                or (domain and domain in self._domains)
                or (na and na in self._name_addr)
            ):
                continue
            self._ids.add(r.source_id)
            if phone:
                self._phones.add(phone)
            if domain:
                self._domains.add(domain)
            if na:
                self._name_addr.add(na)
            candidates.append((r, phone, domain))
        self._bump("duplicates", duplicates)

        if self.triage is not None and candidates:
            drop = await self.triage([c[0] for c in candidates])
            if drop:
                self.rejected += [c for i, c in enumerate(candidates) if i in drop]
                candidates = [c for i, c in enumerate(candidates) if i not in drop]
                self._bump("triaged", len(drop))

        self.fresh += candidates
        return len(candidates)

    async def _load_seen(self, keyed: list[Keyed]) -> tuple[set[str], set[str], set[str]]:
        ids: set[str] = set()
        phones: set[str] = set()
        domains: set[str] = set()
        if self.skip_dedup:
            return ids, phones, domains
        in_ids = [r.source_id for r, _, _ in keyed if r.source_id]
        in_phones = [p for _, p, _ in keyed if p]
        in_domains = [d for _, _, d in keyed if d]
        if not (in_ids or in_phones or in_domains):
            return ids, phones, domains

        def clauses(model: Any) -> list[Any]:
            out = []
            if in_ids:
                out.append(model.source_id.in_(in_ids))
            if in_phones:
                out.append(model.phone_e164.in_(in_phones))
            if in_domains:
                out.append(model.domain_root.in_(in_domains))
            return out

        async with session_factory() as session:
            queries = []
            if self.user_id:
                queries.append(
                    select(UserSeenLead.source_id, UserSeenLead.phone_e164, UserSeenLead.domain_root)
                    .where(UserSeenLead.user_id == self.user_id)
                    .where(or_(*clauses(UserSeenLead)))
                )
            if self.team_id is not None:
                queries.append(
                    select(TeamSeenLead.source_id, TeamSeenLead.phone_e164, TeamSeenLead.domain_root)
                    .where(TeamSeenLead.team_id == self.team_id)
                    .where(or_(*clauses(TeamSeenLead)))
                )
            for q in queries:
                for sid, phone, domain in (await session.execute(q)).all():
                    if sid:
                        ids.add(sid)
                    if phone:
                        phones.add(phone)
                    if domain:
                        domains.add(domain)
        return ids, phones, domains
