"""Lead task CRUD and my-tasks endpoint (routes/tasks.py)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from leadgen.adapters.web_api import auth as auth_mod
from leadgen.db import session as db_session_mod
from leadgen.db.models import Base, Lead, SearchQuery, User
from leadgen.utils import rate_limit as rate_limit_mod


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def patched_session_factory(monkeypatch, db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db_session_mod, "_engine", db_engine)
    monkeypatch.setattr(db_session_mod, "_session_factory", maker)
    return maker


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    for name in (
        "login_limiter",
        "register_limiter",
        "forgot_password_limiter",
        "forgot_email_limiter",
        "reset_password_limiter",
        "resend_verification_limiter",
    ):
        getattr(rate_limit_mod, name)._events.clear()
    yield


def _client_for(user: User) -> TestClient:
    from leadgen.adapters.web_api.app import create_app

    async def _fake() -> User:
        return user

    app = create_app()
    app.dependency_overrides[auth_mod.get_current_user] = _fake
    return TestClient(app)


@pytest_asyncio.fixture
async def seeded(patched_session_factory):
    user = User(id=1, email="u@example.com")
    q = SearchQuery(
        id=uuid.uuid4(), user_id=1, niche="dentist", region="Chicago", scope="city"
    )
    lead = Lead(
        id=uuid.uuid4(),
        query_id=q.id,
        name="Smile Clinic",
        source="google",
        source_id="g1",
    )
    async with patched_session_factory() as s:
        s.add_all([user, q, lead])
        await s.commit()
    return user, lead


@pytest.mark.asyncio
async def test_create_and_list_task(seeded):
    user, lead = seeded
    client = _client_for(user)

    resp = client.post(
        f"/api/v1/leads/{lead.id}/tasks",
        json={"content": "Call back tomorrow"},
    )
    assert resp.status_code == 200, resp.text
    task = resp.json()
    assert task["content"] == "Call back tomorrow"
    assert task["done_at"] is None
    task_id = task["id"]

    resp = client.get(f"/api/v1/leads/{lead.id}/tasks")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == task_id


@pytest.mark.asyncio
async def test_update_task_marks_done(seeded):
    user, lead = seeded
    client = _client_for(user)

    resp = client.post(
        f"/api/v1/leads/{lead.id}/tasks",
        json={"content": "Send proposal"},
    )
    task_id = resp.json()["id"]

    resp = client.patch(f"/api/v1/tasks/{task_id}", json={"done": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["done_at"] is not None

    resp = client.patch(f"/api/v1/tasks/{task_id}", json={"done": False})
    assert resp.status_code == 200
    assert resp.json()["done_at"] is None


@pytest.mark.asyncio
async def test_update_task_content(seeded):
    user, lead = seeded
    client = _client_for(user)

    resp = client.post(
        f"/api/v1/leads/{lead.id}/tasks",
        json={"content": "Old text"},
    )
    task_id = resp.json()["id"]

    resp = client.patch(f"/api/v1/tasks/{task_id}", json={"content": "New text"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "New text"


@pytest.mark.asyncio
async def test_delete_task(seeded):
    user, lead = seeded
    client = _client_for(user)

    resp = client.post(
        f"/api/v1/leads/{lead.id}/tasks",
        json={"content": "Delete me"},
    )
    task_id = resp.json()["id"]

    resp = client.delete(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp = client.get(f"/api/v1/leads/{lead.id}/tasks")
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_delete_task_wrong_user_returns_not_deleted(seeded, patched_session_factory):
    user, lead = seeded
    user2 = User(id=2, email="u2@example.com")
    async with patched_session_factory() as s:
        s.add(user2)
        await s.commit()

    resp = _client_for(user).post(
        f"/api/v1/leads/{lead.id}/tasks",
        json={"content": "Private task"},
    )
    task_id = resp.json()["id"]

    resp = _client_for(user2).delete(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is False


@pytest.mark.asyncio
async def test_list_my_tasks_open_only(seeded):
    user, lead = seeded
    client = _client_for(user)

    client.post(f"/api/v1/leads/{lead.id}/tasks", json={"content": "Open task"})
    resp = client.post(
        f"/api/v1/leads/{lead.id}/tasks", json={"content": "Done task"}
    )
    done_id = resp.json()["id"]
    client.patch(f"/api/v1/tasks/{done_id}", json={"done": True})

    resp = client.get("/api/v1/users/me/tasks?open_only=true")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["content"] == "Open task"


@pytest.mark.asyncio
async def test_list_my_tasks_all(seeded):
    user, lead = seeded
    client = _client_for(user)

    client.post(f"/api/v1/leads/{lead.id}/tasks", json={"content": "Task A"})
    resp = client.post(
        f"/api/v1/leads/{lead.id}/tasks", json={"content": "Task B"}
    )
    client.patch(f"/api/v1/tasks/{resp.json()['id']}", json={"done": True})

    resp = client.get("/api/v1/users/me/tasks?open_only=false")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2
