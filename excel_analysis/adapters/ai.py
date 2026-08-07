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
    "preserve every number exactly as written; put data-integrity issues first. Output "
    "only the bullet points, one per line, and nothing else."
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
    return _SYSTEM, f"FINDINGS:\n{build_facts(insights, warnings)}"


# --- restate-only guard -----------------------------------------------------

_GLUE = frozenset(
    "a an and are as at be been by for from had has have in into is it its may not of on "
    "or than that the their them these this those to was were will with".split()
)
_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _norm(word: str) -> str:
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") else w  # crude singular/plural fold


def passes_guard(output: str, facts: str) -> bool:
    """True only if every NUMBER in `output` appears in `facts`, and every WORD is
    in the facts (singular/plural-insensitive) or a small function-word set."""
    allowed_words = {_norm(m.group()) for m in _WORD_RE.finditer(facts)} | _GLUE
    if any(_norm(m.group()) not in allowed_words for m in _WORD_RE.finditer(output)):
        return False
    fact_numbers = {m.group() for m in _NUM_RE.finditer(facts)}
    return all(m.group() in fact_numbers for m in _NUM_RE.finditer(output))


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
    def __init__(self, model: str, host: str = "http://localhost:11434", timeout: float = 60.0):
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
            {"model": self.model, "system": system, "prompt": user, "stream": False}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8")).get("response", "")
