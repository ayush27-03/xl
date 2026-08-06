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

from typing import Sequence

from ..domain.config import DEFAULT_CONFIG, Config
from ..domain.detector import detect_selection, detect_tables
from ..domain.diagnostics import Diagnostics
from ..domain.models import (
    AnalysisReport,
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
