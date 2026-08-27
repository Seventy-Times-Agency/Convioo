"""Tests for the in-process per-user rate limiter."""

from __future__ import annotations

import time

from leadgen.utils.rate_limit import RateLimiter


def test_within_budget_allows() -> None:
    rl = RateLimiter(max_actions=3, window_sec=60.0)
    assert rl.check_and_record(1)
    assert rl.check_and_record(1)
    assert rl.check_and_record(1)


def test_over_budget_rejects() -> None:
    rl = RateLimiter(max_actions=2, window_sec=60.0)
    assert rl.check_and_record(1)
    assert rl.check_and_record(1)
    assert not rl.check_and_record(1)


def test_different_users_tracked_independently() -> None:
    rl = RateLimiter(max_actions=1, window_sec=60.0)
    assert rl.check_and_record(1)
    assert rl.check_and_record(2)
    assert not rl.check_and_record(1)
    assert not rl.check_and_record(2)


def test_window_expiry(monkeypatch) -> None:
    rl = RateLimiter(max_actions=2, window_sec=1.0)
    t = [1000.0]

    def fake_monotonic() -> float:
        return t[0]

    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    assert rl.check_and_record(1)
    assert rl.check_and_record(1)
    assert not rl.check_and_record(1)

    t[0] += 1.1
    # Window elapsed → slot free again.
    assert rl.check_and_record(1)


def test_retry_after_positive_when_blocked() -> None:
    rl = RateLimiter(max_actions=1, window_sec=60.0)
    assert rl.check_and_record(1)
    assert not rl.check_and_record(1)
    assert rl.retry_after(1) > 0


def test_retry_after_zero_when_free() -> None:
    rl = RateLimiter(max_actions=3, window_sec=60.0)
    rl.check_and_record(1)
    assert rl.retry_after(1) == 0.0
