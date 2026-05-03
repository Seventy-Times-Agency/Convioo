"""LLM-powered lead analyzer.

For each enriched lead we send a structured context (Google Maps data,
website snapshot, recent reviews) to Claude and ask for a JSON verdict:
score, tags, advice, strengths/weaknesses, red flags.

Also generates a high-level base summary from a list of analysed leads.

The big monolithic AIAnalyzer class was split into focused mixins under
``leadgen.analysis.{parsers,scoring,tagging,advice,research,email_drafting}``
in PR #refactor — this module is now the thin composition point and the
back-compat surface (``AIAnalyzer``, ``LeadAnalysis``, ``SYSTEM_PROMPT``,
``_extract_json``).
"""

from __future__ import annotations

import asyncio
import logging

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    InternalServerError,
    RateLimitError,
)

# Re-exports for back-compat with existing call sites and tests.
from leadgen.analysis._helpers import (  # noqa: F401
    _AGE_RANGE_CODES,
    _BIZ_KEYWORDS,
    _BUSINESS_SIZE_CODES,
    _NAME_PREFIX_PATTERNS,
    _NICHE_LIMIT,
    _NICHE_MAX,
    _NICHE_MIN,
    _REGION_PREFIX_PATTERNS,
    LeadAnalysis,
    _age_from_number,
    _biz_from_headcount,
    _bucket_tag,
    _clean_niches,
    _clean_profile_suggestion,
    _clean_team_suggestion,
    _extract_json,
    _format_lead_for_email,
    _heuristic_analysis,
    _heuristic_consult,
    _heuristic_email,
    _heuristic_intent,
    _strip_patterns,
    _trim_or_none,
)
from leadgen.analysis.advice import AdviceMixin
from leadgen.analysis.email_drafting import EmailDraftingMixin
from leadgen.analysis.parsers import ParsersMixin
from leadgen.analysis.prompts import (  # noqa: F401
    SYSTEM_PROMPT_BASE,
    _assistant_personal_system_prompt,
    _assistant_team_system_prompt,
    _build_lead_context,
    _build_system_prompt,
    _format_user_profile,
)
from leadgen.analysis.research import ResearchMixin
from leadgen.analysis.scoring import ScoringMixin
from leadgen.analysis.tagging import TaggingMixin
from leadgen.config import get_settings

logger = logging.getLogger(__name__)


# Back-compat alias for existing tests/imports.
SYSTEM_PROMPT = SYSTEM_PROMPT_BASE


class AIAnalyzer(
    ParsersMixin,
    ScoringMixin,
    TaggingMixin,
    AdviceMixin,
    ResearchMixin,
    EmailDraftingMixin,
):
    """Async wrapper around the Anthropic Messages API with heuristic fallback."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        concurrency: int | None = None,
    ) -> None:
        _settings = get_settings()
        resolved_key = _settings.anthropic_api_key if api_key is None else api_key
        self.api_key = resolved_key.strip()
        self.client = (
            AsyncAnthropic(api_key=self.api_key, max_retries=2, timeout=45.0)
            if self.api_key
            else None
        )
        self.model = model or _settings.anthropic_model
        self._sem = asyncio.Semaphore(concurrency or _settings.enrich_concurrency)

    @staticmethod
    def _classify_anthropic_error(exc: BaseException) -> tuple[str, str]:
        """Map an Anthropic SDK exception to (slug, ru_label)."""
        if isinstance(exc, RateLimitError):
            return ("rate_limit", "лимит запросов")
        if isinstance(exc, APITimeoutError):
            return ("timeout", "таймаут")
        if isinstance(exc, InternalServerError):
            return ("overloaded", "сервер AI перегружен")
        if isinstance(exc, APIConnectionError):
            return ("network", "проблема со связью")
        if isinstance(exc, APIStatusError):
            return (f"http_{exc.status_code}", f"ошибка {exc.status_code}")
        return ("unknown", "что-то пошло не так")

    async def _short_completion(
        self, system: str, user_text: str, max_tokens: int = 60
    ) -> str | None:
        """Small helper for single-field extraction prompts."""
        if self.client is None:
            return None
        try:
            async with self._sem:
                msg = await self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user_text}],
                )
                out = "".join(
                    getattr(block, "text", "") for block in msg.content
                ).strip()
                return out or None
        except Exception:  # noqa: BLE001
            logger.exception("short-completion call failed")
            return None
