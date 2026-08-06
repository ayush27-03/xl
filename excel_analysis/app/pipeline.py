"""Pipeline — the application-layer orchestrator.

Wires the deterministic domain stages in order: detect -> normalize -> profile.
It depends only on domain modules and the Diagnostics collector; it imports no
adapter, no openpyxl, no CLI. The CLI is the composition root that feeds it
RawWorkbooks and renders the result.

M3: one parameterized flow over table selections and multiple sources (do not
fork per use case). When selections are present, only the selected tables are
profiled; otherwise every sheet is auto-detected. No Aligner or Comparator yet.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..domain.aligner import align
from ..domain.comparator import compare
from ..domain.config import DEFAULT_CONFIG, Config
from ..domain.detector import detect_selection, detect_tables
from ..domain.diagnostics import Diagnostics
from ..domain.errors import NoTableError
from ..domain.models import (
    AnalysisReport,
    AnalysisResult,
    Dataset,
    RawWorkbook,
    TableAnalysis,
    WorkbookAnalysis,
)
from ..domain.normalizer import normalize
from ..domain.profiler import profile_dataset


def analyze(
    raw: RawWorkbook, config: Config = DEFAULT_CONFIG, source_index: int = 0
) -> WorkbookAnalysis:
    diagnostics = Diagnostics()
    analyses: list[TableAnalysis] = []

    selections = [s for s in config.selections if s.source in (None, source_index)]
    if selections:
        for selection in selections:
            matching = [sh for sh in raw.sheets if sh.name == selection.sheet]
            if not matching:
                present = ", ".join(sh.name for sh in raw.sheets)
                diagnostics.warning(
                    "selection-sheet-not-found",
                    f"Selection targets sheet '{selection.sheet}', not in "
                    f"'{raw.path}' (present: {present}).",
                    location=selection.sheet,
                )
                continue
            for sheet in matching:
                for table in detect_selection(sheet, selection, diagnostics, config):
                    analyses.append(_profile(sheet, table, diagnostics, config))
    else:
        for sheet in raw.sheets:
            for table in detect_tables(sheet, diagnostics, config):
                analyses.append(_profile(sheet, table, diagnostics, config))

    return WorkbookAnalysis(
        source_path=raw.path,
        tables=tuple(analyses),
        diagnostics=diagnostics.to_tuple(),
    )


def _profile(sheet, table, diagnostics, config) -> TableAnalysis:
    dataset = normalize(sheet, table, diagnostics, config)
    return TableAnalysis(detected=table, profile=profile_dataset(dataset))


def analyze_sources(
    sources: Sequence[RawWorkbook], config: Config = DEFAULT_CONFIG
) -> AnalysisReport:
    return AnalysisReport(
        sources=tuple(analyze(src, config, i) for i, src in enumerate(sources))
    )


def compare_workbooks(
    left_raw: RawWorkbook,
    right_raw: RawWorkbook,
    config: Config = DEFAULT_CONFIG,
    left_sheet: Optional[str] = None,
    right_sheet: Optional[str] = None,
) -> AnalysisResult:
    """Compare the main table of each workbook: detect -> normalize -> align ->
    compare -> profile. All stage diagnostics accumulate into `warnings`."""
    diagnostics = Diagnostics()
    left_ds = _main_dataset(left_raw, config, left_sheet, diagnostics)
    right_ds = _main_dataset(right_raw, config, right_sheet, diagnostics)
    if left_ds is None:
        raise NoTableError(_no_table_message(left_raw, left_sheet))
    if right_ds is None:
        raise NoTableError(_no_table_message(right_raw, right_sheet))

    alignment = align(left_ds, right_ds, diagnostics)
    diff = compare(left_ds, right_ds, alignment, diagnostics)
    return AnalysisResult(
        left_profile=profile_dataset(left_ds),
        right_profile=profile_dataset(right_ds),
        diff=diff,
        warnings=diagnostics.to_tuple(),
        insights=(),
    )


def _main_dataset(
    raw: RawWorkbook, config: Config, sheet: Optional[str], diagnostics: Diagnostics
) -> Optional[Dataset]:
    """The largest detected table (optionally restricted to one sheet)."""
    best: Optional[tuple[int, Dataset]] = None
    for s in raw.sheets:
        if sheet is not None and s.name != sheet:
            continue
        for table in detect_tables(s, diagnostics, config):
            ds = normalize(s, table, diagnostics, config)
            score = ds.n_rows * len(ds.columns)
            if best is None or score > best[0]:
                best = (score, ds)
    return best[1] if best is not None else None


def _no_table_message(raw: RawWorkbook, sheet: Optional[str]) -> str:
    where = f" on sheet '{sheet}'" if sheet else ""
    return f"No table found to compare in '{raw.path}'{where}."
