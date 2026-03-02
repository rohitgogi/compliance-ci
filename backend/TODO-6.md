# Compliance CI Milestone 3 Implementation Plan (Detailed)

## Milestone 3: API + PR Comment Integration for Hybrid Evaluation

## Sequencing Strategy
- Wire fusion into API first, then update PR comment formatting so outputs remain consistent end-to-end.
- Keep persistence unchanged in this milestone to isolate behavior-level integration from storage migration risk.
- Lock failure-degradation semantics early (LLM fallback, malformed LLM output, mixed-signal policy) to prevent ambiguous CI outcomes.

### Todo 6.1: Extend API response contract for hybrid result visibility
- Why this way: integration consumers need deterministic and fused context without guessing internal policy behavior.
- Acceptance criteria: per-feature response includes deterministic result fields, LLM observation fields, and fusion output fields while preserving existing required keys.
- Testing plan:
  - Contract test: new fields are present and typed correctly.
  - Backward-safety test: existing required fields remain unchanged.
  - Multi-feature test: mixed feature outcomes serialize consistently.

### Todo 6.2: Wire deterministic + LLM + fusion orchestration in `evaluate_pr`
- Why this way: one orchestration layer should own signal composition and final decision assignment.
- Acceptance criteria: when LLM is enabled, each feature runs deterministic evaluation, optional LLM observation, and fusion decision computation; when disabled, behavior remains deterministic.
- Testing plan:
  - Flag-off test: deterministic behavior unchanged.
  - Flag-on test: fusion decision is used.
  - Mixed-signal test: policy output is `REVIEW_REQUIRED` where required.

### Todo 6.3: Compute deterministic confidence consistently for fusion input
- Why this way: fusion should not rely on implicit or ad-hoc confidence conversions.
- Acceptance criteria: deterministic risk score maps to deterministic confidence via stable function and is bounded to `[0,1]`.
- Testing plan:
  - Mapping test: representative risk values map to expected confidence.
  - Clamp test: any out-of-range values are bounded safely.
  - Determinism test: repeated mapping yields identical output.

### Todo 6.4: Propagate fusion reason codes into API payload
- Why this way: machine-readable reasons are required for downstream comment generation and debugging.
- Acceptance criteria: API response includes reason codes and fused confidence for each feature whenever LLM path is active.
- Testing plan:
  - Reason-code test: expected reason appears for threshold miss and mixed signals.
  - Confidence test: fused confidence appears and is in range.
  - Fallback-reason test: fallback path includes conservative reason code.

### Todo 6.5: Upgrade PR comment renderer to explain policy decisions
- Why this way: reviewers need explicit rationale and remediation, not just final status labels.
- Acceptance criteria: comment includes final gate, per-feature fused rationale, confidence, and remediation hints for all non-pass outcomes.
- Testing plan:
  - Rendering test: mixed outcomes show explanation blocks.
  - Remediation test: non-pass entries include actionable hints.
  - Stability test: comment ordering/format remains deterministic.

### Todo 6.6: Include evidence references in comment output
- Why this way: audit and remediation workflows require traceable evidence links/IDs.
- Acceptance criteria: comment includes evidence chunk IDs from deterministic and/or LLM observations when available, and explicit fallback wording when missing.
- Testing plan:
  - Evidence-present test: IDs are rendered correctly.
  - Evidence-empty test: `none` fallback text appears.
  - Dedup test: repeated evidence IDs are shown once.

### Todo 6.7: Harden CI response contract for new hybrid fields
- Why this way: CI parser should accept enriched responses without accidental rejection.
- Acceptance criteria: response validator supports new optional hybrid fields while preserving strict validation of critical required fields.
- Testing plan:
  - Compatibility test: enriched backend response validates successfully.
  - Missing-critical-field test: still fails if required gate fields are absent.
  - Unknown-critical-state test: invalid decision values still rejected.

### Todo 6.8: Add safety behavior for LLM fallback in API flow
- Why this way: LLM outages should produce predictable conservative outcomes, not partial undefined behavior.
- Acceptance criteria: fallback observations still feed fusion, resulting in conservative non-pass output with explicit reason metadata.
- Testing plan:
  - Fallback integration test: fallback path yields `REVIEW_REQUIRED`.
  - Consistency test: repeated fallback inputs produce stable outputs.
  - Explanation test: fallback reason is reflected in comment text.

### Todo 6.9: Add integration tests for threshold and mixed-signal scenarios
- Why this way: TODO-6 is primarily orchestration and requires high-fidelity integration tests.
- Acceptance criteria: tests cover high-confidence pass, low-confidence threshold miss, mixed pass/fail, and mixed pass/review combinations.
- Testing plan:
  - High-confidence pass scenario.
  - Threshold-miss review scenario.
  - Mixed-signal review scenarios.

### Todo 6.10: Add policy-regression tests for final gate aggregation
- Why this way: once per-feature decisions are fused, PR-level gate aggregation must remain correct.
- Acceptance criteria: strictest-outcome aggregation remains valid using fused per-feature decisions.
- Testing plan:
  - PR aggregation matrix test across fused decisions.
  - Dominance test: any fail still dominates.
  - Ambiguity test: review dominates pass where no fail exists.

### Todo 6.11: Add observability checks for hybrid decision path
- Why this way: when debugging policy outcomes, reviewers need both deterministic and fused context.
- Acceptance criteria: logs/comments include enough metadata to diagnose why fusion chose final outcomes without leaking sensitive payloads.
- Testing plan:
  - Metadata completeness test: decision/confidence/reason fields visible.
  - Redaction test: no secret prompt or key material in logs/comments.
  - Triage test: mixed-signal path is diagnosable from response/comment.

### Todo 6.12: Validate milestone safety + readiness for TODO-7
- Why this way: TODO-7 will persist these fields; contracts must be stable first.
- Acceptance criteria: full suite passes, hybrid API behavior is deterministic, and contracts are ready for storage-layer extension.
- Testing plan:
  - Full-suite regression run.
  - Contract snapshot run for hybrid response shape.
  - API behavior check for LLM-enabled and LLM-disabled modes.
