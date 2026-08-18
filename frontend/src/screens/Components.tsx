import { useMemo, useState } from "react";
import type { EmployeeFilter, PortalModel } from "../lib/analytics";
import { componentMovements, num } from "../lib/analytics";
import { inr, inrSigned, pct } from "../lib/format";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Table, Td, Th } from "../components/ui/table";
import { MetricTile } from "../components/MetricTile";
import { CategoryBadge } from "./Dashboard";

interface Props {
  model: PortalModel;
  onOpenEmployee: (id: string) => void;
  onViewEmployees: (filter: EmployeeFilter) => void;
}

export function Components({ model, onOpenEmployee, onViewEmployees }: Props) {
  const [threshold, setThreshold] = useState(0);

  const all = useMemo(() => componentMovements(model, model.componentColumns), [model]);
  const totalNet = useMemo(() => all.reduce((s, c) => s + c.netImpact, 0), [all]);
  const totalAbs = useMemo(() => all.reduce((s, c) => s + Math.abs(c.netImpact), 0), [all]);
  const shown = all.filter((c) => Math.abs(c.netImpact) >= threshold);
  const maxAbs = Math.max(1, ...all.map((c) => Math.abs(c.netImpact)));
  const rec = model.reconciliation;

  const affectedIds = (column: string) =>
    model.employees
      .filter((e) => e.status === "retained" && e.left && e.right && Math.abs((num(e.right[column]) ?? 0) - (num(e.left[column]) ?? 0)) > 0.005)
      .map((e) => e.id);

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <MetricTile
          label="Net impact of components"
          value={inrSigned(totalNet)}
          tone={totalNet >= 0 ? "positive" : "negative"}
          sub="on retained-population movement"
        />
        <MetricTile label="Gross component churn" value={inr(totalAbs)} sub="sum of absolute movements" />
        <MetricTile
          label="Retained movement (bridge)"
          value={inrSigned(rec.retained.compensation_delta + rec.retained.reimbursement_delta)}
          sub={Math.abs(rec.retained.residual) > 0.5 ? `+ ${inrSigned(rec.retained.residual)} residual` : "components tie out"}
          tone="neutral"
        />
      </section>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <div>
            <CardTitle>Component analytics</CardTitle>
            <CardDescription>
              Net impact is signed toward {model.anchor} — a growing deduction reduces net. Ranked by absolute impact.
            </CardDescription>
          </div>
          <label className="flex items-center gap-2 whitespace-nowrap text-xs text-muted-foreground">
            Materiality ≥ ₹
            <input
              type="number"
              min={0}
              step={1000}
              value={threshold}
              onChange={(e) => setThreshold(Math.max(0, Number(e.target.value) || 0))}
              className="h-9 w-28 rounded-md border bg-white px-2 text-sm text-foreground"
            />
          </label>
        </CardHeader>
        <CardContent>
          <Table>
            <thead>
              <tr>
                <Th>Component</Th>
                <Th className="text-right">Prev total</Th>
                <Th className="text-right">Curr total</Th>
                <Th className="text-right">Net impact</Th>
                <Th className="w-40">Share</Th>
                <Th className="text-right">Employees</Th>
                <Th>Largest change</Th>
              </tr>
            </thead>
            <tbody>
              {shown.map((c) => {
                const share = totalAbs ? Math.abs(c.netImpact) / totalAbs : 0;
                return (
                  <tr
                    key={c.column}
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => onViewEmployees({ ids: affectedIds(c.column), label: `${c.column} changed` })}
                  >
                    <Td className="font-medium">
                      <span className="flex items-center gap-2">{c.column} <CategoryBadge category={c.category} /></span>
                    </Td>
                    <Td className="text-right tabular-nums text-muted-foreground">{inr(c.left)}</Td>
                    <Td className="text-right tabular-nums text-muted-foreground">{inr(c.right)}</Td>
                    <Td className={`text-right tabular-nums font-medium ${c.netImpact >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                      {inrSigned(c.netImpact)}
                    </Td>
                    <Td>
                      <div className="flex items-center gap-2">
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className={c.netImpact >= 0 ? "h-full bg-emerald-500" : "h-full bg-red-500"}
                            style={{ width: `${(Math.abs(c.netImpact) / maxAbs) * 100}%` }}
                          />
                        </div>
                        <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">{(share * 100).toFixed(0)}%</span>
                      </div>
                    </Td>
                    <Td className="text-right tabular-nums text-muted-foreground">{c.employeesAffected}</Td>
                    <Td className="text-xs">
                      {c.topIncrease ? (
                        <button
                          className="text-emerald-700 hover:underline"
                          onClick={(e) => { e.stopPropagation(); onOpenEmployee(c.topIncrease!.id); }}
                        >
                          ▲ {c.topIncrease.name ?? c.topIncrease.id} {inrSigned(c.topIncrease.amount)}
                        </button>
                      ) : null}
                      {c.topIncrease && c.topDecrease ? <br /> : null}
                      {c.topDecrease ? (
                        <button
                          className="text-red-700 hover:underline"
                          onClick={(e) => { e.stopPropagation(); onOpenEmployee(c.topDecrease!.id); }}
                        >
                          ▼ {c.topDecrease.name ?? c.topDecrease.id} {inrSigned(c.topDecrease.amount)}
                        </button>
                      ) : null}
                    </Td>
                  </tr>
                );
              })}
              {shown.length === 0 ? (
                <tr><Td colSpan={7} className="py-8 text-center text-muted-foreground">No components meet the materiality threshold.</Td></tr>
              ) : null}
            </tbody>
          </Table>
          <p className="mt-3 text-xs text-muted-foreground">
            Click a component to see the employees it moved. Net impact is measured over the retained population (same
            people, both periods); joiners and leavers are headcount, shown on the Organization and Dashboard views.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
