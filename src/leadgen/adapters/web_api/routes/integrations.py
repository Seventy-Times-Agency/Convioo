"""Integration route handlers: Notion, Gmail, Outlook, HubSpot, Pipedrive,
email-open tracking pixel, and affiliate dashboard.

Extracted from ``app.py`` (lines 2229-4850).  Path contracts are identical —
no new paths were added, none removed.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import (
    extract_lead_email as _extract_lead_email,
)
from leadgen.adapters.web_api.routes._helpers import (
    membership as _membership,
)
from leadgen.adapters.web_api.routes._helpers import (
    tags_by_lead as _tags_by_lead,
)
from leadgen.adapters.web_api.schemas import (
    AffiliateCodeCreateRequest,
    AffiliateCodeSchema,
    AffiliateCodeUpdate,
    AffiliateOverview,
    BulkSendRequest,
    GmailAuthorizeResponse,
    GmailIntegrationStatus,
    GmailSendRequest,
    GmailSendResponse,
    HubspotAuthorizeResponse,
    HubspotExportItem,
    HubspotExportRequest,
    HubspotExportResponse,
    HubspotIntegrationStatus,
    NotionAuthorizeResponse,
    NotionConnectRequest,
    NotionDatabase,
    NotionDatabaseList,
    NotionExportItem,
    NotionExportRequest,
    NotionExportResponse,
    NotionIntegrationStatus,
    NotionSetDatabaseRequest,
    OutlookAuthorizeResponse,
    OutlookIntegrationStatus,
    PipedriveAuthorizeResponse,
    PipedriveConfigUpdate,
    PipedriveExportItem,
    PipedriveExportRequest,
    PipedriveExportResponse,
    PipedriveIntegrationStatus,
    PipedrivePipelinesResponse,
    PipedrivePipelineView,
    PipedriveStageView,
)
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.config import get_settings
from leadgen.core.services import sanitize_email_header
from leadgen.db.models import (
    AffiliateCode,
    Lead,
    LeadActivity,
    OAuthCredential,
    Referral,
    SearchQuery,
    User,
    UserIntegrationCredential,
)
from leadgen.db.session import session_factory
from leadgen.utils.locale_text import pick as locale_pick

router = APIRouter()
logger = logging.getLogger(__name__)

# 1×1 transparent GIF for the email-open tracking pixel.
_gif_pixel = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00,
    0x80, 0x00, 0x00, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x21,
    0xf9, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x2c, 0x00, 0x00,
    0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44,
    0x01, 0x00, 0x3b,
])


# ── /api/v1/integrations/notion ────────────────────────────────────────
#
# Two connection paths:
# 1. Public OAuth — user clicks "Connect Notion", authorizes via
#    Notion's consent screen, callback saves the access_token.
#    503-safe when NOTION_OAUTH_CLIENT_ID / _SECRET are unset.
# 2. Internal integration token (legacy) — user pastes a token
#    from notion.so/my-integrations. Still works for power users.
#
# Either way, the user must set a database_id via PATCH before
# export works.


def _notion_oauth_configured() -> bool:
    s = get_settings()
    return bool(s.notion_oauth_client_id and s.notion_oauth_client_secret)


def _notion_oauth_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Notion public OAuth is not configured on this deployment. "
            "Set NOTION_OAUTH_CLIENT_ID, NOTION_OAUTH_CLIENT_SECRET and "
            "NOTION_OAUTH_REDIRECT_URI to enable OAuth. You can still "
            "connect via an internal integration token using PUT."
        ),
    )


@router.get(
    "/api/v1/integrations/notion/authorize",
    response_model=NotionAuthorizeResponse,
)
async def notion_authorize(
    current_user: User = Depends(get_current_user),
) -> NotionAuthorizeResponse:
    """Return the Notion consent URL for the public OAuth flow."""
    if not _notion_oauth_configured():
        raise _notion_oauth_unavailable()
    from leadgen.integrations.notion_oauth import (
        StateValidationError,
        build_authorize_url,
        issue_state,
    )

    settings = get_settings()
    try:
        state = issue_state(
            current_user.id, secret=settings.auth_jwt_secret
        )
    except StateValidationError as exc:
        # Misconfigured deployment (no AUTH_JWT_SECRET). Surface as
        # 503 so ops sees the missing env var instead of a generic
        # 500.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    url = build_authorize_url(
        client_id=settings.notion_oauth_client_id,
        redirect_uri=settings.notion_oauth_redirect_uri,
        state=state,
    )
    return NotionAuthorizeResponse(url=url, state=state)


@router.get("/api/v1/integrations/notion/callback")
async def notion_callback(
    code: str = Query(..., min_length=10, max_length=512),
    state: str = Query(..., min_length=1, max_length=256),
    error: str | None = Query(default=None),
) -> Response:
    """OAuth callback — exchanges the code and saves the access token.

    On success, redirects to /app/settings?notion=connected so the
    user sees the "set your database" prompt.
    """
    settings = get_settings()
    return_base = settings.public_app_url.rstrip("/") + "/app/settings"

    if error:
        return Response(
            status_code=302,
            content="redirecting",
            headers={
                "Location": f"{return_base}?notion=error&reason={error}"
            },
        )

    if not _notion_oauth_configured():
        raise _notion_oauth_unavailable()

    from leadgen.core.services.secrets_vault import encrypt
    from leadgen.integrations.notion_oauth import (
        NotionOAuthError,
        StateValidationError,
        exchange_code_for_token,
        verify_state,
    )

    try:
        async with session_factory() as session:
            user_id = await verify_state(
                state,
                secret=settings.auth_jwt_secret,
                session=session,
            )
    except StateValidationError as exc:
        # Malformed / forged / expired state. Don't reveal which —
        # uniform 400 prevents oracles. Logging captures the reason
        # for ops without leaking it to the caller.
        logger.warning(
            "notion_oauth: rejected callback state reason=%s",
            str(exc),
        )
        raise HTTPException(
            status_code=400, detail="invalid state"
        ) from exc

    try:
        token_data = await exchange_code_for_token(
            code,
            client_id=settings.notion_oauth_client_id,
            client_secret=settings.notion_oauth_client_secret,
            redirect_uri=settings.notion_oauth_redirect_uri,
        )
    except NotionOAuthError as exc:
        raise HTTPException(
            status_code=400, detail=f"oauth: {exc}"
        ) from exc

    ciphertext = encrypt(token_data.access_token)
    config: dict[str, Any] = {
        "workspace_id": token_data.workspace_id,
        "workspace_name": token_data.workspace_name,
        "auth_type": "oauth",
    }
    if token_data.owner_email:
        config["owner_email"] = token_data.owner_email

    async with session_factory() as session:
        existing = (
            await session.execute(
                select(UserIntegrationCredential)
                .where(UserIntegrationCredential.user_id == user_id)
                .where(UserIntegrationCredential.provider == "notion")
            )
        ).scalar_one_or_none()
        if existing is None:
            row = UserIntegrationCredential(
                user_id=user_id,
                provider="notion",
                token_ciphertext=ciphertext,
                config=config,
            )
            session.add(row)
        else:
            existing.token_ciphertext = ciphertext
            # Preserve existing database_id if the user already set one.
            if existing.config and existing.config.get("database_id"):
                config["database_id"] = existing.config["database_id"]
            existing.config = config
            existing.updated_at = datetime.now(timezone.utc)
        await session.commit()

    return Response(
        status_code=302,
        content="redirecting",
        headers={"Location": f"{return_base}?notion=connected"},
    )


@router.get(
    "/api/v1/integrations/notion/databases",
    response_model=NotionDatabaseList,
)
async def list_notion_databases(
    current_user: User = Depends(get_current_user),
) -> NotionDatabaseList:
    """Surface databases the connected workspace has shared with us.

    Powers the in-Settings picker the SPA shows after OAuth. The
    legacy internal-token flow can call it too — by then the user
    already pasted ``database_id`` so it's mostly a courtesy there.
    """
    from leadgen.core.services.secrets_vault import decrypt
    from leadgen.integrations.notion import NotionClient, NotionError

    async with session_factory() as session:
        cred = (
            await session.execute(
                select(UserIntegrationCredential)
                .where(
                    UserIntegrationCredential.user_id == current_user.id
                )
                .where(UserIntegrationCredential.provider == "notion")
            )
        ).scalar_one_or_none()
    if cred is None:
        raise HTTPException(
            status_code=400, detail="Notion is not connected"
        )
    try:
        token = decrypt(cred.token_ciphertext)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Saved Notion credentials are unreadable; reconnect.",
        ) from exc
    try:
        async with NotionClient(token) as client:
            results = await client.list_databases()
    except NotionError as exc:
        raise HTTPException(
            status_code=502, detail=f"notion: {exc}"
        ) from exc

    items: list[NotionDatabase] = []
    for db in results:
        db_id = db.get("id")
        if not db_id:
            continue
        title_blocks = db.get("title") or []
        title = "".join(
            str(b.get("plain_text") or "") for b in title_blocks
        ).strip() or "Без названия"
        icon_block = db.get("icon") or {}
        icon = icon_block.get("emoji") or (
            (icon_block.get("external") or {}).get("url")
            if icon_block.get("type") == "external"
            else None
        )
        items.append(
            NotionDatabase(
                id=db_id,
                title=title,
                icon=icon,
                url=db.get("url"),
            )
        )
    return NotionDatabaseList(items=items)


@router.patch(
    "/api/v1/integrations/notion/database",
    response_model=NotionIntegrationStatus,
)
async def set_notion_database(
    body: NotionSetDatabaseRequest,
    current_user: User = Depends(get_current_user),
) -> NotionIntegrationStatus:
    """Set (or update) the database_id for an already-connected Notion account.

    Used after the OAuth flow completes — the token is already saved
    but the user hasn't chosen a target database yet.  Validates
    the database_id against the stored token before saving.
    """
    from leadgen.core.services.secrets_vault import decrypt, mask_token
    from leadgen.integrations.notion import NotionClient, NotionError

    async with session_factory() as session:
        row = (
            await session.execute(
                select(UserIntegrationCredential)
                .where(
                    UserIntegrationCredential.user_id == current_user.id
                )
                .where(UserIntegrationCredential.provider == "notion")
            )
        ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Notion is not connected yet. Connect via OAuth or "
                "supply an internal token first."
            ),
        )

    try:
        token = decrypt(row.token_ciphertext)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Saved token is unreadable — please reconnect Notion.",
        ) from exc

    database_id = body.database_id.strip()
    try:
        async with NotionClient(token) as client:
            schema = await client.get_database(database_id)
    except NotionError as exc:
        raise HTTPException(
            status_code=400,
            detail=locale_pick(
                current_user.language_code,
                ru=(
                    "Notion отказал в доступе к базе. Убедитесь что "
                    "интеграция/подключение имеет доступ к этой базе. "
                    f"Подробности: {exc}"
                ),
                uk=(
                    "Notion відмовив у доступі до бази. Переконайтеся, "
                    "що інтеграція/підключення має доступ до цієї бази. "
                    f"Деталі: {exc}"
                ),
                en=(
                    "Notion denied access to the database. Make sure "
                    "the integration/connection has access to it. "
                    f"Details: {exc}"
                ),
            ),
        ) from exc

    db_title = (schema.get("title") or [{}])[0].get("plain_text") or None
    config = dict(row.config or {})
    config["database_id"] = database_id
    if db_title and not config.get("workspace_name"):
        config["workspace_name"] = db_title

    async with session_factory() as session:
        existing = (
            await session.execute(
                select(UserIntegrationCredential)
                .where(
                    UserIntegrationCredential.user_id == current_user.id
                )
                .where(UserIntegrationCredential.provider == "notion")
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.config = config
            existing.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(existing)
            row = existing

    return NotionIntegrationStatus(
        connected=True,
        token_preview=mask_token(token),
        database_id=database_id,
        workspace_name=config.get("workspace_name"),
        updated_at=row.updated_at,
    )


@router.get(
    "/api/v1/integrations/notion",
    response_model=NotionIntegrationStatus,
)
async def get_notion_integration(
    current_user: User = Depends(get_current_user),
) -> NotionIntegrationStatus:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(UserIntegrationCredential)
                .where(UserIntegrationCredential.user_id == current_user.id)
                .where(UserIntegrationCredential.provider == "notion")
            )
        ).scalar_one_or_none()
    if row is None:
        return NotionIntegrationStatus(connected=False)
    from leadgen.core.services.secrets_vault import decrypt, mask_token

    try:
        preview = mask_token(decrypt(row.token_ciphertext))
    except ValueError:
        preview = None  # key rotated; UI will offer reconnect
    config = row.config or {}
    return NotionIntegrationStatus(
        connected=True,
        token_preview=preview,
        database_id=config.get("database_id"),
        workspace_name=config.get("workspace_name"),
        owner_email=config.get("owner_email"),
        auth_type=config.get("auth_type", "internal"),
        updated_at=row.updated_at,
    )


@router.put(
    "/api/v1/integrations/notion",
    response_model=NotionIntegrationStatus,
)
async def connect_notion(
    body: NotionConnectRequest,
    current_user: User = Depends(get_current_user),
) -> NotionIntegrationStatus:
    """Save (or replace) the user's Notion credentials.

    We immediately probe the database to validate the token has
    access — saving an unworkable credential would just give the
    user a misleading "connected" badge.
    """
    from leadgen.core.services.secrets_vault import encrypt, mask_token
    from leadgen.integrations.notion import NotionClient, NotionError

    token = body.token.strip()
    database_id = body.database_id.strip()
    try:
        async with NotionClient(token) as client:
            schema = await client.get_database(database_id)
    except NotionError as exc:
        raise HTTPException(
            status_code=400,
            detail=locale_pick(
                current_user.language_code,
                ru=(
                    "Notion отказал в доступе к базе. Проверьте что "
                    "интеграция share-нута на эту базу и токен "
                    f"актуален. Подробности: {exc}"
                ),
                uk=(
                    "Notion відмовив у доступі до бази. Перевірте, що "
                    "інтеграцію розшарено на цю базу і токен "
                    f"актуальний. Деталі: {exc}"
                ),
                en=(
                    "Notion denied access to the database. Check that "
                    "the integration is shared with this database and "
                    f"the token is valid. Details: {exc}"
                ),
            ),
        ) from exc

    workspace_name = (schema.get("title") or [{}])[0].get(
        "plain_text"
    ) or None
    ciphertext = encrypt(token)
    config: dict[str, Any] = {
        "database_id": database_id,
        "workspace_name": workspace_name,
    }
    async with session_factory() as session:
        existing = (
            await session.execute(
                select(UserIntegrationCredential)
                .where(
                    UserIntegrationCredential.user_id == current_user.id
                )
                .where(UserIntegrationCredential.provider == "notion")
            )
        ).scalar_one_or_none()
        if existing is None:
            row = UserIntegrationCredential(
                user_id=current_user.id,
                provider="notion",
                token_ciphertext=ciphertext,
                config=config,
            )
            session.add(row)
        else:
            existing.token_ciphertext = ciphertext
            existing.config = config
            existing.updated_at = datetime.now(timezone.utc)
            row = existing
        await session.commit()
        await session.refresh(row)

    return NotionIntegrationStatus(
        connected=True,
        token_preview=mask_token(token),
        database_id=database_id,
        workspace_name=workspace_name,
        updated_at=row.updated_at,
    )


@router.delete("/api/v1/integrations/notion")
async def disconnect_notion(
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(UserIntegrationCredential)
                .where(
                    UserIntegrationCredential.user_id == current_user.id
                )
                .where(UserIntegrationCredential.provider == "notion")
            )
        ).scalar_one_or_none()
        if row is not None:
            await session.delete(row)
            await session.commit()
    return {"ok": True}


@router.post(
    "/api/v1/leads/export-to-notion",
    response_model=NotionExportResponse,
)
async def export_leads_to_notion(
    body: NotionExportRequest,
    current_user: User = Depends(get_current_user),
) -> NotionExportResponse:
    """Push a batch of selected leads as new pages in the user's database.

    Authorisation is per-lead — only leads the caller owns (or can
    see via team membership) get pushed. Per-lead failures inline
    as ``error`` so a misconfigured property doesn't sink the
    whole batch.
    """
    from leadgen.core.services.secrets_vault import decrypt
    from leadgen.integrations.notion import (
        NotionClient,
        NotionError,
        NotionExportRow,
        resolve_property_map,
        row_to_properties,
    )

    async with session_factory() as session:
        cred = (
            await session.execute(
                select(UserIntegrationCredential)
                .where(
                    UserIntegrationCredential.user_id == current_user.id
                )
                .where(UserIntegrationCredential.provider == "notion")
            )
        ).scalar_one_or_none()
        if cred is None:
            raise HTTPException(
                status_code=400,
                detail="Notion is not connected. Connect it in Settings → Интеграции.",
            )
        try:
            token = decrypt(cred.token_ciphertext)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Saved Notion credentials are unreadable "
                    "(encryption key rotated). Reconnect in Settings."
                ),
            ) from exc
        database_id = (cred.config or {}).get("database_id")
        if not database_id:
            raise HTTPException(
                status_code=400,
                detail="Notion database is not set; reconnect in Settings.",
            )

        # Lead authorisation join (same pattern as bulk-draft).
        lead_rows = (
            (
                await session.execute(
                    select(Lead, SearchQuery)
                    .join(SearchQuery, SearchQuery.id == Lead.query_id)
                    .where(Lead.id.in_(list(body.lead_ids)))
                )
            )
            .all()
        )
        authorised: dict[uuid.UUID, tuple[Lead, SearchQuery]] = {}
        for lead, search in lead_rows:
            if search.user_id == current_user.id:
                authorised[lead.id] = (lead, search)
                continue
            if search.team_id is not None and (
                await _membership(session, search.team_id, current_user.id)
            ):
                authorised[lead.id] = (lead, search)
        tags_by_lead = await _tags_by_lead(session, list(authorised))


    items: list[NotionExportItem] = []
    async with NotionClient(token) as client:
        try:
            schema = await client.get_database(database_id)
        except NotionError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Notion database is unreachable: {exc}",
            ) from exc
        mapping = resolve_property_map(schema)
        if "name" not in mapping:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Notion database must have a Title column. "
                    "Add one in Notion and try again."
                ),
            )

        for lead_id in body.lead_ids:
            pair = authorised.get(lead_id)
            if pair is None:
                items.append(
                    NotionExportItem(
                        lead_id=lead_id, error="not authorised"
                    )
                )
                continue
            lead, search = pair
            row = NotionExportRow(
                name=lead.name or "(unnamed)",
                score=int(round(lead.score_ai)) if lead.score_ai else None,
                status=lead.lead_status,
                rating=lead.rating,
                reviews=lead.reviews_count,
                phone=lead.phone,
                website=lead.website,
                address=lead.address,
                category=lead.category,
                notes=lead.notes,
                niche=search.niche,
                region=search.region,
                tags=tuple(
                    tag.name
                    for tag in tags_by_lead.get(lead_id, ())
                ),
            )
            properties = row_to_properties(row, mapping)
            try:
                page = await client.create_page(
                    database_id=database_id, properties=properties
                )
                items.append(
                    NotionExportItem(
                        lead_id=lead_id,
                        notion_url=page.get("url"),
                    )
                )
            except NotionError as exc:
                logger.exception(
                    "notion export: failed for lead %s", lead_id
                )
                items.append(
                    NotionExportItem(lead_id=lead_id, error=str(exc)[:200])
                )

    successes = sum(1 for it in items if it.notion_url)
    return NotionExportResponse(
        items=items,
        success_count=successes,
        failure_count=len(items) - successes,
    )


# ── /api/v1/track — email open pixel (no auth) ─────────────────────────


@router.get("/api/v1/track/{token}", include_in_schema=False)
async def track_email_open(
    token: str,
    lead_id: str,
    user_id: int,
) -> Response:
    try:
        from leadgen.core.services.tracking import verify_track_token

        if verify_track_token(token, lead_id, str(user_id)):
            async with session_factory() as session:
                lead = await session.get(Lead, uuid.UUID(lead_id))
                if lead is not None and lead.deleted_at is None:
                    session.add(
                        LeadActivity(
                            lead_id=uuid.UUID(lead_id),
                            user_id=user_id,
                            kind="email_opened",
                            payload={},
                        )
                    )
                    await session.commit()
    except Exception:
        pass
    return Response(content=_gif_pixel, media_type="image/gif")


# ── /api/v1/oauth/gmail (OAuth flow + send-as-user) ────────────────────
#
# Stage-mode: empty GOOGLE_OAUTH_CLIENT_ID / _SECRET makes
# /authorize, /callback and /leads/{id}/send-email respond 503,
# leaving the rest of the API healthy.


def _gmail_oauth_configured() -> bool:
    s = get_settings()
    return bool(s.google_oauth_client_id and s.google_oauth_client_secret)


def _gmail_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Gmail OAuth is not configured on this deployment. "
            "Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET "
            "and GOOGLE_OAUTH_REDIRECT_URI to enable Gmail send."
        ),
    )


@router.get(
    "/api/v1/oauth/gmail",
    response_model=GmailIntegrationStatus,
)
async def gmail_status(
    current_user: User = Depends(get_current_user),
) -> GmailIntegrationStatus:
    async with session_factory() as session:
        cred = (
            await session.execute(
                select(OAuthCredential)
                .where(OAuthCredential.user_id == current_user.id)
                .where(OAuthCredential.provider == "gmail")
            )
        ).scalar_one_or_none()
    if cred is None:
        return GmailIntegrationStatus(connected=False)
    return GmailIntegrationStatus(
        connected=True,
        account_email=cred.account_email,
        scope=cred.scope,
        expires_at=cred.expires_at,
    )


@router.get(
    "/api/v1/oauth/gmail/authorize",
    response_model=GmailAuthorizeResponse,
)
async def gmail_authorize(
    current_user: User = Depends(get_current_user),
) -> GmailAuthorizeResponse:
    """Mint a consent-screen URL the SPA redirects the user to.

    ``state`` is signed (HMAC-SHA256 over user_id + nonce + ts)
    with ``AUTH_JWT_SECRET`` so the callback can verify the user
    identity without a session-side nonce store. The shared helper
    in ``core.services.oauth_state`` is also used by Notion and
    Outlook.
    """
    if not _gmail_oauth_configured():
        raise _gmail_unavailable()
    from leadgen.core.services.oauth_state import (
        StateValidationError,
        issue_state,
    )
    from leadgen.integrations.gmail import build_authorize_url

    settings = get_settings()
    try:
        state = issue_state(
            current_user.id, secret=settings.auth_jwt_secret
        )
    except StateValidationError as exc:
        # Misconfigured deployment (no AUTH_JWT_SECRET). Surface
        # as 503 so ops sees the missing env var instead of a
        # generic 500.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    url = build_authorize_url(
        client_id=settings.google_oauth_client_id,
        redirect_uri=settings.google_oauth_redirect_uri,
        state=state,
    )
    return GmailAuthorizeResponse(url=url, state=state)


@router.get("/api/v1/oauth/gmail/callback")
async def gmail_callback(
    code: str = Query(..., min_length=10, max_length=512),
    state: str = Query(..., min_length=1, max_length=512),
) -> Response:
    """Receive Google's callback, exchange the code, store tokens.

    We don't go through ``get_current_user`` here because Google
    bounces back without our session cookie when the consent
    happens in a fresh browser context. The user-id is recovered
    from ``state``, which is HMAC-signed — so a forged
    ``"<victim_id>:..."`` callback can't write the attacker's
    Gmail token under the victim's account.
    """
    if not _gmail_oauth_configured():
        raise _gmail_unavailable()
    from leadgen.core.services.oauth_state import (
        StateValidationError,
        verify_state,
    )
    from leadgen.core.services.oauth_store import save_tokens
    from leadgen.integrations.gmail import (
        GmailError,
        exchange_code_for_tokens,
        fetch_account_email,
    )

    settings = get_settings()
    try:
        async with session_factory() as session:
            user_id = await verify_state(
                state,
                secret=settings.auth_jwt_secret,
                session=session,
            )
    except StateValidationError as exc:
        logger.warning(
            "gmail_oauth: rejected callback state reason=%s",
            str(exc),
        )
        raise HTTPException(
            status_code=400, detail="invalid state"
        ) from exc

    try:
        tokens = await exchange_code_for_tokens(
            code,
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=settings.google_oauth_redirect_uri,
        )
    except GmailError as exc:
        raise HTTPException(
            status_code=400, detail=f"oauth: {exc}"
        ) from exc

    account_email = await fetch_account_email(tokens.access_token)
    async with session_factory() as session:
        await save_tokens(
            session,
            user_id=user_id,
            provider="gmail",
            tokens=tokens,
            account_email=account_email,
        )

    # Bounce back to the Settings page where the user kicked the
    # flow off. ``PUBLIC_APP_URL`` is the canonical front-end
    # origin so the redirect lands in their browser tab.
    return_to = (
        settings.public_app_url.rstrip("/") + "/app/settings?gmail=connected"
    )
    return Response(
        status_code=302,
        content="redirecting",
        headers={"Location": return_to},
    )


@router.delete("/api/v1/oauth/gmail")
async def gmail_disconnect(
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        cred = (
            await session.execute(
                select(OAuthCredential)
                .where(OAuthCredential.user_id == current_user.id)
                .where(OAuthCredential.provider == "gmail")
            )
        ).scalar_one_or_none()
        if cred is not None:
            await session.delete(cred)
            await session.commit()
    return {"ok": True}


@router.post(
    "/api/v1/leads/{lead_id}/send-email",
    response_model=GmailSendResponse,
)
async def gmail_send_email(
    lead_id: uuid.UUID,
    body: GmailSendRequest,
    current_user: User = Depends(get_current_user),
) -> GmailSendResponse:
    """Send an email through the user's Gmail or Outlook account.

    Provider is selected via ``body.provider`` (default: gmail).
    Both providers log a ``LeadActivity`` of kind="email_sent" so
    the timeline on the lead modal shows the message went out.
    Body is truncated to 4000 chars in the activity record so the
    JSONB column doesn't bloat over time.
    """
    provider = (body.provider or "gmail").lower()
    if provider == "gmail" and not _gmail_oauth_configured():
        raise _gmail_unavailable()
    if provider == "outlook" and not _outlook_oauth_configured():
        raise _outlook_unavailable()
    from leadgen.core.services.oauth_store import (
        OAuthStoreError,
        ensure_fresh_token,
    )

    async with session_factory() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None or lead.deleted_at is not None:
            raise HTTPException(status_code=404, detail="lead not found")
        # Use the explicit override or pull the first email out of
        # the website-meta blob; fail loudly if neither is set.
        # Sanitize both the recipient and the subject so a CRLF in
        # lead/user-controlled data can't inject extra headers.
        recipient = sanitize_email_header(
            body.to or _extract_lead_email(lead) or ""
        )
        if not recipient:
            raise HTTPException(
                status_code=400,
                detail="lead has no email address on file",
            )
        subject = sanitize_email_header(body.subject)

        try:
            fresh = await ensure_fresh_token(
                session, user_id=current_user.id, provider=provider
            )
        except OAuthStoreError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc)
            ) from exc

        from_addr = fresh.account_email or current_user.email or ""
        if not from_addr:
            raise HTTPException(
                status_code=400,
                detail="cannot determine sender address",
            )

        from leadgen.core.services.tracking import generate_track_token

        _track_token = generate_track_token(
            str(lead_id), str(current_user.id)
        )
        _base = get_settings().public_app_url.rstrip("/")
        _pixel_url = (
            f"{_base}/api/v1/track/{_track_token}"
            f"?lead_id={lead_id}&user_id={current_user.id}"
        )
        _html_body = (
            f"<p>{body.body}</p>"
            f'<img src="{_pixel_url}" width="1" height="1"'
            f' style="display:none" alt="">'
        )

        message_id: str | None = None
        thread_id: str | None = None
        if provider == "gmail":
            from leadgen.integrations.gmail import (
                GmailError,
                build_raw_message,
                send_message,
            )

            raw = build_raw_message(
                from_addr=from_addr,
                to_addr=recipient,
                subject=subject,
                body=body.body,
                html_body=_html_body,
            )
            try:
                resp = await send_message(
                    access_token=fresh.access_token, raw_message=raw
                )
            except GmailError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"gmail send failed: {exc}",
                ) from exc
            message_id = resp.get("id")
            thread_id = resp.get("threadId")
        else:  # outlook
            from leadgen.integrations.outlook import (
                OutlookError,
            )
            from leadgen.integrations.outlook import (
                send_message as outlook_send,
            )

            try:
                await outlook_send(
                    access_token=fresh.access_token,
                    from_addr=from_addr,
                    to_addr=recipient,
                    subject=subject,
                    body=body.body,
                    html_body=_html_body,
                )
            except OutlookError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"outlook send failed: {exc}",
                ) from exc
            # Microsoft Graph's sendMail returns 202 + empty body —
            # we don't get a message id back. Stamp the activity
            # with a synthetic provider-prefixed sentinel so the
            # reply tracker can still tell which provider sent it
            # even without a real message id.
            message_id = None
            thread_id = None

        now = datetime.now(timezone.utc)
        activity = LeadActivity(
            lead_id=lead_id,
            user_id=current_user.id,
            kind="email_sent",
            payload={
                "to": recipient,
                "subject": subject[:255],
                "body": body.body[:4000],
                "message_id": message_id,
                "thread_id": thread_id,
                "provider": provider,
            },
            created_at=now,
        )
        session.add(activity)
        lead.last_touched_at = now
        if lead.lead_status == "new":
            lead.lead_status = "contacted"
        await session.commit()

    return GmailSendResponse(
        message_id=message_id or "",
        thread_id=thread_id,
        sent_at=now,
    )


@router.post("/api/v1/leads/bulk-send-email")
async def bulk_send_email(
    data: BulkSendRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send personalized emails to multiple leads via Henry.

    Rate-limited to 1 email per 2 seconds. Max 50 leads per call.
    Returns summary of sent/failed counts.
    """
    provider = (data.provider or "gmail").lower()
    if provider == "gmail" and not _gmail_oauth_configured():
        raise _gmail_unavailable()
    if provider == "outlook" and not _outlook_oauth_configured():
        raise _outlook_unavailable()

    from leadgen.core.services.oauth_store import (
        OAuthStoreError,
        ensure_fresh_token,
    )

    lead_ids = data.lead_ids[:50]
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")

    analyzer = AIAnalyzer()
    sent = 0
    failed = 0
    errors: list[str] = []

    async with session_factory() as session:
        try:
            fresh = await ensure_fresh_token(
                session, user_id=current_user.id, provider=provider
            )
        except OAuthStoreError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc)
            ) from exc

        from_addr = fresh.account_email or current_user.email or ""
        if not from_addr:
            raise HTTPException(
                status_code=400,
                detail="cannot determine sender address",
            )

        for lead_id_str in lead_ids:
            try:
                try:
                    lead_uuid = uuid.UUID(lead_id_str)
                except (ValueError, AttributeError):
                    failed += 1
                    errors.append(f"{lead_id_str}: invalid id")
                    continue

                lead = await session.get(Lead, lead_uuid)
                if lead is None or lead.deleted_at is not None:
                    failed += 1
                    continue

                # Authorize via the parent search query owner.
                sq = await session.get(SearchQuery, lead.query_id)
                if sq is None or sq.user_id != current_user.id:
                    failed += 1
                    continue

                recipient = sanitize_email_header(
                    _extract_lead_email(lead) or ""
                )
                if not recipient:
                    failed += 1
                    errors.append(
                        locale_pick(
                            current_user.language_code,
                            ru=f"{lead.name}: нет email",
                            uk=f"{lead.name}: немає email",
                            en=f"{lead.name}: no email",
                        )
                    )
                    continue

                email_draft = await analyzer.generate_cold_email(
                    lead={
                        "name": lead.name,
                        "category": lead.category,
                        "address": lead.address,
                        "website": lead.website,
                        "rating": lead.rating,
                        "reviews_count": lead.reviews_count,
                        "tags": lead.tags or [],
                        "summary": lead.summary,
                        "advice": lead.advice,
                    },
                    user_profile={
                        "display_name": current_user.display_name,
                        "email": current_user.email,
                        "language_code": current_user.language_code,
                        "calendly_url": getattr(
                            current_user, "calendly_url", None
                        ),
                        "icp_profile": getattr(
                            current_user, "icp_profile", None
                        ),
                    },
                )
                subject = sanitize_email_header(
                    (email_draft.get("subject") or "").strip()
                    or locale_pick(
                        current_user.language_code,
                        ru=f"Привет от {current_user.display_name or 'нас'}",
                        uk=f"Привіт від {current_user.display_name or 'нас'}",
                        en=f"Hello from {current_user.display_name or 'us'}",
                    )
                )
                body_text = email_draft.get("body") or ""
                html_body = f"<p>{body_text}</p>"

                if provider == "gmail":
                    from leadgen.integrations.gmail import (
                        GmailError,
                        build_raw_message,
                        send_message,
                    )

                    raw = build_raw_message(
                        from_addr=from_addr,
                        to_addr=recipient,
                        subject=subject,
                        body=body_text,
                        html_body=html_body,
                    )
                    try:
                        await send_message(
                            access_token=fresh.access_token,
                            raw_message=raw,
                        )
                    except GmailError as exc:
                        failed += 1
                        errors.append(f"{lead.name}: {str(exc)[:50]}")
                        continue
                else:
                    from leadgen.integrations.outlook import (
                        OutlookError,
                    )
                    from leadgen.integrations.outlook import (
                        send_message as outlook_send,
                    )

                    try:
                        await outlook_send(
                            access_token=fresh.access_token,
                            from_addr=from_addr,
                            to_addr=recipient,
                            subject=subject,
                            body=body_text,
                            html_body=html_body,
                        )
                    except OutlookError as exc:
                        failed += 1
                        errors.append(f"{lead.name}: {str(exc)[:50]}")
                        continue

                now = datetime.now(timezone.utc)
                session.add(
                    LeadActivity(
                        lead_id=lead.id,
                        user_id=current_user.id,
                        kind="email_sent",
                        payload={
                            "to": recipient,
                            "subject": subject[:255],
                            "body": body_text[:4000],
                            "provider": provider,
                            "bulk": True,
                        },
                        created_at=now,
                    )
                )
                lead.last_touched_at = now
                if lead.lead_status == "new":
                    lead.lead_status = "contacted"
                sent += 1
                await asyncio.sleep(2)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "bulk_send: failed lead_id=%s err=%s",
                    lead_id_str,
                    exc,
                )
                failed += 1
                errors.append(f"{lead_id_str}: {str(exc)[:50]}")

        await session.commit()

    return {"sent": sent, "failed": failed, "errors": errors[:10]}


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


# ── /api/v1/integrations/hubspot (OAuth + push-to-CRM) ─────────────────
#
# Stage-mode: empty HUBSPOT_OAUTH_CLIENT_ID / _SECRET makes every
# endpoint below respond 503 — the rest of the API stays usable.


def _hubspot_oauth_configured() -> bool:
    s = get_settings()
    return bool(
        s.hubspot_oauth_client_id and s.hubspot_oauth_client_secret
    )


def _hubspot_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "HubSpot OAuth is not configured on this deployment. "
            "Set HUBSPOT_OAUTH_CLIENT_ID, HUBSPOT_OAUTH_CLIENT_SECRET "
            "and HUBSPOT_OAUTH_REDIRECT_URI to enable HubSpot."
        ),
    )


@router.get(
    "/api/v1/integrations/hubspot",
    response_model=HubspotIntegrationStatus,
)
async def hubspot_status(
    current_user: User = Depends(get_current_user),
) -> HubspotIntegrationStatus:
    async with session_factory() as session:
        cred = (
            await session.execute(
                select(OAuthCredential)
                .where(OAuthCredential.user_id == current_user.id)
                .where(OAuthCredential.provider == "hubspot")
            )
        ).scalar_one_or_none()
    if cred is None:
        return HubspotIntegrationStatus(connected=False)
    # Portal id is appended to the scope string on connect as
    # ``portal:<id>`` so we don't have to widen the OAuth schema
    # for one provider; recover it on read.
    portal_id: int | None = None
    for token in (cred.scope or "").split():
        if token.startswith("portal:"):
            try:
                portal_id = int(token.split(":", 1)[1])
            except (ValueError, IndexError):
                portal_id = None
            break
    return HubspotIntegrationStatus(
        connected=True,
        portal_id=portal_id,
        account_email=cred.account_email,
        scope=cred.scope,
        expires_at=cred.expires_at,
    )


@router.get(
    "/api/v1/integrations/hubspot/authorize",
    response_model=HubspotAuthorizeResponse,
)
async def hubspot_authorize(
    current_user: User = Depends(get_current_user),
) -> HubspotAuthorizeResponse:
    if not _hubspot_oauth_configured():
        raise _hubspot_unavailable()
    from leadgen.core.services.oauth_state import (
        StateValidationError,
        issue_state,
    )
    from leadgen.integrations.hubspot import build_authorize_url

    settings = get_settings()
    try:
        state = issue_state(
            current_user.id, secret=settings.auth_jwt_secret
        )
    except StateValidationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    url = build_authorize_url(
        client_id=settings.hubspot_oauth_client_id,
        redirect_uri=settings.hubspot_oauth_redirect_uri,
        state=state,
    )
    return HubspotAuthorizeResponse(url=url, state=state)


@router.get("/api/v1/integrations/hubspot/callback")
async def hubspot_callback(
    code: str = Query(..., min_length=10, max_length=512),
    state: str = Query(..., min_length=1, max_length=512),
) -> Response:
    if not _hubspot_oauth_configured():
        raise _hubspot_unavailable()
    from leadgen.core.services.oauth_state import (
        StateValidationError,
        verify_state,
    )
    from leadgen.core.services.oauth_store import save_tokens
    from leadgen.integrations.gmail import TokenSet
    from leadgen.integrations.hubspot import (
        HubspotError,
        exchange_code_for_tokens,
        fetch_token_info,
    )

    settings = get_settings()
    try:
        async with session_factory() as session:
            user_id = await verify_state(
                state,
                secret=settings.auth_jwt_secret,
                session=session,
            )
    except StateValidationError as exc:
        logger.warning(
            "hubspot_oauth: rejected callback state reason=%s",
            str(exc),
        )
        raise HTTPException(
            status_code=400, detail="invalid state"
        ) from exc
    try:
        tokens = await exchange_code_for_tokens(
            code,
            client_id=settings.hubspot_oauth_client_id,
            client_secret=settings.hubspot_oauth_client_secret,
            redirect_uri=settings.hubspot_oauth_redirect_uri,
        )
    except HubspotError as exc:
        raise HTTPException(
            status_code=400, detail=f"oauth: {exc}"
        ) from exc

    # Try to enrich with portal id + user email; failure is fine.
    portal_id = tokens.portal_id
    account_email: str | None = None
    try:
        info = await fetch_token_info(tokens.access_token)
        portal_id = portal_id or info.get("hub_id")
        account_email = info.get("user")
    except HubspotError:
        pass

    # Stuff portal id into the scope string so we don't have to
    # widen the OAuthCredential schema for one provider.
    scope_with_portal = tokens.scope or ""
    if portal_id is not None:
        scope_with_portal = (
            f"{scope_with_portal} portal:{portal_id}".strip()
        )
    save_payload = TokenSet(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=tokens.expires_at,
        scope=scope_with_portal or None,
    )
    async with session_factory() as session:
        await save_tokens(
            session,
            user_id=user_id,
            provider="hubspot",
            tokens=save_payload,
            account_email=account_email,
        )

    return_to = (
        settings.public_app_url.rstrip("/")
        + "/app/settings?hubspot=connected"
    )
    return Response(
        status_code=302,
        content="redirecting",
        headers={"Location": return_to},
    )


@router.delete("/api/v1/integrations/hubspot")
async def hubspot_disconnect(
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        cred = (
            await session.execute(
                select(OAuthCredential)
                .where(OAuthCredential.user_id == current_user.id)
                .where(OAuthCredential.provider == "hubspot")
            )
        ).scalar_one_or_none()
        if cred is not None:
            await session.delete(cred)
            await session.commit()
    return {"ok": True}


@router.post(
    "/api/v1/leads/export-to-hubspot",
    response_model=HubspotExportResponse,
)
async def export_leads_to_hubspot(
    body: HubspotExportRequest,
    current_user: User = Depends(get_current_user),
) -> HubspotExportResponse:
    """Push a batch of leads into the user's HubSpot portal as contacts.

    Authorisation matches the Notion export: each lead must belong
    to the caller (or to a team they're a member of). Per-lead
    failures inline as ``error`` strings so a single bad row
    doesn't sink the whole batch.
    """
    if not _hubspot_oauth_configured():
        raise _hubspot_unavailable()
    from leadgen.core.services.oauth_store import (
        OAuthStoreError,
        ensure_fresh_token,
    )
    from leadgen.integrations.hubspot import (
        HubspotClient,
        HubspotContactInput,
        HubspotError,
        split_full_name,
    )

    async with session_factory() as session:
        try:
            fresh = await ensure_fresh_token(
                session, user_id=current_user.id, provider="hubspot"
            )
        except OAuthStoreError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc)
            ) from exc

        lead_rows = (
            await session.execute(
                select(Lead, SearchQuery)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(Lead.id.in_(list(body.lead_ids)))
            )
        ).all()
        authorised: dict[uuid.UUID, tuple[Lead, SearchQuery]] = {}
        for lead, search in lead_rows:
            if search.user_id == current_user.id:
                authorised[lead.id] = (lead, search)
                continue
            if search.team_id is not None and (
                await _membership(
                    session, search.team_id, current_user.id
                )
            ):
                authorised[lead.id] = (lead, search)

    items: list[HubspotExportItem] = []
    async with HubspotClient(fresh.access_token) as client:
        for lead_id in body.lead_ids:
            pair = authorised.get(lead_id)
            if pair is None:
                items.append(
                    HubspotExportItem(
                        lead_id=lead_id, error="not authorised"
                    )
                )
                continue
            lead, search = pair
            email = _extract_lead_email(lead)
            if not email:
                items.append(
                    HubspotExportItem(
                        lead_id=lead_id,
                        error="lead has no email on file",
                    )
                )
                continue
            first, last = split_full_name(lead.name)
            contact = HubspotContactInput(
                email=email,
                firstname=first,
                lastname=last,
                phone=lead.phone,
                company=lead.name,
                website=lead.website,
                city=search.region,
                convioo_score=lead.score_ai,
                convioo_status=lead.lead_status,
            )
            try:
                contact_id = await client.upsert_contact(contact)
                items.append(
                    HubspotExportItem(
                        lead_id=lead_id, contact_id=contact_id
                    )
                )
            except HubspotError as exc:
                logger.exception(
                    "hubspot export: failed for lead %s", lead_id
                )
                items.append(
                    HubspotExportItem(
                        lead_id=lead_id, error=str(exc)[:200]
                    )
                )

    successes = sum(1 for it in items if it.contact_id)

    # LeadActivity rows so the timeline shows the export.
    if successes:
        now = datetime.now(timezone.utc)
        async with session_factory() as session:
            for it in items:
                if not it.contact_id:
                    continue
                session.add(
                    LeadActivity(
                        lead_id=it.lead_id,
                        user_id=current_user.id,
                        kind="exported_hubspot",
                        payload={"contact_id": it.contact_id},
                        created_at=now,
                    )
                )
            await session.commit()

    return HubspotExportResponse(
        items=items,
        success_count=successes,
        failure_count=len(items) - successes,
    )


# ── /api/v1/integrations/pipedrive (OAuth + push-to-CRM) ───────────────
#
# Stage-mode: empty PIPEDRIVE_OAUTH_CLIENT_ID / _SECRET makes every
# endpoint below respond 503 — the rest of the API stays usable.


def _pipedrive_oauth_configured() -> bool:
    s = get_settings()
    return bool(
        s.pipedrive_oauth_client_id and s.pipedrive_oauth_client_secret
    )


def _pipedrive_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Pipedrive OAuth is not configured on this deployment. "
            "Set PIPEDRIVE_OAUTH_CLIENT_ID, "
            "PIPEDRIVE_OAUTH_CLIENT_SECRET and "
            "PIPEDRIVE_OAUTH_REDIRECT_URI to enable Pipedrive."
        ),
    )


async def _pipedrive_credential(
    session, user_id: int
) -> tuple[OAuthCredential, UserIntegrationCredential | None]:
    oauth = (
        await session.execute(
            select(OAuthCredential)
            .where(OAuthCredential.user_id == user_id)
            .where(OAuthCredential.provider == "pipedrive")
        )
    ).scalar_one_or_none()
    if oauth is None:
        return None, None  # type: ignore[return-value]
    cfg = (
        await session.execute(
            select(UserIntegrationCredential)
            .where(
                UserIntegrationCredential.user_id == user_id
            )
            .where(UserIntegrationCredential.provider == "pipedrive")
        )
    ).scalar_one_or_none()
    return oauth, cfg


def _pipedrive_api_domain(scope: str | None) -> str | None:
    for token in (scope or "").split():
        if token.startswith("api_domain:"):
            return token.split(":", 1)[1]
    return None


@router.get(
    "/api/v1/integrations/pipedrive",
    response_model=PipedriveIntegrationStatus,
)
async def pipedrive_status(
    current_user: User = Depends(get_current_user),
) -> PipedriveIntegrationStatus:
    async with session_factory() as session:
        oauth, cfg = await _pipedrive_credential(
            session, current_user.id
        )
    if oauth is None:
        return PipedriveIntegrationStatus(connected=False)
    config = (cfg.config if cfg is not None else {}) or {}
    return PipedriveIntegrationStatus(
        connected=True,
        api_domain=_pipedrive_api_domain(oauth.scope),
        account_email=oauth.account_email,
        scope=oauth.scope,
        expires_at=oauth.expires_at,
        default_pipeline_id=config.get("default_pipeline_id"),
        default_stage_id=config.get("default_stage_id"),
    )


@router.get(
    "/api/v1/integrations/pipedrive/authorize",
    response_model=PipedriveAuthorizeResponse,
)
async def pipedrive_authorize(
    current_user: User = Depends(get_current_user),
) -> PipedriveAuthorizeResponse:
    if not _pipedrive_oauth_configured():
        raise _pipedrive_unavailable()
    from leadgen.core.services.oauth_state import (
        StateValidationError,
        issue_state,
    )
    from leadgen.integrations.pipedrive import build_authorize_url

    settings = get_settings()
    try:
        state = issue_state(
            current_user.id, secret=settings.auth_jwt_secret
        )
    except StateValidationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    url = build_authorize_url(
        client_id=settings.pipedrive_oauth_client_id,
        redirect_uri=settings.pipedrive_oauth_redirect_uri,
        state=state,
    )
    return PipedriveAuthorizeResponse(url=url, state=state)


@router.get("/api/v1/integrations/pipedrive/callback")
async def pipedrive_callback(
    code: str = Query(..., min_length=10, max_length=512),
    state: str = Query(..., min_length=1, max_length=512),
) -> Response:
    if not _pipedrive_oauth_configured():
        raise _pipedrive_unavailable()
    from leadgen.core.services.oauth_state import (
        StateValidationError,
        verify_state,
    )
    from leadgen.core.services.oauth_store import save_tokens
    from leadgen.integrations.gmail import TokenSet
    from leadgen.integrations.pipedrive import (
        PipedriveError,
        exchange_code_for_tokens,
    )

    settings = get_settings()
    try:
        async with session_factory() as session:
            user_id = await verify_state(
                state,
                secret=settings.auth_jwt_secret,
                session=session,
            )
    except StateValidationError as exc:
        logger.warning(
            "pipedrive_oauth: rejected callback state reason=%s",
            str(exc),
        )
        raise HTTPException(
            status_code=400, detail="invalid state"
        ) from exc
    try:
        tokens = await exchange_code_for_tokens(
            code,
            client_id=settings.pipedrive_oauth_client_id,
            client_secret=settings.pipedrive_oauth_client_secret,
            redirect_uri=settings.pipedrive_oauth_redirect_uri,
        )
    except PipedriveError as exc:
        raise HTTPException(
            status_code=400, detail=f"oauth: {exc}"
        ) from exc

    scope_with_domain = tokens.scope or ""
    if tokens.api_domain:
        scope_with_domain = (
            f"{scope_with_domain} api_domain:{tokens.api_domain}".strip()
        )
    save_payload = TokenSet(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=tokens.expires_at,
        scope=scope_with_domain or None,
    )
    async with session_factory() as session:
        await save_tokens(
            session,
            user_id=user_id,
            provider="pipedrive",
            tokens=save_payload,
            account_email=tokens.account_email,
        )

    return_to = (
        settings.public_app_url.rstrip("/")
        + "/app/settings?pipedrive=connected"
    )
    return Response(
        status_code=302,
        content="redirecting",
        headers={"Location": return_to},
    )


@router.delete("/api/v1/integrations/pipedrive")
async def pipedrive_disconnect(
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        oauth, cfg = await _pipedrive_credential(
            session, current_user.id
        )
        if oauth is not None:
            await session.delete(oauth)
        if cfg is not None:
            await session.delete(cfg)
        await session.commit()
    return {"ok": True}


@router.put(
    "/api/v1/integrations/pipedrive/config",
    response_model=PipedriveIntegrationStatus,
)
async def pipedrive_set_config(
    body: PipedriveConfigUpdate,
    current_user: User = Depends(get_current_user),
) -> PipedriveIntegrationStatus:
    async with session_factory() as session:
        oauth, cfg = await _pipedrive_credential(
            session, current_user.id
        )
        if oauth is None:
            raise HTTPException(
                status_code=400, detail="pipedrive is not connected"
            )
        payload = {
            "default_pipeline_id": int(body.default_pipeline_id),
            "default_stage_id": int(body.default_stage_id),
        }
        if cfg is None:
            from leadgen.core.services.secrets_vault import encrypt

            cfg = UserIntegrationCredential(
                user_id=current_user.id,
                provider="pipedrive",
                token_ciphertext=encrypt("pipedrive-config"),
                config=payload,
            )
            session.add(cfg)
        else:
            cfg.config = payload
            cfg.updated_at = datetime.now(timezone.utc)
        await session.commit()
    return PipedriveIntegrationStatus(
        connected=True,
        api_domain=_pipedrive_api_domain(oauth.scope),
        account_email=oauth.account_email,
        scope=oauth.scope,
        expires_at=oauth.expires_at,
        default_pipeline_id=payload["default_pipeline_id"],
        default_stage_id=payload["default_stage_id"],
    )


@router.get(
    "/api/v1/integrations/pipedrive/pipelines",
    response_model=PipedrivePipelinesResponse,
)
async def pipedrive_list_pipelines(
    current_user: User = Depends(get_current_user),
) -> PipedrivePipelinesResponse:
    if not _pipedrive_oauth_configured():
        raise _pipedrive_unavailable()
    from leadgen.core.services.oauth_store import (
        OAuthStoreError,
        ensure_fresh_token,
    )
    from leadgen.integrations.pipedrive import (
        PipedriveClient,
        PipedriveError,
    )

    async with session_factory() as session:
        oauth, _ = await _pipedrive_credential(
            session, current_user.id
        )
        if oauth is None:
            raise HTTPException(
                status_code=400,
                detail="pipedrive is not connected",
            )
        api_domain = _pipedrive_api_domain(oauth.scope)
        if not api_domain:
            raise HTTPException(
                status_code=400,
                detail="pipedrive api_domain unknown — reconnect",
            )
        try:
            fresh = await ensure_fresh_token(
                session,
                user_id=current_user.id,
                provider="pipedrive",
            )
        except OAuthStoreError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc)
            ) from exc

    try:
        async with PipedriveClient(
            fresh.access_token, api_domain
        ) as client:
            pipelines = await client.list_pipelines()
    except PipedriveError as exc:
        raise HTTPException(
            status_code=502, detail=f"pipedrive: {exc}"
        ) from exc

    items = [
        PipedrivePipelineView(
            id=p.id,
            name=p.name,
            stages=[
                PipedriveStageView(
                    id=s.id,
                    name=s.name,
                    pipeline_id=s.pipeline_id,
                    order_nr=s.order_nr,
                )
                for s in p.stages
            ],
        )
        for p in pipelines
    ]
    return PipedrivePipelinesResponse(items=items)


@router.post(
    "/api/v1/leads/export-to-pipedrive",
    response_model=PipedriveExportResponse,
)
async def export_leads_to_pipedrive(
    body: PipedriveExportRequest,
    current_user: User = Depends(get_current_user),
) -> PipedriveExportResponse:
    """Push selected leads into Pipedrive as Person + Deal pairs."""
    if not _pipedrive_oauth_configured():
        raise _pipedrive_unavailable()
    from leadgen.core.services.oauth_store import (
        OAuthStoreError,
        ensure_fresh_token,
    )
    from leadgen.integrations.pipedrive import (
        PipedriveClient,
        PipedriveError,
        PipedrivePersonInput,
    )

    async with session_factory() as session:
        oauth, cfg = await _pipedrive_credential(
            session, current_user.id
        )
        if oauth is None:
            raise HTTPException(
                status_code=400,
                detail="pipedrive is not connected",
            )
        api_domain = _pipedrive_api_domain(oauth.scope)
        if not api_domain:
            raise HTTPException(
                status_code=400,
                detail="pipedrive api_domain unknown — reconnect",
            )
        config = (cfg.config if cfg is not None else {}) or {}
        pipeline_id = config.get("default_pipeline_id")
        stage_id = config.get("default_stage_id")
        if not (pipeline_id and stage_id):
            raise HTTPException(
                status_code=400,
                detail=(
                    "pick a pipeline + stage in Settings → "
                    "Pipedrive before exporting leads"
                ),
            )

        try:
            fresh = await ensure_fresh_token(
                session,
                user_id=current_user.id,
                provider="pipedrive",
            )
        except OAuthStoreError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc)
            ) from exc

        lead_rows = (
            await session.execute(
                select(Lead, SearchQuery)
                .join(SearchQuery, SearchQuery.id == Lead.query_id)
                .where(Lead.id.in_(list(body.lead_ids)))
            )
        ).all()
        authorised: dict[uuid.UUID, tuple[Lead, SearchQuery]] = {}
        for lead, search in lead_rows:
            if search.user_id == current_user.id:
                authorised[lead.id] = (lead, search)
                continue
            if search.team_id is not None and (
                await _membership(
                    session, search.team_id, current_user.id
                )
            ):
                authorised[lead.id] = (lead, search)

    items: list[PipedriveExportItem] = []
    async with PipedriveClient(fresh.access_token, api_domain) as client:
        for lead_id in body.lead_ids:
            pair = authorised.get(lead_id)
            if pair is None:
                items.append(
                    PipedriveExportItem(
                        lead_id=lead_id, error="not authorised"
                    )
                )
                continue
            lead, search = pair
            person_name = lead.name or "(unnamed)"
            email = _extract_lead_email(lead)
            person = PipedrivePersonInput(
                name=person_name,
                email=email,
                phone=lead.phone,
                org_name=lead.name,
            )
            try:
                person_id = await client.upsert_person(person)
                deal_id = await client.create_deal(
                    person_id=person_id,
                    title=f"{search.niche} · {person_name}"[:255],
                    pipeline_id=int(pipeline_id),
                    stage_id=int(stage_id),
                )
                items.append(
                    PipedriveExportItem(
                        lead_id=lead_id,
                        person_id=person_id,
                        deal_id=deal_id,
                    )
                )
            except PipedriveError as exc:
                logger.exception(
                    "pipedrive export: failed for lead %s", lead_id
                )
                items.append(
                    PipedriveExportItem(
                        lead_id=lead_id, error=str(exc)[:200]
                    )
                )

    successes = sum(1 for it in items if it.deal_id)
    if successes:
        now = datetime.now(timezone.utc)
        async with session_factory() as session:
            for it in items:
                if not it.deal_id:
                    continue
                session.add(
                    LeadActivity(
                        lead_id=it.lead_id,
                        user_id=current_user.id,
                        kind="exported_pipedrive",
                        payload={
                            "person_id": it.person_id,
                            "deal_id": it.deal_id,
                        },
                        created_at=now,
                    )
                )
            await session.commit()

    return PipedriveExportResponse(
        items=items,
        success_count=successes,
        failure_count=len(items) - successes,
    )


# ── /api/v1/affiliate (per-user partner dashboard) ─────────────────────


@router.get("/api/v1/affiliate", response_model=AffiliateOverview)
async def get_affiliate_overview(
    current_user: User = Depends(get_current_user),
) -> AffiliateOverview:
    async with session_factory() as session:
        codes = list(
            (
                await session.execute(
                    select(AffiliateCode)
                    .where(AffiliateCode.owner_user_id == current_user.id)
                    .order_by(AffiliateCode.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        counts: dict[str, tuple[int, int]] = {c.code: (0, 0) for c in codes}
        if codes:
            rows = (
                await session.execute(
                    select(
                        Referral.code,
                        func.count(Referral.id),
                        func.count(Referral.first_paid_at),
                    )
                    .where(
                        Referral.code.in_([c.code for c in codes])
                    )
                    .group_by(Referral.code)
                )
            ).all()
            for code, total, paid in rows:
                counts[code] = (int(total or 0), int(paid or 0))

    items = [
        AffiliateCodeSchema(
            code=c.code,
            name=c.name,
            percent_share=c.percent_share,
            active=c.active,
            created_at=c.created_at,
            referrals_count=counts.get(c.code, (0, 0))[0],
            paid_referrals_count=counts.get(c.code, (0, 0))[1],
        )
        for c in codes
    ]
    return AffiliateOverview(
        codes=items,
        total_referrals=sum(i.referrals_count for i in items),
        total_paid_referrals=sum(i.paid_referrals_count for i in items),
    )


@router.post(
    "/api/v1/affiliate/codes", response_model=AffiliateCodeSchema
)
async def create_affiliate_code(
    body: AffiliateCodeCreateRequest,
    current_user: User = Depends(get_current_user),
) -> AffiliateCodeSchema:
    """Create or claim an affiliate slug.

    Empty ``code`` → generate ~8-char URL-safe random slug. Caller-
    chosen slugs are normalised lowercase + restricted to
    ``[a-z0-9_-]`` so the public ``/r/{code}`` URL stays clean.
    """
    raw = (body.code or "").strip().lower()
    if raw:
        cleaned = "".join(
            ch for ch in raw if ch.isalnum() or ch in "-_"
        )
        if len(cleaned) < 3:
            raise HTTPException(
                status_code=400,
                detail="code must be at least 3 alphanumeric chars",
            )
        slug = cleaned[:64]
    else:
        slug = secrets.token_urlsafe(6).lower().replace("_", "").replace("-", "")[:8]
        if len(slug) < 3:
            slug = secrets.token_hex(4)
    async with session_factory() as session:
        existing = await session.get(AffiliateCode, slug)
        if existing is not None:
            raise HTTPException(
                status_code=409, detail="this code is already taken"
            )
        row = AffiliateCode(
            code=slug,
            owner_user_id=current_user.id,
            name=(body.name or "").strip() or None,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return AffiliateCodeSchema(
        code=row.code,
        name=row.name,
        percent_share=row.percent_share,
        active=row.active,
        created_at=row.created_at,
    )


@router.patch(
    "/api/v1/affiliate/codes/{code}",
    response_model=AffiliateCodeSchema,
)
async def update_affiliate_code(
    code: str,
    body: AffiliateCodeUpdate,
    current_user: User = Depends(get_current_user),
) -> AffiliateCodeSchema:
    async with session_factory() as session:
        row = await session.get(AffiliateCode, code.lower())
        if row is None or row.owner_user_id != current_user.id:
            raise HTTPException(status_code=404, detail="code not found")
        if body.name is not None:
            row.name = body.name.strip() or None
        if body.active is not None:
            row.active = bool(body.active)
        await session.commit()
        await session.refresh(row)
    return AffiliateCodeSchema(
        code=row.code,
        name=row.name,
        percent_share=row.percent_share,
        active=row.active,
        created_at=row.created_at,
    )


@router.delete("/api/v1/affiliate/codes/{code}")
async def delete_affiliate_code(
    code: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    async with session_factory() as session:
        row = await session.get(AffiliateCode, code.lower())
        if row is None or row.owner_user_id != current_user.id:
            raise HTTPException(status_code=404, detail="code not found")
        await session.delete(row)
        await session.commit()
    return {"ok": True}
