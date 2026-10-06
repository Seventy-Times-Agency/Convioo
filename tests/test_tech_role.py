"""Роль «Техник»: полный доступ, кроме удаления команды и передачи
владения; выдаёт только владелец; место владельца неприкосновенно."""

from __future__ import annotations

import pytest

from leadgen.core.services.account.team_permissions import (
    PERM_DELETE_TEAM,
    PERM_MANAGE_BILLING,
    PERM_TRANSFER_OWNERSHIP,
    has_full_access,
    has_permission,
    outranks,
)

pytest_plugins = ["tests.test_team_roles_wave1"]


def test_tech_matrix():
    assert has_full_access("tech") and has_full_access("owner")
    assert not has_full_access("admin")
    assert has_permission("tech", PERM_MANAGE_BILLING)
    assert not has_permission("tech", PERM_DELETE_TEAM)
    assert not has_permission("tech", PERM_TRANSFER_OWNERSHIP)
    assert outranks("tech", "admin") and outranks("tech", "sales")
    assert not outranks("tech", "owner") and not outranks("tech", "tech")
    assert not outranks("admin", "tech")


@pytest.mark.asyncio
async def test_tech_role_flow(crew):
    team_id = crew["team_id"]
    ids = crew["ids"]
    c = crew["clients"]
    # Админ не может выдать техника — только владелец.
    r = c["admin"].patch(f"/api/v1/teams/{team_id}/members/{ids['manager']}", json={"role": "tech"})
    assert r.status_code == 403
    r = c["owner"].patch(f"/api/v1/teams/{team_id}/members/{ids['manager']}", json={"role": "tech"})
    assert r.status_code == 200, r.text

    tech = c["manager"]  # теперь техник
    # Деньги и токены — доступны.
    assert tech.get(f"/api/v1/teams/{team_id}/money").status_code == 200
    # Управляет участниками ниже себя.
    r = tech.patch(f"/api/v1/teams/{team_id}/members/{ids['sales2']}", json={"role": "manager"})
    assert r.status_code == 200, r.text
    # Место владельца — нет.
    r = tech.patch(f"/api/v1/teams/{team_id}/members/{ids['owner']}", json={"role": "sales"})
    assert r.status_code == 403
    # Передать владение — нет.
    r = tech.post(f"/api/v1/teams/{team_id}/transfer-ownership", json={"new_owner_user_id": ids["admin"]})
    assert r.status_code == 403
    # Админ не трогает техника.
    r = c["admin"].patch(f"/api/v1/teams/{team_id}/members/{ids['manager']}", json={"role": "sales"})
    assert r.status_code == 403
