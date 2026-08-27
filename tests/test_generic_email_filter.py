"""Tests for generic-email filtering in the website collector."""

from __future__ import annotations

import pytest

from leadgen.collectors.website import _is_generic_email


@pytest.mark.parametrize(
    "email",
    [
        "info@example.com",
        "hello@example.com",
        "support@example.com",
        "noreply@example.com",
        "no-reply@example.com",
        "do-not-reply@example.com",
        "admin@example.com",
        "contact@example.com",
        "contacts@example.com",
        "info-uk@example.com",
        "support.en@example.com",
        "sales+usa@example.com",
        "hello_team@example.com",
    ],
)
def test_generic_email_detected(email: str) -> None:
    assert _is_generic_email(email)


@pytest.mark.parametrize(
    "email",
    [
        "ivan.petrov@example.com",
        "aaliyah@example.com",
        "ceo@example.com",  # not in our generic list
        "ivan@example.com",
        "hr.manager@example.com",
        "mark@startup.io",
    ],
)
def test_real_email_not_flagged(email: str) -> None:
    assert not _is_generic_email(email)


def test_generic_prefix_with_non_separator_is_real() -> None:
    # "infoservice@..." is not "info<separator>..." — treat as real.
    assert not _is_generic_email("infoservice@example.com")
