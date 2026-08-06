"""Shared pytest fixtures: build the messy-workbook corpus once per session."""

from __future__ import annotations

import pytest

from _corpus import build_all, build_compare_pair


@pytest.fixture(scope="session")
def corpus(tmp_path_factory) -> dict[str, str]:
    """Build all fixtures into a temp dir; return {name: path}."""
    dest = tmp_path_factory.mktemp("corpus")
    return build_all(str(dest))


@pytest.fixture(scope="session")
def compare_pair(tmp_path_factory) -> dict[str, str]:
    """Build the synthetic compare pair; return {compare_left, compare_right}."""
    dest = tmp_path_factory.mktemp("compare")
    return build_compare_pair(str(dest))
