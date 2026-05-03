"""Source health probes — unconfigured + classification logic.

We don't hit live APIs from CI; the probes are wired for happy-path
in-prod use, and the unconfigured branches let us assert the fan-out
shape without network access.
"""

from __future__ import annotations

import httpx
import pytest

from leadgen.core.services import source_health


@pytest.mark.asyncio
async def test_check_all_returns_unconfigured_when_keys_missing(monkeypatch) -> None:
    # Strip every key the probes look at — the in-process Settings
    # singleton is cached, so patch the attributes directly on its
    # instance.
    from leadgen.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "google_places_api_key", "", raising=False)
    monkeypatch.setattr(s, "yelp_api_key", "", raising=False)
    monkeypatch.setattr(s, "fsq_api_key", "", raising=False)
    monkeypatch.setattr(s, "osm_enabled", False, raising=False)

    results = await source_health.check_all()
    by_name = {r.source: r for r in results}
    assert set(by_name) == {"google_places", "yelp", "foursquare", "osm"}
    for r in results:
        assert r.status == "unconfigured"
        assert r.detail


@pytest.mark.asyncio
async def test_probe_classifies_429_as_rate_limited(monkeypatch) -> None:
    from leadgen.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "yelp_api_key", "sk_test", raising=False)
    monkeypatch.setattr(s, "yelp_enabled", True, raising=False)

    class _Resp:
        status_code = 429
        text = '{"error":"too many"}'

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, *a, **kw):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    out = await source_health._probe_yelp()
    assert out.source == "yelp"
    assert out.status == "rate_limited"
    assert out.http_status == 429


def test_classify_status_code() -> None:
    assert source_health._classify(200) == "ok"
    assert source_health._classify(204) == "ok"
    assert source_health._classify(429) == "rate_limited"
    assert source_health._classify(500) == "degraded"
    assert source_health._classify(503) == "degraded"
    assert source_health._classify(401) == "error"
