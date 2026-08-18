"""Architecture-fitness tests — enforce CLAUDE.md rule 2 automatically.

The clean layering is only real if it can't silently rot. These tests parse each
module's imports and fail if the domain layer reaches for I/O, or if openpyxl
escapes the WorkbookLoader.
"""

from __future__ import annotations

import ast
import os

import pytest

PKG_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "excel_analysis")
DOMAIN = os.path.join(PKG_ROOT, "domain")
FORBIDDEN_IN_DOMAIN = {"openpyxl", "pandas", "argparse", "json"}


def _top_level_imports(path: str) -> set[str]:
    """Top-level package names imported *absolutely* (relative imports ignored)."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def _py_files(root: str) -> list[str]:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for fn in files:
            if fn.endswith(".py"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


@pytest.mark.parametrize("path", _py_files(DOMAIN), ids=os.path.basename)
def test_domain_layer_is_pure(path):
    leaked = _top_level_imports(path) & FORBIDDEN_IN_DOMAIN
    assert not leaked, f"{os.path.basename(path)} imports forbidden module(s): {sorted(leaked)}"


def test_openpyxl_is_confined_to_loader_and_xlsx_writer():
    # openpyxl is the INPUT parser and stays in the loader. The xlsx OUTPUT
    # renderer (report_xlsx) legitimately uses openpyxl as a *writer* — a terminal
    # adapter that never surfaces openpyxl types to the domain or across a stage
    # boundary (see architecture.md M11 addendum). Any OTHER module importing
    # openpyxl is the rot this test exists to catch.
    allowed = {"adapters/workbook_loader.py", "adapters/report_xlsx.py"}
    offenders = []
    for path in _py_files(PKG_ROOT):
        if "openpyxl" in _top_level_imports(path):
            rel = os.path.relpath(path, PKG_ROOT).replace(os.sep, "/")
            if rel not in allowed:
                offenders.append(rel)
    assert offenders == [], f"openpyxl imported outside the loader/xlsx-writer: {offenders}"
