"""Diagnostics collector — the append-only audit trail (CLAUDE.md rule 4).

Every assumption or ambiguous decision the pipeline makes is recorded here, in
order. Stages receive one collector and append to it; nothing is dropped
silently. Insertion order is preserved, which keeps output deterministic
(CLAUDE.md rule 3).
"""

from __future__ import annotations

from typing import Optional

from .models import Diagnostic, Severity


class Diagnostics:
    def __init__(self) -> None:
        self._items: list[Diagnostic] = []

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        location: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> None:
        self._items.append(Diagnostic(severity, code, message, location, confidence))

    def info(self, code: str, message: str, **kw) -> None:
        self.add(Severity.INFO, code, message, **kw)

    def warning(self, code: str, message: str, **kw) -> None:
        self.add(Severity.WARNING, code, message, **kw)

    def error(self, code: str, message: str, **kw) -> None:
        self.add(Severity.ERROR, code, message, **kw)

    def to_tuple(self) -> tuple[Diagnostic, ...]:
        return tuple(self._items)
