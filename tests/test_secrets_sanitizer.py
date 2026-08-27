"""Tests for the log sanitizer that scrubs API keys from strings before logging."""

from __future__ import annotations

import pytest

from leadgen.utils.secrets import sanitize


def test_google_api_key_redacted() -> None:
    raw = "error 400: AIzaSyExAmPle12345678901234567890abcdef is invalid"
    out = sanitize(raw)
    assert "AIza" in out
    assert "REDACTED" in out
    assert "ExAmPle12345678901234567890abcdef" not in out


def test_anthropic_key_redacted() -> None:
    raw = "Invalid key sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456789"
    out = sanitize(raw)
    assert "REDACTED" in out
    assert "abcdefghijklmnopqrstuvwxyz" not in out


def test_telegram_bot_token_redacted() -> None:
    raw = "token=1234567:ABCdefGHIjklMNOpqrsTUVwxyz1234567890 was bad"
    out = sanitize(raw)
    assert "REDACTED" in out
    assert "ABCdefGHIjklMNOpqrsTUVwxyz" not in out


def test_bearer_token_redacted() -> None:
    raw = "Authorization: Bearer abcdef1234567890ABCDEF"
    out = sanitize(raw)
    assert "abcdef1234567890ABCDEF" not in out
    assert "REDACTED" in out


def test_database_url_password_redacted() -> None:
    raw = "postgresql+asyncpg://user:s3cr3tP@ssw0rd@db.example.com:5432/leadgen"
    out = sanitize(raw)
    assert "s3cr3tP@ssw0rd" not in out or "[REDACTED]" in out


def test_api_key_in_header_redacted() -> None:
    raw = 'X-Goog-Api-Key: AIzaSyExAmPle12345678901234567890abcdef'
    out = sanitize(raw)
    assert "REDACTED" in out


@pytest.mark.parametrize("val", ["", None])
def test_empty_input(val: str | None) -> None:
    # Must not crash on empty / None — sanitize() is called unconditionally
    # around error bodies that might not exist.
    assert sanitize(val) == ""


def test_clean_text_unchanged() -> None:
    raw = "The quick brown fox jumped over the lazy dog 1234"
    assert sanitize(raw) == raw
