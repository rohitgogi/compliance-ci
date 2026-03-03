"use client";

import { useState } from "react";
import Link from "next/link";
import { getFeatureById, getEvaluationsByFeature, getContributors } from "@/lib/mock";
import StatusBadge from "@/components/shared/StatusBadge";
import RiskGauge from "@/components/shared/RiskGauge";
import DataClassificationBadge from "@/components/shared/DataClassificationBadge";
import JurisdictionTags from "@/components/shared/JurisdictionTags";
import ComplianceTimeline from "@/components/charts/ComplianceTimeline";
import ControlsTable from "@/components/tables/ControlsTable";
import type { Evaluation } from "@/lib/types";
import { formatDate, truncateSha, riskScoreColor } from "@/lib/utils";

export default function FeatureDetailContent({ featureId }: { featureId: string }) {
  const feature = getFeatureById(featureId);
  const evaluations = getEvaluationsByFeature(featureId);
  const contributors = getContributors();
  const [expandedEval, setExpandedEval] = useState<number | null>(null);

  if (!feature) {
    return (
      <div className="flex flex-col items-center justify-center py-24 animate-fade-in">
        <div className="w-12 h-12 rounded-xl bg-bg-light-elevated dark:bg-bg-elevated flex items-center justify-center mb-4">
          <svg className="w-6 h-6 text-text-light-muted dark:text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
          </svg>
        </div>
        <p className="text-[15px] font-medium text-text-light-primary dark:text-text-primary mb-1">Feature not found</p>
        <p className="text-[13px] text-text-light-muted dark:text-text-muted mb-4">No feature with ID &ldquo;{featureId}&rdquo;</p>
        <Link href="/features" className="text-[13px] font-medium text-accent dark:text-accent-secondary hover:underline">
          Back to features
        </Link>
      </div>
    );
  }

  const latestEval = evaluations[0];

  return (
    <div className="space-y-5 max-w-[1200px] animate-fade-in">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-[12px] text-text-light-muted dark:text-text-muted">
        <Link href="/features" className="hover:text-accent dark:hover:text-accent-secondary transition-colors">
          Features
        </Link>
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
        </svg>
        <span className="text-text-light-primary dark:text-text-primary font-medium">{feature.feature_name}</span>
      </div>

      {/* Header Card */}
      <div className="card p-5">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5">
          <div className="space-y-3 min-w-0 flex-1">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-lg font-semibold text-text-light-primary dark:text-text-primary">{feature.feature_name}</h1>
              {latestEval && <StatusBadge decision={latestEval.decision} size="md" />}
            </div>
            <div className="flex items-center gap-2 text-[13px] text-text-light-secondary dark:text-text-secondary">
              <span>{feature.owner_team}</span>
              <span className="text-text-light-muted dark:text-text-muted">/</span>
              <span className="mono text-[12px] text-text-light-muted dark:text-text-muted">{feature.spec_version}</span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <DataClassificationBadge classification={feature.data_classification} />
              <JurisdictionTags jurisdictions={feature.jurisdictions} />
            </div>
            <div className="mt-2 p-3 rounded-lg bg-bg-light-elevated dark:bg-white/3 border border-border-light dark:border-border-dark">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted mb-1.5">Latest Change</p>
              <p className="text-[13px] text-text-light-primary dark:text-text-primary leading-relaxed">{feature.change_summary}</p>
            </div>
          </div>
          {latestEval && (
            <div className="flex items-center gap-6 lg:flex-col lg:items-end lg:gap-4">
              <RiskGauge score={latestEval.risk_score} size={80} strokeWidth={6} />
              <div className="text-right">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted mb-0.5">Corpus Version</p>
                <p className="mono text-[12px] text-text-light-secondary dark:text-text-secondary">{latestEval.corpus_version}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Compliance Timeline */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="section-title">Compliance Timeline</h2>
          <div className="flex items-center gap-3 text-[10px] text-text-light-muted dark:text-text-muted">
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-status-pass" /> Pass</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-status-review" /> Review</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-status-fail" /> Fail</span>
          </div>
        </div>
        <ComplianceTimeline evaluations={evaluations} />
      </div>

      {/* Evaluation History */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-light dark:border-border-dark">
          <h2 className="section-title">Evaluation History</h2>
          <span className="text-[11px] text-text-light-muted dark:text-text-muted">{evaluations.length} records</span>
        </div>
        <div>
          {evaluations.map((ev, i) => (
            <EvalRow
              key={`${ev.commit_sha}-${i}`}
              evaluation={ev}
              isExpanded={expandedEval === i}
              onToggle={() => setExpandedEval(expandedEval === i ? null : i)}
            />
          ))}
          {evaluations.length === 0 && (
            <div className="flex items-center justify-center py-12 text-[13px] text-text-light-muted dark:text-text-muted">
              No evaluations yet
            </div>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-light dark:border-border-dark">
          <h2 className="section-title">Controls</h2>
          <span className="text-[11px] text-text-light-muted dark:text-text-muted">
            {feature.controls.filter((c) => c.status === "verified").length}/{feature.controls.length} verified
          </span>
        </div>
        <ControlsTable controls={feature.controls} />
      </div>

      {/* Contributors */}
      <div className="card p-4">
        <h2 className="section-title mb-3">Contributors</h2>
        <div className="flex items-center gap-4 flex-wrap">
          {contributors.map((c, i) => (
            <div key={c.name} className="flex items-center gap-2.5 animate-scale-in" style={{ animationDelay: `${i * 50}ms`, animationFillMode: "backwards" }}>
              <div className="w-8 h-8 rounded-full bg-accent/15 dark:bg-accent/10 flex items-center justify-center text-[11px] font-bold text-accent dark:text-accent-secondary ring-1 ring-accent/20">
                {c.name.split(" ").map((n) => n[0]).join("")}
              </div>
              <div className="hidden sm:block">
                <p className="text-[12px] font-medium text-text-light-primary dark:text-text-primary leading-tight">{c.name}</p>
                <p className="text-[10px] text-text-light-muted dark:text-text-muted">{c.commits} commits</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function EvalRow({ evaluation, isExpanded, onToggle }: { evaluation: Evaluation; isExpanded: boolean; onToggle: () => void }) {
  return (
    <div className="border-b border-border-light dark:border-border-dark last:border-b-0">
      <button onClick={onToggle} className="w-full flex items-center gap-3 px-4 py-3 text-[13px] hover:bg-bg-light-hover dark:hover:bg-bg-hover transition-colors text-left">
        <svg className={`w-3.5 h-3.5 text-text-light-muted dark:text-text-muted transition-transform duration-200 shrink-0 ${isExpanded ? "rotate-90" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
        </svg>
        <span className="text-text-light-secondary dark:text-text-secondary whitespace-nowrap min-w-[90px]">{formatDate(evaluation.evaluated_at)}</span>
        <span className="mono text-[11px] text-text-light-muted dark:text-text-muted min-w-[60px]">{truncateSha(evaluation.commit_sha)}</span>
        <span className="text-text-light-secondary dark:text-text-secondary min-w-[50px]">{evaluation.pr_number ? `#${evaluation.pr_number}` : "—"}</span>
        <StatusBadge decision={evaluation.decision} />
        <span className={`font-bold tabular-nums min-w-[28px] ${riskScoreColor(evaluation.risk_score)}`}>{evaluation.risk_score}</span>
        <span className="mono text-[11px] text-text-light-muted dark:text-text-muted ml-auto hidden lg:block">{evaluation.corpus_version}</span>
      </button>

      {isExpanded && (
        <div className="px-4 pb-4 pl-11 space-y-3 animate-slide-down">
          <div className="rounded-lg bg-bg-light-elevated dark:bg-white/3 border border-border-light dark:border-border-dark p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted mb-1.5">Reasoning</p>
            <p className="text-[13px] text-text-light-primary dark:text-text-primary leading-relaxed">{evaluation.reasoning_summary}</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {evaluation.evidence_chunk_ids.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted mb-2">Obligations Cited</p>
                <div className="flex flex-wrap gap-1.5">
                  {evaluation.evidence_chunk_ids.map((id) => (
                    <span key={id} className="px-2 py-1 text-[11px] mono rounded-md bg-accent/8 dark:bg-accent/10 text-accent dark:text-accent-secondary border border-accent/15">
                      {id}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {evaluation.field_diffs && evaluation.field_diffs.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted mb-2">Field Changes</p>
                <div className="space-y-1.5">
                  {evaluation.field_diffs.map((diff) => (
                    <div key={diff.field} className="flex items-center gap-2 text-[12px]">
                      <span className="mono text-text-light-muted dark:text-text-muted">{diff.field}</span>
                      <span className="text-status-fail line-through opacity-70">{diff.old_value}</span>
                      <svg className="w-3 h-3 text-text-light-muted dark:text-text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                      </svg>
                      <span className="text-status-pass font-semibold">{diff.new_value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {evaluation.modified_files && evaluation.modified_files.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted mb-2">Modified Files</p>
              <div className="space-y-1">
                {evaluation.modified_files.map((mf) => (
                  <div key={mf.path} className="flex items-center gap-3 text-[12px] py-1">
                    <svg className="w-3.5 h-3.5 text-text-light-muted dark:text-text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
                    </svg>
                    <span className="mono text-text-light-secondary dark:text-text-secondary truncate flex-1">{mf.path}</span>
                    <span className="text-status-pass font-semibold tabular-nums">+{mf.additions}</span>
                    <span className="text-status-fail font-semibold tabular-nums">-{mf.deletions}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
