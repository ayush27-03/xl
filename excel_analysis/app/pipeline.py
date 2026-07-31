"""Pipeline — the application-layer orchestrator.

Wires the deterministic domain stages in order for one workbook:
detect -> normalize -> profile. It depends only on domain modules and the
Diagnostics collector; it imports no adapter, no openpyxl, no CLI. The CLI is
the composition root that feeds it a RawWorkbook and renders the result.

No Aligner or Comparator yet — this is the first vertical slice.
"""

from __future__ import annotations

from ..domain.detector import detect_tables
from ..domain.diagnostics import Diagnostics
from ..domain.models import RawWorkbook, TableAnalysis, WorkbookAnalysis
from ..domain.normalizer import normalize
from ..domain.profiler import profile_dataset


def analyze(raw: RawWorkbook) -> WorkbookAnalysis:
    diagnostics = Diagnostics()
    analyses: list[TableAnalysis] = []
    for sheet in raw.sheets:
        for table in detect_tables(sheet, diagnostics):
            dataset = normalize(sheet, table, diagnostics)
            profile = profile_dataset(dataset)
            analyses.append(TableAnalysis(detected=table, profile=profile))
    return WorkbookAnalysis(
        source_path=raw.path,
        tables=tuple(analyses),
        diagnostics=diagnostics.to_tuple(),
    )
