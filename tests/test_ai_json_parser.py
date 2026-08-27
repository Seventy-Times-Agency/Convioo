from __future__ import annotations

from leadgen.analysis.ai_analyzer import _extract_json


def test_extract_json_plain() -> None:
    payload = '{"score": 80, "tags": ["hot"]}'
    assert _extract_json(payload) == {"score": 80, "tags": ["hot"]}


def test_extract_json_from_markdown_fence() -> None:
    payload = '```json\n{"score": 50, "summary": "ok"}\n```'
    assert _extract_json(payload)["score"] == 50


def test_extract_json_embedded() -> None:
    payload = 'Result: {"score": 20, "tags": ["cold"]} thanks'
    data = _extract_json(payload)
    assert data["score"] == 20
    assert data["tags"] == ["cold"]
