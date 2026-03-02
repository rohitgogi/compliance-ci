# Compliance CI Milestone 2 Implementation Plan (Detailed)

## Milestone 2: CI Integration and Merge Gating

## Sequencing Strategy
- Build from left to right in the PR flow: detect changed specs -> call backend -> present result -> compute gate -> publish required check.
- Keep each step independently testable so failures are easy to localize.
- Enforce idempotency early (especially comment updates) because PR workflows rerun frequently.

### Todo 2.1: Create workflow skeleton and execution boundaries
- Why this way: a stable workflow shell first prevents coupling implementation details to uncertain trigger behavior.
- Acceptance criteria: GitHub Action file exists, runs only on pull request events, and uses least-privilege job permissions required for reading files and writing PR comments/status.
- Testing plan:
  - Trigger test: open/update PR and verify workflow starts.
  - Non-trigger test: push to non-PR branch and verify workflow does not run.
  - Permissions test: remove comment permission intentionally and verify expected failure is explicit.

### Todo 2.2: Implement changed-file discovery for PR diff
- Why this way: correctness of changed-file detection drives all downstream logic and prevents unnecessary backend calls.
- Acceptance criteria: workflow enumerates PR-changed files using base/head diff and captures added/modified/renamed paths deterministically.
- Testing plan:
  - Added-file test: new spec file appears in changed list.
  - Modified-file test: edited spec file appears once.
  - Rename test: renamed spec path resolves to new path.
  - Deleted-file test: deleted files are excluded from evaluation payload.

### Todo 2.3: Filter changed files to compliance YAML specs only
- Why this way: strict filtering minimizes noise and keeps evaluator payload bounded.
- Acceptance criteria: only files matching compliance spec path and YAML extension (`.yaml`/`.yml`) are selected; all other files are ignored.
- Testing plan:
  - Positive test: valid spec path with `.yaml` is included.
  - Extension test: `.yml` also included.
  - Negative test: markdown/code/config changes excluded.
  - Safety test: empty filtered set leads to clean no-op branch.

### Todo 2.4: Build normalized evaluator request payload
- Why this way: explicit payload normalization avoids backend ambiguity and makes failures reproducible.
- Acceptance criteria: payload includes repository metadata, PR metadata, and per-spec content objects with path and file body; payload shape is versioned and documented.
- Testing plan:
  - Schema test: payload contract matches expected keys/types.
  - Single-spec test: one file serialized correctly.
  - Multi-spec test: multiple files serialized in deterministic order.
  - Invalid-content test: unreadable file or empty body returns clear local error.

### Todo 2.5: Add backend call client with timeout and retry policy
- Why this way: network calls are the main reliability risk; explicit timeout/retry behavior prevents hanging workflows.
- Acceptance criteria: workflow posts payload to evaluator endpoint, applies bounded retries for transient failures, and fails fast on persistent errors with actionable logs.
- Testing plan:
  - Happy-path test: 200 response parsed successfully.
  - Timeout test: forced slow endpoint triggers timeout and retry.
  - 5xx test: transient server failure retries then succeeds/fails as configured.
  - 4xx test: client error fails immediately without retries.

### Todo 2.6: Validate and normalize evaluator response object
- Why this way: response validation protects gate logic from malformed backend output.
- Acceptance criteria: response parser enforces required fields per feature (`decision`, `score`, `evidence`, `message`) and rejects unknown critical states.
- Testing plan:
  - Contract test: valid response accepted.
  - Missing-field test: absent `decision` or `score` fails with explicit message.
  - Range test: score outside `0-100` is rejected.
  - Enum test: non-supported decision value is rejected.

### Todo 2.7: Generate deterministic PR comment markdown
- Why this way: deterministic formatting makes reruns diff-stable and easy to audit.
- Acceptance criteria: comment template includes overall outcome plus per-feature table/sections for decision, score, and evidence summary in consistent ordering.
- Testing plan:
  - Snapshot test: generated markdown stable for fixed input.
  - Multi-feature formatting test: mixed decisions render clearly.
  - Empty-evidence test: fallback wording shown without breaking format.

### Todo 2.8: Implement comment upsert (create once, update thereafter)
- Why this way: idempotent comment behavior avoids PR noise and preserves single source of truth.
- Acceptance criteria: workflow identifies prior bot comment via stable marker and updates it; if none exists, creates exactly one new comment.
- Testing plan:
  - First-run test: comment created once.
  - Rerun test: same comment updated, no duplicate.
  - Concurrency test: rapid reruns still leave one canonical comment.

### Todo 2.9: Implement strictest-outcome aggregation logic
- Why this way: centralizing gate logic as a pure function makes it easy to verify and reuse.
- Acceptance criteria: final PR outcome is derived from all feature decisions with strict ordering `FAIL` > `REVIEW_REQUIRED` > `PASS`.
- Testing plan:
  - Truth-table tests: all single-feature and mixed-feature combinations.
  - Dominance test: any single `FAIL` forces final `FAIL`.
  - Ambiguity test: no `FAIL` but at least one `REVIEW_REQUIRED` yields `REVIEW_REQUIRED`.

### Todo 2.10: Map final outcome to branch-protection-compatible status
- Why this way: explicit mapping ensures GitHub branch protection enforces compliance policy consistently.
- Acceptance criteria: check conclusion is success only for all-`PASS`; `REVIEW_REQUIRED` and `FAIL` both produce non-pass conclusion and clear summary text for reviewers.
- Testing plan:
  - Outcome mapping test: verify each final state maps to expected check conclusion.
  - Branch-protection simulation: required check blocks merge on non-pass conclusions.
  - UX test: check summary explains why merge is blocked and next action.

### Todo 2.11: Add observability and failure diagnostics
- Why this way: CI failures must be debuggable quickly or teams will bypass the control.
- Acceptance criteria: logs include request correlation IDs, selected spec files, final outcome, and sanitized backend error details.
- Testing plan:
  - Log completeness test: verify required fields appear for success and failure paths.
  - Redaction test: sensitive payload fields are not printed in logs.
  - Triage test: simulated failure can be diagnosed from logs without rerunning.

### Todo 2.12: Validate end-to-end workflow behavior on realistic PR scenarios
- Why this way: final E2E scenarios confirm cross-step assumptions and prevent integration regressions.
- Acceptance criteria: full workflow validated for all final outcomes (`PASS`, `REVIEW_REQUIRED`, `FAIL`) and for no-spec-change PRs.
- Testing plan:
  - E2E PASS scenario: all specs pass, comment posted, check passes.
  - E2E REVIEW_REQUIRED scenario: comment shows rationale, check non-pass.
  - E2E FAIL scenario: blocking outcome with clear evidence.
  - E2E no-op scenario: no spec changes, workflow exits cleanly with informative message.
