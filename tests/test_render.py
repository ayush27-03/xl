"""Tests for the Markdown/HTML renderers (M8). Markdown is golden-snapshotted;
HTML is checked structurally (self-contained, escaped, finance labels)."""

from __future__ import annotations

import os

from excel_analysis.adapters.renderers import render_html, render_markdown
from excel_analysis.adapters.workbook_loader import load_workbook
from excel_analysis.app.pipeline import compare_workbooks
from excel_analysis.cli import main

GOLDEN_MD = os.path.join(os.path.dirname(__file__), "golden", "compare_pair.md")
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def _result(compare_pair):
    return compare_workbooks(
        load_workbook(compare_pair["compare_left"]),
        load_workbook(compare_pair["compare_right"]),
    )


def test_markdown_golden(compare_pair):
    produced = render_markdown(_result(compare_pair))
    if UPDATE:
        with open(GOLDEN_MD, "w", encoding="utf-8", newline="\n") as f:
            f.write(produced)
    with open(GOLDEN_MD, encoding="utf-8", newline="") as f:
        assert produced == f.read().replace("\r\n", "\n")


def test_markdown_uses_finance_labels_and_verbatim_numbers(compare_pair):
    md = render_markdown(_result(compare_pair))
    assert "## Structural changes" in md          # finance label, not "schema"
    assert "schema" not in md.lower()
    assert "## Key findings" in md
    assert "**Integrity**" in md                  # the DoB integrity callout
    assert "+10.0%" in md                         # a number rendered verbatim


def test_html_is_self_contained(compare_pair):
    html = render_html(_result(compare_pair))
    assert html.startswith("<!doctype html>")
    assert "<style>" in html
    assert "http://" not in html and "https://" not in html   # no external refs
    assert "Structural changes" in html
    assert 'class="callout integrity"' in html    # DoB integrity, styled


def test_cli_format_flag(compare_pair, capsys):
    left, right = compare_pair["compare_left"], compare_pair["compare_right"]

    assert main(["compare", left, right, "--format", "md"]) == 0
    assert capsys.readouterr().out.startswith("# Comparison Report")

    assert main(["compare", left, right, "--format", "html"]) == 0
    assert capsys.readouterr().out.startswith("<!doctype html>")

    assert main(["compare", left, right]) == 0    # default stays json
    assert capsys.readouterr().out.lstrip().startswith("{")
