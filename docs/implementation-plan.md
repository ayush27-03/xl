# Implementation Plan — Excel Analysis Tool

**Status:** M0 (extraction & profiling vertical slice) is **shipped**. This plan
covers M1–M10 — the road from the current slice to the full comparison tool.
**Design source of truth:** [architecture.md](architecture.md). Non-negotiable
rules: [../CLAUDE.md](../CLAUDE.md).

Anchoring fact: M0 shipped **without automated tests**, with hardcoded
thresholds, and only the single-workbook *profile* path. This plan is "harden
what exists, then extend toward comparison," not greenfield.

One hard sequencing constraint: the **Comparator cannot precede the Aligner** —
a diff is meaningless without a correspondence. That chain is isolated;
everything around it is parallelized.

---

## 1. Implementation milestones

Each milestone is a shippable, independently verifiable increment. "Needs" =
what must exist before it can start.

| ID | Milestone | Goal (one line) | What makes it independently testable | Needs |
|----|-----------|-----------------|--------------------------------------|-------|
| **M0** | Extraction & profiling slice | *(shipped)* load → detect → normalize → profile → JSON | Already verified | — |
| **M1** | Test harness & regression net | Lock M0's behavior in golden files; enforce layering automatically | Runs against M0 alone | M0 |
| **M2** | Configuration & detection overrides | Extract thresholds to `Config`; let users pin sheet/range/header | Override a header on a fixture, assert the region | M1 |
| **M3** | Multi-source ingestion & table selection | Load 2 workbooks; select N table-regions across sheets/files | Select & profile N tables from 1–2 files | M1 |
| **M4** | Alignment engine | `(Dataset A, Dataset B) → Alignment` with confidence | Unit-test on two hand-built Datasets | M1 (+Dataset) |
| **M5** | Comparator (diff & variance) | `(A, B, Alignment) → DiffResult`: schema/row/cell | Feed hand-built Dataset+Alignment, assert diff | M3, M4 |
| **M6** | Comparison pipeline & CLI | Wire `compare` end-to-end; `AnalysisResult` | Run `compare` on two fixtures, snapshot | M5 |
| **M7** | Insight engine | Ordered deterministic rules → ranked `Insight`s | Unit-test each rule vs. a crafted diff/profile | M5 |
| **M8** | Renderer suite (Markdown/HTML) | Present profile & compare results in human formats | Render a fixed `AnalysisResult`, snapshot | M6 |
| **M9** | AI provider port (V2, optional) | `AIProvider` null-object port + one advisory adapter | Prove pipeline identical with AI on vs. off | M2, M4, M7 |
| **M10** | Additional loaders (optional) | CSV / `.xls` behind `WorkbookLoader` | Load a CSV fixture into a `RawWorkbook` | M1 |

**Recommended near-term order:** M1 first (non-negotiable — see risks), then
parallelize **M2 / M3 / M4**, converge on **M5 → M6**, then **M7**. M8/M9/M10
are deferred by design (YAGNI until the comparison core is real).

---

## 2. Dependency graph

```
                M0 (shipped)
                   │
                   ▼
                 ┌─M1─┐  Test harness & regression net  ◀── gate for everything
                 │    │
     ┌───────────┼────┴───────────┐
     ▼           ▼                ▼
    M2          M3               M4                 ← three parallel streams
 (config/    (2 files +       (alignment
  overrides)  selection)       engine)
     │           │                │
     │           └──────┬─────────┘
     │                  ▼
     │                 M5  (comparator: diff & variance)
     │                  │
     │            ┌─────┴─────┐
     │            ▼           ▼
     │           M6          M7
     │      (compare       (insight
     │       pipeline/CLI)   engine)
     │            │           │
     │            └─────┬─────┘
     │                  ▼
     │                 M8  (Markdown / HTML renderers)
     │
     └──────────┐   M10 (extra loaders) ── depends only on M1, slot in anytime
                ▼
   M2 + M4 + M7 ──▶ M9  (AI port + advisory adapter, V2, optional)
```

- **Critical path to comparison:** `M1 → {M3 ∥ M4} → M5 → M6`.
- **Longest pole:** M4 (alignment) — start it the moment M1 lands.
- **Fully optional / cuttable for V1:** M9, M10.

---

## 3. Project backlog

Epics = milestones; stories below.

**M1 — Test harness & regression net**
- Stand up `pytest`; commit a `tests/fixtures/` corpus of *ugly* `.xlsx` files
  (title rows, merged headers, stacked tables, mixed types, hidden sheets,
  empty/blank-only, single-column, no-header). Replace the throwaway scratchpad
  generator with committed fixtures.
- Golden-file (snapshot) tests over the CLI JSON for each fixture.
- Determinism gate: run each fixture twice, assert byte-identical.
- **Architecture-fitness test:** `domain/*` must not import
  openpyxl/pandas/argparse/json; only `workbook_loader` may import openpyxl.
- Backfill unit tests for M0: `score_header_row` math, block splitting, name
  canonicalization/dedupe, type inference incl. `MIXED`, profiler stats +
  deterministic `most_common` tie-break.
- Fatal-path tests: missing file, non-OOXML, empty workbook.

**M2 — Configuration & detection overrides**
- Immutable `Config` (scoring weights, `LOW_CONFIDENCE`, candidate window,
  unmerge policy) with documented defaults; threaded through the stages.
- CLI flags / config-file loading; precedence (flag > file > default) recorded
  as diagnostics.
- User override: pin `sheet!range` and/or explicit header row; detector honors
  it, emits a `user-override` diagnostic, still reports a confidence.
- Boundary tests: weight extremes, override contradicting the heuristic,
  invalid override (fatal vs. recoverable).

**M3 — Multi-source ingestion & table selection**
- Load a **second** workbook; list of `RawWorkbook`.
- `TableSelection` primitive (sheet + region, auto or user-pinned) — the "one
  pipeline over N selections" the architecture requires; do **not** fork per use
  case.
- CLI: accept two paths and/or `--select` targets; profile-N mode.
- Decide/implement unstructured-region handling (report as `non-tabular`, don't
  profile).

**M4 — Alignment engine**
- `ColumnMatcher`: exact → normalized → fuzzy → content-signature → positional,
  each with confidence + basis.
- `RowMatcher`: declared/detected key → composite key → positional fallback;
  **emit the basis loudly**.
- "Not comparable" as a first-class `Alignment` outcome, not an exception.
- Property tests: self-alignment is identity (confidence 1.0); column reorder
  still matches by name.

**M5 — Comparator (diff & variance)**
- Schema diff: added/removed/renamed/retyped/reordered columns.
- Row diff: added/removed/unchanged/changed under the alignment.
- Cell variance: numeric Δ and %Δ; categorical before→after; explicit handling
  of `MIXED`/type-changed cells (compare within type, flag cross-type).
- Property test: `diff(A, A) == empty` for every fixture.

**M6 — Comparison pipeline & CLI**
- Define & **freeze** `AnalysisResult` (profiles + diff + insights slot +
  diagnostics) — the renderer-facing contract.
- `compare` orchestration for two-sheet and cross-workbook over
  `TableSelection`s.
- CLI subcommands (`profile` | `compare`); JSON renderer extended for diffs.
- Golden-file snapshots for both comparison modes.

**M7 — Insight engine**
- `InsightRule` interface + an *ordered, capped* set (~12): row-count drift,
  column added/removed, type change, null-rate spike, large numeric variance,
  distribution shift. Each `Insight` scored and traceable to a fact.
- Deterministic ranking with a stable tie-break.
- Per-rule unit tests on crafted diffs.

**M8 — Renderer suite (Markdown/HTML)**
- `Renderer` interface; Markdown + self-contained HTML for profile *and*
  compare results.
- Snapshot tests; confirm low-confidence items and "matched by position" surface
  **prominently**.

**M9 — AI provider port (optional, V2)**
- `AIProvider` port + null-object default; advisory hooks at the three
  sanctioned seams (header assist, semantic column match, insight narration),
  each with a deterministic fallback.
- Opt-in flag + explicit egress consent; AI kept out of the default test path.
- Test: whole suite passes byte-identically with AI disabled.

**M10 — Additional loaders (optional)**
- CSV loader → `RawWorkbook`; `.xls` via a legacy reader.
- Fixtures + fitness test that the new loader is the only new importer.

---

## 4. Definition of Done

**Universal DoD (every milestone must satisfy all):**
- ☐ New domain code is pure — passes the **architecture-fitness import test**.
- ☐ No `RawCell` or DataFrame appears in any cross-stage type (contract test).
- ☐ Every new heuristic/ambiguous decision emits a **confidence** and a
  **`Diagnostic`**; recoverable failures degrade, only fatal conditions raise.
- ☐ **Determinism gate** green: run-twice byte-identical on all fixtures.
- ☐ Unit tests for new pure logic + golden-file coverage for any new end-to-end
  path; suite + lint green.
- ☐ `CLAUDE.md` / `architecture.md` updated **only if** a rule/contract changed
  (via the "spec first" process).

**Milestone-specific DoD:**

| ID | Done when… |
|----|-----------|
| M1 | Corpus of ≥10 messy fixtures committed; M0 fully snapshotted; fitness + determinism gates run in one command and fail loudly. |
| M2 | A user can pin a header/range and the detector provably obeys it; every threshold is config-driven with defaults preserved. |
| M3 | Two workbooks load; N explicit selections profile correctly; unstructured regions reported, never silently profiled. |
| M4 | `Alignment` produced for name/positional/key cases with correct basis+confidence; self-alignment is identity; "not comparable" returns a result. |
| M5 | `diff(A,A)` empty for all fixtures; schema/row/cell diffs correct on crafted pairs; cross-type cell changes flagged. |
| M6 | `AnalysisResult` shape frozen; `compare` works for two-sheet **and** cross-workbook; both snapshotted. |
| M7 | Rule set capped and ordered; ranking deterministic; each insight traces to a fact; per-rule tests pass. |
| M8 | Markdown + HTML render both result types; low-confidence/positional-match warnings visibly surfaced; artifacts snapshot-stable. |
| M9 | Suite passes identically with AI off; AI never reached in the default path; egress opt-in and consented. |
| M10 | New format loads into `RawWorkbook`; fitness test confirms import confinement. |

---

## 5. Testing strategy

Layered, mirroring the architecture — clean seams mean most logic is
unit-testable in isolation.

- **Unit tests (bulk of coverage):** each pure domain stage against hand-built
  inputs. No files needed — construct domain objects directly.
- **Contract / boundary tests:** the `Dataset` boundary holds (no raw cells
  downstream, no DataFrames anywhere); stage outputs conform to model shapes.
- **Architecture-fitness tests:** static import checks so CLAUDE.md rule 2 can't
  silently rot.
- **Golden-file / snapshot tests:** the messy-fixture corpus → CLI JSON, checked
  into git. Rebaselining is a deliberate, reviewed act.
- **Property-based tests (invariants):** `confidence ∈ [0,1]`; `diff(A,A)` empty;
  self-alignment is identity; column reorder doesn't change name matches;
  profiling is order-independent.
- **Determinism gate:** every fixture run twice → byte-identical.
- **Negative/fatal-path tests:** corrupt/missing/empty → correct exit codes and
  `AnalysisError`, never a stack trace.
- **The corpus is a living asset:** every real-world misdetection becomes a new
  committed fixture + snapshot **before** the fix.

**Out of scope:** performance/load tests (deprioritized); AI-in-the-loop tests
in the default suite (M9 proves *removability*, not model quality).

---

## 6. Estimated complexity

Complexity/effort, not calendar. Scale S < M < L < XL; "confidence" = how sure
the estimate holds.

| ID | Complexity | Primary cost driver | Est. confidence |
|----|:---------:|---------------------|:--------------:|
| M1 | **M** | Curating a *representative* messy corpus | High |
| M2 | **S–M** | Override UX + threading config without disturbing M0 snapshots | High |
| M3 | **M** | Selection semantics & CLI surface | Med |
| M4 | **L** | Fuzzy matching, key inference, confidence calibration — 2nd ambiguity sink | **Low** |
| M5 | **M** | Row-diff bookkeeping + cross-type cell variance | Med |
| M6 | **M** | Freezing `AnalysisResult`; subcommand wiring | High |
| M7 | **M** | Rule design + ranking; resisting scope creep | Med |
| M8 | **S–M** | Presentation; self-contained HTML | High |
| M9 | **L** | Safe advisory integration, fallback, privacy, nondeterminism containment | Low |
| M10 | **S**/fmt | CSV easy; `.xls` needs a legacy reader | High |

Cost concentrates in **M4** and **M9** (the low-confidence estimates). The
deterministic spine (M5/M6) is predictable; the ambiguity sinks (M2, M4) are
where effort overruns. Budget accordingly.

---

## 7. Risks

| # | Risk | Likelihood | Impact | Milestone(s) | Mitigation |
|---|------|:---------:|:------:|--------------|------------|
| R1 | Extending M0 with no test net — regressions go unnoticed | High | High | M1 | Make M1 the hard gate before feature work. |
| R2 | Alignment ambiguity / no reliable row key → meaningless diffs | High | High | M4, M5 | Positional fallback with **loud** basis reporting + key override; "not comparable" first-class. |
| R3 | Detection long tail (side-by-side tables, exotic layouts) | High | Med | M2, M3 | Confidence + diagnostics + overrides; grow corpus from real misses. |
| R4 | Cross-platform nondeterminism (float repr, dict/set order) | Med | High | all | Determinism gate; canonical number formatting; never emit set-ordered output. |
| R5 | Corpus unrepresentative of real files | Med | High | M1 | Source real, anonymized workbooks early; corpus is a living deliverable. |
| R6 | Insight scope creep — accidentally a BI tool | Med | Med | M7 | Cap the rule set; ranked, traceable-to-fact. |
| R7 | pandas leaks across the Dataset boundary | Med | Med | M5, M7 | Fitness test forbids DataFrames in cross-stage types. |
| R8 | AI privacy/egress + nondeterminism | Med | High | M9 | Null default; opt-in + consent; deterministic fallback; excluded from default path. |
| R9 | Building ahead of need (M8/M9/M10 too early) | Med | Med | M8–M10 | Enforce sequencing; YAGNI. |
| R10 | `AnalysisResult` churn breaking renderers | Med | Med | M6, M8 | Freeze the contract at M6 before building M8 on it. |

---

## Product decisions that gate milestones

Answer these **before** the milestone starts, not during:

- Detection posture — auto vs. override-first → **gates M2**.
- Is there usually a natural row key, or must positional be first-class? →
  **gates M4/M5**.
- Are unstructured regions formally cut from V1? → **gates M3** selection
  semantics.
- Which human renderer is the V1 priority (Markdown vs. HTML)? → **gates M8**.

---

## Web layer (delivered post-M8; V1, internal single-machine tool)

Beyond the M0–M10 plan, an optional web front-end shipped: a **FastAPI adapter**
(`excel_analysis/api.py`) and a **React/Vite/Tailwind SPA** (`frontend/`) — the
"GUI over the same library API" the roadmap placed at V2+, brought forward for an
**internal, single-machine team** (not a hosted product; no auth/DB/cloud).

| Aspect | How it holds the line |
|---|---|
| **Contract reuse** | API returns the existing `AnalysisResult` (via `compare_workbooks` → `analysis_to_json`) under `{ metadata, analysis }`; the SPA types mirror it and render verbatim. Recomputes nothing. |
| **Determinism** | Domain/pipeline untouched and AI-free; JSON/Markdown goldens unchanged. Byte-identical-with-AI-off preserved. |
| **Local-only** | API binds `127.0.0.1` (`run()`); a middleware 403s non-loopback peers even under `--host 0.0.0.0`; uploads are size-capped → 413 before openpyxl. Runtime match to the data-hygiene stance. |
| **Opt-in AI** | SPA toggle (off by default) requests a local-Ollama narrative; the API runs the **same restate-only guard server-side** and returns validated bullets as a separate `ai_summary` field — never inside `AnalysisResult`. Rejection/unavailable → deterministic-insights fallback. |
| **Tests** | `tests/test_api.py` covers the happy path, non-xlsx rejection, oversized-upload 413, loopback enforcement, and the opt-in AI wiring (off by default, validated-bullets, and rejection fallback). Frontend is `npm`-built, not in the pytest suite. |

Scope is unchanged from §Scope: still not a distributed system, SaaS, multi-user,
or authenticated service.
