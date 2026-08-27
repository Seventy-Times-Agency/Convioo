"""Email header (CRLF) injection guard — Wave 6 item 1."""

from __future__ import annotations

from leadgen.core.services.email_sender import sanitize_email_header


def test_strips_crlf_to_single_line() -> None:
    # A lead name carrying a CRLF + injected header must collapse to one
    # line — the injected "Bcc:" can never reach the transport as a header.
    dirty = "Acme Roofing\r\nBcc: evil@example.test"
    cleaned = sanitize_email_header(dirty)
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert cleaned == "Acme Roofing Bcc: evil@example.test"


def test_strips_bare_cr_and_lf_and_tab() -> None:
    assert sanitize_email_header("a\rb") == "a b"
    assert sanitize_email_header("a\nb") == "a b"
    assert sanitize_email_header("a\tb") == "a b"
    assert sanitize_email_header("a\x00b") == "a b"


def test_trims_and_handles_empty() -> None:
    assert sanitize_email_header("  hi  ") == "hi"
    assert sanitize_email_header("") == ""
    assert sanitize_email_header(None) == ""
    # Leading/trailing CRLF is trimmed away entirely.
    assert sanitize_email_header("\r\nSubject line\r\n") == "Subject line"


def test_template_substitution_subject_is_single_line() -> None:
    # Mirrors the worker's subject build: substitute then sanitize.
    template = "Hi {{name}}, quick question"
    lead_name = "Bob\r\nBcc: spam@x.test"
    subject = sanitize_email_header(
        template.replace("{{name}}", lead_name)
    )
    assert "\n" not in subject and "\r" not in subject
    assert subject == "Hi Bob Bcc: spam@x.test, quick question"


def test_recipient_with_crlf_is_cleaned() -> None:
    recipient = "lead@example.test\r\nBcc: evil@x.test"
    cleaned = sanitize_email_header(recipient)
    assert "\n" not in cleaned and "\r" not in cleaned
    assert cleaned == "lead@example.test Bcc: evil@x.test"
