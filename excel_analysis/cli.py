"""CLI — the composition root and interface layer.

Two subcommands:
  profile FILE [FILE2] ...   detect and profile tables (M0-M3)
  compare LEFT RIGHT ...      align + diff two tables (M6)

Wires the adapters (loaders, config, renderers) to the application pipeline.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .adapters.config_loader import load_config_file
from .adapters.serialization import analysis_to_json, report_to_json
from .adapters.workbook_loader import load_workbook
from .app.pipeline import analyze_sources, compare_workbooks
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


def _tuned_config(args: argparse.Namespace) -> Config:
    """Apply --config file then --min-confidence (default < file < flag)."""
    config = DEFAULT_CONFIG
    if args.config:
        config = config.with_overrides(load_config_file(args.config))
    if args.min_confidence is not None:
        config = config.with_overrides({"low_confidence_threshold": args.min_confidence})
    return config


def _profile_config(args: argparse.Namespace) -> Config:
    config = _tuned_config(args)
    selections: list[TableSelection] = []
    if args.sheet is not None:
        header0 = args.header - 1 if args.header is not None else None
        selections.append(TableSelection(sheet=args.sheet, header_row=header0))
    for spec in args.select or []:
        selections.append(_parse_select(spec))  # may raise ValueError
    return config.with_selections(selections) if selections else config


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--compact", action="store_true", help="Single-line JSON.")
    p.add_argument("--config", metavar="FILE", help="JSON file overriding thresholds/weights.")
    p.add_argument(
        "--min-confidence", dest="min_confidence", type=float, metavar="X",
        help="Low-confidence threshold in [0,1]; headers below it are flagged.",
    )


def _run_profile(args: argparse.Namespace) -> int:
    try:
        config = _profile_config(args)
    except (ValueError, AnalysisError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        sources = [load_workbook(p) for p in args.paths]
    except AnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(report_to_json(analyze_sources(sources, config), indent=None if args.compact else 2))
    return 0


def _run_compare(args: argparse.Namespace) -> int:
    try:
        config = _tuned_config(args)
        left = load_workbook(args.left)
        right = load_workbook(args.right)
        result = compare_workbooks(left, right, config, args.left_sheet, args.right_sheet)
    except AnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(analysis_to_json(result, indent=None if args.compact else 2))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="excel-analyze",
        description="Detect, profile, and compare tables in .xlsx workbooks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pp = sub.add_parser("profile", help="Detect and profile tables in one or two workbooks.")
    pp.add_argument("paths", nargs="+", help="One or two .xlsx workbooks.")
    _add_common(pp)
    pp.add_argument("--sheet", help="Restrict analysis to this sheet.")
    pp.add_argument("--header", type=int, metavar="N", help="Force 1-based row N as header (requires --sheet).")
    pp.add_argument("--select", action="append", metavar="SHEET[!A1:D10]", help="Profile a specific sheet/region; repeatable.")

    pc = sub.add_parser("compare", help="Compare a table in LEFT against a table in RIGHT.")
    pc.add_argument("left", help="Left .xlsx workbook.")
    pc.add_argument("right", help="Right .xlsx workbook.")
    _add_common(pc)
    pc.add_argument("--left-sheet", help="Sheet to use in LEFT (default: largest table).")
    pc.add_argument("--right-sheet", help="Sheet to use in RIGHT (default: largest table).")

    args = parser.parse_args(argv)

    if args.command == "profile":
        if len(args.paths) > 2:
            parser.error("profile: at most two workbooks are supported")
        if args.header is not None and args.sheet is None:
            parser.error("--header requires --sheet")
        if args.header is not None and args.header < 1:
            parser.error("--header must be >= 1")
        return _run_profile(args)
    return _run_compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
