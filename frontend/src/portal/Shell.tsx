import { useState } from "react";
import {
  BarChart3,
  Building2,
  FileText,
  GitCompareArrows,
  LayoutDashboard,
  Layers,
  Printer,
  RefreshCw,
  ShieldCheck,
  Users
} from "lucide-react";
import type { AnalysisResponse } from "../lib/types";
import type { EmployeeFilter, PortalModel } from "../lib/analytics";
import { Dashboard } from "../screens/Dashboard";
import { Employees } from "../screens/Employees";
import { Components } from "../screens/Components";
import { Organization } from "../screens/Organization";
import { DataQuality } from "../screens/DataQuality";
import { Reports } from "../screens/Reports";
import { cn } from "../lib/utils";

type View = "dashboard" | "employees" | "components" | "organization" | "reports" | "quality";

const NAV: { id: View | string; label: string; icon: typeof Users; ready: boolean }[] = [
  { id: "dashboard", label: "Executive Dashboard", icon: LayoutDashboard, ready: true },
  { id: "employees", label: "Employees", icon: Users, ready: true },
  { id: "components", label: "Components", icon: Layers, ready: true },
  { id: "organization", label: "Organization", icon: Building2, ready: true },
  { id: "reports", label: "Reports", icon: FileText, ready: true },
  { id: "change", label: "Change Intelligence", icon: GitCompareArrows, ready: false },
  { id: "analytics", label: "Deep Analytics", icon: BarChart3, ready: false },
  { id: "quality", label: "Data Quality", icon: ShieldCheck, ready: true }
];

const TITLES: Record<View, string> = {
  dashboard: "Executive Dashboard",
  employees: "Employees",
  components: "Component Analytics",
  organization: "Organization",
  reports: "Report Center",
  quality: "Data Quality"
};

const ANCHORS = ["Net Payable", "Gross Earnings", "Net Pay"];

interface Props {
  response: AnalysisResponse;
  model: PortalModel;
  anchor: string;
  files: { left: File | null; right: File | null };
  onAnchorChange: (anchor: string) => void;
  onReset: () => void;
}

export function Shell({ response, model, anchor, files, onAnchorChange, onReset }: Props) {
  const [view, setView] = useState<View>("dashboard");
  const [focusId, setFocusId] = useState<string | null>(null);
  const [filter, setFilter] = useState<EmployeeFilter | undefined>(undefined);

  const openEmployee = (id: string) => {
    setFocusId(id);
    setFilter(undefined);
    setView("employees");
  };
  const viewEmployees = (next?: EmployeeFilter) => {
    setFocusId(null);
    // New object identity each time so Employees' sync effect re-applies it.
    setFilter(next ? { ...next } : {});
    setView("employees");
  };

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar */}
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r bg-[#0f2f4c] text-slate-100 md:flex print:hidden">
        <div className="flex items-center gap-2 border-b border-white/10 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent text-sm font-bold">₹</div>
          <div>
            <div className="text-sm font-semibold leading-tight">Payroll Intelligence</div>
            <div className="text-xs text-slate-400">Reconciliation portal</div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = view === item.id;
            return (
              <button
                key={item.id}
                disabled={!item.ready}
                onClick={() => item.ready && setView(item.id as View)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active ? "bg-white/15 font-semibold" : "text-slate-300 hover:bg-white/10",
                  !item.ready && "cursor-not-allowed opacity-40 hover:bg-transparent"
                )}
              >
                <Icon className="h-4 w-4" />
                <span className="flex-1 text-left">{item.label}</span>
                {!item.ready ? <span className="text-[10px] uppercase text-slate-400">soon</span> : null}
              </button>
            );
          })}
        </nav>
        <div className="border-t border-white/10 px-5 py-3 text-xs text-slate-400">
          Local · offline · engine {response.metadata.engine_version}
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b bg-card/95 px-5 py-3 backdrop-blur print:hidden">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-medium">
              <span className="truncate max-w-[180px]" title={response.metadata.left_filename}>
                {response.metadata.left_filename}
              </span>
              <span className="text-muted-foreground">→</span>
              <span className="truncate max-w-[180px]" title={response.metadata.right_filename}>
                {response.metadata.right_filename}
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              {model.employees.length} employees · keyed on {model.keyColumn ?? "position"}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              Headline
              <select
                value={anchor}
                onChange={(e) => onAnchorChange(e.target.value)}
                className="h-9 rounded-md border bg-white px-2 text-sm text-foreground"
              >
                {ANCHORS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </label>
            <button
              onClick={() => setView("reports")}
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium hover:bg-muted/50"
            >
              <Printer className="h-4 w-4" /> Report
            </button>
            <button
              onClick={onReset}
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium hover:bg-muted/50"
            >
              <RefreshCw className="h-4 w-4" /> New
            </button>
          </div>
        </header>

        {/* Below md the sidebar is hidden, so nav lives here. */}
        <nav className="flex gap-1 overflow-x-auto border-b bg-card px-3 py-2 md:hidden print:hidden">
          {NAV.filter((n) => n.ready).map((item) => {
            const Icon = item.icon;
            const active = view === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setView(item.id as View)}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium",
                  active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {item.label}
              </button>
            );
          })}
        </nav>

        <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 md:px-6">
          <div className="mb-4 print:hidden">
            <h1 className="text-xl font-semibold">{TITLES[view]}</h1>
          </div>
          {view === "dashboard" ? (
            <Dashboard
              model={model}
              filenames={{ left: response.metadata.left_filename, right: response.metadata.right_filename }}
              onOpenEmployee={openEmployee}
              onViewEmployees={viewEmployees}
            />
          ) : view === "components" ? (
            <Components model={model} onOpenEmployee={openEmployee} onViewEmployees={viewEmployees} />
          ) : view === "organization" ? (
            <Organization model={model} onViewEmployees={viewEmployees} />
          ) : view === "reports" ? (
            <Reports model={model} files={files} anchor={anchor} />
          ) : view === "quality" ? (
            <DataQuality
              model={model}
              warnings={response.analysis.warnings}
              onOpenEmployee={openEmployee}
              onViewEmployees={viewEmployees}
            />
          ) : (
            <Employees model={model} focusId={focusId} filter={filter} />
          )}
        </main>
      </div>
    </div>
  );
}
