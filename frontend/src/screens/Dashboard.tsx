import { useMemo } from "react";
import { AlertTriangle, ArrowRight, TrendingDown, TrendingUp } from "lucide-react";
import type { PortalModel } from "../lib/analytics";
import { componentMovements } from "../lib/analytics";
import { inr, inrSigned, pct } from "../lib/format";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Table, Td, Th } from "../components/ui/table";
import { MetricTile } from "../components/MetricTile";
import { BridgeWaterfall, type BridgeStep } from "../components/BridgeWaterfall";

interface Props {
  model: PortalModel;
  filenames: { left: string; right: string };
  onOpenEmployee: (id: string) => void;
  onViewEmployees: (filter?: { status?: string }) => void;
}

export function Dashboard({ model, filenames, onOpenEmployee, onViewEmployees }: Props) {
  const rec = model.reconciliation;
  const b = rec.buckets;
  const comp = rec.retained.compensation_delta;
  const reimb = rec.retained.reimbursement_delta;
  const residual = rec.retained.residual;

  const steps: BridgeStep[] = useMemo(() => {
    const s: BridgeStep[] = [{ label: "Previous", value: rec.total_left, kind: "total" }];
    if (b.joiners.count) s.push({ label: "Joiners", value: b.joiners.amount, kind: "delta" });
    if (b.leavers.count) s.push({ label: "Leavers", value: b.leavers.amount, kind: "delta" });
    s.push({ label: "Compensation cost", value: comp, kind: "delta" });
    if (Math.abs(reimb) > 0.5) s.push({ label: "Reimbursement & recovery", value: reimb, kind: "delta" });
    if (Math.abs(residual) > 0.5) s.push({ label: "Unexplained residual", value: residual, kind: "delta" });
    s.push({ label: "Current", value: rec.total_right, kind: "total" });
    return s;
  }, [rec, b, comp, reimb, residual]);

  const topComponents = useMemo(
    () => componentMovements(model, model.componentColumns).slice(0, 8),
    [model]
  );
  const topMovers = useMemo(() => model.employees.slice(0, 8), [model]);

  const deltaPct = rec.total_left !== 0 ? (rec.delta / Math.abs(rec.total_left)) * 100 : null;
  const highIssues = model.validations.filter((v) => v.severity === "high");

  return (
    <div className="space-y-6">
      {/* Headline */}
      <section className="grid gap-4 lg:grid-cols-3">
        <MetricTile label={`Previous · ${filenames.left}`} value={inr(rec.total_left)} sub={`${model.anchor}`} />
        <MetricTile label={`Current · ${filenames.right}`} value={inr(rec.total_right)} sub={`${model.anchor}`} />
        <MetricTile
          label="Net movement"
          value={inrSigned(rec.delta)}
          tone={rec.delta >= 0 ? "positive" : "negative"}
          sub={deltaPct !== null ? `${pct(deltaPct)} vs previous` : undefined}
        />
      </section>

      {rec.anchor_substituted ? (
        <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            The requested headline anchor was not present in both files; this bridge uses{" "}
            <strong>{model.anchor}</strong>. Use the same anchor across periods for comparability.
          </span>
        </div>
      ) : null}

      {/* The bridge */}
      <Card>
        <CardHeader>
          <CardTitle>Reconciliation bridge — {model.anchor}</CardTitle>
          <CardDescription>
            How the previous total becomes the current total, through mutually exclusive buckets that tie out to the rupee.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <BridgeWaterfall steps={steps} />
          <p className="rounded-md border bg-muted/30 px-4 py-3 text-sm leading-6">
            {model.anchor} moved <strong className={rec.delta >= 0 ? "text-emerald-700" : "text-red-700"}>{inrSigned(rec.delta)}</strong>.
            Of that, <strong className={comp >= 0 ? "text-emerald-700" : "text-red-700"}>{inrSigned(comp)}</strong> is real
            compensation-cost movement{Math.abs(reimb) > 0.5 ? (
              <>
                {" "}and <strong className={reimb >= 0 ? "text-emerald-700" : "text-red-700"}>{inrSigned(reimb)}</strong> is
                reimbursement/recovery movement (pass-through that doesn't reflect a salary change)
              </>
            ) : null}
            {Math.abs(residual) > 0.5 ? (
              <> , with an <strong className="text-red-700">{inrSigned(residual)}</strong> unexplained residual</>
            ) : null}
            .
          </p>
        </CardContent>
      </Card>

      {/* Headcount + ring-fence tiles */}
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricTile
          label="Retained employees"
          value={b.retained.count}
          sub={`median move ${inrSigned(model.retainedMedianDelta)}`}
          onClick={() => onViewEmployees({ status: "retained" })}
        />
        <MetricTile
          label="Joiners (in current only)"
          value={b.joiners.count}
          tone={b.joiners.count ? "positive" : "neutral"}
          sub={b.joiners.count ? `${inr(b.joiners.amount)} added` : "none"}
          onClick={() => onViewEmployees({ status: "joiner" })}
        />
        <MetricTile
          label="Leavers (in previous only)"
          value={b.leavers.count}
          tone={b.leavers.count ? "negative" : "neutral"}
          sub={b.leavers.count ? `${inr(Math.abs(b.leavers.amount))} removed` : "none"}
          onClick={() => onViewEmployees({ status: "leaver" })}
        />
        <MetricTile
          label="Attention items"
          value={highIssues.length}
          tone={highIssues.length ? "negative" : "positive"}
          sub={highIssues.length ? "business-impact issues" : "none flagged"}
        />
      </section>

      {/* Materiality */}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Where the money moved — components</CardTitle>
              <CardDescription>Retained-population movement by pay component.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <thead>
                <tr>
                  <Th>Component</Th>
                  <Th>Category</Th>
                  <Th className="text-right">Movement</Th>
                  <Th className="text-right">Employees</Th>
                </tr>
              </thead>
              <tbody>
                {topComponents.map((c) => (
                  <tr key={c.column}>
                    <Td className="font-medium">{c.column}</Td>
                    <Td><CategoryBadge category={c.category} /></Td>
                    <Td className={`text-right tabular-nums ${c.delta >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                      {inrSigned(c.delta)}
                    </Td>
                    <Td className="text-right tabular-nums text-muted-foreground">{c.employeesAffected}</Td>
                  </tr>
                ))}
                {topComponents.length === 0 ? (
                  <tr><Td colSpan={4} className="text-muted-foreground">No component movement.</Td></tr>
                ) : null}
              </tbody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Largest employee movements</CardTitle>
            <CardDescription>Concentration is where payroll swings live — start here.</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <thead>
                <tr>
                  <Th>Employee</Th>
                  <Th>Status</Th>
                  <Th className="text-right">{model.anchor} move</Th>
                </tr>
              </thead>
              <tbody>
                {topMovers.map((e) => (
                  <tr
                    key={e.id}
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => onOpenEmployee(e.id)}
                  >
                    <Td className="font-medium">
                      <span className="flex items-center gap-2">
                        {e.anchorDelta >= 0 ? (
                          <TrendingUp className="h-4 w-4 text-emerald-600" />
                        ) : (
                          <TrendingDown className="h-4 w-4 text-red-600" />
                        )}
                        {e.name ?? e.id}
                        <span className="text-xs text-muted-foreground">#{e.id}</span>
                      </span>
                    </Td>
                    <Td><StatusBadge status={e.status} /></Td>
                    <Td className={`text-right tabular-nums ${e.anchorDelta >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                      {inrSigned(e.anchorDelta)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <button
              onClick={() => onViewEmployees()}
              className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
            >
              Open employee directory <ArrowRight className="h-4 w-4" />
            </button>
          </CardContent>
        </Card>
      </div>

      {/* Business-impact issues */}
      {model.validations.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Requires attention</CardTitle>
            <CardDescription>Business-impact findings that change the numbers or the sign-off.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {model.validations.map((v) => (
              <div
                key={v.code}
                className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${
                  v.severity === "high" ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"
                }`}
              >
                <AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${v.severity === "high" ? "text-red-700" : "text-amber-700"}`} />
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{v.title}</p>
                  <p className="text-sm leading-6 text-muted-foreground">{v.detail}</p>
                  {v.employeeIds.length ? (
                    <button
                      onClick={() => v.employeeIds[0] && onOpenEmployee(v.employeeIds[0])}
                      className="mt-1 text-xs font-medium text-accent hover:underline"
                    >
                      {v.employeeIds.length} employee(s) affected · inspect
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  const map: Record<string, string> = {
    earning: "bg-emerald-50 text-emerald-700 border-emerald-200",
    deduction: "bg-red-50 text-red-700 border-red-200",
    reimbursement: "bg-sky-50 text-sky-700 border-sky-200",
    none: "bg-slate-50 text-slate-600 border-slate-200"
  };
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${map[category] ?? map.none}`}>
      {category}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, "success" | "danger" | "muted"> = {
    joiner: "success",
    leaver: "danger",
    retained: "muted"
  };
  return <Badge variant={map[status] ?? "muted"}>{status}</Badge>;
}
