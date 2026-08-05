"""Config — tunable detection/normalization parameters.

Pure domain data: no I/O (a config *file* is read by an adapter, then validated
here). The defaults reproduce the M0 behavior exactly, so existing golden
snapshots are unaffected unless a tuning value is deliberately changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Optional

from .errors import ConfigError


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
class Override:
    """A user instruction to pin detection. Auto-first posture: an override is
    applied only where it targets; sheets it does not name still auto-detect."""

    sheet: Optional[str] = None
    header_row: Optional[int] = None  # 0-based


@dataclass(frozen=True)
class Config:
    header_weights: dict = field(default_factory=lambda: dict(_DEFAULT_WEIGHTS))
    low_confidence_threshold: float = 0.5
    max_header_candidates: int = 5
    unmerge_policy: UnmergePolicy = UnmergePolicy.PROPAGATE_TOP_LEFT
    override: Optional[Override] = None

    def with_override(self, override: Optional[Override]) -> "Config":
        return replace(self, override=override)

    def with_overrides(self, mapping: dict[str, Any]) -> "Config":
        """Return a new Config with recognized tuning keys overridden. Used to
        layer config-file then CLI values over the defaults (precedence:
        default < file < flag). Unknown keys or bad types raise ConfigError."""
        weights = dict(self.header_weights)
        low = self.low_confidence_threshold
        candidates = self.max_header_candidates
        for key, value in mapping.items():
            if key == "low_confidence_threshold":
                low = _as_unit_float(value, key)
            elif key == "max_header_candidates":
                candidates = _as_positive_int(value, key)
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
