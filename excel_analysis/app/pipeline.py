"""Pipeline — the application-layer orchestrator.

Wires the deterministic domain stages in order for one workbook:
detect -> normalize -> profile. It depends only on domain modules and the
Diagnostics collector; it imports no adapter, no openpyxl, no CLI. The CLI is
the composition root that feeds it a RawWorkbook and renders the result.

Auto-first override posture: when config pins a sheet, analysis is restricted to
it; a missing target sheet degrades to a warning, not a crash. No Aligner or
Comparator yet — this is the first vertical slice.
"""

from __future__ import annotations

from ..domain.config import DEFAULT_CONFIG, Config
from ..domain.detector import detect_tables
from ..domain.diagnostics import Diagnostics
from ..domain.models import RawWorkbook, TableAnalysis, WorkbookAnalysis
from ..domain.normalizer import normalize
from ..domain.profiler import profile_dataset


def analyze(raw: RawWorkbook, config: Config = DEFAULT_CONFIG) -> WorkbookAnalysis:
    diagnostics = Diagnostics()

    sheets = raw.sheets
    override = config.override
    if override is not None and override.sheet is not None:
        matching = tuple(s for s in raw.sheets if s.name == override.sheet)
        if not matching:
            present = ", ".join(s.name for s in raw.sheets)
            diagnostics.warning(
                "override-sheet-not-found",
                f"Override targets sheet '{override.sheet}', which is not in the "
                f"workbook (present: {present}). Nothing analyzed.",
                location=override.sheet,
            )
            sheets = ()
        else:
            sheets = matching

    analyses: list[TableAnalysis] = []
    for sheet in sheets:
        for table in detect_tables(sheet, diagnostics, config):
            dataset = normalize(sheet, table, diagnostics, config)
            profile = profile_dataset(dataset)
            analyses.append(TableAnalysis(detected=table, profile=profile))
    return WorkbookAnalysis(
        source_path=raw.path,
        tables=tuple(analyses),
        diagnostics=diagnostics.to_tuple(),
    )
