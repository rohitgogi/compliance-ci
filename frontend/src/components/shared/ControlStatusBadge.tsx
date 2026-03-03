import type { ControlStatus } from "@/lib/types";

const styles: Record<ControlStatus, { bg: string; dot: string }> = {
  planned: { bg: "bg-slate-500/10 text-slate-500 dark:text-slate-400", dot: "bg-slate-400" },
  implemented: { bg: "bg-blue-500/10 text-blue-500 dark:text-blue-400", dot: "bg-blue-400" },
  verified: { bg: "bg-status-pass-dim text-status-pass", dot: "bg-status-pass" },
};

interface ControlStatusBadgeProps {
  status: ControlStatus;
}

export default function ControlStatusBadge({ status }: ControlStatusBadgeProps) {
  const s = styles[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-[3px] text-[11px] font-semibold rounded-md capitalize ${s.bg}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {status}
    </span>
  );
}
