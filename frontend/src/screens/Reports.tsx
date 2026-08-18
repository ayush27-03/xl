import { useMemo, useState } from "react";
import { CheckCircle2, Download, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import type { PortalModel } from "../lib/analytics";
import { componentMovements } from "../lib/analytics";
import { downloadReport } from "../lib/api";
import { inr, inrSigned, pct } from "../lib/format";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Alert } from "../components/ui/alert";
import { MetricTile } from "../components/MetricTile";

interface Props {
  model: PortalModel;
  files: { left: File | null; right: File | null };
  anchor: string;
}

export function Reports({ model, files, anchor }: Props) {
  const rec = model.reconciliation;
  const [preparedBy, setPreparedBy] = useState("");
  const [busy, setBusy] = useState<null | "pdf" | "xlsx">(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const churn = useMemo(() => {
    const comps = componentMovements(model, model.componentColumns);
    return comps.reduce((s, c) => s + Math.abs(c.netImpact), 0);
  }, [model]);

  const canDownload = files.left !== null && files.right !== null;
  const highIssues = model.validations.filter((v) => v.severity === "high");

  const generate = async (format: "pdf" | "xlsx") => {
    if (!files.left || !files.right) {
      setError("The original workbooks are needed to generate a report — re-upload them to enable downloads.");
      return;
    }
    setError(null);
    setDone(null);
    setBusy(format);
    try {
      const name = await downloadReport(files.left, files.right, { format, anchor, preparedBy });
      setDone(name);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Report Center</CardTitle>
          <CardDescription>
            A one-page management summary you can sign and forward, plus a reconciling Excel workbook. Every figure is the
            engine's canonical number — the report renders the bridge, it does not recompute it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
            <label className="block max-w-sm text-sm font-medium">
              Prepared by
              <input
                value={preparedBy}
                onChange={(e) => setPreparedBy(e.target.value)}
                placeholder="Your name (appears on the report header)"
                className="mt-2 h-10 w-full rounded-md border bg-white px-3 text-sm font-normal"
              />
            </label>
            <div className="flex flex-wrap gap-3">
              <button
                disabled={!canDownload || busy !== null}
                onClick={() => generate("pdf")}
                className="inline-flex items-center gap-2 rounded-md bg-[#0f2f4c] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
              >
                {busy === "pdf" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                Download PDF
              </button>
              <button
                disabled={!canDownload || busy !== null}
                onClick={() => generate("xlsx")}
                className="inline-flex items-center gap-2 rounded-md border px-4 py-2.5 text-sm font-semibold hover:bg-muted/50 disabled:opacity-50"
              >
                {busy === "xlsx" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSpreadsheet className="h-4 w-4" />}
                Download Excel
              </button>
            </div>
          </div>

          {!canDownload ? (
            <Alert variant="warning">
              Re-run a comparison from the upload screen to enable report downloads (the original workbooks are needed to
              generate the file).
            </Alert>
          ) : null}
          {error ? <Alert variant="danger">{error}</Alert> : null}
          {done ? (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              <CheckCircle2 className="h-4 w-4" /> Saved <strong>{done}</strong> to your downloads.
            </div>
          ) : null}

          <div className="rounded-lg border bg-muted/20 p-4 text-sm leading-6">
            <p className="mb-2 font-semibold">What the report contains</p>
            <ul className="list-inside list-disc space-y-1 text-muted-foreground">
              <li>Header — entity &amp; both period labels pulled from the files, anchor basis, prepared-by, run date</li>
              <li>Headline &amp; reconciliation bridge with the compensation vs reimbursement ring-fence</li>
              <li>Headcount, top-5 components and top-5 employees by net impact</li>
              <li>Exceptions requiring attention, and the assurance line</li>
              <li>Excel companion: bridge · component decomposition · employee decomposition · exceptions (each foots to the headline)</li>
            </ul>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preview — {anchor}</CardTitle>
          <CardDescription>The headline figures the report will carry. <Download className="inline h-3.5 w-3.5" /> downloads the full document.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <MetricTile label="Previous" value={inr(rec.total_left)} />
            <MetricTile label="Current" value={inr(rec.total_right)} />
            <MetricTile
              label="Net movement"
              value={inrSigned(rec.delta)}
              tone={rec.delta >= 0 ? "positive" : "negative"}
              sub={rec.total_left !== 0 ? `${pct((rec.delta / Math.abs(rec.total_left)) * 100)} vs previous` : undefined}
            />
          </div>
          <p className="rounded-md border bg-muted/30 px-4 py-3 text-sm leading-6">
            {anchor} moved <strong>{inrSigned(rec.delta)}</strong> — <strong>{inrSigned(rec.retained.compensation_delta)}</strong> compensation-cost
            {Math.abs(rec.retained.reimbursement_delta) > 0.5 ? <> and <strong>{inrSigned(rec.retained.reimbursement_delta)}</strong> reimbursement/recovery</> : null}.
            Net movement sits on <strong>{inr(churn)}</strong> of gross component churn.
            {rec.anchor_substituted ? <span className="font-semibold text-amber-700"> Anchor was substituted.</span> : null}
          </p>
          <div className="text-sm">
            {highIssues.length ? (
              <span className="font-medium text-red-700">{highIssues.length} business-impact issue(s) will appear in the exceptions section.</span>
            ) : (
              <span className="font-medium text-emerald-700">No business-impact issues — the report will show a clean bill.</span>
            )}
            {Math.abs(rec.retained.residual) >= 1 ? (
              <span className="ml-2 font-semibold text-red-700">Residual {inrSigned(rec.retained.residual)} — flagged as not fully tying out.</span>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
