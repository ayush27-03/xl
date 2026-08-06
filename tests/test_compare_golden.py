"""Golden snapshot of the compare subcommand's JSON on the synthetic pair (M6)."""

from __future__ import annotations

import json
import os

from excel_analysis.adapters.serialization import analysis_to_json
from excel_analysis.adapters.workbook_loader import load_workbook
from excel_analysis.app.pipeline import compare_workbooks

GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "compare_pair.json")
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def test_compare_golden(compare_pair):
    left = load_workbook(compare_pair["compare_left"])
    right = load_workbook(compare_pair["compare_right"])
    produced = json.dumps(json.loads(analysis_to_json(compare_workbooks(left, right))), indent=2)
    if UPDATE:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
            f.write(produced + "\n")
    with open(GOLDEN, encoding="utf-8", newline="") as f:
        assert produced + "\n" == f.read().replace("\r\n", "\n")
