# Compliance CI Milestone 4 Implementation Plan (Detailed)

## Milestone 4: Persistence + Reevaluation Alignment for Hybrid Decisions

## Sequencing Strategy
- Start with storage schema evolution and compatibility guards before writing runtime logic.
- Persist hybrid evaluation outputs in PR flow first, then align corpus-update reevaluation to the exact same fusion policy.
- Add migration-safe fallbacks and deterministic reporting so old rows and new rows can coexist without breaking queries.

### Todo 7.1: Extend evaluation storage schema for hybrid signals
- Why this way: TODO-6 introduced runtime fusion outputs that must now be persisted for audit and replay.
- Acceptance criteria: evaluation records can store deterministic confidence, LLM decision/confidence/fallback metadata, fused decision/confidence, and fusion reason codes.
- Testing plan:
  - Schema-bootstrap test: fresh DB includes all new hybrid columns/tables.
  - Backward-compat test: existing records without hybrid fields remain readable.
  - Constraint test: enum/range constraints reject invalid persisted values.

### Todo 7.2: Add migration-safe read/write helpers for hybrid fields
- Why this way: runtime code should not manage column-evolution logic inline.
- Acceptance criteria: storage layer exposes explicit typed methods for writing and reading hybrid evaluation data, with deterministic defaults when fields are absent.
- Testing plan:
  - Write-read roundtrip test for hybrid records.
  - Legacy-row read test with defaulted hybrid values.
  - Nullability test for optional LLM metadata fields.

### Todo 7.3: Persist hybrid outputs during PR evaluation path
- Why this way: PR-time decisions should be auditable with exact deterministic/LLM/fusion context used at decision time.
- Acceptance criteria: API evaluation flow writes full hybrid payload to persistence for each evaluated feature.
- Testing plan:
  - API integration test: hybrid fields are persisted for LLM-enabled runs.
  - Deterministic-only test: persistence still works when LLM disabled.
  - Multi-feature test: all evaluated features persist correctly.

### Todo 7.4: Persist reason codes and remediation hints in structured format
- Why this way: text-only storage loses machine-readable policy reasoning.
- Acceptance criteria: reason codes and remediation hints are persisted as structured data suitable for querying/reporting.
- Testing plan:
  - Serialization test: reason/hints store and load losslessly.
  - Determinism test: ordering is stable across repeated writes.
  - Queryability test: reason-code filtering returns expected rows.

### Todo 7.5: Align reevaluation executor to use fusion policy module
- Why this way: corpus-update reevaluations must produce decisions consistent with PR-time evaluations.
- Acceptance criteria: reevaluation flow computes deterministic + LLM + fusion outputs using the same module/path as API flow.
- Testing plan:
  - Consistency test: same input produces same fusion output in API and reevaluation paths.
  - Fallback test: reevaluation handles LLM fallback conservatively.
  - Policy parity test: reason codes match expected fusion path.

### Todo 7.6: Update reevaluation result persistence to capture hybrid diffs
- Why this way: regressions should be traceable by both decision shift and confidence/reason changes.
- Acceptance criteria: reevaluation result rows include previous/new fused decisions, confidences, reason codes, and regression flag.
- Testing plan:
  - Diff test: previous vs new fused outputs are stored correctly.
  - Confidence-delta test: confidence changes are captured.
  - Reason-delta test: reason-code changes are captured.

### Todo 7.7: Define regression detection rules for hybrid outcomes
- Why this way: hybrid regressions need explicit severity ordering and confidence-aware handling.
- Acceptance criteria: regression logic uses fused decision severity ordering and supports edge rules (e.g., same decision but materially lower confidence can optionally trigger review flag).
- Testing plan:
  - Decision-transition matrix test for fused decisions.
  - Confidence-degrade edge test (threshold crossing scenarios).
  - Non-regression control test for stable/improved outcomes.

### Todo 7.8: Emit machine-readable hybrid reevaluation reports
- Why this way: downstream remediation workflows need deterministic report contracts.
- Acceptance criteria: reports include per-feature deterministic/LLM/fused outputs, confidence values, reason codes, remediation hints, and regression status.
- Testing plan:
  - Report-schema test for full hybrid payload.
  - Count/aggregation test for regressions and statuses.
  - Deterministic-order test for stable report generation.

### Todo 7.9: Add observability for persistence and reevaluation hybrid paths
- Why this way: diagnosing mismatches between API and reevaluation paths requires rich but safe telemetry.
- Acceptance criteria: logs include correlation IDs, job IDs, model metadata, fusion reason codes, and sanitized error details without prompt/content leaks.
- Testing plan:
  - Success-log completeness test.
  - Failure-log triage test with sanitized metadata.
  - Redaction test confirming no secret/prompt leakage.

### Todo 7.10: Add idempotency guarantees for hybrid reevaluation writes
- Why this way: retried jobs must not duplicate hybrid rows or create drift in counts.
- Acceptance criteria: reruns for same `(job_id, feature_id)` upsert deterministically; repeated writes do not duplicate.
- Testing plan:
  - Duplicate-run test: same job rerun produces one canonical row per feature.
  - Partial-rerun test: only unresolved features are updated.
  - Counter-integrity test: success/failure/regression counts remain accurate.

### Todo 7.11: Add comprehensive integration tests across PR + reevaluation lifecycle
- Why this way: milestone success depends on consistency across two execution contexts.
- Acceptance criteria: tests verify hybrid values persist at PR-time and are reused/aligned during corpus-update reevaluations.
- Testing plan:
  - End-to-end PR evaluation persistence scenario.
  - End-to-end reevaluation scenario with mixed outcomes.
  - Cross-path parity test between API and reevaluation fusion outputs.

### Todo 7.12: Validate milestone completion and migration readiness
- Why this way: this milestone introduces schema + runtime coupling and must be release-safe.
- Acceptance criteria: full suite passes, migration path is documented, and rollback/backward-compat behavior is validated.
- Testing plan:
  - Full regression suite run.
  - Migration smoke test from pre-hybrid DB state.
  - Rollback-read test to confirm legacy data remains accessible.
