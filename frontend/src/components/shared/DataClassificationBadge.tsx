import type { DataClassification } from "@/lib/types";

const styles: Record<DataClassification, string> = {
  public: "bg-blue-500/10 text-blue-500 dark:text-blue-400 border-blue-500/15",
  internal: "bg-slate-500/10 text-slate-500 dark:text-slate-400 border-slate-500/15",
  confidential: "bg-amber-500/10 text-amber-500 dark:text-amber-400 border-amber-500/15",
  restricted: "bg-red-500/10 text-red-500 dark:text-red-400 border-red-500/15",
};

interface DataClassificationBadgeProps {
  classification: DataClassification;
}

export default function DataClassificationBadge({ classification }: DataClassificationBadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-[1px] text-[10px] font-semibold rounded border capitalize ${styles[classification]}`}
    >
      {classification}
    </span>
  );
}
