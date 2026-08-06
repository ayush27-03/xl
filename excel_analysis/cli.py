"""CLI — the composition root and interface layer.

Wires the adapters (WorkbookLoader, config loader) to the application pipeline
and a renderer (JSON). Takes one or two .xlsx workbooks, builds a Config from
optional flags/file/selections, runs the pipeline, and prints a JSON report.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .adapters.config_loader import load_config_file
from .adapters.serialization import report_to_json
from .adapters.workbook_loader import load_workbook
from .app.pipeline import analyze_sources
from .domain.config import DEFAULT_CONFIG, Config, TableSelection
from .domain.errors import AnalysisError
from .domain.models import parse_range


def _parse_select(spec: str) -> TableSelection:
    """Parse a --select value: 'Sheet' or 'Sheet!A1:D10'. Raises ValueError."""
    if "!" in spec:
        sheet, rng = spec.split("!", 1)
        if not sheet:
            raise ValueError(f"invalid selection '{spec}': missing sheet name")
        return TableSelection(sheet=sheet, region=parse_range(rng))
    if not spec:
        raise ValueError("invalid selection: empty sheet name")
    return TableSelection(sheet=spec)


def _build_config(args: argparse.Namespace) -> Config:
    config = DEFAULT_CONFIG
    if args.config:
        config = config.with_overrides(load_config_file(args.config))  # default < file
    if args.min_confidence is not None:
        config = config.with_overrides({"low_confidence_threshold": args.min_confidence})
    selections: list[TableSelection] = []
    if args.sheet is not None:
        header0 = args.header - 1 if args.header is not None else None
        selections.append(TableSelection(sheet=args.sheet, header_row=header0))
    for spec in args.select or []:
        selections.append(_parse_select(spec))  # may raise ValueError
    if selections:
        config = config.with_selections(selections)
    return config


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="excel-analyze",
        description=(
            "Analyze one or two .xlsx workbooks: detect tables and profile them. "
            "Prints a JSON report to stdout."
        ),
    )
    parser.add_argument("paths", nargs="+", help="One or two .xlsx workbooks.")
    parser.add_argument(
        "--compact", action="store_true", help="Single-line JSON instead of indented."
    )
    parser.add_argument(
        "--config", metavar="FILE",
        help="JSON file overriding detection thresholds/weights.",
    )
    parser.add_argument(
        "--min-confidence", dest="min_confidence", type=float, metavar="X",
        help="Low-confidence threshold in [0,1]; headers below it are flagged.",
    )
    parser.add_argument(
        "--sheet", help="Restrict analysis to this sheet (auto-detect within it)."
    )
    parser.add_argument(
        "--header", type=int, metavar="N",
        help="Force 1-based row N as the header on --sheet (requires --sheet).",
    )
    parser.add_argument(
        "--select", action="append", metavar="SHEET[!A1:D10]",
        help="Profile a specific sheet or region; repeatable.",
    )
    args = parser.parse_args(argv)

    if len(args.paths) > 2:
        parser.error("at most two workbooks are supported")
    if args.header is not None and args.sheet is None:
        parser.error("--header requires --sheet")
    if args.header is not None and args.header < 1:
        parser.error("--header must be >= 1")

    try:
        config = _build_config(args)
    except ValueError as exc:  # malformed --select
        parser.error(str(exc))
    except AnalysisError as exc:  # bad config file/values
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        sources = [load_workbook(p) for p in args.paths]
    except AnalysisError as exc:  # unreadable workbook
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = analyze_sources(sources, config)
    print(report_to_json(report, indent=None if args.compact else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
