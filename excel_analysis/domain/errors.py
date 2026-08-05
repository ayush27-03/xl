"""Fatal errors (CLAUDE.md rule 5).

Raised only when the pipeline genuinely cannot proceed (missing/corrupt file).
Recoverable ambiguity is never raised — it is modelled as a Diagnostic and the
pipeline degrades and continues.
"""

from __future__ import annotations


class AnalysisError(Exception):
    """Base class for fatal, unrecoverable errors surfaced to the user."""


class WorkbookLoadError(AnalysisError):
    """The workbook could not be opened or is not a valid .xlsx file."""


class ConfigError(AnalysisError):
    """A configuration file or option was invalid."""
