"""Pure-function tests for the session-cookie auth helpers.

DB-free: covers token hashing, device fingerprint stability, lockout
counter math, recovery-email masking, and email-template rendering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from leadgen.adapters.web_api.auth import (
    LOCKOUT_DURATION,
    LOCKOUT_THRESHOLD,
    clear_failed_logins,
    device_fingerprint,
    hash_token,
    is_locked,
    record_failed_login,
)
from leadgen.core.services.email_sender import (
    mask_email,
    render_account_locked_email,
    render_email_changed_alert,
    render_email_recovery_email,
    render_new_device_login_email,
    render_password_changed_email,
    render_password_reset_email,
)
from leadgen.db.models import User


def test_hash_token_is_deterministic_and_hex() -> None:
    h1 = hash_token("abc")
    h2 = hash_token("abc")
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_hash_token_collision_resistant() -> None:
    # Different tokens map to different hashes.
    assert hash_token("abc") != hash_token("abcd")
    assert hash_token("") != hash_token("\x00")


def test_device_fingerprint_groups_same_subnet() -> None:
    a = device_fingerprint("1.2.3.10", "Mozilla/5.0 X")
    b = device_fingerprint("1.2.3.250", "Mozilla/5.0 X")
    # Same /24 + same UA → same fingerprint.
    assert a == b


def test_device_fingerprint_changes_with_different_ua() -> None:
    a = device_fingerprint("1.2.3.10", "Chrome 120")
    b = device_fingerprint("1.2.3.10", "Firefox 122")
    assert a != b


def test_device_fingerprint_handles_ipv6() -> None:
    # Different addresses inside the same /48 bucket must collapse.
    a = device_fingerprint("2001:db8:1::1", "ua")
    b = device_fingerprint("2001:db8:1::ffff", "ua")
    assert a == b
    c = device_fingerprint("2001:db8:2::1", "ua")
    assert a != c


def test_device_fingerprint_handles_missing_inputs() -> None:
    assert device_fingerprint(None, None)
    assert device_fingerprint("", "")
    assert device_fingerprint(None, "ua") != device_fingerprint("1.2.3.4", "ua")


def test_lockout_counter_increments_until_threshold() -> None:
    user = User(id=1, queries_limit=5)
    user.failed_login_attempts = 0
    for i in range(1, LOCKOUT_THRESHOLD):
        just_locked = record_failed_login(user)
        assert just_locked is False
        assert user.failed_login_attempts == i
    just_locked = record_failed_login(user)
    assert just_locked is True
    assert user.failed_login_attempts == LOCKOUT_THRESHOLD
    assert user.locked_until is not None


def test_is_locked_respects_locked_until() -> None:
    user = User(id=1, queries_limit=5)
    user.locked_until = None
    assert is_locked(user) is False
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    assert is_locked(user) is True
    user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert is_locked(user) is False


def test_clear_failed_logins_resets_state() -> None:
    user = User(id=1, queries_limit=5)
    user.failed_login_attempts = 7
    user.locked_until = datetime.now(timezone.utc) + LOCKOUT_DURATION
    clear_failed_logins(user)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


# ── mask_email ───────────────────────────────────────────────────────


AT = "@"


def test_mask_email_short_local() -> None:
    assert mask_email(f"a{AT}example.com") == f"*{AT}example.com"
    assert mask_email(f"abc{AT}example.com") == f"a*{AT}example.com"


def test_mask_email_long_local() -> None:
    masked = mask_email(f"jonathan{AT}example.com")
    assert masked.startswith("j")
    assert masked.endswith(f"{AT}example.com")
    assert "*" in masked


def test_mask_email_handles_garbage() -> None:
    assert mask_email(None) == "(unknown)"
    assert mask_email("") == "(unknown)"
    assert mask_email("not-an-email") == "(unknown)"


# ── render_*_email returns (html, text) shape ────────────────────────


def test_password_reset_email_includes_url() -> None:
    html, text = render_password_reset_email(
        name="Alex", reset_url="https://convioo.com/reset/abc"
    )
    assert "Alex" in html and "Alex" in text
    assert "https://convioo.com/reset/abc" in html
    assert "https://convioo.com/reset/abc" in text


def test_password_changed_email_carries_metadata() -> None:
    html, text = render_password_changed_email(
        name="Alex",
        ip="1.2.3.4",
        user_agent="Chrome",
        when_iso="2026-05-02T10:00:00+00:00",
    )
    assert "1.2.3.4" in html
    assert "Chrome" in text
    assert "2026-05-02T10:00:00+00:00" in text


def test_email_recovery_email_contains_masked_account() -> None:
    masked = f"j****n{AT}example.com"
    html, text = render_email_recovery_email(
        name="Alex",
        account_email_masked=masked,
        change_url="https://convioo.com/verify-email/x",
    )
    assert masked in html
    assert "https://convioo.com/verify-email/x" in text


def test_email_changed_alert_warns_about_swap() -> None:
    masked = f"n****w{AT}example.com"
    html, text = render_email_changed_alert(
        name="Alex",
        new_email_masked=masked,
        when_iso="2026-05-02T10:00:00+00:00",
    )
    assert masked in html
    assert "2026-05-02T10:00:00+00:00" in text


def test_new_device_login_email_lists_ip_and_ua() -> None:
    html, text = render_new_device_login_email(
        name="Alex",
        ip="9.9.9.9",
        user_agent="Firefox 122",
        when_iso="now",
    )
    assert "9.9.9.9" in html
    assert "Firefox 122" in text


def test_account_locked_email_says_when_unlocked() -> None:
    html, text = render_account_locked_email(
        name="Alex", unlock_iso="2026-05-02T10:15:00+00:00"
    )
    assert "2026-05-02T10:15:00+00:00" in html
    assert "Alex" in text
