"""email_reply_tracker tz fix — Wave 6 item 5b.

A naive ``email_reply_last_checked_at`` must be treated as UTC before
``.timestamp()`` so the Gmail ``after:`` window isn't shifted by the
host's local offset.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import leadgen.core.services.email_reply_tracker as tracker


@pytest.mark.asyncio
async def test_naive_watermark_is_treated_as_utc(monkeypatch) -> None:
    captured: dict[str, int | None] = {}

    async def _fake_list(access_token: str, *, after_epoch: int | None):
        captured["after_epoch"] = after_epoch
        return []  # no messages -> scan does nothing else

    async def _noop_commit():
        return None

    monkeypatch.setattr(tracker, "_list_recent_messages", _fake_list)

    # A naive datetime that, if read as UTC, yields a known epoch.
    naive = datetime(2026, 1, 1, 0, 0, 0)  # no tzinfo
    expected = int(naive.replace(tzinfo=timezone.utc).timestamp())

    class _Session:
        async def execute(self, *a, **kw):
            return None

        async def commit(self):
            return None

    user = SimpleNamespace(
        id=1,
        email_reply_tracking_enabled=True,
        email_reply_last_checked_at=naive,
    )

    await tracker.scan_replies_for_user(
        _Session(), user, access_token="tok"
    )
    assert captured["after_epoch"] == expected


@pytest.mark.asyncio
async def test_aware_watermark_unchanged(monkeypatch) -> None:
    captured: dict[str, int | None] = {}

    async def _fake_list(access_token: str, *, after_epoch: int | None):
        captured["after_epoch"] = after_epoch
        return []

    monkeypatch.setattr(tracker, "_list_recent_messages", _fake_list)

    aware = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    class _Session:
        async def execute(self, *a, **kw):
            return None

        async def commit(self):
            return None

    user = SimpleNamespace(
        id=1,
        email_reply_tracking_enabled=True,
        email_reply_last_checked_at=aware,
    )

    await tracker.scan_replies_for_user(
        _Session(), user, access_token="tok"
    )
    assert captured["after_epoch"] == int(aware.timestamp())
