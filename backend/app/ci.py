"""CI utility logic for gating and PR comment generation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Iterable

COMMENT_MARKER = "<!-- compliance-ci-comment -->"


def _to_mapping(value: object | None) -> dict:
    """Normalize optional dict-like or Pydantic-like objects to plain dict."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        return dumped if isinstance(dumped, dict) else {}
    return {}


def determine_pr_gate(results: Iterable[object]) -> str:
    """
    Determine final gate with strictest-outcome policy.

    Policy:
    - Any schema or processing error behaves as FAIL.
    - FAIL dominates REVIEW_REQUIRED, which dominates PASS.
    """
    has_review_required = False
    for result in results:
        error = getattr(result, "error", None)
        decision = getattr(result, "decision", None)
        if error:
            return "FAIL"
        if decision == "FAIL":
            return "FAIL"
        if decision == "REVIEW_REQUIRED":
            has_review_required = True

    if has_review_required:
        return "REVIEW_REQUIRED"
    return "PASS"


def map_gate_to_check_conclusion(gate: str) -> dict[str, str]:
    """
    Map gate state to GitHub-check-compatible conclusion and reviewer summary.

    - PASS => success (merge can proceed)
    - REVIEW_REQUIRED/FAIL => failure (required check blocks merge)
    """
    if gate == "PASS":
        return {
            "conclusion": "success",
            "summary": "All evaluated compliance specs passed policy checks.",
        }
    if gate == "REVIEW_REQUIRED":
        return {
            "conclusion": "failure",
            "summary": "Manual compliance review is required before merge.",
        }
    if gate == "FAIL":
        return {
            "conclusion": "failure",
            "summary": "Compliance checks failed; merge is blocked until remediated.",
        }
    raise ValueError(f"Unsupported gate value: {gate}")


def render_pr_comment(results: list[object], gate: str) -> str:
    """Render a stable markdown report consumed by CI pull-request comments."""
    ordered_results = sorted(results, key=lambda item: getattr(item, "path", ""))
    lines = [
        COMMENT_MARKER,
        "## Compliance CI Result",
        "",
        f"- Final Gate: `{gate}`",
        f"- Features Evaluated: `{len(ordered_results)}`",
        "",
        "### Per-feature Results",
    ]

    for result in ordered_results:
        path = getattr(result, "path", "unknown-path")
        error = getattr(result, "error", None)
        decision = getattr(result, "decision", None)
        risk_score = getattr(result, "risk_score", None)
        evidence_chunk_ids = getattr(result, "evidence_chunk_ids", []) or []
        fusion_observation = _to_mapping(getattr(result, "fusion_observation", None))
        llm_observation = _to_mapping(getattr(result, "llm_observation", None))
        if error:
            lines.append(
                f"- `{path}` -> `FAIL` (invalid spec): {error}"
            )
            continue

        evidence = ", ".join(evidence_chunk_ids) if evidence_chunk_ids else "none"
        lines.append(
            f"- `{path}` -> `{decision}` (risk `{risk_score}`), evidence: {evidence}"
        )
        if fusion_observation:
            fused_confidence = fusion_observation.get("fused_confidence")
            reason_codes = ", ".join(fusion_observation.get("reason_codes", [])) or "none"
            explanation = fusion_observation.get("explanation", "")
            lines.append(
                f"  - Fusion confidence: `{fused_confidence}` | reasons: {reason_codes}"
            )
            if explanation:
                lines.append(f"  - Why: {explanation}")

            remediation_hints = fusion_observation.get("remediation_hints", []) or []
            if remediation_hints:
                lines.append(f"  - Remediation: {'; '.join(remediation_hints)}")
        elif llm_observation:
            lines.append(
                f"  - LLM observation: decision `{llm_observation.get('decision')}` "
                f"confidence `{llm_observation.get('confidence')}`"
            )
    return "\n".join(lines)


def upsert_comment(existing_comments: list[dict], new_body: str) -> dict:
    """
    Find existing bot comment by marker; return create/update instruction.

    This function is side-effect-free so it can be tested without GitHub API calls.
    """
    for comment in existing_comments:
        if COMMENT_MARKER in comment.get("body", ""):
            return {"action": "update", "comment_id": comment["id"], "body": new_body}
    return {"action": "create", "body": new_body}
