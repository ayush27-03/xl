# AGENTS.md — Excel Analysis Tool

The design spec is [docs/architecture.md](docs/architecture.md). **That file is the
source of truth.** This file lists only the rules that must never be broken.

If a change requires breaking a rule below, it is not a code change — it is an
*architecture* change. Stop, and update the spec first in a separate discussion.

**In one line:** a local, offline tool that extracts tables from arbitrary, messy
`.xlsx` workbooks and produces deterministic profiling, comparison, and variance
analysis. Extraction is the hard part; comparison is the easy tail.

---

## 1. The `Dataset` contract is the hard boundary between detection and analysis

- The system has two halves. **Structure discovery** (load → detect tables →
  normalize) turns spreadsheet chaos into a `Dataset`. **Analysis** (profile,
  align, compare, insights) consumes a `Dataset` and nothing earlier.
- `Dataset` is the single most important interface in the codebase. Design it and
  protect it first.
- Detection code MUST NOT know what a diff, a profile, or an alignment is.
  Analysis code MUST NOT know what a cell, a merge, or a header row is.
- Nothing above `Dataset` may leak downward; nothing below it may leak upward.
  If you are reaching across this line, you are doing something wrong.

## 2. Only domain models cross stage boundaries — never raw cells or DataFrames

- Stages communicate **exclusively** through the contract spine:
  `RawWorkbook` → `RawSheetGrid` → `DetectedTable` → `Dataset` →
  (`DatasetProfile` | `Alignment` → `DiffResult`) → `Insight` → `AnalysisResult`,
  with `Diagnostic`s accumulating alongside.
- **`openpyxl` types stay inside the Workbook Loader.** No other module imports
  openpyxl.
- **pandas / DataFrames stay behind `Dataset`.** A DataFrame must never appear in a
  `DiffResult`, an `Insight`, or any other cross-stage type. Use pandas as an
  implementation detail *inside* a stage, never as a boundary type.
- The domain modules — Detector, Normalizer, Profiler, Aligner, Comparator,
  Insight Engine — **MUST NOT import one another.** They are wired only through the
  Orchestrator, via contracts.
- Dependencies point inward: Interface → Application → Domain ← Adapters. The pure
  domain imports no I/O library, no CLI, and no AI SDK.

## 3. Deterministic core; AI is optional and lives behind a null-object port

- **Same inputs + same config → byte-identical output.** No reliance on dict/set
  iteration order, wall-clock time, or randomness. **No AI in the default path.**
- AI is reached only through the `AIProvider` port, whose **default implementation
  is a no-op null object.** The full pipeline must produce correct results with AI
  removed entirely.
- AI may only ever **propose**; deterministic code **disposes** — it validates the
  suggestion or falls back. AI never makes a final decision.
- AI is confined to exactly three advisory jobs: header/table-boundary detection
  assist, semantic column matching, and natural-language insight narration.
  Nowhere else.
- **Offline by default.** No network egress in the default path. An AI adapter
  requires explicit, opt-in consent, because the inputs are the user's private
  spreadsheets.

## 4. Every heuristic carries a confidence; every assumption is auditable

- Any ambiguous decision — which row is the header, where a table starts and ends,
  how columns or rows correspond — **MUST emit a confidence score**, not a bare
  answer.
- Every assumption the system makes is recorded as a `Diagnostic`
  (severity + confidence + provenance). **Never guess silently. Never drop data
  silently** — a discarded region, a skipped sheet, or a coerced value each becomes
  a `Diagnostic`.
- Low-confidence decisions must surface prominently in the output, not hide in logs.

## 5. Messy input is the normal case, not an error

- Split every failure into two tracks:
  - **Fatal** (fail fast, clear message): file missing, not valid OOXML,
    unreadable, or genuinely empty.
  - **Recoverable / ambiguous** (degrade, record a `Diagnostic`, continue with a
    documented assumption): no confident header, a mixed-type column, no common row
    key, sheets that are not comparable.
- Recoverable outcomes are **modeled as data (result/outcome objects), not thrown
  as exceptions.** Exceptions are for fatal and programmer errors only.
- **"Not comparable" is a successful result**, reported honestly — never a crash.
- **Never assume:** row 1 is the header · one table per sheet · a rectangular,
  gap-free grid · matching column names mean the same concept · a stable row key
  exists · hidden sheets are safe to analyze silently.
- Bias every ambiguous call toward "make a reasonable choice and flag it loudly,"
  never "guess quietly."

---

## Before you merge — self-check

- [ ] No new module imports `openpyxl` except the Workbook Loader; no DataFrame or
      raw cell appears in a cross-stage type.
- [ ] Detection code contains no analysis concepts, and vice versa; the `Dataset`
      boundary is intact.
- [ ] The change runs correctly with the null `AIProvider`; any AI use is advisory
      with a deterministic fallback.
- [ ] Every new heuristic emits a confidence and records a `Diagnostic`.
- [ ] New failure modes are classified fatal vs. recoverable; recoverable ones
      degrade instead of throwing.
- [ ] Output is deterministic (no ordering / time / randomness dependence) and a
      golden-file test covers it.
