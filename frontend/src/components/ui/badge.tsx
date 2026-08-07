import * as React from "react";
import { cn } from "../../lib/utils";

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "muted" | "danger" | "success" | "warning";
};

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variants = {
    default: "bg-primary text-primary-foreground",
    muted: "bg-muted text-muted-foreground",
    danger: "bg-red-50 text-red-800 ring-1 ring-red-200",
    success: "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200",
    warning: "bg-amber-50 text-amber-900 ring-1 ring-amber-200"
  };
  return (
    <span
      className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium", variants[variant], className)}
      {...props}
    />
  );
}
