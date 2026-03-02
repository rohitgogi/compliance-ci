"""Pure-function decision and confidence fusion policy module.

Milestone-2 scope:
- Encode conservative policy matrix in one deterministic module.
- Provide typed IO contracts and reason codes for later API/comment integration.
- Keep existing API gate behavior unchanged until Milestone-3 wiring.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Decision(str, Enum):
    """Supported compliance gate states."""

    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAIL = "FAIL"


class FusionReason(str, Enum):
    """Machine-readable policy rationale codes."""

    PASS_THRESHOLD_MET = "PASS_THRESHOLD_MET"
    PASS_THRESHOLD_MISS = "PASS_THRESHOLD_MISS"
    MIXED_SIGNAL_REVIEW = "MIXED_SIGNAL_REVIEW"
    DOUBLE_FAIL = "DOUBLE_FAIL"
    CONSERVATIVE_DEFAULT_REVIEW = "CONSERVATIVE_DEFAULT_REVIEW"
    LLM_FALLBACK_CONSERVATIVE = "LLM_FALLBACK_CONSERVATIVE"


class FusionInput(BaseModel):
    """Fusion input contract combining deterministic and LLM signals."""

    model_config = ConfigDict(extra="forbid")

    deterministic_decision: Decision
    deterministic_confidence: float = Field(ge=0.0, le=1.0)
    llm_decision: Decision
    llm_confidence: float = Field(ge=0.0, le=1.0)
    llm_fallback: bool = False
    llm_findings: list[str] = Field(default_factory=list)
    llm_remediation_hints: list[str] = Field(default_factory=list)


class FusionOutput(BaseModel):
    """Fusion output contract consumed by higher layers."""

    model_config = ConfigDict(extra="forbid")

    final_decision: Decision
    fused_confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: list[FusionReason] = Field(min_length=1)
    explanation: str
    remediation_hints: list[str] = Field(default_factory=list)

    @field_validator("reason_codes")
    @classmethod
    def dedupe_reason_codes(cls, values: list[FusionReason]) -> list[FusionReason]:
        deduped: list[FusionReason] = []
        seen: set[FusionReason] = set()
        for value in values:
            if value not in seen:
                deduped.append(value)
                seen.add(value)
        return deduped


def normalize_confidence_percent(percent_value: float) -> float:
    """Convert percent-scale confidence to canonical `[0,1]` float."""
    if percent_value < 0 or percent_value > 100:
        raise ValueError("Percent confidence must be between 0 and 100")
    return percent_value / 100.0


def compute_fused_confidence(
    deterministic_confidence: float,
    llm_confidence: float,
    deterministic_weight: float = 0.4,
    llm_weight: float = 0.6,
) -> float:
    """Compute weighted fused confidence and clamp to `[0,1]`."""
    raw = deterministic_confidence * deterministic_weight + llm_confidence * llm_weight
    return max(0.0, min(1.0, raw))


def _build_explanation(reason_codes: list[FusionReason]) -> str:
    parts: list[str] = []
    mapping = {
        FusionReason.PASS_THRESHOLD_MET: "Both deterministic and LLM decisions are PASS with sufficient confidence.",
        FusionReason.PASS_THRESHOLD_MISS: "Both signals are PASS but fused confidence is below threshold.",
        FusionReason.MIXED_SIGNAL_REVIEW: "Deterministic and LLM signals differ, so conservative review is required.",
        FusionReason.DOUBLE_FAIL: "Both deterministic and LLM signals indicate FAIL.",
        FusionReason.CONSERVATIVE_DEFAULT_REVIEW: "Conservative policy selected REVIEW_REQUIRED for this combination.",
        FusionReason.LLM_FALLBACK_CONSERVATIVE: "LLM fallback was active, so the policy prevented automatic PASS.",
    }
    for code in reason_codes:
        parts.append(mapping[code])
    return " ".join(parts)


def _build_remediation_hints(input_data: FusionInput, reason_codes: list[FusionReason]) -> list[str]:
    hints: list[str] = []
    if FusionReason.MIXED_SIGNAL_REVIEW in reason_codes:
        hints.append("Review conflicting deterministic and LLM findings before merge.")
    if FusionReason.PASS_THRESHOLD_MISS in reason_codes:
        hints.append("Increase evidence quality to raise confidence above the pass threshold.")
    if FusionReason.DOUBLE_FAIL in reason_codes:
        hints.append("Address high-severity compliance gaps before re-submitting.")
    if FusionReason.LLM_FALLBACK_CONSERVATIVE in reason_codes:
        hints.append("Retry evaluation once LLM service is healthy or request manual review.")
    hints.extend(input_data.llm_remediation_hints)

    # Deterministic dedupe for stable outputs.
    deduped: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        normalized = hint.strip()
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped


def fuse_decision(input_data: FusionInput, pass_threshold: float = 0.75) -> FusionOutput:
    """Apply conservative policy matrix to produce final decision."""
    fused_confidence = compute_fused_confidence(
        deterministic_confidence=input_data.deterministic_confidence,
        llm_confidence=input_data.llm_confidence,
    )
    reason_codes: list[FusionReason] = []

    # Safety override during LLM fallback: never auto-pass.
    if input_data.llm_fallback:
        reason_codes.append(FusionReason.LLM_FALLBACK_CONSERVATIVE)
        final_decision = Decision.REVIEW_REQUIRED
        reason_codes.append(FusionReason.CONSERVATIVE_DEFAULT_REVIEW)
        return FusionOutput(
            final_decision=final_decision,
            fused_confidence=fused_confidence,
            reason_codes=reason_codes,
            explanation=_build_explanation(reason_codes),
            remediation_hints=_build_remediation_hints(input_data, reason_codes),
        )

    if (
        input_data.deterministic_decision == Decision.PASS
        and input_data.llm_decision == Decision.PASS
    ):
        if fused_confidence >= pass_threshold:
            reason_codes.append(FusionReason.PASS_THRESHOLD_MET)
            final_decision = Decision.PASS
        else:
            reason_codes.append(FusionReason.PASS_THRESHOLD_MISS)
            final_decision = Decision.REVIEW_REQUIRED
        return FusionOutput(
            final_decision=final_decision,
            fused_confidence=fused_confidence,
            reason_codes=reason_codes,
            explanation=_build_explanation(reason_codes),
            remediation_hints=_build_remediation_hints(input_data, reason_codes),
        )

    if input_data.deterministic_decision == Decision.FAIL and input_data.llm_decision == Decision.FAIL:
        reason_codes.append(FusionReason.DOUBLE_FAIL)
        final_decision = Decision.FAIL
        return FusionOutput(
            final_decision=final_decision,
            fused_confidence=fused_confidence,
            reason_codes=reason_codes,
            explanation=_build_explanation(reason_codes),
            remediation_hints=_build_remediation_hints(input_data, reason_codes),
        )

    if (
        {input_data.deterministic_decision, input_data.llm_decision}
        in [
            {Decision.PASS, Decision.FAIL},
            {Decision.PASS, Decision.REVIEW_REQUIRED},
        ]
    ):
        reason_codes.append(FusionReason.MIXED_SIGNAL_REVIEW)
        final_decision = Decision.REVIEW_REQUIRED
        return FusionOutput(
            final_decision=final_decision,
            fused_confidence=fused_confidence,
            reason_codes=reason_codes,
            explanation=_build_explanation(reason_codes),
            remediation_hints=_build_remediation_hints(input_data, reason_codes),
        )

    reason_codes.append(FusionReason.CONSERVATIVE_DEFAULT_REVIEW)
    final_decision = Decision.REVIEW_REQUIRED
    return FusionOutput(
        final_decision=final_decision,
        fused_confidence=fused_confidence,
        reason_codes=reason_codes,
        explanation=_build_explanation(reason_codes),
        remediation_hints=_build_remediation_hints(input_data, reason_codes),
    )
