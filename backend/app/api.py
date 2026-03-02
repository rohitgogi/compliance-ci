"""FastAPI application for PR-level compliance evaluation."""

from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ci import determine_pr_gate, render_pr_comment
from app.evaluator import evaluate_feature_spec
from app.llm_adapter import LLMEvaluationRequest, evaluate_with_openai
from app.parser import SpecValidationError, parse_feature_spec_yaml

app = FastAPI(title="Compliance CI Backend", version="0.1.0")


class ChangedSpecInput(BaseModel):
    """A single changed YAML file from a PR diff."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    path: str = Field(min_length=1, max_length=512)
    spec_yaml: str = Field(min_length=1, max_length=100_000)

    @field_validator("path")
    @classmethod
    def validate_spec_path(cls, value: str) -> str:
        """Only allow feature spec files under backend/features to limit CI scope."""
        normalized = value.strip()
        if ".." in normalized:
            raise ValueError("path traversal is not allowed")
        if not normalized.startswith("backend/features/"):
            raise ValueError("path must be under backend/features/")
        if not (normalized.endswith(".yml") or normalized.endswith(".yaml")):
            raise ValueError("path must point to a YAML file")
        return normalized


class EvaluatePRRequest(BaseModel):
    """Payload sent by GitHub Action for PR-level evaluation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    repo: str = Field(min_length=1, max_length=256)
    pr_number: int = Field(gt=0, le=1_000_000_000)
    commit_sha: str = Field(min_length=7, max_length=64)
    specs: list[ChangedSpecInput] = Field(min_length=1, max_length=200)


class FeatureEvaluationResponse(BaseModel):
    """Per-feature evaluation result returned to CI."""

    path: str
    feature_id: str | None = None
    decision: str | None = None
    risk_score: int | None = None
    evidence_chunk_ids: list[str] = []
    reasoning_summary: str | None = None
    llm_observation: dict | None = None
    error: str | None = None
    validation_details: list[dict] = []


class EvaluatePRResponse(BaseModel):
    """Full CI response for all changed specs in a PR."""

    repo: str
    pr_number: int
    commit_sha: str
    final_gate: str
    comment_markdown: str
    llm_adapter_enabled: bool = False
    results: list[FeatureEvaluationResponse]


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe endpoint."""
    return {"status": "ok"}


@app.post("/v1/evaluate-pr", response_model=EvaluatePRResponse)
def evaluate_pr(payload: EvaluatePRRequest) -> EvaluatePRResponse:
    """
    Evaluate all changed feature specs in a PR.

    Partial failure is explicit by design: one invalid spec should not suppress
    evaluation of other changed specs.
    """
    results: list[FeatureEvaluationResponse] = []
    llm_enabled = os.environ.get("COMPLIANCE_LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
    for changed_spec in payload.specs:
        try:
            parsed = parse_feature_spec_yaml(changed_spec.spec_yaml)
            evaluation = evaluate_feature_spec(parsed)
            llm_observation: dict | None = None
            if llm_enabled:
                # Milestone-1: observational only. Final gate remains deterministic.
                llm_result = evaluate_with_openai(
                    LLMEvaluationRequest(
                        feature=parsed,
                        evidence_chunks=[],
                        correlation_id=f"pr-{payload.pr_number}:{parsed.feature_id}",
                    )
                )
                llm_observation = {
                    "decision": llm_result.decision,
                    "confidence": llm_result.confidence,
                    "summary": llm_result.summary,
                    "fallback": llm_result.fallback,
                    "error_type": llm_result.error_type,
                    "attempts": llm_result.attempts,
                }
            results.append(
                FeatureEvaluationResponse(
                    path=changed_spec.path,
                    feature_id=evaluation.feature_id,
                    decision=evaluation.decision,
                    risk_score=evaluation.risk_score,
                    evidence_chunk_ids=evaluation.evidence_chunk_ids,
                    reasoning_summary=evaluation.reasoning_summary,
                    llm_observation=llm_observation,
                )
            )
        except SpecValidationError as exc:
            results.append(
                FeatureEvaluationResponse(
                    path=changed_spec.path,
                    error=exc.message,
                    validation_details=exc.details,
                )
            )

    final_gate = determine_pr_gate(results)
    comment_markdown = render_pr_comment(results, gate=final_gate)

    return EvaluatePRResponse(
        repo=payload.repo,
        pr_number=payload.pr_number,
        commit_sha=payload.commit_sha,
        final_gate=final_gate,
        comment_markdown=comment_markdown,
        llm_adapter_enabled=llm_enabled,
        results=results,
    )
