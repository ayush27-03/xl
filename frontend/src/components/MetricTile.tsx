import type { ReactNode } from "react";
import { cn } from "../lib/utils";

interface MetricTileProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "positive" | "negative" | "neutral";
  onClick?: () => void;
  hint?: string;
}

const toneClass: Record<string, string> = {
  default: "text-foreground",
  positive: "text-emerald-700",
  negative: "text-red-700",
  neutral: "text-slate-600"
};

export function MetricTile({ label, value, sub, tone = "default", onClick, hint }: MetricTileProps) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      onClick={onClick}
      title={hint}
      className={cn(
        "flex w-full flex-col rounded-lg border bg-card p-4 text-left shadow-soft",
        onClick && "cursor-pointer transition-colors hover:border-accent/60 hover:bg-muted/30"
      )}
    >
      <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className={cn("mt-2 text-2xl font-semibold tabular-nums", toneClass[tone])}>{value}</span>
      {sub ? <span className="mt-1 text-sm text-muted-foreground">{sub}</span> : null}
    </Comp>
  );
}
