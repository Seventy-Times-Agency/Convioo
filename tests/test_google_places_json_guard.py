"""Google Places JSON content-type guard.

A 5xx or a fronting proxy can return an HTML/text error page (sometimes
even with a 200). ``resp.json()`` on that raises ``JSONDecodeError`` and
kills enrichment — the collector must surface its own ``GooglePlacesError``
instead.
"""

from __future__ import annotations

import httpx
import pytest

from leadgen.collectors.google_places import (
    GooglePlacesCollector,
    GooglePlacesError,
    _parse_json_response,
)


def _resp(status: int, *, content_type: str, text: str) -> httpx.Response:
    return httpx.Response(
        status,
        headers={"content-type": content_type},
        text=text,
    )


def test_parse_json_response_rejects_html_502() -> None:
    resp = _resp(
        502,
        content_type="text/html",
        text="<html><body>502 Bad Gateway</body></html>",
    )
    with pytest.raises(GooglePlacesError) as exc:
        _parse_json_response(resp, "Text Search")
    assert "502" in str(exc.value)


def test_parse_json_response_rejects_html_with_200() -> None:
    # Proxy serving an HTML error page with a misleading 200.
    resp = _resp(
        200,
        content_type="text/html; charset=utf-8",
        text="<html>maintenance</html>",
    )
    with pytest.raises(GooglePlacesError):
        _parse_json_response(resp, "Text Search")


def test_parse_json_response_rejects_malformed_json_body() -> None:
    # Correct content-type but a truncated/garbage body.
    resp = _resp(200, content_type="application/json", text="{ not json")
    with pytest.raises(GooglePlacesError) as exc:
        _parse_json_response(resp, "Place Details")
    assert "malformed JSON" in str(exc.value)


def test_parse_json_response_accepts_valid_json() -> None:
    resp = _resp(
        200,
        content_type="application/json",
        text='{"places": []}',
    )
    assert _parse_json_response(resp, "Text Search") == {"places": []}


@pytest.mark.asyncio
async def test_get_details_raises_on_non_json_502(monkeypatch) -> None:
    collector = GooglePlacesCollector(api_key="k")

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, headers=None, **kw):
            return httpx.Response(
                502,
                headers={"content-type": "text/html"},
                text="<html>502 Bad Gateway</html>",
            )

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    with pytest.raises(GooglePlacesError):
        await collector.get_details("place-123")
