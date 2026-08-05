"""Config-file loader (adapter): read a JSON config into a plain dict.

Parsing and file I/O live here; validation of the values is the domain's job
(Config.with_overrides). Keeps json out of the domain (CLAUDE.md rule 2).
"""

from __future__ import annotations

import json
import os

from ..domain.errors import ConfigError


def load_config_file(path: str) -> dict:
    if not os.path.isfile(path):
        raise ConfigError(f"Config file not found: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Could not parse config file '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("Config file must contain a JSON object at the top level.")
    return data
