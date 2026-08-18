***
```
/engineering:architecture 
You are acting as a Principal Software Architect, Data Platform Engineer, and Python Systems Designer.
Your responsibility is NOT to write code immediately.
Your responsibility is to design an extensible, production-quality architecture for an Excel Analysis Tool.
Treat this as a real software engineering design exercise similar to what would happen during an architecture review in industry.
Primary Objective
Design a modular software system that can analyze one or more Excel workbooks containing structured, semi-structured, or unstructured data and generate meaningful comparison reports, variance analysis, statistics, and insights.
The tool should prioritize deterministic analysis wherever possible.
Artificial Intelligence should be treated as an OPTIONAL enhancement layer rather than a dependency.
Current MVP
Version 1 only needs to support Microsoft Excel (.xlsx).
The user should be able to

* upload one workbook
* upload two workbooks
* compare two sheets inside one workbook
* compare sheets across two workbooks

The workbook layout cannot be assumed.
Some files may contain

* title rows
* merged cells
* blank rows
* notes
* multiple tables
* inconsistent header positions
* inconsistent formatting
* missing values
* duplicate values
* mixed datatypes
* hidden sheets

The architecture must be designed to gracefully handle these situations.
Expected Output
I want architecture—not implementation.
Before writing code, help me answer questions such as

* What modules should exist?
* What responsibilities belong to each module?
* Which modules should remain independent?
* Where should deterministic logic end?
* Where could optional AI integration exist later?
* Which design patterns are appropriate?
* How should data flow through the system?
* What assumptions are safe?
* What assumptions should never be made?
* Which architectural decisions improve long-term maintainability?

Engineering Principles
Optimize for

* correctness
* determinism
* maintainability
* modularity
* extensibility
* testability
* readability
* separation of concerns

Avoid optimizing for premature performance.
Scope
Do NOT design for

* distributed systems
* cloud deployment
* Kubernetes
* authentication
* multi-user collaboration
* databases
* SaaS
* billing
* enterprise infrastructure

Assume this is initially a local desktop application or CLI.
AI Policy
Do NOT assume an LLM is always available.
The architecture should work without AI.
If AI is proposed, it should exist as a replaceable module with clearly defined interfaces.
The deterministic pipeline must remain functional even if the AI module is removed.
Deliverables
Walk through the architecture in this order.

1. Problem decomposition
2. Functional requirements
3. Non-functional requirements
4. System boundaries
5. Core architectural principles
6. High-level architecture
7. Major software modules
8. Responsibilities of every module
9. Data flow
10. Internal processing pipeline
11. Error-handling strategy
12. Extension points
13. Risks and trade-offs
14. Future roadmap

Important Constraints
Do NOT generate Python code.
Do NOT generate class implementations.
Do NOT generate project files.
Do NOT generate directory structures yet.
Stay entirely in architecture and engineering design.
Challenge my assumptions when appropriate.
Recommend simpler solutions whenever they provide the same value.
Think like a staff engineer reviewing a greenfield software project rather than an AI assistant trying to finish the project quickly.
```


Before I walk the fourteen sections, one reframe — because it changes where you should spend your engineering budget.

You've described this as a **comparison** tool. It isn't, primarily. Comparison, variance, and statistics are the _easy, deterministic tail_ of this system. Once you hold two clean, typed, aligned tables in memory, diffing them is a few hundred lines of obvious code. The hard 70% — and essentially all of the risk — lives _before_ comparison: **turning an arbitrary, messy grid of cells into a table you can trust.** Every ugly item on your list (title rows, merged cells, multiple tables per sheet, floating headers) is an _extraction_ problem, not a comparison problem.

`★ Insight ─────────────────────────────────────` The single most important architectural seam in this system is the line between **structure discovery** ("where is the table, and what are its columns?") and **analysis** ("how do these two tables differ?"). Keep them in separate modules with a hard contract between them. Almost every design mistake you can make here comes from letting comparison logic peek at raw cells, or letting detection logic know what a "diff" is. `─────────────────────────────────────────────────`

With that lens, here's the review.

---

## 1. Problem decomposition

The system is a pipeline of six genuinely distinct problems, in increasing determinism:

|#|Sub-problem|Nature|Difficulty|
|---|---|---|---|
|A|**Ingest** the workbook as a raw cell grid (values, types, merges, hidden flags)|I/O, mechanical|Low|
|B|**Detect structure** — find table region(s), the header row, discard noise|Heuristic, ambiguous|**Highest**|
|C|**Normalize** — clean column names, infer/coerce types, canonicalize a table|Rule-based|Medium|
|D|**Align** — decide which columns and rows of A correspond to B|Heuristic, ambiguous|**High**|
|E|**Compare / profile** — schema diff, row diff, cell variance, statistics|Deterministic math|Low|
|F|**Explain & render** — rank findings into insights, emit an artifact|Rule-based + presentation|Low–Medium|

The two ambiguity sinks are **B (detection)** and **D (alignment)**. That's where confidence scoring, diagnostics, user overrides, and _later_ optional AI all belong. Everything else should be boringly deterministic and heavily unit-tested.

**A reframe I'd push back on:** your four use cases — one workbook, two workbooks, two sheets in one, two sheets across two — are not four features. They're permutations of one primitive: _select N table-regions, then either profile each or pairwise-compare them._ Build **one parameterized pipeline over a set of "table selections,"** not four pipelines. If you find yourself writing a `compare_across_workbooks` module distinct from `compare_within_workbook`, you've already taken on avoidable maintenance debt.

---

## 2. Functional requirements

**Inputs**

- Load one or two `.xlsx` workbooks from the local filesystem.
- Enumerate all sheets, including hidden ones (surfaced, not silently analyzed).
- Select target regions: an entire sheet, or (later) a user-specified range/header row.

**Core capabilities**

- **Profile** a single dataset: row/column counts, per-column type, null count, unique count, basic descriptive stats, distribution summary.
- **Compare** two datasets and produce:
    - _Schema diff_ — columns added / removed / renamed / retyped / reordered.
    - _Row diff_ — rows added / removed / unchanged / changed (requires an alignment key or positional fallback).
    - _Cell variance_ — for changed rows: numeric delta and % change; categorical before→after.
- **Detect** and report structural facts: multiple tables on a sheet, merged headers, blank separators, title/notes regions, mixed-type columns, duplicate rows.
- **Rank** findings into human-readable insights.
- **Emit** a structured result plus a diagnostics/audit trail.

**Outputs**

- At minimum a machine-readable result (JSON) and one human format (CLI table or Markdown/HTML). Renderers are pluggable.

**Explicit non-goals for V1** — say these out loud so they don't creep in:

- No formula evaluation/recalculation (read computed values, don't re-derive).
- No charts, pivot tables, or macro interpretation.
- No writing back into the source workbook.
- No true _unstructured_ text analysis (see §4 — I recommend cutting this from your list).

---

## 3. Non-functional requirements

|Requirement|What it means here|Priority|
|---|---|---|
|**Determinism**|Same files + config → byte-identical output. No dependence on dict/set ordering; **no AI in the default path.**|Critical|
|**Correctness**|A wrong-but-confident answer is worse than an honest "ambiguous."|Critical|
|**Testability**|Pure, side-effect-free core; boundaries injected; golden-file tests over messy fixtures.|Critical|
|**Maintainability / readability**|Small modules, one responsibility, stable contracts between them.|High|
|**Extensibility**|New formats, renderers, matching strategies, optional AI — all via existing interfaces, no core surgery.|High|
|**Observability / auditability**|Every assumption the system makes is recorded as a diagnostic.|High|
|**Privacy / offline-first**|Runs fully offline. Sensitive spreadsheets never leave the machine unless an AI adapter is _explicitly_ opted in.|High|
|**Performance**|Deliberately de-prioritized. _One_ caveat below.|Low|

The one performance thing worth designing around now (not optimizing, just not architecting yourself into a corner): **memory.** You'll be tempted to hold the raw `openpyxl` grid, a pandas frame, _and_ copies for both sides of a comparison simultaneously. Keep the raw grid short-lived — discard it once a normalized `Dataset` exists. Don't build streaming or parallelism yet; just don't triple-hold large workbooks.

---

## 4. System boundaries

**Inside the system:** a pure function of `(files, config) → (AnalysisResult, Diagnostics)`. No persistence, no hidden state, no network in the default path, no background services.

**At the edges (behind interfaces):**

- **Input adapter** — the file loader (openpyxl today; CSV/`.xls`/ODS later).
- **Output adapter** — renderers.
- **AI adapter** — a port that is **null by default** and treated as untrusted, optional, and fallible.
- **UI** — CLI now, GUI later, both driving the _same library API_. Analysis logic must never know it's being called from a CLI.

### Assumptions register — the part most designs get wrong

**Safe to assume:**

- The file is a valid ZIP/OOXML container (verify, then trust the parser).
- A worksheet is a finite 2D grid of cells with a value and a type.
- Within a _single detected table_, a column is intended to be one concept.
- Numbers, dates, booleans, and strings are distinguishable at the cell level (openpyxl gives you cell types).

**Never assume:**

- ...that row 1 is the header. (It's the single most common wrong assumption; `pandas.read_excel` bakes it in — see §10.)
- ...that a sheet contains exactly one table.
- ...that the grid is rectangular or gap-free.
- ...that column _names_ mean the columns are the same concept, or that identical concepts share a name.
- ...that two sheets are comparable at all. "**Not comparable**" must be a first-class _result_, not an exception.
- ...that there is a stable row key. Sometimes there's only position — and position is a weak, must-be-flagged basis for comparison.
- ...that a merged cell means what it looks like. Decide an unmerge policy explicitly (§10).
- ...that hidden sheets are safe to analyze as if visible — the author hid them for a reason; surface, don't silently include.

---

## 5. Core architectural principles

1. **Deterministic core, advisory edges.** The core computes measurable facts. AI, if ever present, only _proposes_; deterministic code _disposes_ (validates or falls back).
2. **Separate structure discovery from analysis.** The crux seam from the intro.
3. **Contracts over coupling.** Stages communicate through stable domain models (§9), never by reaching into each other's internals. A stage depends on the _shape of the data_, not on the module that produced it.
4. **Dependency rule points inward.** Interface → application → domain → (adapters plug into the domain's ports). The pure domain has zero knowledge of openpyxl, the CLI, or any AI SDK.
5. **Fail loud on fatal, degrade-and-record on ambiguous.** (§11)
6. **Every assumption is auditable.** Diagnostics are a first-class output, not log spew.
7. **Purity where possible.** Prefer pure functions and immutable value objects; it's what makes determinism and testing cheap.
8. **One pipeline, parameterized** — not one per use case.
9. **YAGNI.** No plugin runtime, no rules DSL, no database, no async, until something proven forces it.
10. **Offline-first, privacy-preserving default.**

---

## 6. High-level architecture

A four-layer hexagonal-ish structure. The ceremony is deliberately _minimal_ — just enough seams at the real boundaries (loader, matcher, renderer, AI), not abstraction for its own sake.

```
┌──────────────────────────────────────────────────────────┐
│  INTERFACE          CLI  (later: GUI)                      │  thin
├──────────────────────────────────────────────────────────┤
│  APPLICATION        Orchestrator / one parameterized       │  wiring only,
│                     pipeline over "table selections"       │  no analysis
├──────────────────────────────────────────────────────────┤
│  DOMAIN (pure)      Detector · Normalizer · Profiler ·     │  all the
│                     Aligner · Comparator · InsightEngine   │  real logic,
│                     + Domain Models (contracts)            │  zero I/O
├──────────────────────────────────────────────────────────┤
│  ADAPTERS           WorkbookLoader · Renderers ·           │  touch the
│                     AIProvider(null default) · Config      │  outside world
└──────────────────────────────────────────────────────────┘
        dependencies point DOWNWARD / INWARD only
```

**Design patterns — where each earns its place (and where it doesn't):**

|Pattern|Applied to|Why|
|---|---|---|
|**Pipes & Filters**|The whole ingest→render flow|Natural fit; each stage is testable in isolation|
|**Strategy**|Header detection, type inference, column/row matching, rendering|The ambiguous decisions have multiple valid algorithms; swap without touching callers|
|**Ports & Adapters (Hexagonal)**|Loader, Renderer, **AIProvider**|Keeps the core pure and offline; AI becomes trivially removable|
|**Null Object**|Default AIProvider|Core never null-checks "is AI available?" — it just calls the port|
|**Factory**|Building the right loader/renderer/pipeline per request|Isolates construction from logic|
|**Value Objects (immutable)**|All domain models|Determinism, safe sharing, cheap tests|
|**Accumulator/Collector**|Diagnostics|Gather warnings across stages without threading returns everywhere|
|⚠️ **Visitor, plugin registry, rules DSL**|—|**Avoid in V1.** Premature. Plain strategy interfaces wired in code cover every need you actually have.|

---

## 7. Major software modules

Grouped by layer. Note that the **domain modules are the only place analysis logic may live.**

**Domain (pure):**

1. **Domain Models / Contracts** — the data structures every stage exchanges.
2. **Table Detector** — raw grid → one or more `DetectedTable` regions with header location + confidence.
3. **Normalizer** — `DetectedTable` → canonical `Dataset` (clean names, inferred types, standardized missing values).
4. **Profiler** — `Dataset` → `DatasetProfile` (per-column + dataset stats).
5. **Aligner** — `(Dataset A, Dataset B)` → `Alignment` (column correspondence + row-matching basis).
6. **Comparator** — `(A, B, Alignment)` → `DiffResult` (schema/row/cell variance).
7. **Insight Engine** — `(profiles, diff)` → ranked `Insight` list via ordered deterministic rules.

**Application:** 8. **Orchestrator / Pipeline** — selects regions, runs stages in order, threads diagnostics, assembles `AnalysisResult`.

**Adapters:** 9. **Workbook Loader** — file → `RawWorkbook`. Owns openpyxl; nothing else imports openpyxl. 10. **Renderers** — `AnalysisResult` → JSON / Markdown / HTML / CLI. 11. **AI Provider (port + null impl)** — advisory hooks for detection, matching, narration. 12. **Config** — thresholds, feature toggles, unmerge policy.

**Cross-cutting:** 13. **Diagnostics Collector** — accumulates severity-tagged, confidence-scored observations alongside the data.

---

## 8. Responsibilities of every module

|Module|Owns (responsibility)|Explicitly does NOT|Depends on|
|---|---|---|---|
|**Domain Models**|Define stable data shapes: `RawWorkbook`, `RawSheetGrid`, `DetectedTable`, `Dataset`, `ColumnProfile`, `DatasetProfile`, `Alignment`, `DiffResult`, `Insight`, `Diagnostic`, `AnalysisResult`|Contain behavior/logic|Nothing|
|**Workbook Loader**|Read `.xlsx` into raw grids incl. cell types, merged ranges, hidden flags|Interpret which rows are headers|openpyxl|
|**Table Detector**|Find table region(s), locate header, separate title/notes/blank noise, score confidence|Clean data or coerce types|Raw grid + Diagnostics|
|**Normalizer**|Canonical names, type inference/coercion, standardize missing/duplicate handling, record provenance|Compute statistics|`DetectedTable`|
|**Profiler**|Descriptive stats per column and per dataset|Compare two datasets|`Dataset`|
|**Aligner**|Decide column↔column and row↔row correspondence + the basis (key vs. position) and its confidence|Compute the actual deltas|Two `Dataset`s|
|**Comparator**|Schema diff, row diff, cell variance, given a fixed alignment|Decide _how_ to align; rank importance|Datasets + `Alignment`|
|**Insight Engine**|Turn facts into ranked, human-meaningful observations|Do math it can't trace to a fact|Profiles + `DiffResult`|
|**Orchestrator**|Wire stages, choose profile-vs-compare mode, thread diagnostics, build result|Any analysis logic of its own|Domain modules (via contracts)|
|**Renderers**|Present `AnalysisResult` in a target format|Change the result's content|`AnalysisResult`|
|**AI Provider**|_Optionally_ suggest a header row, a column match, or narrative prose — advisory only|Ever be required; ever make a final decision|Port interface only|
|**Diagnostics**|Collect severity + confidence + provenance for every assumption|Halt the pipeline|—|
|**Config**|Supply thresholds and toggles|Contain logic|—|

The independence rule: **Detector, Normalizer, Profiler, Aligner, Comparator, and Insight Engine must not import one another.** They communicate only through domain models via the Orchestrator. That's what lets you test each with hand-built fixtures and swap any one out.

---

## 9. Data flow

The **contract spine** — every arrow is a domain model, and that's the entire public surface between stages:

```
 file.xlsx
    │  WorkbookLoader
    ▼
 RawWorkbook ──▶ RawSheetGrid (per sheet: cells, types, merges, hidden)
    │  TableDetector
    ▼
 List<DetectedTable>  (header row + region + confidence)
    │  Normalizer
    ▼
 Dataset  (typed columns, clean names, provenance)  ◀── THE pivotal contract
    │
    ├──▶ Profiler ──▶ DatasetProfile
    │
    └──(with a second Dataset)──▶ Aligner ──▶ Alignment
                                     │  Comparator
                                     ▼
                                  DiffResult
                                     │
         (DatasetProfiles + DiffResult) ──▶ InsightEngine ──▶ List<Insight>
                                     │  Orchestrator assembles
                                     ▼
                              AnalysisResult ──▶ Renderer ──▶ artifact

  Diagnostics  ══════ accumulates alongside EVERY stage ══════▶ (attached to AnalysisResult)
```

`Dataset` is the most important interface in the system: it's the boundary where "spreadsheet chaos" ends and "clean tabular analysis" begins. If it's well-designed, everything downstream is easy. Design it first, and protect it — nothing above it should leak upward (no raw cells in a `DiffResult`), nothing below it should leak downward (the Comparator must never see openpyxl).

---

## 10. Internal processing pipeline

Stage by stage, with the decisions that matter at each:

1. **Load.** Open with a _structural_ reader (openpyxl), not `pandas.read_excel`. You need the raw grid, cell types, merged-cell ranges, and hidden-sheet flags — all of which pandas throws away or guesses at. **This is a load-bearing decision:** pandas assumes row-0 headers and a single rectangular table, i.e. exactly the assumptions §4 says you must never make. Use pandas _later_, as the in-memory representation of an already-detected table.
    
2. **Detect.** For each sheet: find contiguous populated regions → for each candidate region, locate the header row (heuristics: first row where cells are mostly text, distinct from the rows below, low null density) → separate title/notes (merged across width, isolated) and blank separators → emit `DetectedTable`s **each with a confidence score.** Multiple tables per sheet is normal output here, not an error.
    
3. **Resolve merged cells.** Apply the configured **unmerge policy** — propagate the top-left value into the merged span, or treat the merge as a structural boundary. This must be an explicit, recorded choice; it silently corrupts alignment otherwise.
    
4. **Normalize.** Canonicalize headers (trim, dedupe, handle `Unnamed`), infer column types from the _values_ (not from what Excel stored), coerce consistently, standardize missing values, flag mixed-type columns rather than forcing them. Emit `Dataset` with **provenance** (which sheet, which cell range each column came from) — provenance is what makes results explainable.
    
5. **Profile.** Pure descriptive statistics. Cheap, deterministic, useful standalone (single-workbook mode ends here).
    
6. **Align** (comparison mode only). First columns: by exact name → normalized name → fuzzy name → content signature → positional, in that fallback order, each with confidence. Then rows: by a detected/declared key column → composite key → positional fallback. **Emit the basis and its confidence** — "matched by position, no key found" is a critical caveat the user must see.
    
7. **Compare.** Given the fixed alignment: schema diff, then row diff (added/removed/changed/unchanged), then per-changed-cell variance (numeric delta + %, categorical before→after). Pure math.
    
8. **Insights.** Run an _ordered list of deterministic rule functions_ over profiles + diff; each emits zero or more scored `Insight`s; sort by score. Keep this list small (a dozen rules) — resist building a BI engine.
    
9. **Render.** Serialize `AnalysisResult` (+ diagnostics) to the chosen format.
    

---

## 11. Error-handling strategy

The governing idea: **messy input is the normal case, not the error case.** A tool that throws on a merged cell is useless here. So split failures into two tracks:

- **Fatal** (fail fast, clear message, stop): file missing/corrupt, not valid OOXML, unreadable, genuinely empty. These are programmer/environment errors — exceptions are appropriate.
- **Recoverable / ambiguous** (degrade, record, continue): couldn't confidently find a header, a column has mixed types, no common row key, two sheets aren't comparable. These are **outcomes, not exceptions** — model them as data (a result/outcome object carrying the finding), attach a `Diagnostic`, proceed with a documented assumption.

Principles:

- **Never silently drop data.** A discarded region, an ignored sheet, a coerced value → each becomes a diagnostic.
- **Every heuristic decision carries a confidence**, and low-confidence decisions render prominently in output.
- **Assumptions are auditable.** "Assumed row 3 is the header (confidence 0.6)" appears in the report. This is the entire defense against "the tool guessed wrong and I didn't notice."
- **The core is side-effect-free**, so a failure in stage N never leaves half-written state — you simply have a partial `AnalysisResult` plus diagnostics explaining where it stopped.
- **"Not comparable" is a successful run** that reports incomparability, not a crash.

---

## 12. Extension points

Each is a single interface with an obvious default; adding a variant never touches the core.

|Extension point|Interface|Default|Future variants|
|---|---|---|---|
|Input format|`WorkbookLoader`|openpyxl `.xlsx`|CSV, `.xls`, ODS, Google Sheets export|
|Table detection|`TableDetectionStrategy`|Heuristic|User-guided (explicit range/header), **AI-assisted**|
|Type inference|`TypeInferencePolicy`|Value-based rules|Locale-aware, domain-specific|
|Column matching|`ColumnMatcher`|name→fuzzy→positional|**Semantic (AI)**|
|Row matching|`RowMatcher`|key→composite→positional|Learned keys|
|Insights|`InsightRule` (ordered set)|~12 built-in rules|New rules, **AI narration**|
|Output|`Renderer`|JSON + Markdown|HTML, `.xlsx`, PDF|
|**AI**|`AIProvider` port|**Null object (no-op)**|LLM adapter|

`★ Insight ─────────────────────────────────────` **Where determinism ends — and the only three places AI earns its keep.** Everything _measurable_ stays deterministic forever: counts, deltas, type changes, set differences. Determinism ends exactly at _semantic judgment under ambiguity_ — three spots: (1) "is this row a header?" (detection), (2) "are these two differently-named columns the same concept?" (matching), (3) "which finding matters most to a human, in prose?" (narration). AI belongs only there, only as a **suggestion the deterministic layer validates or overrides**, and only opt-in with explicit network-egress consent — because your inputs are the user's private spreadsheets. Everywhere else, AI just adds nondeterminism and a privacy liability for no gain. `─────────────────────────────────────────────────`

---

## 13. Risks and trade-offs

|Risk / tension|Consequence|Mitigation / stance|
|---|---|---|
|**Heuristic detection is imperfect**|Wrong header → garbage downstream|Confidence + diagnostics + **user override hooks** (let users declare header/range/key when they know). Automatic-with-override, not fully-automatic.|
|**Determinism vs. accuracy**|Deterministic heuristics are "dumber" than an LLM on the ambiguous minority|Accept it in the default path; offer AI opt-in only for that minority|
|**Over-abstraction for a local CLI**|Hexagonal ceremony no one needs|Seams _only_ at the four real boundaries (loader, matcher, renderer, AI). Don't abstract the Comparator.|
|**pandas coupling**|Its NaN/dtype quirks leak into results|Use pandas _behind_ the `Dataset` contract; never expose a DataFrame across a stage boundary|
|**Row alignment without a key**|Meaningless "everything changed" diffs|Detect it, fall back to positional, and **loudly flag the basis**|
|**Insight scope creep**|You accidentally build a BI tool|Cap the rule set; ranked, small, traceable-to-a-fact|
|**Merged-cell / multi-table long tail**|Endless edge cases|Explicit unmerge policy + a large fixture corpus of ugly real files, golden-file tested|
|**Unstructured "analysis"**|Undefined behavior; variance on prose is meaningless|**Recommend cutting it from V1.** Detect-and-report unstructured regions; don't pretend to analyze them.|

The recurring trade-off is **automation vs. honesty.** This tool wins by being _honest about its uncertainty_, not by being magically right. Bias every ambiguous decision toward "make a reasonable choice and tell the user loudly," never "guess silently."

---

## 14. Future roadmap

- **V1 (deterministic core, offline):** `.xlsx` load; single- and dual-workbook; sheet & cross-workbook compare via the _one_ parameterized pipeline; heuristic detection + normalization + profiling + variance + ~12 rule-based insights; CLI + JSON/Markdown output; full diagnostics/audit trail. No network, no AI.
- **V1.x (harden the ambiguous seams):** user overrides for header/range/key; more renderers (HTML, `.xlsx`); additional loaders (CSV, `.xls`).
- **V2 (optional AI, behind the port):** AI-assisted header detection, semantic column matching, and natural-language insight narration — each with a deterministic fallback, each opt-in, each with explicit egress consent. The default build still ships with the null provider.
- **V2+:** GUI over the same library API; config profiles for recurring file families; caching of detection results.
- **Only if proven necessary:** batch parallelism, streaming for very large workbooks. Not before.

---

## What I need from you to firm this up

These are genuine judgment calls where your domain knowledge changes the design — not code, just decisions:

1. **Unstructured data** — do we formally cut it from V1 scope (my recommendation) and treat non-tabular regions as _detected-and-reported_ rather than _analyzed_?
2. **Detection posture** — is the default UX "fully automatic," or "automatic with a first-class override" where users can declare the header row/range? This shapes the whole Detector interface.
3. **Row alignment reality** — in your real files, is there _usually_ a natural key column, or must positional comparison be a first-class, well-supported mode?
4. **Merged-cell unmerge policy** — propagate top-left value, or treat as a boundary, as the default?
5. **First renderer** — which single output format is the V1 priority (CLI table, Markdown, HTML, or JSON)? That's the one we build first.

Want me to turn any of this into a formal **ADR** (e.g., "ADR-001: Structural reader over `pandas.read_excel`" and "ADR-002: Deterministic core with a null AI port"), or render the layer + data-flow diagrams as a shareable visual artifact? I'd hold off on directory structure and interfaces until you've weighed in on the five decisions above — they move real walls.

---

## Addendum — Web layer (added after M8; V1, internal single-machine tool)

The tool now ships an optional **web front-end** alongside the CLI: a **FastAPI
adapter** (`excel_analysis/api.py`) and a **React/Vite/Tailwind SPA**
(`frontend/`). This is the "GUI over the same library API" foreshadowed in §14
("V2+"), delivered early for an **internal, single-machine team** — explicitly
**not** a hosted or multi-user product (no auth, no database, no cloud; §Scope
holds).

It changes none of the architectural rules. It is a thinner-than-thin
interface/presentation layer that sits *above* the `AnalysisResult` contract:

- **Recomputes nothing.** The API calls the existing `load_workbook →
  compare_workbooks → analysis_to_json` path and returns the already-serialized
  `AnalysisResult` under a `{ metadata, analysis }` wrapper. The SPA's TypeScript
  types mirror the JSON contract field-for-field and render it verbatim — the
  same dumb-renderer discipline as the Markdown/HTML renderers, one layer out.
- **Domain stays pure and deterministic.** Neither the API nor the SPA touches
  the domain; the deterministic pipeline is unchanged and AI-free. Determinism
  and byte-identical-with-AI-off hold exactly as before.
- **Local-loopback-only, by construction.** The API binds `127.0.0.1` (the
  `run()` entrypoint fixes the host) and a middleware refuses any non-loopback
  client, so even a mis-launched `--host 0.0.0.0` cannot serve payroll over the
  network. Uploads are size-capped and rejected (413) *before* openpyxl parses
  them. This is the runtime match to keeping payroll off the network and out of
  git — consistent with rule 3's "offline by default."
- **AI narration is opt-in and out of the contract.** The SPA may request a
  local-Ollama narrative (a toggle, off by default). The API runs the *same*
  restate-only guard **server-side** and returns validated bullets as a
  **separate presentation field** (`ai_summary`), never inside `AnalysisResult`.
  On guard rejection or model-unavailability it falls back to the deterministic
  insights; the API never returns unvalidated model text. The default `/compare`
  path is AI-free.

---

## Addendum — Payroll Portal & Reconciliation (M11; V1, local single-machine)

The web layer graduates from a *diff viewer* into a **payroll intelligence
portal**: a payroll manager loads two pay runs and, on one screen, sees how much
net disbursement changed, what it is made of, who and what caused it, and what
looks wrong — then exports a management-ready summary. This addendum records the
**two contract changes** that requires. It changes none of the non-negotiable
rules (CLAUDE.md 1–5); it extends the contract *additively* and adds one new
**deterministic** domain stage.

### What does NOT change

- The domain stays pure and AI-free in the default path. The reconciliation math
  is deterministic and byte-identical run-to-run (rule 3).
- Only domain models cross boundaries. The row data exposed below is the
  normalized `Dataset` (domain value objects) — **never a DataFrame or a raw
  cell** (rule 2). openpyxl stays in the loader.
- No new network egress. The API remains loopback-only; the browser already
  receives salary values, so serializing the full roster to the *local* SPA adds
  no exposure the local tool did not already have (rule 3, offline-by-default).
- Determinism is regression-locked: the additive blocks get golden-file coverage;
  existing goldens are unchanged because the new keys are additive.

### Change 1 — a new deterministic stage: the Reconciliation analyzer

A new pure domain module, **`Reconciliation`**, sits beside the Comparator. It
consumes **two `Dataset`s + the `Alignment`** (nothing earlier, no other stage
imported) and emits a `ReconciliationResult`. It answers the sign-off question:
*walk Period-A total to Period-B total through mutually exclusive buckets that tie
out to the rupee.*

- **Headline anchor.** A single total column `T` (default **Net Payable** — the
  cash that leaves the account and reconciles to treasury). The anchor is
  **switchable** (e.g. to Gross Earnings for pure cost-cause analysis) and
  auto-detection is a **fallback that is recorded loudly** (a `Diagnostic`) only
  when the chosen anchor is genuinely absent from a file — never a silent
  redefinition, which would make period-over-period comparisons apples-to-oranges.
  A cost-to-company anchor is offered **only if** employer-contribution columns
  exist; it is never fabricated.
- **Tie-out as a structural identity, not an estimate.** Partition employees by
  the alignment key into Joiners (B-only), Leavers (A-only), Retained (both):

  ```
  Total_B − Total_A ≡ Σ_J T_B − Σ_L T_A + Σ_R (T_B − T_A)
  ```

  The three buckets sum to the headline delta by construction.
- **Ring-fenced reimbursement/recovery.** The Retained bucket is decomposed into
  **mutually exclusive, sign-aware sub-buckets** — *compensation-cost movement*
  (earnings Δ − deductions Δ) vs *reimbursement/recovery movement* (pass-through
  items that swing without a salary change) — plus an explicit **residual**.
- **Classification is structure-derived, auditable, never name-guessed.** The
  file's own subtotal columns (`Gross Earnings`, `Gross Deduction`,
  `Gross Reimbursement`, …) anchor which block each component belongs to, and each
  block is **validated to sum to its subtotal**; a mismatch becomes the residual /
  a `Diagnostic`, never a silent fudge (rules 4 & 5). Every classification carries
  its provenance and is overridable.

### Change 2 — additive serialization of canonical row data

`AnalysisResult` (and its JSON) gains two additive blocks; every existing key is
untouched, so older consumers keep working:

- `analysis.datasets` — the two normalized `Dataset`s (typed columns × row
  values, both periods), so the SPA can build the roster, Employee 360,
  demographic group-bys, medians, distributions, and drill-to-source. This is
  **serialization, not recomputation**: the `Dataset` already exists in
  `compare_workbooks`.
- `analysis.reconciliation` — the `ReconciliationResult` above (buckets, the
  component/category decomposition, the residual, headcount in/out/retained, the
  anchor + any fallback flag).

### Division of labour — Python owns the numbers, TS owns the exploration

- **Python (canonical, golden-tested):** extraction, comparison, and the
  reconciliation bridge — every headline number and its rupee tie-out.
- **TypeScript (derived presentation only):** percentages, group-bys, medians,
  top-N materiality, distributions, and per-employee 360 self-consistency flags
  (transparent, documented rules) computed *from the serialized canonical rows*.
  The SPA never re-derives a canonical total; it presents and interrogates what
  the engine already computed.

### Data quality, split by audience

Business-impact findings that change the numbers or the liability (duplicate
`Employee_ID`, an employee unmatched across files, negative/zero net, a missing
statutory component, out-of-band values) surface **prominently**. Technical
diagnostics (fuzzy column matching, type coercion, encoding, header parsing) stay
in `warnings` and are **collapsed** in the UI — promoted to a business statement
only when they demonstrably corrupted a total.