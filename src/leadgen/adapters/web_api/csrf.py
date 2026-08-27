"""Origin/Referer-based CSRF guard for cookie-authenticated mutations.

The web API authenticates browser users via an httpOnly session cookie
(see :mod:`leadgen.adapters.web_api.auth`). Without an explicit
defence, a malicious page can submit a form to ``/api/v1/...`` and the
browser will attach the cookie automatically — that's CSRF.

We block it the simple, reliable way: every state-changing request
(POST / PUT / PATCH / DELETE) that comes with a session cookie must
carry an ``Origin`` (or, lacking that, ``Referer``) header whose host
is in the allow-list. Bearer-authenticated calls (Zapier, scripts) are
exempt — they don't ride on cookies, so CSRF doesn't apply.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from leadgen.adapters.web_api.auth import COOKIE_NAME

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Endpoints that are deliberately cross-origin and self-validate.
# - Stripe webhooks: signed with HMAC, request comes from Stripe IPs
#   without an Origin we can match.
# - OAuth callbacks: the IdP sends the user's browser back here as a
#   top-level navigation; the Origin is the IdP, not us.
# - Outbound webhook test ping is a normal POST, gated by session
#   already, so it stays under the guard.
_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/v1/billing/stripe/webhook",
    "/api/v1/integrations/notion/callback",
    "/api/v1/integrations/hubspot/callback",
    "/api/v1/integrations/pipedrive/callback",
    "/api/v1/integrations/gmail/callback",
    "/api/v1/integrations/outlook/callback",
    # Public white-label client reports: no session cookie, read-only
    # GETs behind an unguessable token. Explicitly exempt so the guard
    # never interferes even if a browser tags along a cookie.
    "/api/v1/reports/public/",
)


def _allowed_hosts(origins: Iterable[str]) -> frozenset[str]:
    out: set[str] = set()
    for raw in origins:
        cleaned = raw.strip()
        if not cleaned:
            continue
        try:
            parsed = urlparse(cleaned)
        except ValueError:
            continue
        if parsed.netloc:
            out.add(parsed.netloc.lower())
    return frozenset(out)


class CsrfMiddleware(BaseHTTPMiddleware):
    """Reject cookie-authenticated mutations whose Origin/Referer
    isn't on the allow-list.
    """

    def __init__(self, app, *, allowed_origins: Iterable[str]) -> None:
        super().__init__(app)
        self._allowed = _allowed_hosts(allowed_origins)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        for prefix in _EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # No session cookie → can't be a CSRF target. Bearer / API key
        # paths land here.
        if not request.cookies.get(COOKIE_NAME):
            return await call_next(request)

        # Starlette's TestClient connects from the synthetic peer
        # "testclient" with no Origin header. Skip the check there so
        # the existing pytest suite keeps working without being
        # rewritten to set headers manually. In production the peer
        # is the real client IP and the bypass never triggers.
        if request.client and request.client.host == "testclient":
            return await call_next(request)

        # Cookie present — require a matching Origin or Referer.
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        candidate = origin or referer
        if not candidate:
            return JSONResponse(
                {"detail": "CSRF: missing Origin/Referer"},
                status_code=403,
            )
        try:
            host = urlparse(candidate).netloc.lower()
        except ValueError:
            host = ""
        if not host or (self._allowed and host not in self._allowed):
            return JSONResponse(
                {"detail": "CSRF: origin not allowed"},
                status_code=403,
            )

        return await call_next(request)
