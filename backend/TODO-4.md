# Compliance CI Milestone 1 Implementation Plan (Detailed)

## Milestone 1: OpenAI LLM Adapter + Contracts (No Gate Change Yet)

## Sequencing Strategy
- Build strict interfaces first (request/response contracts) before adding network calls so all downstream behavior is testable and stable.
- Keep deterministic evaluator behavior unchanged in this milestone to isolate risk and avoid coupling rollout success to policy changes.
- Make failure handling explicit from day one (timeouts, malformed output, provider errors) so integration can degrade safely instead of failing unpredictably.

### Todo 4.1: Define LLM evaluation domain models and contract boundaries
- Why this way: typed contracts prevent prompt/output drift from leaking into API or CI logic.
- Acceptance criteria: request and response models are defined for LLM evaluation with explicit fields for decision, confidence, evidence references, findings, and remediation hints.
- Testing plan:
  - Model-schema test: required fields and enum constraints validate correctly.
  - Range test: confidence outside allowed range is rejected.
  - Unknown-field test: extra keys in contract payloads fail validation.

### Todo 4.2: Add provider config layer and environment validation
- Why this way: centralizing provider configuration keeps secrets and model options controlled in one place.
- Acceptance criteria: adapter refuses to run when required env vars are missing or invalid; model name/timeout settings are validated and bounded.
- Testing plan:
  - Missing-key test: absent API key returns clear configuration error.
  - Invalid-timeout test: negative/zero timeout values are rejected.
  - Config-default test: valid defaults are applied when optional values are omitted.

### Todo 4.3: Implement prompt-builder module with deterministic structure
- Why this way: deterministic prompt shape improves reproducibility and makes prompt changes auditable.
- Acceptance criteria: prompt builder outputs stable sections (feature context, retrieved evidence, expected JSON schema, constraints) and excludes unsafe/unneeded fields.
- Testing plan:
  - Snapshot test: prompt is byte-stable for fixed input.
  - Evidence-order test: evidence sections are ordered deterministically.
  - Redaction test: prompt excludes sensitive fields and oversized payload content.

### Todo 4.4: Implement OpenAI client wrapper with strict transport controls
- Why this way: wrapping the provider SDK/API enables consistent timeout, retry, and error normalization logic.
- Acceptance criteria: client enforces bounded timeout, bounded retries on transient failures, and immediate fail on non-retryable errors.
- Testing plan:
  - Happy-path test: valid provider response returns parsed payload.
  - Timeout-retry test: first timeout retries and then succeeds/fails deterministically.
  - Non-retryable test: 4xx-like provider error fails fast with actionable message.

### Todo 4.5: Add response parser and JSON-schema-style output validation
- Why this way: LLM output must be treated as untrusted until validated.
- Acceptance criteria: raw model output is parsed into strict contract objects; malformed JSON or missing required fields produce explicit adapter errors.
- Testing plan:
  - Valid-json test: expected output parses successfully.
  - Malformed-json test: parser returns clear parse error.
  - Missing-field test: absent `decision`/`confidence` fails contract validation.

### Todo 4.6: Normalize LLM outputs to internal canonical forms
- Why this way: downstream modules should never handle ambiguous variants (`pass`, `Pass`, `PASS`).
- Acceptance criteria: decisions are canonical (`PASS`, `REVIEW_REQUIRED`, `FAIL`), confidence normalized to `[0,1]`, and evidence IDs normalized to deterministic list format.
- Testing plan:
  - Case-normalization test: mixed-case decision strings normalize correctly.
  - Confidence-normalization test: percentage-style values map to canonical range.
  - Evidence-normalization test: duplicate/empty evidence entries are cleaned.

### Todo 4.7: Add deterministic fallback object for LLM unavailability
- Why this way: milestone 1 must be integration-safe without changing gate logic yet.
- Acceptance criteria: adapter exposes a structured fallback result for provider failures with explicit `error_type`, diagnostic summary, and safe default confidence.
- Testing plan:
  - Provider-down test: fallback object is returned with sanitized error detail.
  - Contract-preservation test: fallback still conforms to adapter response schema.
  - Consistency test: identical failures produce stable error typing.

### Todo 4.8: Wire adapter behind feature flag (disabled by default)
- Why this way: dark-launching allows verification without impacting live decisions.
- Acceptance criteria: LLM adapter can be toggled via env flag; when disabled, system behavior remains deterministic-only and unchanged.
- Testing plan:
  - Flag-off test: adapter path is skipped entirely.
  - Flag-on test: adapter path executes and returns structured result.
  - Toggle-regression test: switching flag does not change deterministic outputs.

### Todo 4.9: Add adapter-level observability and trace identifiers
- Why this way: LLM calls are a major reliability/debugging hotspot and need traceable logs.
- Acceptance criteria: logs include correlation IDs, model name, attempt count, latency bucket, and sanitized error metadata (no prompt/body leaks).
- Testing plan:
  - Success-log test: required observability fields present.
  - Failure-log test: retry/failure events include correlation and reason.
  - Redaction test: logs never print full prompt or secret tokens.

### Todo 4.10: Add unit tests for adapter edge cases and failure taxonomy
- Why this way: most production failures in model integrations happen at boundaries, not happy path.
- Acceptance criteria: test matrix covers parse failure, validation failure, timeout, transient retry, non-retryable failure, and fallback behavior.
- Testing plan:
  - Boundary matrix test: all known failure types map to expected adapter error categories.
  - Retry-limit test: adapter stops at configured retry ceiling.
  - Stability test: same edge input yields same normalized output/error.

### Todo 4.11: Add integration tests with mocked provider responses
- Why this way: integration-level tests validate orchestration without external network dependency.
- Acceptance criteria: end-to-end adapter call flow is validated against mocked provider responses across success and failure modes.
- Testing plan:
  - Mock-success test: full contract object returned.
  - Mock-invalid-output test: provider response rejected by parser/validator.
  - Mock-transient-then-success test: retries behave exactly as configured.

### Todo 4.12: Validate milestone safety condition (no gate-policy change yet)
- Why this way: this milestone should add capability without changing merge behavior.
- Acceptance criteria: existing deterministic gate decisions remain unchanged when adapter is disabled, and adapter outputs are observational only when enabled.
- Testing plan:
  - Regression test: baseline deterministic test suite remains green.
  - Side-effect test: no CI status mapping or branch-protection behavior changes in this milestone.
  - Audit test: adapter outputs can be inspected without altering final gate decisions.
