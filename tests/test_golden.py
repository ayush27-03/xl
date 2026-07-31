"""Golden-file and determinism tests over the messy-workbook corpus.

Golden snapshots (tests/golden/*.json) are the regression oracle. Regenerate
them deliberately with UPDATE_GOLDEN=1 and review the diff before committing.
The volatile absolute source_path is normalized to the fixture name so snapshots
are machine-independent.
"""

from __future__ import annotations

import json
import os

import pytest

from _corpus import FIXTURES
from excel_analysis.adapters.serialization import to_json
from excel_analysis.adapters.workbook_loader import load_workbook
from excel_analysis.app.pipeline import analyze

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def _normalized_json(path: str, name: str) -> str:
    data = json.loads(to_json(analyze(load_workbook(path))))
    data["source_path"] = f"{name}.xlsx"  # strip machine-specific absolute path
    return json.dumps(data, indent=2)


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_golden(corpus, name):
    produced = _normalized_json(corpus[name], name)
    golden_path = os.path.join(GOLDEN_DIR, f"{name}.json")
    if UPDATE:
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        with open(golden_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(produced + "\n")
    with open(golden_path, encoding="utf-8", newline="") as f:
        golden = f.read().replace("\r\n", "\n")  # tolerate git CRLF conversion
    assert produced + "\n" == golden


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_output_is_deterministic(corpus, name):
    first = to_json(analyze(load_workbook(corpus[name])))
    second = to_json(analyze(load_workbook(corpus[name])))
    assert first == second
