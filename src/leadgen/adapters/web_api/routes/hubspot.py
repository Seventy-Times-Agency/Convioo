"""HubSpot OAuth routes and lead-export endpoint."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import (
    extract_lead_email as _extract_lead_email,
)
from leadgen.adapters.web_api.routes._helpers import (
    membership as _membership,
)
from leadgen.adapters.web_api.schemas import (
    HubspotAuthorizeResponse,
    HubspotExportItem,
    HubspotExportRequest,
    HubspotExportResponse,
    HubspotIntegrationStatus,
)
from leadgen.config import get_settings
from leadgen.db.models import (
    Lead,
    LeadActivity,
    OAuthCredential,
    SearchQuery,
    User,
)
from leadgen.db.session import session_factory

router = APIRouter()
logger = logging.getLogger(__name__)

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
