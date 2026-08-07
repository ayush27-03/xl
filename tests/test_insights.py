"""Tests for the Insight engine (M7): ranked, capped, traceable, deterministic."""

from __future__ import annotations

from excel_analysis.adapters.workbook_loader import load_workbook
from excel_analysis.app.pipeline import compare_workbooks
from excel_analysis.domain.models import InsightSeverity


def _insights(compare_pair):
    left = load_workbook(compare_pair["compare_left"])
    right = load_workbook(compare_pair["compare_right"])
    return compare_workbooks(left, right).insights


def test_integrity_ranks_above_variance(compare_pair):
    ins = _insights(compare_pair)
    codes = [i.code for i in ins]
    assert "retyped-columns-changed" in codes   # the DoB integrity defect
    assert "systematic-change" in codes          # the pay-run signal
    order = [i.severity for i in ins]
    first_integrity = order.index(InsightSeverity.INTEGRITY)
    first_variance = next(k for k, s in enumerate(order) if s is InsightSeverity.VARIANCE)
    assert first_integrity < first_variance


def test_structural_signals_present(compare_pair):
    codes = [i.code for i in _insights(compare_pair)]
    assert "columns-removed" in codes   # ExitReason dropped
    assert "columns-added" in codes     # Bonus added
    assert "roster-change" in codes     # emp1 left, emp5 joined


def test_insights_are_capped_and_traceable(compare_pair):
    ins = _insights(compare_pair)
    assert len(ins) <= 12
    assert all(i.evidence for i in ins)  # every insight cites the facts it restates


def test_insights_are_deterministic(compare_pair):
    assert _insights(compare_pair) == _insights(compare_pair)
