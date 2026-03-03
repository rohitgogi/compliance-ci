/**
 * Mock data access layer.
 *
 * Each function below reads from static JSON files that mirror the backend
 * SQLite schema. When real APIs are available, replace the JSON imports with
 * fetch() calls to the backend endpoints listed in the comments.
 *
 * Backend API base: POST /v1/evaluate-pr (see backend/app/api.py)
 * Future read endpoints TBD — the backend currently only has a write path.
 */

import type {
  FeatureSpec,
  Evaluation,
  CorpusVersion,
  ReevaluationResult,
  Contributor,
  Decision,
} from "./types";

import featuresData from "@/data/features.json";
import evaluationsData from "@/data/evaluations.json";
import corpusVersionsData from "@/data/corpus-versions.json";
import reevaluationResultsData from "@/data/reevaluation-results.json";

// --- Features ---
// TODO: Replace with GET /v1/features when backend read API exists

export function getAllFeatures(): FeatureSpec[] {
  return featuresData as FeatureSpec[];
}

export function getFeatureById(featureId: string): FeatureSpec | undefined {
  return (featuresData as FeatureSpec[]).find(
    (f) => f.feature_id === featureId
  );
}

// --- Evaluations ---
// TODO: Replace with GET /v1/evaluations when backend read API exists

export function getAllEvaluations(): Evaluation[] {
  return evaluationsData as Evaluation[];
}

export function getEvaluationsByFeature(featureId: string): Evaluation[] {
  return (evaluationsData as Evaluation[]).filter(
    (e) => e.feature_id === featureId
  );
}

export function getLatestEvaluation(
  featureId: string
): Evaluation | undefined {
  const evals = getEvaluationsByFeature(featureId);
  return evals.length > 0 ? evals[0] : undefined;
}

export function getRecentEvaluations(limit: number = 10): Evaluation[] {
  return [...(evaluationsData as Evaluation[])]
    .sort(
      (a, b) =>
        new Date(b.evaluated_at).getTime() -
        new Date(a.evaluated_at).getTime()
    )
    .slice(0, limit);
}

// --- Corpus Versions ---
// TODO: Replace with GET /v1/corpus-versions when backend read API exists

export function getAllCorpusVersions(): CorpusVersion[] {
  return corpusVersionsData as CorpusVersion[];
}

// --- Reevaluation Results ---
// TODO: Replace with GET /v1/reevaluation-results when backend read API exists

export function getAllReevaluationResults(): ReevaluationResult[] {
  return reevaluationResultsData as ReevaluationResult[];
}

export function getRegressions(): ReevaluationResult[] {
  return (reevaluationResultsData as ReevaluationResult[]).filter(
    (r) => r.regressed
  );
}

// --- Aggregate Stats (computed from mock data) ---
// TODO: Replace with GET /v1/dashboard/stats when backend provides aggregations

export interface DashboardStats {
  totalFeatures: number;
  passRate: number;
  reviewCount: number;
  failCount: number;
  passCount: number;
}

export function getDashboardStats(): DashboardStats {
  const features = getAllFeatures();
  const total = features.length;
  let pass = 0;
  let review = 0;
  let fail = 0;

  for (const f of features) {
    const latest = getLatestEvaluation(f.feature_id);
    if (!latest) continue;
    if (latest.decision === "PASS") pass++;
    else if (latest.decision === "REVIEW_REQUIRED") review++;
    else if (latest.decision === "FAIL") fail++;
  }

  return {
    totalFeatures: total,
    passRate: total > 0 ? Math.round((pass / total) * 100) : 0,
    passCount: pass,
    reviewCount: review,
    failCount: fail,
  };
}

export function getRiskDistribution(): { bucket: string; count: number }[] {
  const features = getAllFeatures();
  const buckets = [
    { bucket: "0-20", count: 0 },
    { bucket: "21-40", count: 0 },
    { bucket: "41-60", count: 0 },
    { bucket: "61-80", count: 0 },
    { bucket: "81-100", count: 0 },
  ];

  for (const f of features) {
    const latest = getLatestEvaluation(f.feature_id);
    if (!latest) continue;
    const score = latest.risk_score;
    if (score <= 20) buckets[0].count++;
    else if (score <= 40) buckets[1].count++;
    else if (score <= 60) buckets[2].count++;
    else if (score <= 80) buckets[3].count++;
    else buckets[4].count++;
  }

  return buckets;
}

// --- Feature list with latest decision merged ---

export interface FeatureWithLatestDecision extends FeatureSpec {
  latest_decision?: Decision;
  latest_risk_score?: number;
  latest_evaluated_at?: string;
  latest_corpus_version?: string;
}

export function getFeaturesWithLatestDecision(): FeatureWithLatestDecision[] {
  return getAllFeatures().map((f) => {
    const latest = getLatestEvaluation(f.feature_id);
    return {
      ...f,
      latest_decision: latest?.decision,
      latest_risk_score: latest?.risk_score,
      latest_evaluated_at: latest?.evaluated_at,
      latest_corpus_version: latest?.corpus_version,
    };
  });
}

// --- Mock contributors ---
// TODO: Replace with GitHub API call to /repos/:owner/:repo/contributors

export function getContributors(): Contributor[] {
  return [
    { name: "Sarah Chen", avatar_url: "", commits: 34 },
    { name: "Marcus Williams", avatar_url: "", commits: 28 },
    { name: "Priya Patel", avatar_url: "", commits: 22 },
    { name: "James O'Brien", avatar_url: "", commits: 15 },
    { name: "Yuki Tanaka", avatar_url: "", commits: 11 },
  ];
}
