from __future__ import annotations

from leadgen.pipeline.search import _safe_filename


def test_safe_filename_replaces_disallowed_characters() -> None:
    assert _safe_filename("leads:moscow/clinics?.xlsx") == "leads_moscow_clinics_.xlsx"


def test_safe_filename_replaces_spaces() -> None:
    assert _safe_filename("leads moscow april.xlsx") == "leads_moscow_april.xlsx"
