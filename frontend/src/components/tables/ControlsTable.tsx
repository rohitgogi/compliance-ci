import type { Control } from "@/lib/types";
import ControlStatusBadge from "@/components/shared/ControlStatusBadge";

interface ControlsTableProps {
  controls: Control[];
}

export default function ControlsTable({ controls }: ControlsTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-border-light dark:border-border-dark">
            <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted w-[140px]">ID</th>
            <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Description</th>
            <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted w-[130px]">Status</th>
          </tr>
        </thead>
        <tbody>
          {controls.map((ctrl) => (
            <tr
              key={ctrl.id}
              className="border-b border-border-light dark:border-border-dark last:border-b-0 hover:bg-bg-light-hover dark:hover:bg-bg-hover transition-colors"
            >
              <td className="py-2.5 px-4 mono text-[12px] text-text-light-muted dark:text-text-muted">
                {ctrl.id}
              </td>
              <td className="py-2.5 px-4 text-text-light-primary dark:text-text-primary leading-snug">
                {ctrl.description}
              </td>
              <td className="py-2.5 px-4">
                <ControlStatusBadge status={ctrl.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
