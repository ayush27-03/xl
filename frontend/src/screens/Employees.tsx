import { useEffect, useMemo, useState } from "react";
import { Download, Search, X } from "lucide-react";
import type { EmployeeFilter, EmployeeRecord, PortalModel } from "../lib/analytics";
import { employeeComponentLines, isStatutory, num } from "../lib/analytics";
import { displayCell, inr, inrSigned, pct } from "../lib/format";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Table, Td, Th } from "../components/ui/table";
import { CategoryBadge, StatusBadge } from "./Dashboard";

interface Props {
  model: PortalModel;
  focusId: string | null;
  filter?: EmployeeFilter;
}

export function Employees({ model, focusId, filter }: Props) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<string>(filter?.status ?? "all");
  const [dim, setDim] = useState<{ column: string; value: string } | null>(filter?.dimension ?? null);
  const [idFilter, setIdFilter] = useState<{ ids: Set<string>; label: string } | null>(
    filter?.ids ? { ids: new Set(filter.ids), label: filter.label ?? "Filtered set" } : null
  );
  const [selected, setSelected] = useState<string | null>(focusId);

  // Keep in sync when navigation targets a specific employee / applies a filter.
  useEffect(() => setSelected(focusId), [focusId]);
  useEffect(() => {
    setStatus(filter?.status ?? "all");
    setDim(filter?.dimension ?? null);
    setIdFilter(filter?.ids ? { ids: new Set(filter.ids), label: filter.label ?? "Filtered set" } : null);
  }, [filter]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return model.employees.filter((e) => {
      if (idFilter && !idFilter.ids.has(e.id)) return false;
      if (status !== "all" && e.status !== status) return false;
      if (dim && dim.value) {
        const src = e.right ?? e.left;
        if (!src || String(src[dim.column] ?? "") !== dim.value) return false;
      }
      if (q) {
        return e.id.toLowerCase().includes(q) || (e.name ?? "").toLowerCase().includes(q);
      }
      return true;
    });
  }, [model.employees, query, status, dim, idFilter]);

  const selectedEmp = selected ? model.byId.get(selected) ?? null : null;
  const dimValues = useMemo(() => (dim ? distinctValues(model, dim.column) : []), [model, dim?.column]);

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>Employee directory</CardTitle>
          <CardDescription>
            {filtered.length} of {model.employees.length} employees. Click a row for the full previous-vs-current record.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {idFilter ? (
            <div className="flex items-center justify-between rounded-md border border-accent/40 bg-accent/10 px-3 py-2 text-sm">
              <span>Filtered to <strong>{idFilter.label}</strong> · {idFilter.ids.size} employee(s)</span>
              <button onClick={() => setIdFilter(null)} className="font-medium text-accent hover:underline">Clear</button>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-56 flex-1">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by ID or name"
                className="h-10 w-full rounded-md border bg-white pl-9 pr-3 text-sm outline-none focus:border-accent"
              />
            </div>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="h-10 rounded-md border bg-white px-3 text-sm"
            >
              <option value="all">All statuses</option>
              <option value="retained">Retained</option>
              <option value="joiner">Joiners</option>
              <option value="leaver">Leavers</option>
            </select>
            <select
              value={dim?.column ?? ""}
              onChange={(e) => setDim(e.target.value ? { column: e.target.value, value: "" } : null)}
              className="h-10 rounded-md border bg-white px-3 text-sm"
            >
              <option value="">Group by…</option>
              {model.groupDimensions.map((d) => (
                <option key={d.column} value={d.column}>{d.column}</option>
              ))}
            </select>
            {dim ? (
              <select
                value={dim.value}
                onChange={(e) => setDim({ column: dim.column, value: e.target.value })}
                className="h-10 rounded-md border bg-white px-3 text-sm"
              >
                <option value="">Any {dim.column}</option>
                {dimValues.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            ) : null}
          </div>

          <div className="max-h-[60vh] overflow-auto rounded-md border">
            <Table>
              <thead className="sticky top-0 z-10">
                <tr>
                  <Th>Employee</Th>
                  <Th>Status</Th>
                  <Th className="text-right">{model.anchor} (prev)</Th>
                  <Th className="text-right">{model.anchor} (curr)</Th>
                  <Th className="text-right">Change</Th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e) => (
                  <tr
                    key={e.id}
                    onClick={() => setSelected(e.id)}
                    className={`cursor-pointer ${selected === e.id ? "bg-accent/10" : "hover:bg-muted/40"}`}
                  >
                    <Td className="font-medium">
                      {e.name ?? "—"} <span className="text-xs text-muted-foreground">#{e.id}</span>
                    </Td>
                    <Td><StatusBadge status={e.status} /></Td>
                    <Td className="text-right tabular-nums">{e.anchorLeft === null ? "—" : inr(e.anchorLeft)}</Td>
                    <Td className="text-right tabular-nums">{e.anchorRight === null ? "—" : inr(e.anchorRight)}</Td>
                    <Td className={`text-right tabular-nums ${e.anchorDelta >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                      {inrSigned(e.anchorDelta)}
                    </Td>
                  </tr>
                ))}
                {filtered.length === 0 ? (
                  <tr><Td colSpan={5} className="py-8 text-center text-muted-foreground">No employees match these filters.</Td></tr>
                ) : null}
              </tbody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <div className="min-w-0">
        {selectedEmp ? (
          <Employee360 model={model} emp={selectedEmp} onClose={() => setSelected(null)} />
        ) : (
          <Card>
            <CardContent className="flex h-full min-h-64 flex-col items-center justify-center text-center text-muted-foreground">
              <p className="text-sm">Select an employee to see the full previous-vs-current record,</p>
              <p className="text-sm">component-by-component, with self-consistency checks.</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function Employee360({ model, emp, onClose }: { model: PortalModel; emp: EmployeeRecord; onClose: () => void }) {
  const [onlyChanged, setOnlyChanged] = useState(true);
  const lines = useMemo(() => employeeComponentLines(model, emp), [model, emp]);
  const shown = onlyChanged ? lines.filter((l) => Math.abs(l.delta) > 0.005) : lines;
  const flags = useMemo(() => employeeFlags(model, emp), [model, emp]);
  const attrs = useMemo(() => identityAttrs(model, emp), [model, emp]);

  return (
    <Card className="sticky top-4">
      <CardHeader className="flex-row items-start justify-between">
        <div>
          <CardTitle>{emp.name ?? "Employee"} <span className="text-sm font-normal text-muted-foreground">#{emp.id}</span></CardTitle>
          <CardDescription>
            <StatusBadge status={emp.status} /> · {model.anchor} {inrSigned(emp.anchorDelta)}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => exportEmployeeCsv(model, emp)}
            className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs font-medium hover:bg-muted/50"
          >
            <Download className="h-3.5 w-3.5" /> CSV
          </button>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted"><X className="h-4 w-4" /></button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {flags.length ? (
          <div className="space-y-2">
            {flags.map((f) => (
              <div key={f} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                ⚠ {f}
              </div>
            ))}
          </div>
        ) : null}

        {attrs.length ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-md border bg-muted/20 p-3 text-sm">
            {attrs.map(([k, v]) => (
              <div key={k} className="min-w-0">
                <div className="text-xs uppercase text-muted-foreground">{k}</div>
                <div className="truncate">{displayCell(v)}</div>
              </div>
            ))}
          </div>
        ) : null}

        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} />
          Show only changed components ({lines.filter((l) => Math.abs(l.delta) > 0.005).length})
        </label>

        <div className="max-h-[46vh] overflow-auto rounded-md border">
          <Table>
            <thead className="sticky top-0">
              <tr>
                <Th>Component</Th>
                <Th className="text-right">Prev</Th>
                <Th className="text-right">Curr</Th>
                <Th className="text-right">Δ</Th>
                <Th className="text-right">%</Th>
              </tr>
            </thead>
            <tbody>
              {shown.map((l) => (
                <tr key={l.column}>
                  <Td>
                    <span className="flex items-center gap-2">
                      {l.column}
                      {l.category !== "none" ? <CategoryBadge category={l.category} /> : null}
                    </span>
                  </Td>
                  <Td className="text-right tabular-nums">{l.left === null ? "—" : inr(l.left)}</Td>
                  <Td className="text-right tabular-nums">{l.right === null ? "—" : inr(l.right)}</Td>
                  <Td className={`text-right tabular-nums ${l.delta >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {Math.abs(l.delta) < 0.005 ? "—" : inrSigned(l.delta)}
                  </Td>
                  <Td className="text-right tabular-nums text-muted-foreground">{l.pct === null ? "—" : pct(l.pct)}</Td>
                </tr>
              ))}
              {shown.length === 0 ? (
                <tr><Td colSpan={5} className="py-6 text-center text-muted-foreground">No component changes.</Td></tr>
              ) : null}
            </tbody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// --- derived helpers (transparent, presentation-only) -----------------------

function distinctValues(model: PortalModel, column: string): string[] {
  const set = new Set<string>();
  for (const e of model.employees) {
    const src = e.right ?? e.left;
    const v = src ? src[column] : null;
    if (v !== null && v !== undefined && String(v).trim() !== "") set.add(String(v));
  }
  return [...set].sort();
}

function identityAttrs(model: PortalModel, emp: EmployeeRecord): [string, string | number | boolean | null][] {
  const src = emp.right ?? emp.left;
  if (!src) return [];
  const cols = model.groupDimensions.map((d) => d.column);
  return cols.filter((c) => src[c] !== null && src[c] !== undefined && String(src[c]).trim() !== "").map((c) => [c, src[c]]);
}

function employeeFlags(model: PortalModel, e: EmployeeRecord): string[] {
  const flags: string[] = [];
  if (e.status !== "retained" || !e.left || !e.right) {
    if (e.status === "joiner") flags.push("New in the current period — no previous record to compare.");
    if (e.status === "leaver") flags.push("Absent from the current period — appeared previously only.");
    if (e.anchorRight !== null && e.anchorRight <= 0 && e.status !== "leaver")
      flags.push(`${model.anchor} is zero or negative in the current period.`);
    return flags;
  }
  if (e.anchorRight !== null && e.anchorRight <= 0) flags.push(`${model.anchor} is zero or negative this period.`);

  const componentMoved = model.componentColumns.some(
    (c) => Math.abs((num(e.right![c]) ?? 0) - (num(e.left![c]) ?? 0)) > 0.005
  );
  if (Math.abs(e.anchorDelta) > 0.5 && !componentMoved) {
    flags.push(`${model.anchor} changed but no individual component moved — check the source record.`);
  }
  // Statutory deduction that vanished.
  for (const c of model.deductionColumns.filter(isStatutory)) {
    if ((num(e.left![c]) ?? 0) > 0 && (num(e.right![c]) ?? 0) === 0) {
      flags.push(`Statutory deduction “${c}” dropped to zero.`);
    }
  }
  return flags;
}

function exportEmployeeCsv(model: PortalModel, emp: EmployeeRecord) {
  const lines = employeeComponentLines(model, emp);
  const rows = [
    ["Employee", emp.name ?? "", "ID", emp.id, "Status", emp.status],
    [],
    ["Component", "Category", "Previous", "Current", "Change", "% change"],
    ...lines.map((l) => [
      l.column,
      l.category,
      l.left ?? "",
      l.right ?? "",
      l.delta.toFixed(2),
      l.pct === null ? "" : l.pct.toFixed(2)
    ])
  ];
  const csv = rows.map((r) => r.map(csvCell).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `employee-${emp.id}-before-after.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function csvCell(v: unknown): string {
  const s = String(v ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
