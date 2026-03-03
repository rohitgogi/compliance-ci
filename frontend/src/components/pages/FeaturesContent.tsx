"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getFeaturesWithLatestDecision } from "@/lib/data";
import StatusBadge from "@/components/shared/StatusBadge";
import DataClassificationBadge from "@/components/shared/DataClassificationBadge";
import JurisdictionTags from "@/components/shared/JurisdictionTags";
import { formatDate, riskScoreColor } from "@/lib/utils";
import type { Decision, FeatureSpec } from "@/lib/types";

type FeatureWithLatestDecision = FeatureSpec & {
  latest_decision?: Decision;
  latest_risk_score?: number;
  latest_evaluated_at?: string;
  latest_corpus_version?: string;
};

const borderColor: Record<Decision, string> = {
  PASS: "border-l-status-pass",
  REVIEW_REQUIRED: "border-l-status-review",
  FAIL: "border-l-status-fail",
};

const barColor: Record<Decision, string> = {
  PASS: "bg-status-pass",
  REVIEW_REQUIRED: "bg-status-review",
  FAIL: "bg-status-fail",
};

export default function FeaturesContent() {
  const [features, setFeatures] = useState<FeatureWithLatestDecision[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next = await getFeaturesWithLatestDecision();
      if (!cancelled) {
        setFeatures(next);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-6 max-w-[1200px] animate-fade-in">
      <div>
        <h1 className="text-xl font-semibold text-text-light-primary dark:text-text-primary">Features</h1>
        <p className="text-[13px] text-text-light-secondary dark:text-text-secondary mt-0.5">
          {features.length} tracked feature compliance specs
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {features.map((f, i) => {
          const decision = f.latest_decision;
          const leftBorder = decision ? borderColor[decision] : "border-l-border-light dark:border-l-border-dark";

          return (
            <Link
              key={f.feature_id}
              href={`/features/${f.feature_id}`}
              className={`group card-hover border-l-[3px] ${leftBorder} p-4 animate-slide-up`}
              style={{ animationDelay: `${i * 50}ms`, animationFillMode: "backwards" }}
            >
              <div className="flex items-start justify-between gap-2 mb-2.5">
                <div className="min-w-0">
                  <h3 className="text-[13px] font-semibold text-text-light-primary dark:text-text-primary group-hover:text-accent dark:group-hover:text-accent-secondary transition-colors truncate">
                    {f.feature_name}
                  </h3>
                  <p className="text-[11px] text-text-light-muted dark:text-text-muted mt-0.5">{f.owner_team}</p>
                </div>
                {decision && <StatusBadge decision={decision} />}
              </div>

              <div className="flex items-center gap-1.5 mb-3">
                <DataClassificationBadge classification={f.data_classification} />
                <JurisdictionTags jurisdictions={f.jurisdictions} max={3} />
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-border-light dark:border-border-dark">
                {f.latest_risk_score !== undefined ? (
                  <div className="flex items-center gap-2.5">
                    <span className={`text-lg font-bold tabular-nums leading-none ${riskScoreColor(f.latest_risk_score)}`}>
                      {f.latest_risk_score}
                    </span>
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[9px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Risk</span>
                      <div className="w-12 h-1 rounded-full bg-border-light dark:bg-white/6 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ${decision ? barColor[decision] : "bg-accent"}`}
                          style={{ width: `${Math.min(f.latest_risk_score, 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ) : (
                  <span className="text-[11px] text-text-light-muted dark:text-text-muted">No evaluations</span>
                )}
                {f.latest_evaluated_at && (
                  <span className="text-[11px] text-text-light-muted dark:text-text-muted">{formatDate(f.latest_evaluated_at)}</span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
