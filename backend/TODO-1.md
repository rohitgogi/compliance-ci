# Compliance CI MVP Detailed Todo List

## Milestone 1: PR Evaluation Path

### Todo 1.1: Define and enforce YAML spec schema
- Acceptance criteria: invalid or missing required fields return structured validation errors; valid specs are normalized into a stable internal shape.
- Tests: unit tests for valid spec, missing required field, wrong type, unknown field behavior, and normalization output.

### Todo 1.2: Build evaluation API endpoint
- Acceptance criteria: endpoint accepts PR metadata plus changed specs and returns per-feature result objects with decision, score, and evidence references.
- Tests: API tests for single feature, multiple features, malformed payload, and partial failure handling.

### Todo 1.3: Implement RAG-backed compliance evaluation
- Acceptance criteria: evaluation retrieves relevant corpus chunks, grounds analysis on retrieved text, and outputs deterministic decision bands from the risk score.
- Tests: integration tests with seeded corpus proving retrieval is used; unit tests for score-to-decision mapping boundaries (`30/31`, `69/70`).

## Milestone 2: CI Integration and Merge Gating

### Todo 2.1: Connect GitHub Action to backend evaluator
- Acceptance criteria: action sends only changed YAML spec files and receives structured evaluation output for each.
- Tests: workflow-level test on a sample PR diff; negative test when backend is unreachable.

### Todo 2.2: Publish structured PR comment
- Acceptance criteria: comment shows per-feature decision, score, and key evidence; reruns update the existing comment instead of posting duplicates.
- Tests: integration tests for first-run comment creation and rerun comment update behavior.

### Todo 2.3: Enforce CI gating status
- Acceptance criteria: PR status is pass only when all features are `PASS`; any `REVIEW_REQUIRED` or `FAIL` marks the check non-pass according to branch protection.
- Tests: decision matrix tests for all combinations across multiple features to verify strictest-outcome rule.

## Milestone 3: Persistence and Corpus-Update Re-evaluation

### Todo 3.1: Persist versioned compliance state
- Acceptance criteria: store feature spec versions, evaluation results, decision history, and corpus version references with audit timestamps.
- Tests: repository/data-layer tests for create, read-latest, read-history, and idempotent writes on repeated evaluations.

### Todo 3.2: Implement corpus version update trigger
- Acceptance criteria: when corpus version changes, system creates a re-evaluation job targeting all active features (or configured scope) and tracks job status.
- Tests: integration tests for version change event creating one job, scoped job behavior, and retry-safe deduplication.

### Todo 3.3: Flag regressions after re-evaluation
- Acceptance criteria: system compares previous vs new decision and marks regressions (`PASS` to `REVIEW_REQUIRED` or `FAIL`) in a machine-readable report.
- Tests: comparison logic tests for all transition pairs and integration test for end-to-end re-evaluation report generation.
