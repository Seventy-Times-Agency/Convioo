"""Static prompt strings + system-prompt builders.

Extracted from ``ai_analyzer.py`` to keep that module focused on the
actual LLM call orchestration and parsing. Behaviour unchanged — these
are the same builders the analyzer used inline before.
"""

from leadgen.analysis.prompts.assistant import (
    _assistant_personal_system_prompt,
    _assistant_team_system_prompt,
)
from leadgen.analysis.prompts.system import (
    _BUSINESS_SIZE_LABEL,
    _PROFILE_FIELDS_BLOCK,
    SYSTEM_PROMPT_BASE,
    _build_lead_context,
    _build_system_prompt,
    _format_user_profile,
)

__all__ = [
    "SYSTEM_PROMPT_BASE",
    "_BUSINESS_SIZE_LABEL",
    "_PROFILE_FIELDS_BLOCK",
    "_assistant_personal_system_prompt",
    "_assistant_team_system_prompt",
    "_build_lead_context",
    "_build_system_prompt",
    "_format_user_profile",
]
