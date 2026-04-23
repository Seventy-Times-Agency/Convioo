"""Tests for the progress-bar helper used during search."""

from __future__ import annotations

from leadgen.pipeline.progress import BAR_WIDTH, render_bar


def test_render_bar_empty() -> None:
    bar = render_bar(0, 10)
    assert bar == "░" * BAR_WIDTH


def test_render_bar_full() -> None:
    bar = render_bar(10, 10)
    assert bar == "█" * BAR_WIDTH


def test_render_bar_half() -> None:
    bar = render_bar(5, 10)
    assert bar.count("█") == BAR_WIDTH // 2 or bar.count("█") == (BAR_WIDTH + 1) // 2
    assert len(bar) == BAR_WIDTH


def test_render_bar_zero_total() -> None:
    # Division-by-zero guard.
    assert render_bar(0, 0) == "░" * BAR_WIDTH


def test_render_bar_overflow_safe() -> None:
    # Done > total (shouldn't happen, but must not crash).
    bar = render_bar(20, 10)
    assert bar == "█" * BAR_WIDTH
