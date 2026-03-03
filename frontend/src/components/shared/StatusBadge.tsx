import type { Decision } from "@/lib/types";
import { decisionLabel } from "@/lib/utils";

interface StatusBadgeProps {
  decision: Decision;
  size?: "sm" | "md";
}

const styles: Record<Decision, string> = {
  PASS: "bg-status-pass-dim text-status-pass border-status-pass/20",
  REVIEW_REQUIRED: "bg-status-review-dim text-status-review border-status-review/20",
  FAIL: "bg-status-fail-dim text-status-fail border-status-fail/20",
};

export default function StatusBadge({ decision, size = "sm" }: StatusBadgeProps) {
  const sizeClasses = size === "sm"
    ? "px-2 py-[2px] text-[11px] gap-1"
    : "px-2.5 py-1 text-[12px] gap-1.5";

  return (
    <span className={`inline-flex items-center font-semibold rounded-md border ${sizeClasses} ${styles[decision]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${
        decision === "PASS" ? "bg-status-pass" : decision === "FAIL" ? "bg-status-fail" : "bg-status-review"
      }`} />
      {decisionLabel(decision)}
    </span>
  );
}
