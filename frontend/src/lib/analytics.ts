// Derived-analytics layer. Turns the engine's serialized rows + reconciliation
// into an employee-centric model the UI reads. This layer NEVER recomputes a
// canonical headline number — those come from the Python `reconciliation` block.
// It only reshapes, groups, ranks, and derives presentation facts (medians,
// per-employee/per-component movement, self-consistency flags) from the same
// canonical rows, using transparent rules.

import type {
  AnalysisResult,
  CellValue,
  ColumnClassification,
  ColumnRole,
  PayCategory,
  Reconciliation,
  SerializedDataset
} from "./types";

export type EmployeeStatus = "retained" | "joiner" | "leaver";

export interface EmployeeRecord {
  id: string;
  name: string | null;
  status: EmployeeStatus;
  anchorLeft: number | null;
  anchorRight: number | null;
  anchorDelta: number; // signed contribution to the headline delta
  left: Record<string, CellValue> | null;
  right: Record<string, CellValue> | null;
}

export interface EmployeeAmount {
  id: string;
  name: string | null;
  amount: number;
}

export interface ComponentMovement {
  column: string;
  category: PayCategory;
  left: number;
  right: number;
  delta: number; // raw column movement (right − left)
  netImpact: number; // signed contribution to the anchor: deductions reduce net
  employeesAffected: number;
  topIncrease: EmployeeAmount | null;
  topDecrease: EmployeeAmount | null;
}

export interface GroupRow {
  value: string;
  countPrev: number;
  countCurr: number;
  totalPrev: number;
  totalCurr: number;
  avgPrev: number | null;
  avgCurr: number | null;
  delta: number; // Σ anchorDelta of employees attributed here (ties to total)
  headcountEffect: number; // joiners + leavers value (people flow)
  perHeadEffect: number; // retained movement (same people, new pay)
  employeeIds: string[];
}

/** A component's signed contribution to anchor movement: an earning or
 * reimbursement adds, a deduction that grows subtracts. Σ over components (net)
 * equals the retained anchor movement, so contributions tie out. */
export function netImpactOf(category: PayCategory, delta: number): number {
  return category === "deduction" ? -delta : delta;
}

/** A cross-screen drill target: navigate to Employees narrowed by status, a
 * dimension value, or an explicit id set (e.g. "affected by this component"). */
export interface EmployeeFilter {
  status?: string;
  dimension?: { column: string; value: string };
  ids?: string[];
  label?: string;
}

export interface GroupDimension {
  column: string;
  distinct: number;
}

export interface Validation {
  code: string;
  severity: "high" | "medium" | "info";
  title: string;
  detail: string;
  employeeIds: string[];
}

export interface PortalModel {
  anchor: string;
  keyColumn: string | null;
  employees: EmployeeRecord[];
  byId: Map<string, EmployeeRecord>;
  classification: Map<string, ColumnClassification>;
  componentColumns: string[];
  earningColumns: string[];
  deductionColumns: string[];
  reimbursementColumns: string[];
  groupDimensions: GroupDimension[];
  retainedMeanDelta: number;
  retainedMedianDelta: number;
  validations: Validation[];
  reconciliation: Reconciliation;
}

export function num(v: CellValue | undefined): number | null {
  if (v === null || v === undefined || typeof v === "boolean") return null;
  if (typeof v === "number") return v;
  const s = String(v).trim().replace(/,/g, "");
  if (s === "") return null;
  const f = Number(s);
  return Number.isFinite(f) ? f : null;
}

/** Mirror the engine's key normalization so left/right rows join correctly. */
export function normKey(v: CellValue): string {
  const s = String(v ?? "").trim();
  if (s === "") return "";
  if (/^[+-]?\d+$/.test(s)) return String(parseInt(s, 10));
  const f = Number(s);
  if (Number.isFinite(f)) return Number.isInteger(f) ? String(f) : String(f);
  return s;
}

export function median(nums: number[]): number {
  if (nums.length === 0) return 0;
  const s = [...nums].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function rowMap(ds: SerializedDataset, row: CellValue[]): Record<string, CellValue> {
  const out: Record<string, CellValue> = {};
  ds.columns.forEach((c, i) => (out[c.name] = row[i] ?? null));
  return out;
}

function indexByKey(ds: SerializedDataset, keyCol: string): Map<string, Record<string, CellValue>> {
  const idx = ds.columns.findIndex((c) => c.name === keyCol);
  const map = new Map<string, Record<string, CellValue>>();
  if (idx < 0) return map;
  for (const row of ds.rows) {
    const k = normKey(row[idx]);
    if (k !== "" && !map.has(k)) map.set(k, rowMap(ds, row));
  }
  return map;
}

function nameColumn(ds: SerializedDataset): string | null {
  const byName = ds.columns.find((c) => /name/i.test(c.name) && !/bank|father|user/i.test(c.name));
  return byName ? byName.name : null;
}

export function buildModel(analysis: AnalysisResult): PortalModel | null {
  const rec = analysis.reconciliation;
  const ds = analysis.datasets;
  if (!rec || !ds || !rec.comparable) return null;

  const classification = new Map<string, ColumnClassification>();
  rec.classification.forEach((c) => classification.set(c.column, c));

  const keyCol = rec.key_column ?? ds.left.columns[0]?.name ?? null;
  const nameCol = nameColumn(ds.right) ?? nameColumn(ds.left);

  const left = keyCol ? indexByKey(ds.left, keyCol) : new Map();
  const right = keyCol ? indexByKey(ds.right, keyCol) : new Map();
  const anchor = rec.anchor ?? "";

  const employees: EmployeeRecord[] = [];
  const keys = new Set<string>([...left.keys(), ...right.keys()]);
  for (const k of keys) {
    const l = left.get(k) ?? null;
    const r = right.get(k) ?? null;
    const status: EmployeeStatus = l && r ? "retained" : r ? "joiner" : "leaver";
    const aL = l ? num(l[anchor]) : null;
    const aR = r ? num(r[anchor]) : null;
    const anchorDelta =
      status === "retained" ? (aR ?? 0) - (aL ?? 0) : status === "joiner" ? aR ?? 0 : -(aL ?? 0);
    const nameSrc = r ?? l;
    employees.push({
      id: k,
      name: nameCol && nameSrc ? (nameSrc[nameCol] as string) ?? null : null,
      status,
      anchorLeft: aL,
      anchorRight: aR,
      anchorDelta,
      left: l,
      right: r
    });
  }
  employees.sort((a, b) => Math.abs(b.anchorDelta) - Math.abs(a.anchorDelta));

  const byRole = (role: ColumnRole, cat?: PayCategory) =>
    rec.classification.filter((c) => c.role === role && (cat ? c.category === cat : true)).map((c) => c.column);
  const componentColumns = byRole("component");
  const earningColumns = byRole("component", "earning");
  const deductionColumns = byRole("component", "deduction");
  const reimbursementColumns = byRole("component", "reimbursement");

  const groupDimensions = deriveGroupDimensions(ds.right, rec.classification, keyCol, nameCol);

  const retainedDeltas = employees.filter((e) => e.status === "retained").map((e) => e.anchorDelta);
  const retainedMeanDelta = retainedDeltas.length
    ? retainedDeltas.reduce((a, b) => a + b, 0) / retainedDeltas.length
    : 0;

  const model: PortalModel = {
    anchor,
    keyColumn: keyCol,
    employees,
    byId: new Map(employees.map((e) => [e.id, e])),
    classification,
    componentColumns,
    earningColumns,
    deductionColumns,
    reimbursementColumns,
    groupDimensions,
    retainedMeanDelta,
    retainedMedianDelta: median(retainedDeltas),
    validations: [],
    reconciliation: rec
  };
  model.validations = deriveValidations(model, ds);
  return model;
}

/** Group-able attributes: identity text columns actually populated with 2+
 * distinct values. We HIDE a dimension the data doesn't support rather than
 * invent an empty one. */
function deriveGroupDimensions(
  ds: SerializedDataset,
  classification: ColumnClassification[],
  keyCol: string | null,
  nameCol: string | null
): GroupDimension[] {
  const idRoles = new Set(classification.filter((c) => c.role === "identity").map((c) => c.column));
  const dims: GroupDimension[] = [];
  ds.columns.forEach((c, i) => {
    if (c.type !== "text") return;
    if (c.name === keyCol || c.name === nameCol) return;
    if (!idRoles.has(c.name) && classification.length > 0) return;
    if (/bank|ifsc|account|pan|uan|pran|pf number|father|position description/i.test(c.name)) return;
    const distinct = new Set(
      ds.rows.map((r) => r[i]).filter((v) => v !== null && v !== undefined && String(v).trim() !== "")
    );
    if (distinct.size >= 2 && distinct.size <= Math.max(2, ds.rows.length * 0.7)) {
      dims.push({ column: c.name, distinct: distinct.size });
    }
  });
  return dims;
}

const STATUTORY = new Set([
  "pf",
  "provident fund",
  "tds",
  "pt",
  "professional tax",
  "esi",
  "employee state insurance"
]);

/** Exact-name match (not substring) so "Excess TDS Refund" is NOT mistaken for a
 * statutory deduction. */
export function isStatutory(column: string): boolean {
  return STATUTORY.has(column.trim().toLowerCase());
}

/** Business-impact validations — findings that change the numbers or liability,
 * derived deterministically from the canonical rows with transparent rules. */
function deriveValidations(model: PortalModel, ds: NonNullable<AnalysisResult["datasets"]>): Validation[] {
  const out: Validation[] = [];
  const rec = model.reconciliation;

  const dupes = (d: SerializedDataset, period: string) => {
    if (!model.keyColumn) return;
    const idx = d.columns.findIndex((c) => c.name === model.keyColumn);
    if (idx < 0) return;
    const seen = new Map<string, number>();
    d.rows.forEach((r) => {
      const k = normKey(r[idx]);
      if (k) seen.set(k, (seen.get(k) ?? 0) + 1);
    });
    const dup = [...seen.entries()].filter(([, n]) => n > 1).map(([k]) => k);
    if (dup.length) {
      out.push({
        code: "duplicate-id",
        severity: "high",
        title: `Duplicate Employee IDs in ${period}`,
        detail: `${dup.length} ID(s) appear more than once and may double-count payroll.`,
        employeeIds: dup
      });
    }
  };
  dupes(ds.left, "the previous period");
  dupes(ds.right, "the current period");

  const nonPositive = model.employees.filter(
    (e) => e.status !== "leaver" && e.anchorRight !== null && e.anchorRight <= 0
  );
  if (nonPositive.length) {
    out.push({
      code: "non-positive-net",
      severity: "high",
      title: `Zero or negative ${model.anchor}`,
      detail: `${nonPositive.length} employee(s) have a current ${model.anchor} of zero or below — review before disbursement.`,
      employeeIds: nonPositive.map((e) => e.id)
    });
  }

  const statutory = model.deductionColumns.filter(isStatutory);
  if (statutory.length) {
    const dropped = model.employees.filter((e) => {
      if (e.status !== "retained" || !e.left || !e.right) return false;
      return statutory.some((c) => (num(e.left![c]) ?? 0) > 0 && (num(e.right![c]) ?? 0) === 0);
    });
    if (dropped.length) {
      out.push({
        code: "statutory-dropped",
        severity: "high",
        title: "Statutory deduction disappeared",
        detail: `${dropped.length} employee(s) had a statutory deduction (${statutory.join(", ")}) previously that is now zero.`,
        employeeIds: dropped.map((e) => e.id)
      });
    }
  }

  if (Math.abs(rec.retained.residual) > 0.5) {
    out.push({
      code: "reconciliation-residual",
      severity: "high",
      title: "Reconciliation does not fully tie out",
      detail: `An unexplained residual of ${rec.retained.residual.toFixed(2)} remains after compensation and reimbursement movement — stored subtotals may not sum to ${model.anchor}.`,
      employeeIds: []
    });
  }
  if (rec.anchor_substituted) {
    out.push({
      code: "anchor-substituted",
      severity: "medium",
      title: "Headline anchor was substituted",
      detail: `The requested anchor was absent, so the bridge uses “${model.anchor}”. Use the same anchor across periods for comparability.`,
      employeeIds: []
    });
  }
  return out;
}

/** Σ movement per component over a population (default: retained employees),
 * with signed net impact and the single largest increaser/decreaser. Sorted by
 * absolute net impact — the order that answers "what drove the change". */
export function componentMovements(
  model: PortalModel,
  columns: string[],
  population?: EmployeeRecord[]
): ComponentMovement[] {
  const pop = population ?? model.employees.filter((e) => e.status === "retained");
  return columns
    .map((column) => {
      const cls = model.classification.get(column);
      const category = cls?.category ?? "none";
      let left = 0;
      let right = 0;
      let affected = 0;
      let topInc: EmployeeAmount | null = null;
      let topDec: EmployeeAmount | null = null;
      for (const e of pop) {
        const l = e.left ? num(e.left[column]) ?? 0 : 0;
        const r = e.right ? num(e.right[column]) ?? 0 : 0;
        left += l;
        right += r;
        const d = r - l;
        if (Math.abs(d) > 0.005) affected += 1;
        if (d > 0 && (!topInc || d > topInc.amount)) topInc = { id: e.id, name: e.name, amount: d };
        if (d < 0 && (!topDec || d < topDec.amount)) topDec = { id: e.id, name: e.name, amount: d };
      }
      const delta = right - left;
      return {
        column,
        category,
        left,
        right,
        delta,
        netImpact: netImpactOf(category, delta),
        employeesAffected: affected,
        topIncrease: topInc,
        topDecrease: topDec
      };
    })
    .filter((m) => Math.abs(m.delta) > 0.005 || m.employeesAffected > 0)
    .sort((a, b) => Math.abs(b.netImpact) - Math.abs(a.netImpact));
}

/** Group employees by a dimension and decompose each group's anchor movement
 * into headcount (joiner/leaver flow) vs per-head (retained) effects. Every
 * employee is attributed to exactly one group — by their current-period value,
 * or previous-period value for a leaver — so Σ group deltas ties to the
 * headline delta exactly. */
export function groupBy(model: PortalModel, dimension: string): GroupRow[] {
  const groups = new Map<string, GroupRow>();
  const get = (value: string): GroupRow => {
    let g = groups.get(value);
    if (!g) {
      g = {
        value,
        countPrev: 0,
        countCurr: 0,
        totalPrev: 0,
        totalCurr: 0,
        avgPrev: null,
        avgCurr: null,
        delta: 0,
        headcountEffect: 0,
        perHeadEffect: 0,
        employeeIds: []
      };
      groups.set(value, g);
    }
    return g;
  };

  for (const e of model.employees) {
    const src = e.right ?? e.left;
    const raw = src ? src[dimension] : null;
    const value = raw === null || raw === undefined || String(raw).trim() === "" ? "(not set)" : String(raw);
    const g = get(value);
    g.employeeIds.push(e.id);
    g.delta += e.anchorDelta;
    if (e.anchorLeft !== null) {
      g.countPrev += 1;
      g.totalPrev += e.anchorLeft;
    }
    if (e.anchorRight !== null) {
      g.countCurr += 1;
      g.totalCurr += e.anchorRight;
    }
    if (e.status === "retained") g.perHeadEffect += e.anchorDelta;
    else g.headcountEffect += e.anchorDelta; // joiners (+) and leavers (−)
  }

  const rows = [...groups.values()];
  for (const g of rows) {
    g.avgPrev = g.countPrev ? g.totalPrev / g.countPrev : null;
    g.avgCurr = g.countCurr ? g.totalCurr / g.countCurr : null;
  }
  return rows.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
}

/** Per-employee component lines for the Employee 360, in file order. */
export function employeeComponentLines(model: PortalModel, e: EmployeeRecord) {
  return model.componentColumns
    .map((column) => {
      const l = e.left ? num(e.left[column]) : null;
      const r = e.right ? num(e.right[column]) : null;
      const left = l ?? 0;
      const right = r ?? 0;
      const delta = right - left;
      return {
        column,
        category: model.classification.get(column)?.category ?? "none",
        left: l,
        right: r,
        delta,
        pct: left !== 0 ? (delta / Math.abs(left)) * 100 : null
      };
    })
    .filter((line) => line.left !== null || line.right !== null);
}
