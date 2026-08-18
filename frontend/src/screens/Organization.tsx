import { useMemo, useState } from "react";
import type { EmployeeFilter, PortalModel } from "../lib/analytics";
import { groupBy } from "../lib/analytics";
import { inr, inrSigned } from "../lib/format";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Table, Td, Th } from "../components/ui/table";

interface Props {
  model: PortalModel;
  onViewEmployees: (filter: EmployeeFilter) => void;
}

export function Organization({ model, onViewEmployees }: Props) {
  const dims = model.groupDimensions;
  const preferred = dims.find((d) => /department/i.test(d.column)) ?? dims[0];
  const [dimension, setDimension] = useState<string>(preferred?.column ?? "");

  const rows = useMemo(() => (dimension ? groupBy(model, dimension) : []), [model, dimension]);
  const totalDelta = rows.reduce((s, r) => s + r.delta, 0);

  if (dims.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-muted-foreground">
          These files carry no organizational attributes (department, designation, location…) with enough distinct values to
          group by. The portal hides dimensions the data doesn't support rather than inventing them.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Organization — grouped variance</CardTitle>
            <CardDescription>
              Each employee is counted once (current group, or previous for a leaver), so groups tie to the headline delta.
              Movement splits into headcount (joiner/leaver flow) vs per-head (same people, new pay).
            </CardDescription>
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Group by
            <select
              value={dimension}
              onChange={(e) => setDimension(e.target.value)}
              className="h-9 rounded-md border bg-white px-2 text-sm text-foreground"
            >
              {dims.map((d) => (
                <option key={d.column} value={d.column}>{d.column} ({d.distinct})</option>
              ))}
            </select>
          </label>
        </CardHeader>
        <CardContent>
          <Table>
            <thead>
              <tr>
                <Th>{dimension}</Th>
                <Th className="text-right">Headcount</Th>
                <Th className="text-right">{model.anchor} prev → curr</Th>
                <Th className="text-right">Avg / head</Th>
                <Th className="text-right">Movement</Th>
                <Th className="text-right">Headcount vs per-head</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.value}
                  className="cursor-pointer hover:bg-muted/40"
                  onClick={() => onViewEmployees({ dimension: { column: dimension, value: r.value }, label: `${dimension}: ${r.value}` })}
                >
                  <Td className="font-medium">{r.value}</Td>
                  <Td className="text-right tabular-nums">
                    {r.countPrev}
                    <span className="text-muted-foreground"> → </span>
                    {r.countCurr}
                    {r.countCurr !== r.countPrev ? (
                      <span className={r.countCurr > r.countPrev ? "text-emerald-700" : "text-red-700"}>
                        {" "}({r.countCurr > r.countPrev ? "+" : ""}{r.countCurr - r.countPrev})
                      </span>
                    ) : null}
                  </Td>
                  <Td className="text-right tabular-nums text-muted-foreground">
                    {inr(r.totalPrev)} → {inr(r.totalCurr)}
                  </Td>
                  <Td className="text-right tabular-nums text-muted-foreground">
                    {r.avgPrev === null ? "—" : inr(r.avgPrev)} → {r.avgCurr === null ? "—" : inr(r.avgCurr)}
                  </Td>
                  <Td className={`text-right tabular-nums font-medium ${r.delta >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {inrSigned(r.delta)}
                  </Td>
                  <Td className="text-right text-xs tabular-nums text-muted-foreground">
                    {Math.abs(r.headcountEffect) > 0.5 ? <>hc {inrSigned(r.headcountEffect)}</> : "hc —"}
                    <span className="mx-1">·</span>
                    {Math.abs(r.perHeadEffect) > 0.5 ? <>ph {inrSigned(r.perHeadEffect)}</> : "ph —"}
                  </Td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 font-semibold">
                <Td>All groups</Td>
                <Td />
                <Td />
                <Td className="text-right text-xs text-muted-foreground">ties to headline</Td>
                <Td className={`text-right tabular-nums ${totalDelta >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                  {inrSigned(totalDelta)}
                </Td>
                <Td />
              </tr>
            </tfoot>
          </Table>
          <p className="mt-3 text-xs text-muted-foreground">
            Click a group to filter the employee directory to that population. hc = headcount effect (joiners − leavers),
            ph = per-head effect (retained pay changes).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
