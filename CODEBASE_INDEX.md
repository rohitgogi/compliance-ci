# Compliance CI — Codebase Index

Quick reference for navigating and understanding the codebase.

---

## 1. Repo Layout

```
compliance-ci/
├── .github/workflows/compliance-ci.yml   # PR-triggered CI job
├── .env                                 # Local env (gitignored)
├── backend/
│   ├── app/                             # Core application
│   │   ├── api.py                       # FastAPI routes
│   │   ├── ci.py                        # Gate logic + PR comment rendering
│   │   ├── ci_integration.py            # GitHub Action helpers
│   │   ├── evaluator.py                 # Deterministic eval + retrieval
│   │   ├── fusion.py                    # LLM + deterministic policy fusion
│   │   ├── llm_adapter.py               # Groq LLM client
│   │   ├── corpus_parser.py             # Corpus YAML parsing (upload)
│   │   ├── parser.py                    # YAML parsing + validation
│   │   ├── rate_limiter.py              # Sliding-window rate limit
│   │   ├── schemas.py                   # Pydantic feature/control models
│   │   ├── storage.py                   # SQLite persistence
│   │   ├── vector_retriever.py          # Local embeddings + pgvector
│   │   └── reevaluation.py             # Corpus-update jobs + regression
│   ├── scripts/
│   │   └── run_ci_check.py              # CI entrypoint (git diff → API → output)
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   └── src/
│       ├── app/                         # Next.js pages
│       ├── components/                  # UI components
│       ├── lib/                         # data.ts (API client), types, utils
│       └── data/                        # MyData.json (mock data, largely superseded)
└── backend/features/                   # Feature YAML specs (PRs touch these)
```

---

## 2. Request Flow (PR → Gate)

```
PR opened/synced
    → .github/workflows/compliance-ci.yml
    → run_ci_check.py (git diff, filter backend/features/*.yaml)
    → POST /v1/evaluate-pr
    → api.evaluate_pr()
        → parser.parse_feature_spec_yaml()
        → evaluator.retrieve_relevant_chunks()  [keyword or pgvector]
        → evaluator.evaluate_feature_spec()
        → [if LLM enabled] llm_adapter.evaluate_with_groq()
        → fusion.fuse_decision()
        → storage.record_evaluation()
    → ci.determine_pr_gate() + render_pr_comment()
    → Workflow upserts PR comment, enforces gate
```

---

## 3. Backend Modules (one-liners)

| File | Role |
|------|------|
| `api.py` | FastAPI app; `POST /v1/evaluate-pr`, `POST /v1/corpus-versions/upload`, `GET /v1/features`, `/evaluations`, `/corpus-versions`, `/reevaluation-results` |
| `parser.py` | `parse_feature_spec_yaml()` → `FeatureComplianceSpec` via Pydantic |
| `schemas.py` | `Control`, `FeatureComplianceSpec` (status, classification, jurisdictions validators) |
| `evaluator.py` | `DEFAULT_CORPUS` (in-code chunks), `retrieve_relevant_chunks()`, `evaluate_feature_spec()` (risk score + decision) |
| `vector_retriever.py` | Local sentence-transformers + pgvector; optional path when `COMPLIANCE_PGVECTOR_DSN` set |
| `llm_adapter.py` | Groq chat completions; JSON contract + one retry on invalid JSON |
| `fusion.py` | Conservative policy: combines deterministic + LLM signals → final decision |
| `ci.py` | `determine_pr_gate()`, `render_pr_comment()`, `upsert_comment()` |
| `ci_integration.py` | `filter_changed_spec_paths()`, `build_evaluate_payload()`, `submit_evaluation()` |
| `corpus_parser.py` | `parse_corpus_yaml()` → `ParsedCorpus` (version_id, source_set, chunks) |
| `storage.py` | SQLite: feature_specs, evaluations, corpus_versions, corpus_chunks, reevaluation_jobs/results |
| `reevaluation.py` | `trigger_corpus_update()`, `execute_reevaluation_job()`, regression report |
| `rate_limiter.py` | Sliding-window rate limit for evaluate-pr |

---

## 4. Frontend Structure

| Path | Purpose |
|------|---------|
| `app/page.tsx` | Overview (stats, timeline, recent evals, regressions) |
| `app/features/page.tsx` | Feature list with latest decision |
| `app/features/[featureId]/page.tsx` | Feature detail + evaluation history |
| `app/evaluations/page.tsx` | Global evaluations table |
| `app/corpus/page.tsx` | Corpus versions + evals per version |
| `lib/data.ts` | API client → `NEXT_PUBLIC_COMPLIANCE_API_URL` |
| `lib/types.ts` | `FeatureSpec`, `Evaluation`, `CorpusVersion`, etc. |
| `lib/mock.ts` | Legacy mock layer (unused after data.ts wiring) |

---

## 5. Key Env Vars

| Var | Default / purpose |
|-----|-------------------|
| `COMPLIANCE_DB_PATH` | `backend/data/compliance.db` |
| `COMPLIANCE_LLM_ENABLED` | `false` |
| `GROQ_API_KEY` | Required for LLM |
| `COMPLIANCE_GROQ_MODEL` | `llama-3.3-70b` |
| `COMPLIANCE_PGVECTOR_DSN` | Empty = no pgvector (keyword fallback) |
| `COMPLIANCE_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` |
| `COMPLIANCE_RATE_LIMIT_PER_MINUTE` | `120` (0 = disabled) |
| `COMPLIANCE_BACKEND_URL` | GitHub Actions secret |
| `NEXT_PUBLIC_COMPLIANCE_API_URL` | `http://localhost:8000` |

---

## 6. Test Layout

| Test file | Covers |
|-----------|--------|
| `test_schema_validation.py` | Parser + Pydantic validation |
| `test_evaluator.py` | Retrieval, score→decision, vector path |
| `test_llm_adapter.py` | Groq config, JSON parsing, retry, fallback |
| `test_fusion.py` | Policy matrix, confidence fusion |
| `test_api_evaluate_pr.py` | POST /v1/evaluate-pr, rate limit |
| `test_api_read_endpoints.py` | GET /v1/features, evaluations, corpus, reeval |
| `test_corpus_upload.py` | Corpus YAML parser, POST /v1/corpus-versions/upload |
| `test_storage.py` | Schema, writes, list helpers |
| `test_reevaluation.py` | Corpus trigger, job exec, regression |
| `test_ci_integration.py` | Payload build, submit, contract validation |
| `test_ci_policy.py` | Gate logic, comment rendering |
| `test_run_ci_check.py` | E2E script behavior |

---

## 7. Corpus Definition

- **Default (fallback):** `backend/app/evaluator.py` — `DEFAULT_CORPUS` (lines ~34–56)
- **Upload:** Corpus tab → Upload corpus → YAML file (see `backend/features/sample-corpus-example.yaml`)
- **Format:** `version_id`, `source_set`, `chunks: [{chunk_id, title, text, tags}]`
- **Storage:** `corpus_versions` + `corpus_chunks` (SQLite). Evaluations use latest uploaded corpus when present.

---

## 8. Decisions

| Decision | Condition |
|----------|-----------|
| PASS | Risk ≤ 30, or (deterministic + LLM both PASS and fused confidence ≥ 0.75) |
| REVIEW_REQUIRED | Risk 31–69, or mixed signals, or LLM fallback |
| FAIL | Risk ≥ 70, or both deterministic + LLM FAIL |
