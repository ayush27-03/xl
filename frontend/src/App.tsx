import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { FileSpreadsheet, Loader2, ShieldCheck, UploadCloud } from "lucide-react";
import { compareWorkbooks, type CompareProgress } from "./lib/api";
import { buildModel } from "./lib/analytics";
import type { AnalysisResponse } from "./lib/types";
import { Alert } from "./components/ui/alert";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./components/ui/card";
import { Progress } from "./components/ui/progress";
import { Shell } from "./portal/Shell";

type Slot = "left" | "right";

function FileSlot({ label, hint, file, onFile }: { label: string; hint: string; file: File | null; onFile: (f: File | null) => void }) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    multiple: false,
    accept: { "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] },
    onDrop: (files) => onFile(files[0] ?? null)
  });
  return (
    <div
      {...getRootProps()}
      className={[
        "flex min-h-36 cursor-pointer flex-col justify-between rounded-lg border border-dashed bg-white p-4 transition-colors",
        isDragActive ? "border-accent bg-cyan-50" : "hover:border-accent/70"
      ].join(" ")}
    >
      <input {...getInputProps()} />
      <div className="flex items-start gap-3">
        <div className="rounded-md bg-muted p-2 text-accent"><UploadCloud className="h-5 w-5" /></div>
        <div>
          <p className="text-sm font-semibold">{label}</p>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{hint}</p>
        </div>
      </div>
      {file ? (
        <div className="mt-4 flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm">
          <FileSpreadsheet className="h-4 w-4 text-emerald-700" />
          <span className="truncate font-medium">{file.name}</span>
          <button
            className="ml-auto text-muted-foreground hover:text-foreground"
            onClick={(e) => { e.stopPropagation(); onFile(null); }}
          >
            Remove
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function App() {
  const [files, setFiles] = useState<Record<Slot, File | null>>({ left: null, right: null });
  const [anchor, setAnchor] = useState("Net Payable");
  const [progress, setProgress] = useState<CompareProgress>({ phase: "idle", value: 0, label: "Waiting for files" });

  const mutation = useMutation<AnalysisResponse, Error, string | undefined>({
    mutationFn: (overrideAnchor) => {
      if (!files.left || !files.right) throw new Error("Two .xlsx pay runs are required.");
      setProgress({ phase: "uploading", value: 0, label: "Preparing upload" });
      return compareWorkbooks(files.left, files.right, { anchor: overrideAnchor ?? anchor }, setProgress);
    }
  });

  const response = mutation.data;
  const model = useMemo(() => (response ? buildModel(response.analysis) : null), [response]);
  const canCompare = files.left !== null && files.right !== null && !mutation.isPending;

  if (response && model) {
    return (
      <Shell
        response={response}
        model={model}
        anchor={anchor}
        files={files}
        onAnchorChange={(a) => { setAnchor(a); mutation.mutate(a); }}
        onReset={() => { mutation.reset(); setFiles({ left: null, right: null }); }}
      />
    );
  }

  return (
    <main className="mx-auto max-w-4xl space-y-8 px-4 py-10 md:px-8">
      <header className="space-y-3">
        <Badge variant="muted">Local · offline · deterministic</Badge>
        <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">Payroll Reconciliation Portal</h1>
        <p className="max-w-2xl text-base leading-7 text-muted-foreground">
          Upload two pay runs. The portal reconciles previous → current to the rupee — separating real compensation-cost
          movement from reimbursement/recovery noise — and lets you drill from the headline down to any employee's record.
          Your payroll never leaves this machine.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Compare two pay runs</CardTitle>
          <CardDescription>Previous period on the left, current period on the right.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 md:grid-cols-2">
            <FileSlot label="Previous period" hint="Drop the earlier pay run (.xlsx)" file={files.left} onFile={(f) => setFiles((p) => ({ ...p, left: f }))} />
            <FileSlot label="Current period" hint="Drop the current pay run (.xlsx)" file={files.right} onFile={(f) => setFiles((p) => ({ ...p, right: f }))} />
          </div>

          <label className="flex max-w-sm flex-col text-sm font-medium">
            Headline total (reconciliation anchor)
            <select value={anchor} onChange={(e) => setAnchor(e.target.value)} className="mt-2 h-10 rounded-md border bg-white px-3 text-sm">
              <option>Net Payable</option>
              <option>Gross Earnings</option>
              <option>Net Pay</option>
            </select>
            <span className="mt-1 text-xs font-normal text-muted-foreground">
              Net Payable is the cash disbursed. You can switch this later.
            </span>
          </label>

          <div className="flex flex-col gap-4 md:flex-row md:items-center">
            <Button disabled={!canCompare} onClick={() => mutation.mutate(undefined)}>
              {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSpreadsheet className="h-4 w-4" />}
              Reconcile pay runs
            </Button>
            <div className="min-w-0 flex-1">
              <div className="mb-2 flex items-center justify-between text-sm text-muted-foreground">
                <span>{progress.label}</span>
                <span>{progress.value}%</span>
              </div>
              <Progress value={progress.value} />
            </div>
          </div>

          {mutation.error ? <Alert variant="danger">{mutation.error.message}</Alert> : null}
          {response && !model ? (
            <Alert variant="warning">
              These files were compared, but no shared payroll total (e.g. Net Payable) was found, so the reconciliation
              bridge isn't applicable. Check that both files are pay runs with matching total columns.
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <ShieldCheck className="h-4 w-4" /> Files are processed by a loopback-only local engine and are never sent over the network.
      </p>
    </main>
  );
}
