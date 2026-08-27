"""HTTP helpers shared by every outbound integration.

``request_with_retry`` wraps ``httpx.AsyncClient`` calls with the
existing :func:`leadgen.utils.retry.retry_async` backoff so a single
transient blip from Notion / HubSpot / Pipedrive / Slack does not
surface as a 500 to the user. Retries are limited to connection
failures, timeouts, and 5xx responses — 4xx errors (auth, validation)
are returned unchanged so callers can handle them deterministically.
"""

from __future__ import annotations

from typing import Any

import httpx

from leadgen.utils.retry import retry_async


class _ServerError(Exception):
    """Sentinel raised on 5xx so retry_async knows to back off."""


# Connection / read / write timeouts and other transient transport
# errors are worth retrying; 4xx is not — that's a permanent error
# from the caller's perspective.
_RETRYABLE = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    _ServerError,
)


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 2,
    source: str | None = None,
    retry_on_5xx: bool = True,
    **kwargs: Any,
) -> httpx.Response:
    """``client.request(method, url, **kwargs)`` with exponential backoff.

    Retries up to ``retries`` times (3 total attempts) on:
    - ``httpx.TimeoutException`` / ``NetworkError`` / ``RemoteProtocolError``
    - any 5xx response (when ``retry_on_5xx`` is true)

    4xx responses are returned to the caller unchanged.
    """

    # Dispatch through ``getattr(client, method.lower())`` rather than
    # ``client.request(method, ...)`` so test suites that monkeypatch
    # ``AsyncClient.get`` / ``.post`` keep working unchanged.
    verb = method.lower()
    if not hasattr(client, verb):
        raise ValueError(f"unsupported HTTP method: {method}")
    call = getattr(client, verb)

    async def _attempt() -> httpx.Response:
        response = await call(url, **kwargs)
        if retry_on_5xx and 500 <= response.status_code < 600:
            raise _ServerError(
                f"upstream {response.status_code} from {url}"
            )
        return response

    return await retry_async(
        _attempt,
        retries=retries,
        base_delay=0.5,
        max_delay=5.0,
        retry_on=_RETRYABLE,
        source=source,
    )
