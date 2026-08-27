"""Henry knowledge registry: structural integrity + back-compat strings."""

from __future__ import annotations

from leadgen.analysis import knowledge


def test_registry_has_entries() -> None:
    assert len(knowledge.REGISTRY) >= 5


def test_every_doc_has_unique_id() -> None:
    ids = [d.id for d in knowledge.REGISTRY]
    assert len(ids) == len(set(ids))


def test_section_buckets_cover_canonical_set() -> None:
    sections = {d.section for d in knowledge.REGISTRY}
    assert sections == {"features", "scoring", "principles", "workflow"}


def test_find_resolves_known_doc_and_misses_unknown() -> None:
    doc = knowledge.find("ai_score")
    assert doc is not None
    assert doc.section == "scoring"
    assert knowledge.find("totally-fake-thing") is None


def test_account_recovery_doc_is_registered() -> None:
    """Phase 1 features must be visible to Henry."""
    doc = knowledge.find("account_recovery")
    assert doc is not None
    body = " ".join(doc.bullets).lower()
    assert "забыли пароль" in body or "сброс" in body


def test_dedup_doc_is_registered() -> None:
    """Phase 2 fuzzy dedup must be visible to Henry."""
    doc = knowledge.find("dedup")
    assert doc is not None
    body = " ".join(doc.bullets).lower()
    assert "телефон" in body or "phone" in body


def test_niche_autocomplete_doc_is_registered() -> None:
    """Phase 3a feature must be visible to Henry."""
    doc = knowledge.find("niche_autocomplete")
    assert doc is not None
    body = " ".join(doc.bullets).lower()
    assert "автокомплит" in body or "таксономии" in body


def test_all_blocks_concatenates_every_section() -> None:
    rendered = knowledge.all_blocks()
    assert "Что умеет Convioo" in rendered
    assert "Как работает AI-скор" in rendered
    assert "B2B-sales принципы" in rendered
    assert "Как юзер обычно работает" in rendered


def test_legacy_constants_still_exported() -> None:
    """Older callers import the four block constants directly."""
    assert "Convioo" in knowledge.PRODUCT_FEATURES
    assert knowledge.SCORING_EXPLAINED
    assert knowledge.SALES_PRINCIPLES
    assert knowledge.WORKFLOW_TIPS


def test_system_prompt_includes_b2b_frameworks() -> None:
    """Phase 4 prompt enrichment must mention the canonical frameworks."""
    from leadgen.analysis.ai_analyzer import SYSTEM_PROMPT_BASE

    text = SYSTEM_PROMPT_BASE
    assert "BANT" in text
    assert "MEDDIC" in text
    assert "Jobs-To-Be-Done" in text or "JTBD" in text
    assert "ICP" in text
