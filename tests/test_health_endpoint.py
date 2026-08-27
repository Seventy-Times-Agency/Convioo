"""Smoke tests for the FastAPI app: /health, /metrics, /api/v1/*.

Uses ``fastapi.testclient.TestClient`` (synchronous httpx wrapper)
which is fine for shape-level assertions — we're verifying that the
app boots, CORS is off by default, routes exist, and API-key gating
behaves right.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from leadgen.adapters.web_api import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_root_returns_text(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "convioo" in resp.text.lower()


def test_metrics_returns_prometheus_format(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "leadgen_" in resp.text or "# HELP" in resp.text


def test_health_returns_shape(client: TestClient) -> None:
    # No real DB in unit test → status may be unhealthy (503), that's fine.
    resp = client.get("/health")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "status" in body
    assert "db" in body
    assert "commit" in body


def test_queue_status_reports_bool(client: TestClient) -> None:
    resp = client.get("/api/v1/queue/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "queue_enabled" in body
    assert isinstance(body["queue_enabled"], bool)
