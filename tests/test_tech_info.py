"""Техническая сводка: только владелец и техник, без секретов."""

from __future__ import annotations

import json

import pytest

pytest_plugins = ["tests.test_team_roles_wave1"]


@pytest.mark.asyncio
async def test_tech_info_access_and_no_secrets(crew, monkeypatch):
    from leadgen.config import get_settings
    from leadgen.core.services.platform import tech_info

    async def _no_ip():
        return "203.0.113.7"

    monkeypatch.setattr(tech_info, "egress_ip", _no_ip)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SECRET-VALUE")
    get_settings.cache_clear()
    try:
        team_id = crew["team_id"]
        assert crew["clients"]["admin"].get(f"/api/v1/teams/{team_id}/tech-info").status_code == 403
        r = crew["clients"]["owner"].get(f"/api/v1/teams/{team_id}/tech-info")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["network"]["egress_ip"] == "203.0.113.7"
        assert {"lead.created", "search.finished"} <= set(body["outbound_webhooks"]["events"])
        assert any(row["path"] == "/api/v1/teams/{team_id}/tech-info" for row in body["api"])
        assert len(body["team"]["members"]) == 5
        anthropic = next(i for i in body["integrations"] if i["key"] == "anthropic")
        assert anthropic["configured"] is True
        assert "SECRET-VALUE" not in json.dumps(body)
    finally:
        get_settings.cache_clear()
