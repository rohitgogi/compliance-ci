"use client";

import { useState, useMemo } from "react";
import { getAllEvaluations } from "@/lib/mock";
import EvaluationTable from "@/components/tables/EvaluationTable";
import type { Decision } from "@/lib/types";

const allEvaluations = getAllEvaluations();

type SortField = "evaluated_at" | "risk_score" | "feature_id" | "decision";
type SortDir = "asc" | "desc";

export default function EvaluationsContent() {
  const [sortField, setSortField] = useState<SortField>("evaluated_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(() => {
    return [...allEvaluations].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "evaluated_at":
          cmp = new Date(a.evaluated_at).getTime() - new Date(b.evaluated_at).getTime();
          break;
        case "risk_score":
          cmp = a.risk_score - b.risk_score;
          break;
        case "feature_id":
          cmp = a.feature_id.localeCompare(b.feature_id);
          break;
        case "decision": {
          const order: Record<Decision, number> = { PASS: 0, REVIEW_REQUIRED: 1, FAIL: 2 };
          cmp = order[a.decision] - order[b.decision];
          break;
        }
      }
      return sortDir === "desc" ? -cmp : cmp;
    });
  }, [sortField, sortDir]);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const sortOptions: { field: SortField; label: string }[] = [
    { field: "evaluated_at", label: "Date" },
    { field: "risk_score", label: "Risk" },
    { field: "feature_id", label: "Feature" },
    { field: "decision", label: "Decision" },
  ];

  return (
    <div className="space-y-5 max-w-[1200px] animate-fade-in">
      <div>
        <h1 className="text-xl font-semibold text-text-light-primary dark:text-text-primary">Evaluations</h1>
        <p className="text-[13px] text-text-light-secondary dark:text-text-secondary mt-0.5">Global audit log of all compliance evaluations</p>
      </div>

      <div className="flex items-center gap-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted mr-1">Sort</span>
        {sortOptions.map((s) => {
          const active = sortField === s.field;
          return (
            <button
              key={s.field}
              onClick={() => toggleSort(s.field)}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-[12px] font-medium rounded-md border transition-all duration-150 ${
                active
                  ? "bg-accent/10 dark:bg-accent/8 text-accent dark:text-accent-secondary border-accent/20"
                  : "border-transparent text-text-light-muted dark:text-text-muted hover:text-text-light-secondary dark:hover:text-text-secondary hover:bg-bg-light-hover dark:hover:bg-bg-hover"
              }`}
            >
              {s.label}
              {active && (
                <svg className={`w-3 h-3 transition-transform ${sortDir === "asc" ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" />
                </svg>
              )}
            </button>
          );
        })}
      </div>

      <div className="card overflow-hidden">
        <EvaluationTable evaluations={sorted} showFeature={true} />
      </div>

      <p className="text-[11px] text-text-light-muted dark:text-text-muted text-center pb-2">
        {allEvaluations.length} total evaluation records
      </p>
    </div>
  );
}
