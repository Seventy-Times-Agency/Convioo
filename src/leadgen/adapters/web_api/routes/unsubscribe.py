"""Public one-click unsubscribe endpoint (no auth).

A recipient who clicks the footer link (GET) or whose mailbox sends the
RFC 8058 one-click POST is added to the sender's suppression list, so the
outreach paths never contact them again. The token is HMAC-signed and
self-contained (see ``core/services/unsubscribe``) — no session needed.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from leadgen.core.services.suppression import add_suppression
from leadgen.core.services.unsubscribe import parse_unsubscribe_token
from leadgen.db.session import session_factory

router = APIRouter(tags=["unsubscribe"])


async def _suppress(token: str) -> bool:
    parsed = parse_unsubscribe_token(token)
    if parsed is None:
        return False
    user_id, email = parsed
    async with session_factory() as session:
        await add_suppression(
            session, user_id=user_id, email=email, source="unsubscribe"
        )
        await session.commit()
    return True


_PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<title>Unsubscribe</title></head>"
    "<body style='font-family:system-ui,sans-serif;max-width:480px;"
    "margin:80px auto;padding:0 20px;text-align:center;color:#222'>"
    "<h2>{title}</h2><p style='color:#666'>{body}</p></body></html>"
)


@router.get(
    "/api/v1/unsubscribe/{token}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def unsubscribe_page(token: str) -> HTMLResponse:
    ok = await _suppress(token)
    if ok:
        html = _PAGE.format(
            title="You're unsubscribed",
            body="You won't receive further emails from this sender.",
        )
        return HTMLResponse(content=html)
    html = _PAGE.format(
        title="Invalid link",
        body="This unsubscribe link is invalid or expired.",
    )
    return HTMLResponse(content=html, status_code=400)


@router.post(
    "/api/v1/unsubscribe/{token}",
    include_in_schema=False,
)
async def unsubscribe_one_click(token: str) -> JSONResponse:
    # RFC 8058: mailbox providers POST here to unsubscribe in one click.
    ok = await _suppress(token)
    return JSONResponse(
        {"unsubscribed": ok}, status_code=200 if ok else 400
    )
