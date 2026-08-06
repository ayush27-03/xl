"""Aligner — decides how two Datasets correspond (M4).

Consumes the Dataset contract and produces an Alignment: column-to-column and
row-to-row correspondence with a basis and confidence (CLAUDE.md rule 4). Pure
domain: no I/O, and it imports no other domain stage.

Columns (two tiers, no more): exact match on canonical column names, then a
collision-safe normalized match (case/whitespace/punctuation); unmatched columns
are reported per side. No fuzzy or content-signature matching — deliberately
unbuilt until evidence shows they are needed.

Rows: detect candidate keys (fully populated + unique after key-normalization in
BOTH datasets), rank them by cross-dataset value overlap, and align via a keyed
dictionary on the best one. With no usable key, fall back to POSITION and say so
loudly. With no shared columns at all, the datasets are "not comparable" — a
first-class result, never a crash (CLAUDE.md rule 5).
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

from .diagnostics import Diagnostics
from .models import (
    Alignment,
    ColumnMatch,
    ColumnMatchBasis,
    Dataset,
    RowMatch,
    RowMatchBasis,
)

_NORMALIZED_MATCH_CONFIDENCE = 0.9
_POSITIONAL_CONFIDENCE = 0.3
_LOW_ROW_OVERLAP = 0.5


def align(left: Dataset, right: Dataset, diagnostics: Diagnostics) -> Alignment:
    matches, only_left, only_right = _match_columns(left, right, diagnostics)
    row = _match_rows(left, right, matches, diagnostics)
    return Alignment(
        column_matches=tuple(matches),
        columns_only_in_left=only_left,
        columns_only_in_right=only_right,
        row_basis=row.basis,
        row_key=row.key,
        row_confidence=row.confidence,
        row_matches=row.matches,
        rows_only_in_left=row.only_left,
        rows_only_in_right=row.only_right,
    )


# --- Column matching --------------------------------------------------------


def _normalize_header(name: str) -> str:
    collapsed = re.sub(r"[^0-9a-z]+", " ", name.strip().lower())
    return re.sub(r"\s+", " ", collapsed).strip()


def _match_columns(left, right, diagnostics):
    left_names = [c.name for c in left.columns]
    right_names = [c.name for c in right.columns]
    right_set = set(right_names)
    matched_left: set[str] = set()
    matched_right: set[str] = set()
    matches: list[ColumnMatch] = []

    # Tier 1: exact match on canonical names (unique per side; dedup already done).
    for name in left_names:
        if name in right_set:
            matches.append(ColumnMatch(name, name, ColumnMatchBasis.EXACT, 1.0))
            matched_left.add(name)
            matched_right.add(name)

    # Tier 2: normalized (case/whitespace/punctuation) on the remainder.
    norm_left: dict[str, list[str]] = {}
    norm_right: dict[str, list[str]] = {}
    for n in left_names:
        if n not in matched_left:
            norm_left.setdefault(_normalize_header(n), []).append(n)
    for n in right_names:
        if n not in matched_right:
            norm_right.setdefault(_normalize_header(n), []).append(n)
    for key in sorted(norm_left):
        lefts = norm_left[key]
        rights = norm_right.get(key)
        if not rights:
            continue
        if len(lefts) == 1 and len(rights) == 1:
            matches.append(
                ColumnMatch(lefts[0], rights[0], ColumnMatchBasis.NORMALIZED, _NORMALIZED_MATCH_CONFIDENCE)
            )
            matched_left.add(lefts[0])
            matched_right.add(rights[0])
        else:
            # Collision: a normalized key maps to >1 column on a side. Never
            # merge — leave them unmatched (reported per side) and flag it.
            diagnostics.warning(
                "ambiguous-column-match",
                f"normalized name '{key}' maps to multiple columns "
                f"(left: {lefts}, right: {rights}); not merged.",
            )

    only_left = tuple(n for n in left_names if n not in matched_left)
    only_right = tuple(n for n in right_names if n not in matched_right)
    if only_left:
        diagnostics.info(
            "columns-only-in-left",
            f"{len(only_left)} column(s) only in the left dataset: {list(only_left)}.",
        )
    if only_right:
        diagnostics.info(
            "columns-only-in-right",
            f"{len(only_right)} column(s) only in the right dataset: {list(only_right)}.",
        )
    return matches, only_left, only_right


# --- Row matching -----------------------------------------------------------


class _RowResult(NamedTuple):
    basis: RowMatchBasis
    key: Optional[str]
    confidence: float
    matches: tuple
    only_left: tuple
    only_right: tuple


def _normalize_key(value) -> Optional[str]:
    """Key normalization: trim whitespace, drop leading zeros, unify text vs
    number. (Date/text reconciliation is an M5 cell-comparison concern.)"""
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    if re.fullmatch(r"[+-]?\d+", s):
        return str(int(s))
    try:
        f = float(s)
    except (ValueError, OverflowError):
        return s
    return str(int(f)) if f.is_integer() else repr(f)


def _column(dataset: Dataset, name: str):
    for c in dataset.columns:
        if c.name == name:
            return c
    raise KeyError(name)  # names come from the dataset itself


def _key_values(dataset: Dataset, name: str) -> Optional[list[str]]:
    """Normalized key strings if the column is a clean key (fully populated and
    unique after normalization), else None."""
    normed = [_normalize_key(v) for v in _column(dataset, name).values]
    if any(v is None for v in normed):
        return None
    if len(set(normed)) != len(normed):
        return None
    return normed


def _match_rows(left, right, col_matches, diagnostics) -> _RowResult:
    if not col_matches:
        diagnostics.warning(
            "not-comparable",
            "The two datasets share no columns; they are not comparable by row.",
        )
        return _RowResult(
            RowMatchBasis.NONE, None, 0.0, (),
            tuple(range(left.n_rows)), tuple(range(right.n_rows)),
        )

    candidates = []  # (overlap, left_column_index, cm, lvals, rvals)
    for idx, cm in enumerate(col_matches):
        lvals = _key_values(left, cm.left)
        rvals = _key_values(right, cm.right)
        if lvals is None or rvals is None:
            continue
        union = set(lvals) | set(rvals)
        overlap = len(set(lvals) & set(rvals)) / len(union) if union else 0.0
        candidates.append((overlap, idx, cm, lvals, rvals))

    if not candidates:
        return _positional(left, right, diagnostics)

    # Overlap-ranked; deterministic tie-break by left column order.
    candidates.sort(key=lambda t: (-t[0], t[1]))
    overlap, _, cm, lvals, rvals = candidates[0]
    return _keyed(cm, lvals, rvals, overlap, diagnostics)


def _keyed(cm, lvals, rvals, overlap, diagnostics) -> _RowResult:
    right_index = {k: i for i, k in enumerate(rvals)}
    matches: list[RowMatch] = []
    matched_right: set[int] = set()
    only_left: list[int] = []
    for i, k in enumerate(lvals):
        j = right_index.get(k)
        if j is None:
            only_left.append(i)
        else:
            matches.append(RowMatch(i, j, k))
            matched_right.add(j)
    only_right = [j for j in range(len(rvals)) if j not in matched_right]

    confidence = round(overlap, 4)
    label = cm.left if cm.left == cm.right else f"{cm.left} / {cm.right}"
    emit = diagnostics.info if overlap >= _LOW_ROW_OVERLAP else diagnostics.warning
    emit(
        "row-key",
        f"Rows aligned on key '{label}': {len(matches)} matched, "
        f"{len(only_left)} only-left, {len(only_right)} only-right "
        f"(key overlap {confidence}).",
        confidence=confidence,
    )
    return _RowResult(
        RowMatchBasis.KEY, cm.left, confidence, tuple(matches),
        tuple(only_left), tuple(only_right),
    )


def _positional(left, right, diagnostics) -> _RowResult:
    n = min(left.n_rows, right.n_rows)
    matches = tuple(RowMatch(i, i) for i in range(n))
    diagnostics.warning(
        "row-positional",
        f"No reliable row key found; matched {n} row(s) by POSITION only. "
        f"Row correspondence is unverified - treat cell differences with caution.",
        confidence=_POSITIONAL_CONFIDENCE,
    )
    return _RowResult(
        RowMatchBasis.POSITION, None, _POSITIONAL_CONFIDENCE, matches,
        tuple(range(n, left.n_rows)), tuple(range(n, right.n_rows)),
    )
