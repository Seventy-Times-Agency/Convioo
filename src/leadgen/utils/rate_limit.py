"""In-process per-user rate limiter.

Single-instance sliding-window counter: tracks the timestamps of recent
actions and rejects new ones once a user exceeds the budget within the
window. Lives in memory — fine for a single bot process, and the
migration to a multi-instance deployment will swap this module for a
Redis-backed equivalent without touching call sites.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Hashable


class RateLimiter:
    def __init__(self, max_actions: int, window_sec: float) -> None:
        self.max_actions = max_actions
        self.window_sec = window_sec
        self._events: dict[Hashable, deque[float]] = defaultdict(deque)

    def check_and_record(self, key: Hashable) -> bool:
        """Try to record a new action. Returns True if allowed, False if rate-limited.

        ``key`` can be any hashable identifier — Telegram user_id (int),
        IP address (str), email (str), etc. The same ``RateLimiter``
        instance can mix key kinds without collisions because Python
        dicts hash int and str into separate buckets.
        """
        now = time.monotonic()
        cutoff = now - self.window_sec
        events = self._events[key]
        while events and events[0] < cutoff:
            events.popleft()
        if len(events) >= self.max_actions:
            return False
        events.append(now)
        return True

    def retry_after(self, key: Hashable) -> float:
        """Seconds until the oldest event falls out of the window (best-effort)."""
        events = self._events.get(key)
        if not events or len(events) < self.max_actions:
            return 0.0
        return max(0.0, events[0] + self.window_sec - time.monotonic())


# Default limiters tuned for a chat UI: searches are expensive, all other
# actions just need to stop rapid-fire spam.
search_limiter = RateLimiter(max_actions=5, window_sec=60.0)
action_limiter = RateLimiter(max_actions=30, window_sec=60.0)

# Per-user / per-team / per-IP throttles for the expensive endpoints.
# /api/v1/searches: bound the AI cost a single user or team can drive
# in 5 minutes. /api/v1/assistant/chat: bound Claude calls. Keys mix
# ``user:{id}``, ``team:{uuid}``, ``ip:{addr}`` — same dict, no collision.
search_user_limiter = RateLimiter(max_actions=20, window_sec=300.0)
search_team_limiter = RateLimiter(max_actions=60, window_sec=300.0)
search_ip_limiter = RateLimiter(max_actions=30, window_sec=300.0)
assistant_user_limiter = RateLimiter(max_actions=60, window_sec=60.0)
assistant_team_limiter = RateLimiter(max_actions=180, window_sec=60.0)

# Auth limiters. Keys are IPs ("ip:1.2.3.4") or addresses ("email:[email protected]")
# so the same instance handles both axes without collision.
login_limiter = RateLimiter(max_actions=5, window_sec=60.0)
register_limiter = RateLimiter(max_actions=3, window_sec=3600.0)
forgot_password_limiter = RateLimiter(max_actions=3, window_sec=3600.0)
forgot_email_limiter = RateLimiter(max_actions=3, window_sec=3600.0)
reset_password_limiter = RateLimiter(max_actions=5, window_sec=3600.0)
resend_verification_limiter = RateLimiter(max_actions=3, window_sec=3600.0)
