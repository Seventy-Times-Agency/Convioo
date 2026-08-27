"""Sentry init wrapper: no-op without DSN, idempotent, safe import."""

from __future__ import annotations

import importlib

import pytest

from leadgen.config import get_settings


def _reload_sentry_setup():
    import leadgen.core.services.sentry_setup as mod

    importlib.reload(mod)
    return mod


def test_configure_sentry_noop_without_dsn(monkeypatch):
    monkeypatch.setattr(get_settings(), "sentry_dsn_api", "", raising=False)
    mod = _reload_sentry_setup()
    # Should not raise even though sentry-sdk may or may not be on
    # the path; the early return skips the import.
    mod.configure_sentry()
    assert mod._CONFIGURED is False


def test_configure_sentry_initialises_when_dsn_set(monkeypatch):
    """When a DSN is set we expect the wrapper to call sentry_sdk.init.

    We mock sentry_sdk so the test doesn't hit the network. The
    wrapper imports the SDK lazily, so monkeypatching ``sys.modules``
    is the cleanest way to inject the fake.
    """
    import sys
    import types

    captured: dict[str, object] = {}

    fake_sdk = types.ModuleType("sentry_sdk")

    def _init(**kwargs):
        captured["init_kwargs"] = kwargs

    fake_sdk.init = _init

    fake_int_asyncio = types.ModuleType(
        "sentry_sdk.integrations.asyncio"
    )
    fake_int_asyncio.AsyncioIntegration = lambda: "asyncio"
    fake_int_fastapi = types.ModuleType(
        "sentry_sdk.integrations.fastapi"
    )
    fake_int_fastapi.FastApiIntegration = lambda: "fastapi"
    fake_int_starlette = types.ModuleType(
        "sentry_sdk.integrations.starlette"
    )
    fake_int_starlette.StarletteIntegration = lambda: "starlette"
    fake_int_sqla = types.ModuleType(
        "sentry_sdk.integrations.sqlalchemy"
    )
    fake_int_sqla.SqlalchemyIntegration = lambda: "sqla"
    fake_int_root = types.ModuleType("sentry_sdk.integrations")

    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)
    monkeypatch.setitem(
        sys.modules, "sentry_sdk.integrations", fake_int_root
    )
    monkeypatch.setitem(
        sys.modules,
        "sentry_sdk.integrations.asyncio",
        fake_int_asyncio,
    )
    monkeypatch.setitem(
        sys.modules,
        "sentry_sdk.integrations.fastapi",
        fake_int_fastapi,
    )
    monkeypatch.setitem(
        sys.modules,
        "sentry_sdk.integrations.starlette",
        fake_int_starlette,
    )
    monkeypatch.setitem(
        sys.modules,
        "sentry_sdk.integrations.sqlalchemy",
        fake_int_sqla,
    )

    public_key = "abc"
    host = "ingest.sentry.io"
    monkeypatch.setattr(
        get_settings(),
        "sentry_dsn_api",
        "https://" + public_key + "@" + host + "/1",
        raising=False,
    )
    monkeypatch.setattr(
        get_settings(), "sentry_environment", "test", raising=False
    )
    monkeypatch.setattr(
        get_settings(), "sentry_traces_sample_rate", 0.25, raising=False
    )

    mod = _reload_sentry_setup()
    mod.configure_sentry()
    # Init was called with the right knobs.
    assert "ingest.sentry.io" in captured["init_kwargs"]["dsn"]
    assert captured["init_kwargs"]["environment"] == "test"
    assert captured["init_kwargs"]["traces_sample_rate"] == 0.25
    assert mod._CONFIGURED is True

    # Idempotent: a second call doesn't re-init.
    captured.clear()
    mod.configure_sentry()
    assert "init_kwargs" not in captured


@pytest.mark.parametrize("dsn", ["", "   ", None])
def test_configure_sentry_treats_blank_dsn_as_off(monkeypatch, dsn):
    monkeypatch.setattr(
        get_settings(), "sentry_dsn_api", dsn or "", raising=False
    )
    mod = _reload_sentry_setup()
    mod.configure_sentry()
    assert mod._CONFIGURED is False
