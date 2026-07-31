"""Excel Analysis Tool — deterministic .xlsx analysis.

See docs/architecture.md (the source of truth) and CLAUDE.md (the rules).
This package implements the first vertical slice: WorkbookLoader -> TableDetector
-> Normalizer -> Profiler, wired into a CLI. No Aligner or Comparator yet.
"""

__version__ = "0.1.0"
