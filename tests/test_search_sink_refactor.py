"""Smoke test that the client-agnostic search core is importable and callable
without aiogram.

The whole point of the Stage-2 refactor is that ``run_search_with_sinks``
can be invoked from a web API, a CLI, or any other adapter — *not* just
the Telegram bot. This test loads the module without pulling in any
aiogram-specific state and verifies the sink-less call path (no
``ProgressSink``, no ``DeliverySink``) falls through gracefully when
the SearchQuery row is absent, proving the progress/delivery layer is
optional.
"""

from __future__ import annotations

import uuid

import pytest

from leadgen.pipeline.search import run_search_with_sinks


@pytest.mark.asyncio
async def test_runs_without_sinks_and_missing_query_returns_quietly(
    monkeypatch,
) -> None:
    # Stub session_factory so we don't need a real DB for this shape check.
    class _Sess:
        async def __aenter__(self) -> _Sess:
            return self

        async def __aexit__(self, *_a: object) -> None:  # noqa: D401
            return None

        async def get(self, _model: object, _pk: object) -> None:
            return None  # simulate "query not found"

        async def commit(self) -> None:
            return None

        async def execute(self, _stmt: object) -> object:
            class _R:
                def scalar(self) -> None:
                    return None

                def all(self) -> list[object]:
                    return []

                def scalars(self) -> _R:
                    return self

            return _R()

    from leadgen.pipeline import search as mod

    monkeypatch.setattr(mod, "session_factory", _Sess)

    # No sinks, no user_profile — must not raise.
    await run_search_with_sinks(uuid.uuid4(), progress=None, delivery=None)
