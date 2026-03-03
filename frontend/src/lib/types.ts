/**
 * TypeScript interfaces mirroring the backend SQLite schema and Pydantic models.
 *
 * Backend source files:
 *   - app/schemas.py        (FeatureComplianceSpec, Control)
 *   - app/storage.py        (EvaluationRecord, ComplianceStore tables)
 *   - app/reevaluation.py   (ReevaluationPlan, ReevaluationSummary)
 *   - app/api.py            (EvaluatePRRequest/Response)
 */

// --- Feature Specs (maps to feature_specs table + parsed_payload) ---

export type ControlStatus = "planned" | "implemented" | "verified";

export interface Control {
  id: string;
  description: string;
  status: ControlStatus;
}

export type DataClassification =
  | "public"
  | "internal"
  | "confidential"
  | "restricted";

export type Decision = "PASS" | "REVIEW_REQUIRED" | "FAIL";

export interface FeatureSpec {
  feature_id: string;
  feature_name: string;
  owner_team: string;
  data_classification: DataClassification;
  jurisdictions: string[];
  controls: Control[];
  change_summary: string;
  spec_version: string;
  active: boolean;
  created_at: string;
  path: string;
}

// --- Evaluations (maps to evaluations table) ---

export interface Evaluation {
  feature_id: string;
  spec_version: string;
  corpus_version: string;
  risk_score: number;
  decision: Decision;
  evidence_chunk_ids: string[];
  reasoning_summary: string;
  commit_sha: string;
  evaluated_at: string;
  // Mock-only fields — TODO: requires backend schema extension to persist
  pr_number?: number;
  lines_added?: number;
  lines_deleted?: number;
  modified_files?: ModifiedFile[];
  field_diffs?: FieldDiff[];
}

/** Mock field-level diff — TODO: not tracked in backend yet */
export interface FieldDiff {
  field: string;
  old_value: string;
  new_value: string;
}

/** Mock modified file entry — TODO: not tracked in backend yet */
export interface ModifiedFile {
  path: string;
  additions: number;
  deletions: number;
}

// --- Corpus Versions (maps to corpus_versions table) ---

export interface CorpusVersion {
  version_id: string;
  source_set: string;
  released_at: string;
}

// --- Reevaluation Results (maps to reevaluation_results table) ---

export interface ReevaluationResult {
  job_id: string;
  feature_id: string;
  previous_decision: string;
  new_decision: string;
  regressed: boolean;
  details: {
    risk_score?: number;
    target_decision?: string;
    error?: string;
  };
  created_at: string;
}

// --- Reevaluation Jobs (maps to reevaluation_jobs table) ---

export interface ReevaluationJob {
  job_id: string;
  target_corpus_version: string;
  scope: string[];
  status: "pending" | "running" | "completed" | "completed_with_errors";
  success_count: number;
  failure_count: number;
  error_summary: string | null;
  created_at: string;
  updated_at: string;
}

// --- Mock-only: Contributors — TODO: replace with GitHub API ---

export interface Contributor {
  name: string;
  avatar_url: string;
  commits: number;
}
