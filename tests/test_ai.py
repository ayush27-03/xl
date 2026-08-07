"""Tests for M9 AI narration: null default, restate-only guard, hermetic Ollama
(no live model), renderer states, and AI-off byte-identity."""

from __future__ import annotations

from excel_analysis.adapters.ai import (
    AiSummary,
    NullAIProvider,
    OllamaAIProvider,
    build_facts,
    build_prompt,
    passes_guard,
)
from excel_analysis.adapters.renderers import render_html
from excel_analysis.adapters.workbook_loader import load_workbook
from excel_analysis.app.pipeline import compare_workbooks


def _result(compare_pair):
    return compare_workbooks(
        load_workbook(compare_pair["compare_left"]),
        load_workbook(compare_pair["compare_right"]),
    )


# --- null default -----------------------------------------------------------


def test_null_provider_returns_empty():
    assert NullAIProvider().narrate((), ()) == ()


# --- prompt is restate-only and carries the facts ---------------------------


def test_prompt_is_restate_only_and_carries_facts(compare_pair):
    r = _result(compare_pair)
    system, user = build_prompt(r.insights, r.warnings)
    low = system.lower()
    assert "only" in low and "invent no" in low and "integrity" in low
    assert "Salary" in user  # a real fact from the findings


# --- restate-only guard -----------------------------------------------------


def test_guard_allows_lowercase_paraphrase():
    # lowercase verbs/glue are free; only numbers and cap/quoted names are checked
    assert passes_guard("For Salary, 3 rows changed.", "Salary changed in 3 rows.")
    assert passes_guard("Salary increased notably across rows.", "Salary changed across rows.")


def test_guard_rejects_a_new_number():
    assert not passes_guard("Salary changed in 5 rows.", "Salary changed in 3 rows.")


def test_guard_rejects_a_number_with_the_wrong_unit():
    assert not passes_guard(
        "Largest change was +40.0%.",
        "Largest change was +40.0 and percent change was +10.0%.",
    )


def test_guard_normalizes_spelled_out_numbers():
    assert passes_guard("Salary changed in three rows.", "Salary changed in 3 rows.")


def test_guard_rejects_a_wrong_spelled_out_number():
    assert not passes_guard("Salary changed in seven rows.", "Salary changed in 3 rows.")


def test_guard_rejects_an_invented_quoted_column():
    assert not passes_guard("Bonus changed in the 'Overtime' column.", "Bonus changed.")


def test_guard_rejects_an_invented_midsentence_column():
    assert not passes_guard("Both Salary and Overtime changed.", "Salary changed.")


def test_guard_rejects_an_expanded_column_name():
    assert not passes_guard("The Date of Birth column changed.", "DoB changed.")


def test_guard_allows_a_real_midsentence_column():
    assert passes_guard("Both Salary and City changed.", "Salary changed. City changed.")


def test_guard_accepts_a_faithful_bullet(compare_pair):
    r = _result(compare_pair)
    facts = build_facts(r.insights, r.warnings)
    # real numbers (10.0, three->3) and a real column (Salary), paraphrased
    assert passes_guard("Salary increased by 10.0% across three matched rows.", facts)


# --- Ollama adapter, hermetic (HTTP monkeypatched, never a live model) -------


def test_ollama_unavailable_falls_back_to_empty(compare_pair, monkeypatch):
    r = _result(compare_pair)
    provider = OllamaAIProvider(model="stub")

    def _boom(*_a):
        raise OSError("connection refused")

    monkeypatch.setattr(provider, "_generate", _boom)
    assert provider.narrate(r.insights, r.warnings) == ()


def test_ollama_rejects_hallucinated_output(compare_pair, monkeypatch):
    r = _result(compare_pair)
    provider = OllamaAIProvider(model="stub")
    monkeypatch.setattr(provider, "_generate", lambda *_a: "- Salary rose by 987 dollars.")
    assert provider.narrate(r.insights, r.warnings) == ()  # 987 is not in the facts


def test_ollama_returns_bullets_for_clean_output(compare_pair, monkeypatch):
    r = _result(compare_pair)
    fact = build_facts(r.insights, r.warnings).splitlines()[0].split("] ", 1)[1]
    provider = OllamaAIProvider(model="stub")
    monkeypatch.setattr(provider, "_generate", lambda *_a: f"- {fact}")
    assert provider.narrate(r.insights, r.warnings) == (fact,)


# --- renderer states + AI-off byte-identity ---------------------------------


def test_html_ai_off_is_placeholder_and_unchanged(compare_pair):
    r = _result(compare_pair)
    assert render_html(r) == render_html(r, AiSummary(False, ()))  # default == off
    assert "Not generated" in render_html(r)


def test_html_ai_ready_renders_bullets(compare_pair):
    r = _result(compare_pair)
    h = render_html(r, AiSummary(True, ("Salary changed for all staff.",)))
    assert "Salary changed for all staff." in h
    assert 'class="card ai-summary ready"' in h


def test_html_ai_unavailable_shows_fallback(compare_pair):
    r = _result(compare_pair)
    h = render_html(r, AiSummary(True, ()))
    assert "unavailable" in h.lower()
