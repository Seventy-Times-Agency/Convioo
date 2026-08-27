"""Anthropic prompt-caching helpers.

Wraps a plain system-prompt string in the SDK's content-block format with
``cache_control: {"type": "ephemeral"}``. Anthropic keeps the cached prefix
warm for ~5 minutes, so repeat scoring/advice calls with the same large
system prompt only pay for the per-lead user message — input tokens drop
roughly 80-90 percent on hot paths.

The helper is a no-op below the model's minimum cacheable size (1024 tokens
for Haiku — anything smaller can't be cached and would just add overhead),
so call sites can safely wrap every prompt unconditionally.

Reference: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
"""

from __future__ import annotations

from typing import Any

# Haiku 4.5 has a 1024-token minimum for ephemeral cache blocks. We use a
# conservative character heuristic (~4 chars/token) so we don't have to
# tokenize on every call.
_MIN_CACHEABLE_CHARS = 4096


def cached_system(prompt: str | None) -> str | list[dict[str, Any]]:
    """Wrap a system prompt for ephemeral caching when it is large enough.

    Returns the original string for short prompts (which the API rejects
    for caching) so callers can use the result directly as the ``system=``
    argument either way.
    """
    if not prompt:
        return prompt or ""
    if len(prompt) < _MIN_CACHEABLE_CHARS:
        return prompt
    return [
        {
            "type": "text",
            "text": prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]
