import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

const colorMap: Record<string, string> = {
  COMPLETED: "bg-emerald-50 text-emerald-600",
  APPROVED: "bg-blue-50 text-blue-600",
  EXECUTING: "bg-sky-50 text-sky-600",
  PENDING: "bg-amber-50 text-amber-600",
  REQUIRE_APPROVAL: "bg-orange-50 text-orange-600",
  BLOCKED: "bg-red-50 text-red-600",
  REJECTED: "bg-red-50 text-red-500",
  FAILED: "bg-red-50 text-red-500",
  ACTIVE: "bg-emerald-50 text-emerald-600",
  SUCCESS: "bg-emerald-50 text-emerald-600",
  default: "bg-neutral-100 text-neutral-500",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  status?: string;
}

export function Badge({ status, className, children, ...props }: BadgeProps) {
  const color = (status && colorMap[status]) || colorMap.default;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium tracking-wide",
        color,
        className
      )}
      {...props}
    >
      {children ?? status}
    </span>
  );
}
