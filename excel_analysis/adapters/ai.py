"""AI narration (M9) — optional, local-only, at the presentation edge.

The deterministic core never imports or calls this; narration is computed by the
CLI (composition root) and passed to the HTML renderer. The default is the
null-object provider, so with AI off the whole pipeline is byte-identical.

The AI's only job is to narrate the ALREADY-COMPUTED insights/warnings into short
bullets. A restate-only guard rejects any output that introduces a number, or a
non-generic token, absent from the provided facts; on rejection (or any failure /
model-unavailable) narration is empty and the report falls back to the
deterministic findings. Nothing leaves the machine: transport is a local Ollama
HTTP endpoint.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from ..domain.models import Diagnostic, Insight


@dataclass(frozen=True)
class AiSummary:
    """Presentation-layer narration state (never part of AnalysisResult)."""

    requested: bool
    bullets: tuple[str, ...]


class AIProvider(Protocol):
    def narrate(
        self, insights: tuple[Insight, ...], warnings: tuple[Diagnostic, ...]
    ) -> tuple[str, ...]: ...


class NullAIProvider:
    """Default no-op provider — the pipeline is fully correct without AI."""

    def narrate(self, insights, warnings) -> tuple[str, ...]:
        return ()


# --- prompt (restate-only) --------------------------------------------------

_SYSTEM = (
    "You are a reporting assistant for a finance and HR audience. Rewrite the FINDINGS "
    "below as 3 to 6 short bullet points. Rules: use ONLY the facts given; invent no "
    "numbers, column names, values, or conclusions; do not compute or infer anything; "
    "preserve every numeric token exactly as written, including signs and percent signs; "
    "use column names exactly as written (do not expand abbreviations such as DoB); put "
    "data-integrity issues first. Use only numeric tokens from ALLOWED_NUMERIC_TOKENS; "
    "for example, +40.0% is invalid unless +40.0% appears in that list. Output only the "
    "bullet points, one per line, and nothing else."
)


def build_facts(insights, warnings) -> str:
    lines = [f"[{i.severity.value}] {i.message}" for i in insights]
    lines += [
        f"[{w.severity.value}] {w.message}"
        for w in warnings
        if w.severity.value in ("warning", "error")
    ]
    return "\n".join(lines)


def build_prompt(insights, warnings) -> tuple[str, str]:
    facts = build_facts(insights, warnings)
    numbers = ", ".join(dict.fromkeys(re.findall(r"[+-]?\d+(?:\.\d+)?%?", facts)))
    return _SYSTEM, f"ALLOWED_NUMERIC_TOKENS: {numbers}\n\nFINDINGS:\n{facts}"


# --- restate-only guard -----------------------------------------------------

# Mid-sentence capital words that are ordinary function words, not column names.
_GLUE = frozenset(
    "a an and are as at be been but by for from had has have here in into is it its may not "
    "of on or than that the their them then there these this those to was were will with".split()
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z_]*")
_NUM_RE = re.compile(r"[+-]?\d+(?:\.\d+)?%?")
_QUOTE_RE = re.compile(r"[\"']([^\"']+)[\"']")
_SENTENCE_BOUNDARY = frozenset(".!?:\n\r-*•(")
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11",
    "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15", "sixteen": "16",
    "seventeen": "17", "eighteen": "18", "nineteen": "19", "twenty": "20",
}


def _norm(word: str) -> str:
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") else w  # crude singular/plural fold


def _sentence_initial(text: str, start: int) -> bool:
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    return i < 0 or text[i] in _SENTENCE_BOUNDARY


def _number_key(token: str) -> str:
    return token[1:] if token.startswith("+") else token


def passes_guard(output: str, facts: str) -> bool:
    """Restate-only. Rejects (a) any number in `output` - digit or spelled-out -
    absent from `facts`, and (b) any quoted term or mid-sentence capitalized word
    (the shapes an invented column name takes) absent from `facts`. Lowercase
    paraphrase and sentence-initial capitals are free."""
    fact_words = {_norm(m.group()) for m in _WORD_RE.finditer(facts)}
    fact_numbers = {_number_key(m.group()) for m in _NUM_RE.finditer(facts)}
    facts_lower = facts.lower()

    # (a) numbers, as digits and as spelled-out words
    if any(_number_key(m.group()) not in fact_numbers for m in _NUM_RE.finditer(output)):
        return False
    for m in _WORD_RE.finditer(output):
        digit = _NUMBER_WORDS.get(m.group().lower())
        if digit is not None and digit not in fact_numbers:
            return False

    # (b) quoted terms must appear in the facts
    for m in _QUOTE_RE.finditer(output):
        if m.group(1).strip().lower() not in facts_lower:
            return False

    # (b) mid-sentence capitalized words (likely column names) must be in the facts
    for m in _WORD_RE.finditer(output):
        word = m.group()
        if len(word) < 2 or not word[0].isupper() or _sentence_initial(output, m.start()):
            continue
        low = word.lower()
        if low in _NUMBER_WORDS or low in _GLUE or _norm(low) in fact_words:
            continue
        return False

    return True


_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def _parse_bullets(text: str) -> tuple[str, ...]:
    out = []
    for line in text.splitlines():
        cleaned = _BULLET_RE.sub("", line).strip()
        if cleaned:
            out.append(cleaned)
    return tuple(out)


# --- Ollama adapter (local only) --------------------------------------------


class OllamaAIProvider:
    def __init__(self, model: str, host: str = "http://localhost:11434", timeout: float = 120.0):
        self.model = model
        self.host = host
        self.timeout = timeout

    def narrate(self, insights, warnings) -> tuple[str, ...]:
        system, user = build_prompt(insights, warnings)
        try:
            text = self._generate(system, user)
        except Exception:
            return ()  # model unavailable / refused / timeout -> deterministic fallback
        if not passes_guard(text, build_facts(insights, warnings)):
            return ()  # restate-only violation -> deterministic fallback
        return _parse_bullets(text)

    def _generate(self, system: str, user: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "system": system,
                "prompt": user,
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8")).get("response", "")
