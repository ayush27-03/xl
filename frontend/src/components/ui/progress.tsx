import { cn } from "../../lib/utils";

export function Progress({ value, className }: { value: number; className?: string }) {
  const safe = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("h-2 overflow-hidden rounded-full bg-muted", className)}>
      <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${safe}%` }} />
    </div>
  );
}
