# TODO: Connect Frontend to Backend APIs

This document maps every frontend data need to backend endpoints and implementation tasks. The frontend currently reads from static JSON under `src/data/` via `src/lib/mock.ts`. The backend only exposes **POST /v1/evaluate-pr** and **GET /health**; all read paths must be added.

---

## 1. Frontend Data Consumers (what we need to fill)

| Screen / Component | Data source (mock) | Required shape / fields |
|-------------------|--------------------|--------------------------|
| **Overview** | `getDashboardStats()`, `getRiskDistribution()`, `getRecentEvaluations(8)`, `getRegressions()`, `getFeatureById()` | Stats: totalFeatures, passRate, passCount, reviewCount, failCount. Risk buckets: 0–20, 21–40, … 81–100. Recent evals: full `Evaluation[]`. Regressions: `ReevaluationResult[]` with feature_id, previous_decision, new_decision, details.risk_score. Feature names for regression links. |
| **Features list** | `getFeaturesWithLatestDecision()` | List of features with: FeatureSpec + latest_decision, latest_risk_score, latest_evaluated_at, latest_corpus_version. |
| **Feature detail** | `getFeatureById(id)`, `getEvaluationsByFeature(id)`, `getContributors()` | Single FeatureSpec. Evaluations for that feature (history). Contributors (optional; can stay mock or GitHub API). |
| **Evaluations** | `getAllEvaluations()` | Global list of evaluations (each has feature_id, spec_version, corpus_version, risk_score, decision, evidence_chunk_ids, reasoning_summary, commit_sha, evaluated_at). Optional: pr_number, lines_added/deleted, modified_files, field_diffs. |
| **Corpus** | `getAllCorpusVersions()`, `getAllEvaluations()` | Corpus versions: version_id, source_set, released_at. For each version, evaluations that used it (filter by corpus_version). |
| **Charts** | | |
| – GitBranchTimeline | `getAllEvaluations()` | Same as Evaluations; uses feature_id, evaluated_at, decision, risk_score, commit_sha, pr_number (optional), lines_added/deleted (optional). |
| – ComplianceTimeline | per-feature evaluations | Same Evaluation type. |
| – RiskDistributionChart | `getRiskDistribution()` | Buckets 0–20 … 81–100 with counts (derivable from evaluations). |
| **Tables** | | |
| – EvaluationTable | `Evaluation[]` | Date, feature_id (if showFeature), commit_sha, pr_number, decision, risk_score, corpus_version. |
| **Detail expansion (FeatureDetailContent)** | Per-eval expansion | reasoning_summary, evidence_chunk_ids; optional: field_diffs, modified_files. |

**Backend currently does NOT store:** pr_number, lines_added, lines_deleted, modified_files, field_diffs. The frontend can show "—" or hide those columns when absent; optionally we can add pr_number (and later others) to the backend.

---

## 2. Backend: New Read Endpoints and Storage Methods

### 2.1 GET /v1/features

- **Purpose:** List all active feature specs with latest decision/risk/evaluated_at for the Features list and for dropdowns.
- **Backend work:**
  - **Storage:** Add `list_active_features()` that returns list of dicts: for each active feature (from `list_active_feature_ids()`), call `get_latest_feature_spec(fid)` and merge with `get_latest_evaluation(fid)` to include decision, risk_score, evaluated_at, corpus_version. Or add a single SQL that joins feature_specs (active=1) with a subquery for latest evaluation per feature_id.
  - **API:** New GET handler that returns `{ "features": [ { feature_id, feature_name, owner_team, data_classification, jurisdictions, controls, change_summary, spec_version, path, created_at, latest_decision?, latest_risk_score?, latest_evaluated_at?, latest_corpus_version? } ] }`. Use existing Pydantic/schema types where possible.
- **Response shape:** Array of feature objects matching frontend `FeatureWithLatestDecision` (see `frontend/src/lib/types.ts` and mock `getFeaturesWithLatestDecision()`).

### 2.2 GET /v1/features/:featureId

- **Purpose:** Single feature detail + evaluation history (Feature detail page).
- **Backend work:**
  - **Storage:** Already have `get_latest_feature_spec(feature_id)` and `get_evaluations(feature_id)`.
  - **API:** GET handler that returns 404 if feature not found, else `{ "feature": { ...spec + path, created_at }, "evaluations": [ ... ] }`. Evaluations must include all fields the frontend uses: spec_version, corpus_version, risk_score, decision, evidence_chunk_ids, reasoning_summary, commit_sha, evaluated_at; optionally deterministic_confidence, llm_*, fused_* for future UI.
- **Response shape:** Matches `FeatureSpec` and `Evaluation[]` in frontend types.

### 2.3 GET /v1/evaluations

- **Purpose:** Global audit log (Evaluations page, GitBranchTimeline, Recent Evaluations widget).
- **Backend work:**
  - **Storage:** Add `list_evaluations(limit?: int, offset?: int)` that returns rows from `evaluations` with feature_id (join or ensure feature_id is in SELECT), ordered by evaluated_at DESC. Each row must include feature_id, spec_version, corpus_version, risk_score, decision, evidence_chunk_ids, reasoning_summary, commit_sha, evaluated_at (and optional hybrid fields).
  - **API:** GET handler with optional query params `limit` (default 100), `offset` (default 0), optionally `feature_id` to filter. Return `{ "evaluations": [ ... ], "total": N }` or similar.
- **Response shape:** Array of evaluations; each must have `feature_id` (frontend expects it for links and timeline).

### 2.4 GET /v1/corpus-versions

- **Purpose:** Corpus page: list corpus versions and count of evaluations per version.
- **Backend work:**
  - **Storage:** Add `list_corpus_versions()` that returns all rows from `corpus_versions` (version_id, source_set, released_at) ordered by released_at DESC.
  - **API:** GET handler returning `{ "corpus_versions": [ ... ] }`. Frontend can count evaluations per version by calling GET /v1/evaluations and filtering client-side, or backend can return counts in a separate field (optional).
- **Note:** If DB has no corpus versions yet, either seed a default (e.g. v1) or return empty array; frontend already handles empty.

### 2.5 GET /v1/reevaluation-results

- **Purpose:** Regressions list (Overview), and optionally per-job results.
- **Backend work:**
  - **Storage:** Already have `list_reevaluation_results(job_id)`. Add `list_all_reevaluation_results(regressed_only: bool = False)` that iterates jobs and collects results, or add a new table scan that returns (job_id, feature_id, previous_decision, new_decision, regressed, details, created_at) with optional filter regressed=True.
  - **API:** GET handler with optional query `job_id` (then return results for that job) and/or `regressed_only=true`. Return `{ "results": [ ... ] }` matching frontend `ReevaluationResult[]`.
- **Response shape:** job_id, feature_id, previous_decision, new_decision, regressed, details, created_at.

### 2.6 GET /v1/dashboard/stats (optional)

- **Purpose:** Overview stat cards (total features, pass rate, review count, fail count).
- **Backend work:** Either add a GET endpoint that computes counts from features + latest evaluations, or leave frontend to derive from GET /v1/features (with latest_decision) and GET /v1/evaluations. Prefer deriving on frontend from existing endpoints to avoid duplicate logic; document in frontend that stats are computed from features + latest decision.

### 2.7 Optional: Persist pr_number on evaluations

- **Purpose:** Show PR links in EvaluationTable, GitBranchTimeline, ComplianceTimeline.
- **Backend work:** Add column `pr_number INTEGER` to `evaluations` (migration-safe), extend `EvaluationRecord` and `record_evaluation()`, and set pr_number from `payload.pr_number` in `api.evaluate_pr()`. Then include pr_number in all evaluation read responses.
- **Frontend:** Already uses ev.pr_number when present; show "—" when missing.

### 2.8 Optional: lines_added, lines_deleted, modified_files, field_diffs

- **Purpose:** Nice-to-have in evaluation detail expansion. Not in backend today.
- **Options:** (a) Leave as mock-only and hide in UI when absent. (b) Backend could accept them in evaluate-pr payload (e.g. from GitHub Action) and store in evaluations JSON/details. Defer to a later iteration unless required.

---

## 3. Frontend: API Client and Replace Mock

### 3.1 Environment and API client

- Add `NEXT_PUBLIC_COMPLIANCE_API_URL` (e.g. `http://localhost:8000` for dev). Create `src/lib/api.ts` (or `src/lib/client.ts`) with a base URL and helpers: `getJson<T>(path)`, `getFeatures()`, `getFeatureById(id)`, `getEvaluations(params?)`, `getCorpusVersions()`, `getReevaluationResults(params?)`. Use `fetch` with proper error handling and optional auth headers if needed later.

### 3.2 Data layer swap

- Replace `src/lib/mock.ts` usage with API client calls. Options:
  - **Option A:** New file `src/lib/data.ts` that exports the same function signatures as mock.ts but implemented via fetch to the new GET endpoints. Then replace all `from "@/lib/mock"` with `from "@/lib/data"` (or use an env flag to switch mock vs api).
  - **Option B:** Keep mock.ts for fallback and add `src/lib/api.ts`; in each page/component use a hook or context that chooses mock vs api based on env (e.g. `NEXT_PUBLIC_USE_API=true`).

### 3.3 Response shape alignment

- Ensure backend response types match frontend types (FeatureSpec, Evaluation, CorpusVersion, ReevaluationResult). Add small adapters in the frontend API layer if backend uses different keys (e.g. snake_case vs camelCase). Prefer backend returning snake_case and frontend keeping current types (already snake_case in types.ts).

### 3.4 Loading and error states

- Pages today assume sync data. After switching to fetch:
  - Use React state or SWR/React Query for loading/error. Show skeletons or spinners while loading; show error message and retry on failure.
  - Ensure Overview, Features, Feature detail, Evaluations, and Corpus pages handle loading and error.

### 3.5 Contributors

- `getContributors()` is mock-only. Either keep static mock data for now or add a separate integration (e.g. GitHub API from frontend with token, or backend proxy). Document as out-of-scope for backend compliance APIs; leave as mock unless product requires it.

---

## 4. Checklist Summary (implementation order)

**Backend (recommended order)**

1. [ ] **Storage:** `list_corpus_versions()`.
2. [ ] **Storage:** `list_evaluations(limit, offset, feature_id?)` returning rows with feature_id.
3. [ ] **Storage:** `list_active_features()` (or equivalent) returning features with latest decision/risk/evaluated_at.
4. [ ] **Storage:** `list_all_reevaluation_results(regressed_only?)` or document use of existing `list_reevaluation_results(job_id)` + list jobs.
5. [ ] **API:** GET /v1/corpus-versions.
6. [ ] **API:** GET /v1/evaluations (with limit/offset and optional feature_id).
7. [ ] **API:** GET /v1/features.
8. [ ] **API:** GET /v1/features/:featureId.
9. [ ] **API:** GET /v1/reevaluation-results (with optional job_id, regressed_only).
10. [ ] **Optional:** Add pr_number to evaluations schema and persist in record_evaluation + include in all evaluation responses.

**Frontend**

11. [ ] Add `NEXT_PUBLIC_COMPLIANCE_API_URL` and create `src/lib/api.ts` with getJson and per-resource getters.
12. [ ] Implement data layer (e.g. `src/lib/data.ts`) that calls backend GET endpoints and returns same shapes as current mock.
13. [ ] Replace all `from "@/lib/mock"` imports with the new data layer (or env-based switch).
14. [ ] Add loading and error handling to Overview, Features, Feature detail, Evaluations, Corpus.
15. [ ] Align types: ensure backend JSON matches frontend types (snake_case, optional fields documented).
16. [ ] Leave Contributors as mock unless GitHub integration is added.

**Testing**

17. [ ] Backend: unit tests for new storage methods and GET handlers.
18. [ ] Frontend: smoke test with local backend (or mock server) to confirm all screens populate.
19. [ ] Optional: E2E test that opens each route and checks for non-empty data or graceful empty/error state.

---

## 5. Quick Reference: Frontend Types vs Backend

| Frontend type | Backend source | Notes |
|---------------|----------------|-------|
| FeatureSpec | feature_specs.parsed_payload + path, spec_version, active, created_at | Merge from get_latest_feature_spec. |
| FeatureWithLatestDecision | FeatureSpec + latest_decision, latest_risk_score, latest_evaluated_at, latest_corpus_version | From list_active_features merged with latest evaluation. |
| Evaluation | evaluations table | Include feature_id in list_evaluations. pr_number optional. |
| CorpusVersion | corpus_versions table | version_id, source_set, released_at. |
| ReevaluationResult | reevaluation_results table | job_id, feature_id, previous_decision, new_decision, regressed, details, created_at. |
| DashboardStats | Derived | From features + latest decision counts; can compute on frontend. |
| Risk distribution | Derived | From evaluations risk_score buckets; can compute on frontend. |

---

## 6. CORS and Deployment

- Backend must allow CORS for the frontend origin (e.g. `http://localhost:3000` in dev, production origin in prod). Add FastAPI middleware or CORSMiddleware with appropriate origins and methods (GET, POST).
- In production, frontend and backend may be same-origin (proxy) or different; set `NEXT_PUBLIC_COMPLIANCE_API_URL` accordingly.
