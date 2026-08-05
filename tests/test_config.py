"""Tests for the Config object and config-driven behavior (M2)."""

from __future__ import annotations

import pytest

from _helpers import make_grid, make_workbook
from excel_analysis.app.pipeline import analyze
from excel_analysis.domain.config import DEFAULT_CONFIG, UnmergePolicy
from excel_analysis.domain.detector import score_header_row
from excel_analysis.domain.errors import ConfigError


def _codes(result):
    return [d.code for d in result.diagnostics]


def test_defaults_reproduce_m0():
    c = DEFAULT_CONFIG
    assert c.low_confidence_threshold == 0.5
    assert c.max_header_candidates == 5
    assert c.header_weights == {
        "filled": 0.30, "texty": 0.35, "unique": 0.20, "distinct_from_next": 0.15,
    }
    assert c.unmerge_policy is UnmergePolicy.PROPAGATE_TOP_LEFT
    assert c.override is None


def test_with_overrides_is_immutable_and_layered():
    c = DEFAULT_CONFIG.with_overrides(
        {"low_confidence_threshold": 0.8, "max_header_candidates": 3}
    )
    assert (c.low_confidence_threshold, c.max_header_candidates) == (0.8, 3)
    # original untouched
    assert DEFAULT_CONFIG.low_confidence_threshold == 0.5


def test_with_overrides_merges_weights():
    c = DEFAULT_CONFIG.with_overrides({"header_weights": {"texty": 0.5}})
    assert c.header_weights["texty"] == 0.5
    assert c.header_weights["filled"] == 0.30  # untouched keys preserved


@pytest.mark.parametrize(
    "mapping",
    [
        {"nope": 1},
        {"header_weights": {"bogus": 0.1}},
        {"low_confidence_threshold": 1.5},
        {"max_header_candidates": "five"},
        {"max_header_candidates": 0},
    ],
)
def test_invalid_overrides_raise_config_error(mapping):
    with pytest.raises(ConfigError):
        DEFAULT_CONFIG.with_overrides(mapping)


def test_weights_change_the_header_score():
    grid = make_grid([["A", "B"], ["x", "y"]])
    base, _ = score_header_row(grid, 0, 1, 0, 1, DEFAULT_CONFIG)
    only_filled = DEFAULT_CONFIG.with_overrides(
        {"header_weights": {"filled": 1.0, "texty": 0.0, "unique": 0.0, "distinct_from_next": 0.0}}
    )
    tweaked, _ = score_header_row(grid, 0, 1, 0, 1, only_filled)
    assert base != tweaked
    assert tweaked == 1.0  # fully populated row scores 1.0 under filled-only weights


def test_threshold_drives_low_confidence_flag():
    # A single-column table scores ~0.85: not flagged at 0.5, flagged at 0.95.
    wb = make_workbook([make_grid([["Fruit"], ["Apple"], ["Banana"]])])
    assert "low-confidence-header" not in _codes(analyze(wb, DEFAULT_CONFIG))
    strict = DEFAULT_CONFIG.with_overrides({"low_confidence_threshold": 0.95})
    assert "low-confidence-header" in _codes(analyze(wb, strict))
