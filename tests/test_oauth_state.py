"""Coverage for the shared OAuth state signing + verification helper.

Lives in :mod:`leadgen.core.services.oauth_state` and is consumed by
Notion and Outlook (Gmail / HubSpot / Pipedrive will migrate next).
The earlier per-provider implementation parsed ``state.split(":", 1)``
and trusted the user_id half — a forged ``"<victim_id>:..."`` callback
could write the attacker's provider token under the victim's account.
The fixed flow signs ``user_id:nonce:ts`` with HMAC and verifies on
the callback side; these tests pin both the happy path and the ways
state-handling can fail.
"""

from __future__ import annotations

import pytest

from leadgen.core.services.oauth_state import (
    STATE_TTL_SEC,
    StateValidationError,
    issue_state,
    verify_state,
)

SECRET = "test-secret-for-oauth-state"


def test_issue_then_verify_round_trips_user_id() -> None:
    state = issue_state(42, secret=SECRET)
    assert verify_state(state, secret=SECRET) == 42


def test_two_calls_return_distinct_states() -> None:
    a = issue_state(7, secret=SECRET)
    b = issue_state(7, secret=SECRET)
    assert a != b, "nonce should make every state unique"


def test_tampered_user_id_is_rejected() -> None:
    state = issue_state(42, secret=SECRET)
    parts = state.split(":")
    parts[0] = "1"  # try to swap to victim user_id
    forged = ":".join(parts)
    with pytest.raises(StateValidationError):
        verify_state(forged, secret=SECRET)


def test_tampered_nonce_is_rejected() -> None:
    state = issue_state(42, secret=SECRET)
    parts = state.split(":")
    parts[1] = "evilnonce"
    forged = ":".join(parts)
    with pytest.raises(StateValidationError):
        verify_state(forged, secret=SECRET)


def test_wrong_secret_is_rejected() -> None:
    state = issue_state(42, secret=SECRET)
    with pytest.raises(StateValidationError):
        verify_state(state, secret="other-secret")


def test_empty_secret_refuses_to_mint_or_verify() -> None:
    with pytest.raises(StateValidationError):
        issue_state(42, secret="")
    # A previously-issued state still must not validate against an empty
    # secret (eg. the env var was cleared between mint and callback).
    state = issue_state(42, secret=SECRET)
    with pytest.raises(StateValidationError):
        verify_state(state, secret="")


def test_malformed_state_is_rejected() -> None:
    for bad in ("", "foo", "1:abc", "1:abc:not-a-ts:sig", "1::123:sig"):
        with pytest.raises(StateValidationError):
            verify_state(bad, secret=SECRET)


def test_expired_state_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch the module-level ``time.time`` to mint a state in the past,
    # then verify against real wall-clock to trip the TTL window.
    import leadgen.core.services.oauth_state as state_mod

    real_time = state_mod.time.time
    minted_at = real_time() - STATE_TTL_SEC - 5
    monkeypatch.setattr(state_mod.time, "time", lambda: minted_at)
    stale = issue_state(42, secret=SECRET)
    monkeypatch.setattr(state_mod.time, "time", real_time)
    with pytest.raises(StateValidationError):
        verify_state(stale, secret=SECRET)


def test_short_max_age_window() -> None:
    state = issue_state(42, secret=SECRET)
    assert verify_state(state, secret=SECRET, max_age_sec=60) == 42


def test_legacy_notion_oauth_reexports_still_work() -> None:
    # The notion_oauth module re-exports issue_state / verify_state
    # for back-compat with code that imported from there before the
    # extraction. New code should import from oauth_state directly.
    from leadgen.integrations import notion_oauth

    state = notion_oauth.issue_state(42, secret=SECRET)
    assert notion_oauth.verify_state(state, secret=SECRET) == 42
    assert notion_oauth.STATE_TTL_SEC == STATE_TTL_SEC
    assert notion_oauth.StateValidationError is StateValidationError
