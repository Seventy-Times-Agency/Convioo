"""Outlook OAuth routes: status, authorize, callback, disconnect."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.schemas import (
    OutlookAuthorizeResponse,
    OutlookIntegrationStatus,
)
from leadgen.config import get_settings
from leadgen.db.models import (
    OAuthCredential,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter()
logger = logging.getLogger(__name__)

# ── /api/v1/oauth/outlook (OAuth flow + send-as-user mirror) ───────────
#
# Same shape as Gmail: status / authorize / callback / delete. The
# send endpoint is the same /leads/{id}/send-email — it picks the
# provider from the body. 503-safe when Outlook env vars are unset.


def _outlook_oauth_configured() -> bool:
    s = get_settings()
    return bool(
        s.outlook_oauth_client_id and s.outlook_oauth_client_secret
    )


def _outlook_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Outlook OAuth is not configured on this deployment. "
            "Set OUTLOOK_OAUTH_CLIENT_ID, OUTLOOK_OAUTH_CLIENT_SECRET "
            "and OUTLOOK_OAUTH_REDIRECT_URI to enable Outlook send."
        ),
    )


@router.get(
    "/api/v1/oauth/outlook",
    response_model=OutlookIntegrationStatus,
)
async def outlook_status(
    current_user: User = Depends(get_current_user),
) -> OutlookIntegrationStatus:
    async with session_factory() as session:
        cred = (
            await session.execute(
                select(OAuthCredential)
                .where(OAuthCredential.user_id == current_user.id)
                .where(OAuthCredential.provider == "outlook")
            )
        ).scalar_one_or_none()
    if cred is None:
        return OutlookIntegrationStatus(connected=False)
    return OutlookIntegrationStatus(
        connected=True,
        account_email=cred.account_email,
        scope=cred.scope,
        expires_at=cred.expires_at,
    )


@router.get(
    "/api/v1/oauth/outlook/authorize",
    response_model=OutlookAuthorizeResponse,
)
async def outlook_authorize(
    current_user: User = Depends(get_current_user),
) -> OutlookAuthorizeResponse:
    """Mint a Microsoft consent-screen URL.

    Uses the shared HMAC-signed ``oauth_state`` helper so the
    callback can verify the state parameter without a DB-backed
    nonce table — and forged ``"<victim_id>:..."`` callbacks are
    rejected.
    """
    if not _outlook_oauth_configured():
        raise _outlook_unavailable()
    from leadgen.core.services.oauth_state import (
        StateValidationError,
        issue_state,
    )
    from leadgen.integrations.outlook import build_authorize_url

    settings = get_settings()
    try:
        state = issue_state(
            current_user.id, secret=settings.auth_jwt_secret
        )
    except StateValidationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    url = build_authorize_url(
        client_id=settings.outlook_oauth_client_id,
        redirect_uri=settings.outlook_oauth_redirect_uri,
        state=state,
    )
    return OutlookAuthorizeResponse(url=url, state=state)


@router.get("/api/v1/oauth/outlook/callback")
async def outlook_callback(
    code: str = Query(..., min_length=10, max_length=2048),
    state: str = Query(..., min_length=1, max_length=512),
    error: str | None = Query(default=None),
) -> Response:
    """Microsoft Graph callback — exchanges code, stores tokens.

    On success redirects to /app/settings/integrations?outlook=connected
    so the SPA can render the post-connect state. On state-mismatch
    or token-exchange failure redirects with an error flag.
    """
    settings = get_settings()
    return_base = (
        settings.public_app_url.rstrip("/")
        + "/app/settings/integrations"
    )

    if error:
        return Response(
            status_code=302,
            content="redirecting",
            headers={
                "Location": f"{return_base}?outlook=error&reason={error}"
            },
        )

    if not _outlook_oauth_configured():
        raise _outlook_unavailable()

    from leadgen.core.services.oauth_state import (
        StateValidationError,
        verify_state,
    )
    from leadgen.core.services.oauth_store import save_tokens
    from leadgen.integrations.gmail import TokenSet  # shared shape
    from leadgen.integrations.outlook import (
        OutlookError,
        exchange_code_for_tokens,
        fetch_account_email,
    )

    try:
        async with session_factory() as session:
            user_id = await verify_state(
                state,
                secret=settings.auth_jwt_secret,
                session=session,
            )
    except StateValidationError as exc:
        logger.warning(
            "outlook_oauth: rejected callback state reason=%s",
            str(exc),
        )
        raise HTTPException(
            status_code=400, detail="invalid state"
        ) from exc

    try:
        ms_tokens = await exchange_code_for_tokens(
            code,
            client_id=settings.outlook_oauth_client_id,
            client_secret=settings.outlook_oauth_client_secret,
            redirect_uri=settings.outlook_oauth_redirect_uri,
        )
    except OutlookError as exc:
        raise HTTPException(
            status_code=400, detail=f"oauth: {exc}"
        ) from exc

    account_email = await fetch_account_email(ms_tokens.access_token)

    # Re-shape into the shared TokenSet so save_tokens stays
    # provider-agnostic. The two dataclasses have identical fields;
    # this is a typing nicety, not a behaviour change.
    unified = TokenSet(
        access_token=ms_tokens.access_token,
        refresh_token=ms_tokens.refresh_token,
        expires_at=ms_tokens.expires_at,
        scope=ms_tokens.scope,
    )
    async with session_factory() as session:
        await save_tokens(
            session,
            user_id=user_id,
            provider="outlook",
            tokens=unified,
            account_email=account_email,
        )

    return Response(
        status_code=302,
        content="redirecting",
        headers={"Location": f"{return_base}?outlook=connected"},
    )


@router.delete("/api/v1/oauth/outlook")
async def outlook_disconnect(
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        cred = (
            await session.execute(
                select(OAuthCredential)
                .where(OAuthCredential.user_id == current_user.id)
                .where(OAuthCredential.provider == "outlook")
            )
        ).scalar_one_or_none()
        if cred is not None:
            await session.delete(cred)
            await session.commit()
    return {"ok": True}
