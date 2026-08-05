"""CLI — the composition root and interface layer.

The one module that wires the adapters (WorkbookLoader, config loader) to the
application pipeline and a renderer (JSON). It takes one .xlsx, builds a Config
from optional flags/file, runs the slice, and prints the result as JSON.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .adapters.config_loader import load_config_file
from .adapters.serialization import to_json
from .adapters.workbook_loader import load_workbook
from .app.pipeline import analyze
from .domain.config import DEFAULT_CONFIG, Config, Override
from .domain.errors import AnalysisError


def _build_config(args: argparse.Namespace) -> Config:
    config = DEFAULT_CONFIG
    if args.config:
        config = config.with_overrides(load_config_file(args.config))  # default < file
    if args.min_confidence is not None:
        config = config.with_overrides(  # file < flag
            {"low_confidence_threshold": args.min_confidence}
        )
    if args.sheet is not None:
        header0 = args.header - 1 if args.header is not None else None
        config = config.with_override(Override(sheet=args.sheet, header_row=header0))
    return config


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="excel-analyze",
        description=(
            "Analyze one .xlsx workbook: detect tables and profile them. "
            "Prints JSON to stdout."
        ),
    )
    parser.add_argument("path", help="Path to the .xlsx workbook to analyze.")
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
    args = parser.parse_args(argv)

    if args.header is not None and args.sheet is None:
        parser.error("--header requires --sheet")
    if args.header is not None and args.header < 1:
        parser.error("--header must be >= 1")

    try:
        config = _build_config(args)
        raw = load_workbook(args.path)
    except AnalysisError as exc:  # fatal: bad config or unreadable workbook
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = analyze(raw, config)
    print(to_json(result, indent=None if args.compact else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
