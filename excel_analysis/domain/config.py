"""Config — tunable detection/normalization parameters and table selections.

Pure domain data: no I/O (a config *file* is read by an adapter, then validated
here). The defaults reproduce the M0/M2 behavior exactly, so existing golden
snapshots are unaffected unless a tuning value is deliberately changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Optional, Sequence

from .errors import ConfigError
from .models import CellRange


class UnmergePolicy(str, Enum):
    PROPAGATE_TOP_LEFT = "propagate_top_left"


_DEFAULT_WEIGHTS = {
    "filled": 0.30,
    "texty": 0.35,
    "unique": 0.20,
    "distinct_from_next": 0.15,
}
_WEIGHT_KEYS = frozenset(_DEFAULT_WEIGHTS)


@dataclass(frozen=True)
class TableSelection:
    """A user instruction to profile a specific table (M3).

    Subsumes the M2 single-header override. Auto-first posture: when selections
    are present, only the selected tables are profiled; an invalid pin degrades
    to auto-detection on that sheet.

    - sheet:      the sheet to target (required).
    - header_row: 0-based; pin the header row (auto within the sheet if None).
    - region:     pin the exact table region (auto-detect the sheet if None).
    - source:     source index to target, or None for any source with this sheet.
    """

    sheet: str
    header_row: Optional[int] = None
    region: Optional[CellRange] = None
    source: Optional[int] = None


@dataclass(frozen=True)
class Config:
    header_weights: dict = field(default_factory=lambda: dict(_DEFAULT_WEIGHTS))
    low_confidence_threshold: float = 0.5
    max_header_candidates: int = 5
    unstructured_min_words: int = 3
    unmerge_policy: UnmergePolicy = UnmergePolicy.PROPAGATE_TOP_LEFT
    selections: tuple = ()  # tuple[TableSelection, ...]

    def with_selections(self, selections: Sequence[TableSelection]) -> "Config":
        return replace(self, selections=tuple(selections))

    def with_overrides(self, mapping: dict[str, Any]) -> "Config":
        """Return a new Config with recognized tuning keys overridden. Used to
        layer config-file then CLI values over the defaults (precedence:
        default < file < flag). Unknown keys or bad types raise ConfigError."""
        weights = dict(self.header_weights)
        low = self.low_confidence_threshold
        candidates = self.max_header_candidates
        min_words = self.unstructured_min_words
        for key, value in mapping.items():
            if key == "low_confidence_threshold":
                low = _as_unit_float(value, key)
            elif key == "max_header_candidates":
                candidates = _as_positive_int(value, key)
            elif key == "unstructured_min_words":
                min_words = _as_positive_int(value, key)
            elif key == "header_weights":
                if not isinstance(value, dict):
                    raise ConfigError("'header_weights' must be a JSON object")
                for wk, wv in value.items():
                    if wk not in _WEIGHT_KEYS:
                        raise ConfigError(
                            f"unknown header weight '{wk}'; allowed: {sorted(_WEIGHT_KEYS)}"
                        )
                    weights[wk] = _as_float(wv, wk)
            else:
                raise ConfigError(f"unknown config key '{key}'")
        return replace(
            self,
            header_weights=weights,
            low_confidence_threshold=low,
            max_header_candidates=candidates,
            unstructured_min_words=min_words,
        )


DEFAULT_CONFIG = Config()


def _as_float(value: Any, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"'{key}' must be a number, got {value!r}")
    return float(value)


def _as_unit_float(value: Any, key: str) -> float:
    number = _as_float(value, key)
    if not 0.0 <= number <= 1.0:
        raise ConfigError(f"'{key}' must be within [0, 1], got {number}")
    return number


def _as_positive_int(value: Any, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"'{key}' must be an integer, got {value!r}")
    if value < 1:
        raise ConfigError(f"'{key}' must be >= 1, got {value}")
    return value
