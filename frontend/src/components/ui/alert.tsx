import * as React from "react";
import { cn } from "../../lib/utils";

type AlertProps = React.HTMLAttributes<HTMLDivElement> & {
  variant?: "default" | "danger" | "warning";
};

export function Alert({ className, variant = "default", ...props }: AlertProps) {
  const variants = {
    default: "border-slate-200 bg-white",
    danger: "border-red-200 border-l-red-600 bg-red-50",
    warning: "border-amber-200 border-l-amber-500 bg-amber-50"
  };
  return <div className={cn("rounded-lg border border-l-4 p-4 text-sm leading-6", variants[variant], className)} {...props} />;
}
