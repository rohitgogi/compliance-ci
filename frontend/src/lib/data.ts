import type {
  Contributor,
  CorpusVersion,
  Decision,
  Evaluation,
  FeatureSpec,
  ReevaluationResult,
} from "./types";

const DEFAULT_API_BASE = "http://localhost:8000";
const API_BASE = (process.env.NEXT_PUBLIC_COMPLIANCE_API_URL || DEFAULT_API_BASE).replace(/\/$/, "");

type FeatureWithLatestDecision = FeatureSpec & {
  latest_decision?: Decision;
  latest_risk_score?: number;
  latest_evaluated_at?: string;
  latest_corpus_version?: string;
};

export interface DashboardStats {
  totalFeatures: number;
  passRate: number;
  reviewCount: number;
  failCount: number;
  passCount: number;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getAllFeatures(): Promise<FeatureSpec[]> {
  try {
    const body = await getJson<{ features: FeatureSpec[] }>("/v1/features");
    return body.features ?? [];
  } catch {
    return [];
  }
}

export async function getFeatureById(featureId: string): Promise<FeatureSpec | undefined> {
  try {
    const body = await getJson<{ feature: FeatureSpec }>(`/v1/features/${featureId}`);
    return body.feature;
  } catch {
    return undefined;
  }
}

export async function getAllEvaluations(): Promise<Evaluation[]> {
  try {
    const body = await getJson<{ evaluations: Evaluation[] }>("/v1/evaluations?limit=500");
    return body.evaluations ?? [];
  } catch {
    return [];
  }
}

export async function getEvaluationsByFeature(featureId: string): Promise<Evaluation[]> {
  try {
    const body = await getJson<{ evaluations: Evaluation[] }>(
      `/v1/evaluations?feature_id=${encodeURIComponent(featureId)}&limit=200`
    );
    return body.evaluations ?? [];
  } catch {
    return [];
  }
}

export async function getRecentEvaluations(limit: number = 10): Promise<Evaluation[]> {
  const evaluations = await getAllEvaluations();
  return [...evaluations]
    .sort((a, b) => new Date(b.evaluated_at).getTime() - new Date(a.evaluated_at).getTime())
    .slice(0, limit);
}

export async function getAllCorpusVersions(): Promise<CorpusVersion[]> {
  try {
    const body = await getJson<{ corpus_versions: CorpusVersion[] }>("/v1/corpus-versions?limit=200");
    return body.corpus_versions ?? [];
  } catch {
    return [];
  }
}

export interface CorpusUploadResult {
  version_id: string;
  source_set: string;
  released_at: string;
  chunk_count: number;
  chunk_ids: string[];
}

export async function uploadCorpus(file: File): Promise<CorpusUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE}/v1/corpus-versions/upload`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = err.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d?.msg ?? JSON.stringify(d)).join("; ")
          : JSON.stringify(detail ?? err);
    throw new Error(message);
  }
  return response.json() as Promise<CorpusUploadResult>;
}

export async function getAllReevaluationResults(): Promise<ReevaluationResult[]> {
  try {
    const body = await getJson<{ results: ReevaluationResult[] }>("/v1/reevaluation-results?limit=500");
    return body.results ?? [];
  } catch {
    return [];
  }
}

export async function getRegressions(): Promise<ReevaluationResult[]> {
  try {
    const body = await getJson<{ results: ReevaluationResult[] }>(
      "/v1/reevaluation-results?regressed_only=true&limit=500"
    );
    return body.results ?? [];
  } catch {
    return [];
  }
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const features = await getAllFeatures();
  const total = features.length;
  let pass = 0;
  let review = 0;
  let fail = 0;

  for (const feature of features as FeatureWithLatestDecision[]) {
    if (feature.latest_decision === "PASS") {
      pass += 1;
    } else if (feature.latest_decision === "REVIEW_REQUIRED") {
      review += 1;
    } else if (feature.latest_decision === "FAIL") {
      fail += 1;
    }
  }

  return {
    totalFeatures: total,
    passRate: total > 0 ? Math.round((pass / total) * 100) : 0,
    passCount: pass,
    reviewCount: review,
    failCount: fail,
  };
}

export async function getRiskDistribution(): Promise<{ bucket: string; count: number }[]> {
  const features = (await getAllFeatures()) as FeatureWithLatestDecision[];
  const buckets = [
    { bucket: "0-20", count: 0 },
    { bucket: "21-40", count: 0 },
    { bucket: "41-60", count: 0 },
    { bucket: "61-80", count: 0 },
    { bucket: "81-100", count: 0 },
  ];

  for (const feature of features) {
    const score = feature.latest_risk_score;
    if (score === undefined) {
      continue;
    }
    if (score <= 20) buckets[0].count += 1;
    else if (score <= 40) buckets[1].count += 1;
    else if (score <= 60) buckets[2].count += 1;
    else if (score <= 80) buckets[3].count += 1;
    else buckets[4].count += 1;
  }

  return buckets;
}

export async function getFeaturesWithLatestDecision(): Promise<FeatureWithLatestDecision[]> {
  const features = await getAllFeatures();
  return features as FeatureWithLatestDecision[];
}

export function getContributors(): Contributor[] {
  return [
    { name: "Default", avatar_url: "", commits: 0 },
    { name: "Connect your codebase to get started", avatar_url: "", commits: 0 },
  ];
}
