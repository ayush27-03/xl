"""CLI — the composition root and interface layer.

The one module that wires an adapter (WorkbookLoader) to the application
pipeline and a renderer (JSON). It takes one .xlsx, runs the slice, and prints
the DetectedTables and DatasetProfiles as JSON.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .adapters.serialization import to_json
from .adapters.workbook_loader import load_workbook
from .app.pipeline import analyze
from .domain.errors import AnalysisError


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
        "--compact",
        action="store_true",
        help="Emit single-line JSON instead of indented output.",
    )
    args = parser.parse_args(argv)

    try:
        raw = load_workbook(args.path)
    except AnalysisError as exc:  # fatal: fail fast with a clear message
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = analyze(raw)
    print(to_json(result, indent=None if args.compact else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
