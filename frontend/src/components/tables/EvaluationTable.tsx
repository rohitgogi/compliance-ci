"use client";

import Link from "next/link";
import type { Evaluation } from "@/lib/types";
import StatusBadge from "@/components/shared/StatusBadge";
import { formatDate, truncateSha, riskScoreColor } from "@/lib/utils";

interface EvaluationTableProps {
  evaluations: Evaluation[];
  showFeature?: boolean;
}

export default function EvaluationTable({ evaluations, showFeature = true }: EvaluationTableProps) {
  if (evaluations.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-[13px] text-text-light-muted dark:text-text-muted">
        No evaluations found
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-border-light dark:border-border-dark">
            <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Date</th>
            {showFeature && (
              <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Feature</th>
            )}
            <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Commit</th>
            <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">PR</th>
            <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Decision</th>
            <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Risk</th>
            <th className="text-left py-2.5 px-4 text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Corpus</th>
          </tr>
        </thead>
        <tbody>
          {evaluations.map((ev, i) => (
            <tr
              key={`${ev.feature_id}-${ev.commit_sha}-${i}`}
              className="border-b border-border-light dark:border-border-dark last:border-b-0 hover:bg-bg-light-hover dark:hover:bg-bg-hover transition-colors"
            >
              <td className="py-2.5 px-4 text-text-light-secondary dark:text-text-secondary whitespace-nowrap">
                {formatDate(ev.evaluated_at)}
              </td>
              {showFeature && (
                <td className="py-2.5 px-4">
                  <Link
                    href={`/features/${ev.feature_id}`}
                    className="font-medium text-accent dark:text-accent-secondary hover:underline"
                  >
                    {ev.feature_id}
                  </Link>
                </td>
              )}
              <td className="py-2.5 px-4 mono text-[12px] text-text-light-muted dark:text-text-muted">
                {truncateSha(ev.commit_sha)}
              </td>
              <td className="py-2.5 px-4 text-text-light-secondary dark:text-text-secondary">
                {/* TODO: pr_number requires backend schema extension */}
                {ev.pr_number ? `#${ev.pr_number}` : "—"}
              </td>
              <td className="py-2.5 px-4">
                <StatusBadge decision={ev.decision} />
              </td>
              <td className={`py-2.5 px-4 font-bold tabular-nums ${riskScoreColor(ev.risk_score)}`}>
                {ev.risk_score}
              </td>
              <td className="py-2.5 px-4 mono text-[11px] text-text-light-muted dark:text-text-muted whitespace-nowrap">
                {ev.corpus_version}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
