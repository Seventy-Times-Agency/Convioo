"""Pipedrive OAuth routes, pipeline listing, and lead-export endpoint."""
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
from leadgen.config import get_settings
from leadgen.db.models import (
    Lead,
    LeadActivity,
    OAuthCredential,
    SearchQuery,
    User,
    UserIntegrationCredential,
)
from leadgen.db.session import session_factory

router = APIRouter()
logger = logging.getLogger(__name__)

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
