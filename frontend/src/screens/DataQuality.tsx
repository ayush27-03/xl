import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, ShieldCheck } from "lucide-react";
import type { EmployeeFilter, PortalModel } from "../lib/analytics";
import type { Diagnostic } from "../lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { MetricTile } from "../components/MetricTile";

interface Props {
  model: PortalModel;
  warnings: Diagnostic[];
  onOpenEmployee: (id: string) => void;
  onViewEmployees: (filter: EmployeeFilter) => void;
}

export function DataQuality({ model, warnings, onOpenEmployee, onViewEmployees }: Props) {
  const [showTechnical, setShowTechnical] = useState(false);
  const issues = model.validations;
  const high = issues.filter((i) => i.severity === "high");

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <MetricTile
          label="Business-impact issues"
          value={issues.length}
          tone={high.length ? "negative" : issues.length ? "neutral" : "positive"}
          sub={high.length ? `${high.length} high severity` : issues.length ? "review recommended" : "none flagged"}
        />
        <MetricTile label="Technical diagnostics" value={warnings.length} tone="neutral" sub="engine-level, advanced" />
        <MetricTile
          label="Reconciliation"
          value={Math.abs(model.reconciliation.retained.residual) < 0.5 ? "Ties out" : "Residual"}
          tone={Math.abs(model.reconciliation.retained.residual) < 0.5 ? "positive" : "negative"}
          sub={model.anchor}
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Business-impact findings</CardTitle>
          <CardDescription>
            Issues that change the numbers or the sign-off — duplicate IDs, unmatched employees, non-positive net, vanished
            statutory deductions, or a reconciliation that doesn't tie out.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {issues.length === 0 ? (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              <ShieldCheck className="h-4 w-4" /> No business-impact issues detected in this comparison.
            </div>
          ) : (
            issues.map((v) => (
              <div
                key={v.code}
                className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${
                  v.severity === "high" ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"
                }`}
              >
                <AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${v.severity === "high" ? "text-red-700" : "text-amber-700"}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold">{v.title}</p>
                    <Badge variant={v.severity === "high" ? "danger" : "warning"}>{v.severity}</Badge>
                  </div>
                  <p className="text-sm leading-6 text-muted-foreground">{v.detail}</p>
                  {v.employeeIds.length ? (
                    <div className="mt-1 flex gap-3 text-xs">
                      <button
                        onClick={() => onViewEmployees({ ids: v.employeeIds, label: v.title })}
                        className="font-medium text-accent hover:underline"
                      >
                        View {v.employeeIds.length} affected
                      </button>
                      {v.employeeIds.length === 1 ? (
                        <button onClick={() => onOpenEmployee(v.employeeIds[0])} className="font-medium text-accent hover:underline">
                          Open record
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <button
            className="flex w-full items-center justify-between text-left"
            onClick={() => setShowTechnical((s) => !s)}
          >
            <div>
              <CardTitle>Technical diagnostics</CardTitle>
              <CardDescription>
                Engine-level notes (column matching, type coercion, structure). These matter only if they corrupted a total —
                otherwise they are safe to ignore.
              </CardDescription>
            </div>
            {showTechnical ? <ChevronDown className="h-5 w-5 text-muted-foreground" /> : <ChevronRight className="h-5 w-5 text-muted-foreground" />}
          </button>
        </CardHeader>
        {showTechnical ? (
          <CardContent className="space-y-2">
            {warnings.length === 0 ? (
              <p className="text-sm text-muted-foreground">No technical diagnostics were recorded.</p>
            ) : (
              warnings.map((w, i) => (
                <div key={`${w.code}-${i}`} className="flex items-start gap-3 rounded-md border bg-muted/20 px-3 py-2 text-sm">
                  <Badge variant={w.severity === "error" ? "danger" : w.severity === "warning" ? "warning" : "muted"}>{w.code}</Badge>
                  <span className="min-w-0 flex-1 leading-6 text-muted-foreground">{w.message}</span>
                  {w.confidence !== undefined ? (
                    <span className="whitespace-nowrap text-xs text-muted-foreground">conf {w.confidence}</span>
                  ) : null}
                </div>
              ))
            )}
          </CardContent>
        ) : null}
      </Card>
    </div>
  );
}
