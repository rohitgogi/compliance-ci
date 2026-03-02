# Compliance CI Milestone 3 Implementation Plan (Detailed)

## Milestone 3: Persistence and Corpus-Update Re-evaluation

## Sequencing Strategy
- Build from foundation to automation: storage contracts -> write paths -> read/history paths -> corpus update trigger -> re-evaluation execution -> regression reporting.
- Keep all persistence operations idempotent so CI reruns and retry loops cannot create inconsistent state.
- Treat auditability as a first-class requirement: every decision must be traceable to spec version + corpus version + timestamp.

### Todo 3.1: Formalize persistence schema and migration bootstrap
- Why this way: stable table contracts early prevent downstream logic from coupling to ad-hoc storage assumptions.
- Acceptance criteria: schema defines versioned feature specs, evaluations, corpus versions, re-evaluation jobs, and re-evaluation results with clear keys/constraints.
- Testing plan:
  - Bootstrap test: fresh DB initializes all required tables.
  - Constraint test: primary and foreign key constraints enforce integrity.
  - Re-init test: schema bootstrap can run multiple times safely.

### Todo 3.2: Persist versioned feature specs with active-version semantics
- Why this way: compliance state must survive across commits while preserving historical versions.
- Acceptance criteria: new spec versions are insertable, active version is unique per feature, and historical versions remain queryable.
- Testing plan:
  - Create-version test: first spec version is stored and marked active.
  - Roll-forward test: second version deactivates prior active version.
  - History test: both versions are retrievable with correct metadata.

### Todo 3.3: Persist evaluations as immutable audit entries
- Why this way: decisions should be append-only evidence records, not mutable state.
- Acceptance criteria: each evaluation stores feature/spec/corpus linkage, decision, risk, evidence references, commit SHA, and timestamp.
- Testing plan:
  - Insert test: valid evaluation writes one audit row.
  - Read-latest test: latest decision retrieval returns most recent entry.
  - Immutability test: prior entries are preserved after new evaluations.

### Todo 3.4: Enforce idempotent writes for retry-safe CI behavior
- Why this way: network retries and job reruns must not duplicate equivalent records.
- Acceptance criteria: repeated writes for the same feature/spec/corpus/commit tuple do not create duplicate evaluation rows.
- Testing plan:
  - Duplicate-write test: repeated same input creates one row only.
  - Distinct-commit test: different commit SHA creates a new row.
  - Distinct-corpus test: same commit with new corpus version creates a new row.

### Todo 3.5: Register corpus versions as first-class entities
- Why this way: every evaluation and re-evaluation must be attributable to an explicit regulatory corpus release.
- Acceptance criteria: corpus version registration is idempotent and tracks version ID, source set, and release timestamp.
- Testing plan:
  - Register test: new corpus version persists successfully.
  - Re-register test: duplicate version update is safe and non-destructive.
  - Traceability test: evaluation references can be linked to registered corpus version.

### Todo 3.6: Create re-evaluation job model with deterministic IDs
- Why this way: corpus updates should trigger one canonical job per target version, not many competing jobs.
- Acceptance criteria: job ID is deterministic by target corpus version, creation is idempotent, and scope is persisted.
- Testing plan:
  - First-create test: first trigger creates job in pending state.
  - Duplicate-trigger test: repeated trigger reuses existing job.
  - Scope test: explicit feature scope is stored and honored.

### Todo 3.7: Implement scope resolution for active-feature re-evaluation
- Why this way: default behavior should cover all active features, while allowing narrowed runs for controlled backfills.
- Acceptance criteria: absent explicit scope, re-evaluation targets all active features; provided scope is respected exactly.
- Testing plan:
  - Full-scope test: all active feature IDs are included.
  - Explicit-scope test: only requested features are included.
  - Inactive-feature test: inactive specs are excluded from default scope.

### Todo 3.8: Build re-evaluation executor loop (per feature)
- Why this way: corpus-change behavior needs a deterministic pipeline that can be resumed and diagnosed.
- Acceptance criteria: executor iterates scoped features, recomputes decisions using target corpus version, stores results, and updates job status transitions.
- Testing plan:
  - Happy-path test: pending job completes and writes all expected rows.
  - Partial-failure test: single-feature failure is captured without dropping successful feature results.
  - Resume test: rerun after interruption continues safely without duplicate outputs.

### Todo 3.9: Implement decision-diff logic for regression detection
- Why this way: the core product value is detecting when regulations make previously acceptable features riskier.
- Acceptance criteria: regression is flagged only when decision severity increases (`PASS -> REVIEW_REQUIRED/FAIL`, `REVIEW_REQUIRED -> FAIL`).
- Testing plan:
  - Transition-matrix test: all decision pairs classified correctly.
  - No-regression test: same or improved severity is not flagged.
  - Edge test: missing prior decision is handled explicitly (no false regression).

### Todo 3.10: Generate machine-readable regression reports
- Why this way: teams need structured outputs to automate follow-up workflows and remediation tracking.
- Acceptance criteria: report includes job ID, totals, regression count, and per-feature previous/new decisions, risk, and regression flag.
- Testing plan:
  - Schema test: report shape is consistent and complete.
  - Count test: totals and regression counts match row-level truth.
  - Determinism test: identical inputs produce byte-stable output ordering.

### Todo 3.11: Add observability for re-evaluation jobs and outcomes
- Why this way: corpus-update runs can be long and need operational transparency for debugging and audit.
- Acceptance criteria: logs include correlation/job IDs, target corpus version, feature scope size, success/failure counts, and sanitized error details.
- Testing plan:
  - Success-log test: completion logs contain required summary fields.
  - Failure-log test: feature-level failure details are actionable and sanitized.
  - Redaction test: raw spec content is never logged.

### Todo 3.12: Validate end-to-end corpus-update scenarios
- Why this way: integration tests ensure schema, executor, diff logic, and reports work together under realistic changes.
- Acceptance criteria: end-to-end flows validated for no-regression runs, mixed regression runs, and idempotent retriggers.
- Testing plan:
  - E2E no-regression scenario: corpus update triggers job with zero regressions.
  - E2E mixed scenario: subset of features regress and are correctly flagged.
  - E2E idempotency scenario: duplicate corpus trigger does not create duplicate job/results.
