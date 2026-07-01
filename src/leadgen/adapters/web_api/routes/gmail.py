"""Gmail + email-tracking-pixel routes: OAuth flow, send, bulk-send."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from leadgen.adapters.web_api.auth import get_current_user
from leadgen.adapters.web_api.routes._helpers import (
    extract_lead_email as _extract_lead_email,
)
from leadgen.adapters.web_api.schemas import (
    BulkSendRequest,
    GmailAuthorizeResponse,
    GmailIntegrationStatus,
    GmailSendRequest,
    GmailSendResponse,
)
from leadgen.analysis.ai_analyzer import AIAnalyzer
from leadgen.config import get_settings
from leadgen.core.services import sanitize_email_header
from leadgen.db.models import (
    Lead,
    LeadActivity,
    OAuthCredential,
    SearchQuery,
    User,
)
from leadgen.db.session import session_factory
from leadgen.utils.locale_text import pick as locale_pick

router = APIRouter()
logger = logging.getLogger(__name__)

# 1x1 transparent GIF for the email-open tracking pixel.
_gif_pixel = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00,
    0x80, 0x00, 0x00, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x21,
    0xf9, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x2c, 0x00, 0x00,
    0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44,
    0x01, 0x00, 0x3b,
])


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
        from leadgen.core.services.suppression import is_suppressed

        if await is_suppressed(
            session, user_id=current_user.id, email=recipient
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "recipient is on your do-not-contact (suppression) list"
                ),
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
        from leadgen.core.services.unsubscribe import unsubscribe_url

        _unsub_url = unsubscribe_url(current_user.id, recipient)

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
                list_unsubscribe_url=_unsub_url,
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
                    list_unsubscribe_url=_unsub_url,
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
    skipped = 0
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

                from leadgen.core.services.suppression import is_suppressed

                if await is_suppressed(
                    session, user_id=current_user.id, email=recipient
                ):
                    skipped += 1
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
                from leadgen.core.services.unsubscribe import unsubscribe_url

                bulk_unsub_url = unsubscribe_url(current_user.id, recipient)

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
                        list_unsubscribe_url=bulk_unsub_url,
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
                            list_unsubscribe_url=bulk_unsub_url,
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

    return {
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "errors": errors[:10],
    }
