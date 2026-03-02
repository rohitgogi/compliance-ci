# Compliance CI Milestone 2 Implementation Plan (Detailed)

## Milestone 2: Decision + Confidence Fusion Policy Module (Pure Function Layer)

## Sequencing Strategy
- Implement fusion as a pure, framework-agnostic module before wiring it into API/CI flows.
- Lock policy semantics with exhaustive decision-matrix tests before integrating anywhere else.
- Keep this milestone free of API persistence changes so correctness of policy can be validated in isolation.

### Todo 5.1: Define fusion input/output contracts and enums
- Why this way: typed boundaries prevent ambiguous policy behavior and make integration safer.
- Acceptance criteria: input contract includes deterministic decision/confidence and LLM decision/confidence/fallback metadata; output contract includes final decision, fused confidence, and reason codes.
- Testing plan:
  - Contract test: valid payload parses into typed fusion request.
  - Enum test: unknown decision values are rejected.
  - Required-field test: missing confidence or decision fails fast.

### Todo 5.2: Normalize confidence scales into canonical `[0,1]`
- Why this way: deterministic and LLM confidence sources may use different scales over time.
- Acceptance criteria: module accepts normalized confidence and helper normalization utilities support percent-to-float conversion with strict bounds.
- Testing plan:
  - Boundary test: values `0`, `0.75`, and `1` remain unchanged.
  - Percent test: `75` maps to `0.75`.
  - Range-guard test: negative and >100 percent values fail.

### Todo 5.3: Implement fused confidence formula as pure function
- Why this way: confidence math should be deterministic, unit-testable, and independent of transport/framework code.
- Acceptance criteria: fused confidence uses weighted formula and clamps to `[0,1]`.
- Testing plan:
  - Formula test: known pair values match expected weighted output.
  - Clamp test: out-of-bound intermediate values clamp safely.
  - Determinism test: repeated same input always yields same output.

### Todo 5.4: Encode conservative decision matrix policy
- Why this way: policy semantics are the core compliance behavior and must be explicit.
- Acceptance criteria:
  - `PASS` only if deterministic is `PASS`, LLM is `PASS`, and fused confidence `>= 0.75`
  - `PASS + FAIL` => `REVIEW_REQUIRED`
  - `PASS + REVIEW_REQUIRED` => `REVIEW_REQUIRED`
  - `FAIL + FAIL` => `FAIL`
  - all other non-pass mixed outcomes resolve conservatively to `REVIEW_REQUIRED`
- Testing plan:
  - Matrix test: cover all deterministic/LLM decision pairs.
  - Confidence-threshold test: `0.74`, `0.75`, `0.76` boundary behavior.
  - Stability test: matrix results are deterministic.

### Todo 5.5: Add fallback-aware policy overrides for LLM outages
- Why this way: model outages should degrade predictably and safely.
- Acceptance criteria: when LLM fallback flag is true, final decision cannot become `PASS` unless deterministic policy explicitly allows non-LLM pass mode (not enabled in this milestone).
- Testing plan:
  - Fallback-pass-block test: deterministic+LLM pass with fallback true results in non-pass.
  - Fallback-review test: fallback yields `REVIEW_REQUIRED` with explicit reason code.
  - Retry-consistency test: same fallback scenario produces same output.

### Todo 5.6: Emit structured reason codes for traceable outcomes
- Why this way: integration and PR comments need machine-readable explanations.
- Acceptance criteria: output includes a stable list of reason codes (e.g., `PASS_THRESHOLD_MET`, `MIXED_SIGNAL_REVIEW`, `LLM_FALLBACK_CONSERVATIVE`).
- Testing plan:
  - Reason-code presence test: every policy path includes at least one reason code.
  - Path-specific test: expected code set for mixed outcomes and threshold misses.
  - Ordering test: reason codes are deterministic.

### Todo 5.7: Add human-readable policy explanation helper
- Why this way: reviewers need plain-language rationale, not only enum outputs.
- Acceptance criteria: helper converts reason codes into concise explanation text suitable for PR comments.
- Testing plan:
  - Mapping test: each reason code maps to expected explanation phrase.
  - Combined-message test: multiple reason codes generate coherent output.
  - Unknown-code test: unknown reason code handled safely.

### Todo 5.8: Add remediation hint synthesizer for non-pass outcomes
- Why this way: developers need actionable next steps when gated.
- Acceptance criteria: module synthesizes non-invasive remediation hints based on reason codes and optional LLM findings; output is deduped and deterministic.
- Testing plan:
  - Non-pass hint test: review/fail paths include remediation hints.
  - Dedup test: repeated hint sources collapse to one entry.
  - Pass test: pass path returns empty or informational hint set.

### Todo 5.9: Add policy snapshot tests for regression protection
- Why this way: policy changes are high-impact and should be visible in diffs.
- Acceptance criteria: snapshot-style tests lock output shape and key semantics across representative scenarios.
- Testing plan:
  - Representative snapshot: pass, mixed-review, fail, fallback cases.
  - Snapshot stability: outputs are stable across reruns.
  - Change-detection test: policy changes trigger intentional snapshot diffs.

### Todo 5.10: Add property-based style invariants (determinism + bounds)
- Why this way: confidence-fusion logic benefits from invariant checks beyond fixed examples.
- Acceptance criteria: tests assert invariants: confidence always in `[0,1]`, pure-function determinism, no pass under fallback-conservative policy.
- Testing plan:
  - Invariant test: random confidence inputs always produce bounded output.
  - Determinism test: same random seed/input pair yields identical output.
  - Conservative-safety invariant: fallback path never emits pass.

### Todo 5.11: Add integration-facing smoke tests for future API wiring
- Why this way: ensures module interface is ready for TODO-6 integration with minimal refactor.
- Acceptance criteria: tests validate expected function signatures and adapter compatibility with existing evaluation result structures.
- Testing plan:
  - Signature smoke test: fusion entrypoints accept planned API-layer payload shape.
  - Compatibility test: deterministic + LLM mock results transform without schema errors.
  - Backward-safety test: module can run without persistence changes.

### Todo 5.12: Validate milestone safety boundary (no API gate behavior switch yet)
- Why this way: fusion module should be production-ready without changing runtime behavior until next milestone.
- Acceptance criteria: module exists with full test coverage but is not yet authoritative in API gate path.
- Testing plan:
  - Isolation test: current API tests remain green with no gate change.
  - Import test: fusion module can be imported and called without side effects.
  - Regression test: pre-existing deterministic behavior unchanged in this milestone.
