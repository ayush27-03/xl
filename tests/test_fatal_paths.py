"""Fatal-path tests: unrecoverable inputs fail fast with a clear error and a
non-zero exit code, never a stack trace (CLAUDE.md rule 5)."""

from __future__ import annotations

import pytest

from excel_analysis.adapters.workbook_loader import load_workbook
from excel_analysis.cli import main
from excel_analysis.domain.errors import WorkbookLoadError


def test_missing_file_raises_workbook_load_error():
    with pytest.raises(WorkbookLoadError):
        load_workbook("definitely_does_not_exist_12345.xlsx")


def test_non_xlsx_content_raises_workbook_load_error(tmp_path):
    bogus = tmp_path / "bogus.xlsx"
    bogus.write_text("this is plainly not a zip/xlsx container", encoding="utf-8")
    with pytest.raises(WorkbookLoadError):
        load_workbook(str(bogus))


def test_cli_missing_file_exits_2_with_message(capsys):
    rc = main(["definitely_does_not_exist_12345.xlsx"])
    assert rc == 2
    assert "error:" in capsys.readouterr().err
