"""Coverage for the shared OAuth state signing + verification helper.

Lives in :mod:`leadgen.core.services.oauth_state` and is consumed by
Notion, Gmail, Outlook, HubSpot and Pipedrive. The earlier per-provider
implementation parsed ``state.split(":", 1)`` and trusted the user_id
half — a forged ``"<victim_id>:..."`` callback could write the
attacker's provider token under the victim's account. The fixed flow
signs ``user_id:nonce:ts`` with HMAC and verifies on the callback side;
these tests pin both the happy path and the ways state-handling can
fail.

Replay protection now lives in the ``oauth_consumed_nonces`` table (so
it holds across web replicas) rather than a process-local set, so
``verify_state`` is async and takes an ``AsyncSession``. The fixture
spins up an in-memory SQLite DB with just that table.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import leadgen.core.services.oauth_state as state_mod
from leadgen.core.services.oauth_state import (
    STATE_TTL_SEC,
    StateValidationError,
    issue_state,
    verify_state,
)
from leadgen.db.models import OAuthConsumedNonce

SECRET = "test-secret-for-oauth-state"


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: OAuthConsumedNonce.__table__.create(sync_conn)
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    # Reset the rate-limit timestamp so the opportunistic GC sweep can
    # run deterministically within a test if exercised.
    state_mod._last_gc_at = 0.0
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_issue_then_verify_round_trips_user_id(
    session: AsyncSession,
) -> None:
    state = issue_state(42, secret=SECRET)
    assert await verify_state(state, secret=SECRET, session=session) == 42


def test_two_calls_return_distinct_states() -> None:
    a = issue_state(7, secret=SECRET)
    b = issue_state(7, secret=SECRET)
    assert a != b, "nonce should make every state unique"


@pytest.mark.asyncio
async def test_tampered_user_id_is_rejected(session: AsyncSession) -> None:
    state = issue_state(42, secret=SECRET)
    parts = state.split(":")
    parts[0] = "1"  # try to swap to victim user_id
    forged = ":".join(parts)
    with pytest.raises(StateValidationError):
        await verify_state(forged, secret=SECRET, session=session)


@pytest.mark.asyncio
async def test_tampered_nonce_is_rejected(session: AsyncSession) -> None:
    state = issue_state(42, secret=SECRET)
    parts = state.split(":")
    parts[1] = "evilnonce"
    forged = ":".join(parts)
    with pytest.raises(StateValidationError):
        await verify_state(forged, secret=SECRET, session=session)


@pytest.mark.asyncio
async def test_wrong_secret_is_rejected(session: AsyncSession) -> None:
    state = issue_state(42, secret=SECRET)
    with pytest.raises(StateValidationError):
        await verify_state(state, secret="other-secret", session=session)


@pytest.mark.asyncio
async def test_empty_secret_refuses_to_mint_or_verify(
    session: AsyncSession,
) -> None:
    with pytest.raises(StateValidationError):
        issue_state(42, secret="")
    # A previously-issued state still must not validate against an empty
    # secret (eg. the env var was cleared between mint and callback).
    state = issue_state(42, secret=SECRET)
    with pytest.raises(StateValidationError):
        await verify_state(state, secret="", session=session)


@pytest.mark.asyncio
async def test_malformed_state_is_rejected(session: AsyncSession) -> None:
    for bad in ("", "foo", "1:abc", "1:abc:not-a-ts:sig", "1::123:sig"):
        with pytest.raises(StateValidationError):
            await verify_state(bad, secret=SECRET, session=session)


@pytest.mark.asyncio
async def test_expired_state_is_rejected(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Patch the module-level ``time.time`` to mint a state in the past,
    # then verify against real wall-clock to trip the TTL window.
    real_time = state_mod.time.time
    minted_at = real_time() - STATE_TTL_SEC - 5
    monkeypatch.setattr(state_mod.time, "time", lambda: minted_at)
    stale = issue_state(42, secret=SECRET)
    monkeypatch.setattr(state_mod.time, "time", real_time)
    with pytest.raises(StateValidationError):
        await verify_state(stale, secret=SECRET, session=session)


@pytest.mark.asyncio
async def test_short_max_age_window(session: AsyncSession) -> None:
    state = issue_state(42, secret=SECRET)
    assert (
        await verify_state(
            state, secret=SECRET, session=session, max_age_sec=60
        )
        == 42
    )


@pytest.mark.asyncio
async def test_replayed_state_is_rejected(session: AsyncSession) -> None:
    # First redemption succeeds; the nonce is now recorded in
    # oauth_consumed_nonces. A second redemption of the same state hits
    # the unique PK and is rejected as a replay.
    state = issue_state(42, secret=SECRET)
    assert await verify_state(state, secret=SECRET, session=session) == 42
    with pytest.raises(StateValidationError):
        await verify_state(state, secret=SECRET, session=session)


@pytest.mark.asyncio
async def test_legacy_notion_oauth_reexports_still_work(
    session: AsyncSession,
) -> None:
    # The notion_oauth module re-exports issue_state / verify_state
    # for back-compat with code that imported from there before the
    # extraction. New code should import from oauth_state directly.
    from leadgen.integrations import notion_oauth

    state = notion_oauth.issue_state(42, secret=SECRET)
    assert (
        await notion_oauth.verify_state(state, secret=SECRET, session=session)
        == 42
    )
    assert notion_oauth.STATE_TTL_SEC == STATE_TTL_SEC
    assert notion_oauth.StateValidationError is StateValidationError
