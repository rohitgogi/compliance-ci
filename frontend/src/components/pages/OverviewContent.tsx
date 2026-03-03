"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getAllFeatures,
  getAllEvaluations,
  getDashboardStats,
  getRegressions,
  getRiskDistribution,
  type DashboardStats,
} from "@/lib/data";
import RiskDistributionChart from "@/components/charts/RiskDistributionChart";
import GitBranchTimeline from "@/components/charts/GitBranchTimeline";
import EvaluationTable from "@/components/tables/EvaluationTable";
import StatusBadge from "@/components/shared/StatusBadge";
import type { Decision, Evaluation, ReevaluationResult } from "@/lib/types";

export default function OverviewContent() {
  const [stats, setStats] = useState<DashboardStats>({
    totalFeatures: 0,
    passRate: 0,
    reviewCount: 0,
    failCount: 0,
    passCount: 0,
  });
  const [riskData, setRiskData] = useState<{ bucket: string; count: number }[]>([
    { bucket: "0-20", count: 0 },
    { bucket: "21-40", count: 0 },
    { bucket: "41-60", count: 0 },
    { bucket: "61-80", count: 0 },
    { bucket: "81-100", count: 0 },
  ]);
  const [recentEvals, setRecentEvals] = useState<Evaluation[]>([]);
  const [allEvaluations, setAllEvaluations] = useState<Evaluation[]>([]);
  const [regressions, setRegressions] = useState<ReevaluationResult[]>([]);
  const [featureNameById, setFeatureNameById] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const [nextStats, nextRisk, nextEvaluations, nextRegressions, features] = await Promise.all([
        getDashboardStats(),
        getRiskDistribution(),
        getAllEvaluations(),
        getRegressions(),
        getAllFeatures(),
      ]);
      if (cancelled) {
        return;
      }
      setStats(nextStats);
      setRiskData(nextRisk);
      setAllEvaluations(nextEvaluations);
      setRecentEvals(nextEvaluations.slice(0, 8));
      setRegressions(nextRegressions);
      setFeatureNameById(
        Object.fromEntries(features.map((feature) => [feature.feature_id, feature.feature_name]))
      );
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const statCards = [
    {
      label: "Total Features",
      value: stats.totalFeatures,
      accent: "border-l-accent",
      icon: (
        <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
        </svg>
      ),
    },
    {
      label: "Pass Rate",
      value: `${stats.passRate}%`,
      accent: "border-l-status-pass",
      valueColor: "text-status-pass",
      icon: (
        <svg className="w-4 h-4 text-status-pass" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
        </svg>
      ),
    },
    {
      label: "Review Required",
      value: stats.reviewCount,
      accent: "border-l-status-review",
      valueColor: "text-status-review",
      icon: (
        <svg className="w-4 h-4 text-status-review" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
        </svg>
      ),
    },
    {
      label: "Failed",
      value: stats.failCount,
      accent: "border-l-status-fail",
      valueColor: "text-status-fail",
      icon: (
        <svg className="w-4 h-4 text-status-fail" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
        </svg>
      ),
    },
  ];

  return (
    <div className="space-y-5 max-w-[1200px] animate-fade-in">
      <div>
        <h1 className="text-lg font-semibold text-text-light-primary dark:text-text-primary">Overview</h1>
        <p className="text-[12px] text-text-light-secondary dark:text-text-secondary mt-0.5">
          Compliance evaluation status across all tracked features
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {statCards.map((card, i) => (
          <div
            key={card.label}
            className={`card border-l-[3px] ${card.accent} px-4 py-3.5 animate-slide-up`}
            style={{ animationDelay: `${i * 50}ms`, animationFillMode: "backwards" }}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">
                {card.label}
              </span>
              {card.icon}
            </div>
            <p className={`text-2xl font-bold tabular-nums leading-none ${card.valueColor ?? "text-text-light-primary dark:text-text-primary"}`}>
              {card.value}
            </p>
          </div>
        ))}
      </div>

      {/* Git Branch Timeline */}
      <div className="card p-4 animate-slide-up" style={{ animationDelay: "200ms", animationFillMode: "backwards", overflow: "visible" }}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="section-title">PR Evaluation Timeline</h2>
          <div className="flex items-center gap-3 text-[10px] text-text-light-muted dark:text-text-muted">
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-status-pass" /> Pass</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-status-review" /> Review</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-status-fail" /> Fail</span>
          </div>
        </div>
        <GitBranchTimeline evaluations={allEvaluations} />
      </div>

      {/* Regression Alerts */}
      {regressions.length > 0 && (
        <div className="card border-l-[3px] border-l-status-fail px-4 py-3.5 animate-slide-up" style={{ animationDelay: "260ms", animationFillMode: "backwards" }}>
          <div className="flex items-center gap-2.5 mb-3">
            <div className="relative flex items-center justify-center">
              <span className="absolute w-5 h-5 rounded-full bg-status-fail/20 animate-pulse-subtle" />
              <svg className="relative w-4 h-4 text-status-fail" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
              </svg>
            </div>
            <h2 className="text-[13px] font-semibold text-status-fail">
              {regressions.length} Regression{regressions.length > 1 ? "s" : ""} Detected
            </h2>
            <span className="text-[10px] text-text-light-muted dark:text-text-muted ml-auto">Latest corpus update</span>
          </div>
          <div className="space-y-1">
            {regressions.map((r) => {
              return (
                <Link
                  key={`${r.job_id}-${r.feature_id}`}
                  href={`/features/${r.feature_id}`}
                  className="flex items-center gap-3 px-3 py-2 -mx-1 rounded-lg text-[12px] hover:bg-status-fail-dim transition-colors"
                >
                  <span className="font-medium text-text-light-primary dark:text-text-primary min-w-[140px]">
                    {featureNameById[r.feature_id] ?? r.feature_id}
                  </span>
                  <StatusBadge decision={r.previous_decision as Decision} size="sm" />
                  <svg className="w-3 h-3 text-text-light-muted dark:text-text-muted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
                  </svg>
                  <StatusBadge decision={r.new_decision as Decision} size="sm" />
                  {r.details.risk_score !== undefined && (
                    <span className="text-[10px] text-text-light-muted dark:text-text-muted tabular-nums ml-auto">Risk {r.details.risk_score}</span>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Two-column: Recent Evaluations + Risk Distribution */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <div className="xl:col-span-2 card overflow-hidden animate-slide-up" style={{ animationDelay: "320ms", animationFillMode: "backwards" }}>
          <div className="flex items-center justify-between px-4 py-3 border-b border-border-light dark:border-border-dark">
            <h2 className="text-[12px] font-semibold text-text-light-primary dark:text-text-primary">Recent Evaluations</h2>
            <Link href="/evaluations" className="text-[10px] font-medium text-accent dark:text-accent-secondary hover:underline">View all</Link>
          </div>
          <EvaluationTable evaluations={recentEvals} />
        </div>

        <div className="card p-4 animate-slide-up" style={{ animationDelay: "380ms", animationFillMode: "backwards" }}>
          <h2 className="text-[12px] font-semibold text-text-light-primary dark:text-text-primary mb-4">Risk Distribution</h2>
          <RiskDistributionChart data={riskData} />
          <div className="mt-4 flex items-center justify-center gap-4 text-[10px] text-text-light-muted dark:text-text-muted">
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-status-pass" /> Low</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-status-review" /> Medium</span>
            <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-status-fail" /> High</span>
          </div>
        </div>
      </div>
    </div>
  );
}
