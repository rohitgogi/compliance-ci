"""FastAPI application for PR-level compliance evaluation."""

from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ci import determine_pr_gate, render_pr_comment
from app.evaluator import evaluate_feature_spec, retrieve_relevant_chunks
from app.fusion import FusionInput, fuse_decision
from app.llm_adapter import LLMEvaluationRequest, evaluate_with_openai
from app.parser import SpecValidationError, parse_feature_spec_yaml
from app.rate_limiter import SlidingWindowRateLimiter
from app.storage import ComplianceStore, EvaluationRecord

app = FastAPI(title="Compliance CI Backend", version="0.1.0")


@lru_cache(maxsize=1)
def _get_store() -> ComplianceStore:
    db_path = Path(os.environ.get("COMPLIANCE_DB_PATH", "data/compliance.db"))
    return ComplianceStore(db_path)


@lru_cache(maxsize=1)
def _get_rate_limiter() -> SlidingWindowRateLimiter | None:
    """
    Build endpoint rate limiter from env.

    COMPLIANCE_RATE_LIMIT_PER_MINUTE <= 0 disables in-process limiting.
    """
    limit = int(os.environ.get("COMPLIANCE_RATE_LIMIT_PER_MINUTE", "120"))
    if limit <= 0:
        return None
    return SlidingWindowRateLimiter(max_requests=limit, window_seconds=60)


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

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", normalized):
            raise ValueError("repo must match owner/repository format")
        return normalized

    @field_validator("commit_sha")
    @classmethod
    def validate_commit_sha(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{7,64}", normalized):
            raise ValueError("commit_sha must be a 7-64 char hexadecimal string")
        return normalized


class LLMObservation(BaseModel):
    """Observed LLM metadata included in API output."""

    model_config = ConfigDict(extra="forbid")

    decision: str
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str | None = Field(default=None, max_length=5000)
    fallback: bool
    error_type: str | None = Field(default=None, max_length=128)
    attempts: int = Field(ge=1, le=10)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"PASS", "REVIEW_REQUIRED", "FAIL"}:
            raise ValueError("llm observation decision must be PASS/REVIEW_REQUIRED/FAIL")
        return normalized


class FusionObservation(BaseModel):
    """Observed fusion metadata included in API output."""

    model_config = ConfigDict(extra="forbid")

    final_decision: str
    fused_confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list, max_length=20)
    explanation: str = Field(min_length=1, max_length=5000)
    remediation_hints: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("final_decision")
    @classmethod
    def validate_final_decision(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"PASS", "REVIEW_REQUIRED", "FAIL"}:
            raise ValueError("fusion final_decision must be PASS/REVIEW_REQUIRED/FAIL")
        return normalized


class FeatureEvaluationResponse(BaseModel):
    """Per-feature evaluation result returned to CI."""

    model_config = ConfigDict(extra="forbid")

    path: str
    feature_id: str | None = None
    decision: str | None = None
    risk_score: int | None = None
    deterministic_confidence: float | None = None
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    reasoning_summary: str | None = None
    llm_observation: LLMObservation | None = None
    fusion_observation: FusionObservation | None = None
    error: str | None = None
    validation_details: list[dict] = Field(default_factory=list)


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
def evaluate_pr(payload: EvaluatePRRequest, request: Request) -> EvaluatePRResponse:
    """
    Evaluate all changed feature specs in a PR.

    Partial failure is explicit by design: one invalid spec should not suppress
    evaluation of other changed specs.
    """
    limiter = _get_rate_limiter()
    if limiter is not None:
        client_host = request.client.host if request.client is not None else "unknown"
        rate_key = f"{client_host}:{payload.repo}"
        if not limiter.allow(rate_key):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded for evaluate-pr endpoint",
            )

    results: list[FeatureEvaluationResponse] = []
    llm_enabled = os.environ.get("COMPLIANCE_LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
    store = _get_store()
    for changed_spec in payload.specs:
        try:
            parsed = parse_feature_spec_yaml(changed_spec.spec_yaml)
            evaluation = evaluate_feature_spec(parsed)
            deterministic_confidence = max(0.0, min(1.0, 1.0 - (evaluation.risk_score / 100.0)))
            final_decision = evaluation.decision
            llm_observation: dict | None = None
            fusion_observation: dict | None = None
            if llm_enabled:
                evidence_chunks = retrieve_relevant_chunks(parsed, limit=10)
                llm_result = evaluate_with_openai(
                    LLMEvaluationRequest(
                        feature=parsed,
                        evidence_chunks=evidence_chunks,
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
                fusion_result = fuse_decision(
                    FusionInput(
                        deterministic_decision=evaluation.decision,
                        deterministic_confidence=deterministic_confidence,
                        llm_decision=llm_result.decision,
                        llm_confidence=llm_result.confidence,
                        llm_fallback=llm_result.fallback,
                        llm_findings=[finding.title for finding in llm_result.findings],
                        llm_remediation_hints=llm_result.remediation_hints,
                    )
                )
                final_decision = fusion_result.final_decision.value
                fusion_observation = {
                    "final_decision": fusion_result.final_decision.value,
                    "fused_confidence": fusion_result.fused_confidence,
                    "reason_codes": [reason.value for reason in fusion_result.reason_codes],
                    "explanation": fusion_result.explanation,
                    "remediation_hints": fusion_result.remediation_hints,
                }

            spec_hash = hashlib.sha256(changed_spec.spec_yaml.encode("utf-8")).hexdigest()
            spec_version = payload.commit_sha[:12]
            parsed_payload = parsed.model_dump(mode="python")
            store.upsert_feature_spec(
                feature_id=parsed.feature_id,
                spec_version=spec_version,
                content_hash=spec_hash,
                path=changed_spec.path,
                parsed_payload=parsed_payload,
                active=True,
            )
            store.record_evaluation(
                EvaluationRecord(
                    feature_id=parsed.feature_id,
                    spec_version=spec_version,
                    corpus_version=evaluation.corpus_version,
                    risk_score=evaluation.risk_score,
                    decision=final_decision,
                    evidence_chunk_ids=evaluation.evidence_chunk_ids,
                    reasoning_summary=evaluation.reasoning_summary,
                    commit_sha=payload.commit_sha,
                    deterministic_confidence=deterministic_confidence,
                    llm_decision=llm_observation.get("decision") if llm_observation else None,
                    llm_confidence=llm_observation.get("confidence") if llm_observation else None,
                    llm_fallback=llm_observation.get("fallback") if llm_observation else None,
                    llm_error_type=llm_observation.get("error_type") if llm_observation else None,
                    llm_model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini") if llm_observation else None,
                    llm_attempts=llm_observation.get("attempts") if llm_observation else None,
                    fused_confidence=fusion_observation.get("fused_confidence") if fusion_observation else None,
                    fused_reason_codes=fusion_observation.get("reason_codes") if fusion_observation else None,
                    fused_explanation=fusion_observation.get("explanation") if fusion_observation else None,
                    remediation_hints=fusion_observation.get("remediation_hints") if fusion_observation else None,
                )
            )
            results.append(
                FeatureEvaluationResponse(
                    path=changed_spec.path,
                    feature_id=evaluation.feature_id,
                    decision=final_decision,
                    risk_score=evaluation.risk_score,
                    deterministic_confidence=deterministic_confidence,
                    evidence_chunk_ids=evaluation.evidence_chunk_ids,
                    reasoning_summary=evaluation.reasoning_summary,
                    llm_observation=llm_observation,
                    fusion_observation=fusion_observation,
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
