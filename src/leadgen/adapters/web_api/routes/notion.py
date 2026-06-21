"""Notion integration routes: OAuth flow, database picker, and lead export."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import (
    membership as _membership,
)
from leadgen.adapters.web_api.routes._helpers import (
    tags_by_lead as _tags_by_lead,
)
from leadgen.adapters.web_api.schemas import (
    NotionAuthorizeResponse,
    NotionConnectRequest,
    NotionDatabase,
    NotionDatabaseList,
    NotionExportItem,
    NotionExportRequest,
    NotionExportResponse,
    NotionIntegrationStatus,
    NotionSetDatabaseRequest,
)
from leadgen.config import get_settings
from leadgen.db.models import (
    Lead,
    SearchQuery,
    UserIntegrationCredential,
)
from leadgen.db.session import session_factory
from leadgen.utils.locale_text import pick as locale_pick

router = APIRouter()
logger = logging.getLogger(__name__)

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
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
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
    current_user=Depends(get_current_user),
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
