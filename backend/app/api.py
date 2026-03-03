"""FastAPI application for PR-level compliance evaluation."""

from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ci import determine_pr_gate, render_pr_comment
from app.evaluator import CorpusChunk, DEFAULT_CORPUS, evaluate_feature_spec, retrieve_relevant_chunks
from app.fusion import FusionInput, fuse_decision
from app.llm_adapter import LLMEvaluationRequest, evaluate_with_groq
from app.corpus_parser import CorpusValidationError, parse_corpus_yaml
from app.parser import SpecValidationError, parse_feature_spec_yaml
from app.rate_limiter import SlidingWindowRateLimiter
from app.storage import ComplianceStore, EvaluationRecord

app = FastAPI(title="Compliance CI Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _get_store() -> ComplianceStore:
    db_path = Path(os.environ.get("COMPLIANCE_DB_PATH", "data/compliance.db"))
    return ComplianceStore(db_path)


def _get_corpus_for_evaluation() -> tuple[CorpusChunk, ...]:
    """
    Return the corpus to use for evaluations. Prefers the latest uploaded corpus
    from the DB if it has chunks; otherwise falls back to DEFAULT_CORPUS.
    """
    store = _get_store()
    latest = store.get_latest_corpus_version_with_chunks()
    if latest is None:
        return DEFAULT_CORPUS
    version_id, chunk_dicts = latest
    return tuple(
        CorpusChunk(
            chunk_id=c["chunk_id"],
            title=c["title"],
            text=c["text"],
            tags=tuple(c.get("tags") or []),
            corpus_version=version_id,
        )
        for c in chunk_dicts
    )


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


class FeatureWithLatestDecisionResponse(BaseModel):
    """Feature contract returned for frontend feature lists."""

    model_config = ConfigDict(extra="forbid")

    feature_id: str
    feature_name: str
    owner_team: str
    data_classification: str
    jurisdictions: list[str] = Field(default_factory=list)
    controls: list[dict] = Field(default_factory=list)
    change_summary: str
    spec_version: str
    active: bool
    created_at: str
    path: str
    latest_decision: str | None = None
    latest_risk_score: int | None = None
    latest_evaluated_at: str | None = None
    latest_corpus_version: str | None = None


class FeatureListResponse(BaseModel):
    """Collection response for feature list queries."""

    features: list[FeatureWithLatestDecisionResponse] = Field(default_factory=list)


class EvaluationReadResponse(BaseModel):
    """Evaluation contract returned by read endpoints."""

    model_config = ConfigDict(extra="forbid")

    feature_id: str
    spec_version: str
    corpus_version: str
    risk_score: int = Field(ge=0, le=100)
    decision: str
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    reasoning_summary: str
    commit_sha: str
    evaluated_at: str
    deterministic_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    llm_decision: str | None = None
    llm_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    llm_fallback: bool | None = None
    llm_error_type: str | None = None
    llm_model: str | None = None
    llm_attempts: int | None = Field(default=None, ge=1, le=10)
    fused_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    fused_reason_codes: list[str] = Field(default_factory=list)
    fused_explanation: str | None = None
    remediation_hints: list[str] = Field(default_factory=list)


class EvaluationsListResponse(BaseModel):
    """Collection response for evaluations list queries."""

    evaluations: list[EvaluationReadResponse] = Field(default_factory=list)


class FeatureDetailResponse(BaseModel):
    """Feature detail payload with evaluation history."""

    feature: FeatureWithLatestDecisionResponse
    evaluations: list[EvaluationReadResponse] = Field(default_factory=list)


class CorpusVersionResponse(BaseModel):
    """Corpus version payload."""

    version_id: str
    source_set: str
    released_at: str


class CorpusVersionListResponse(BaseModel):
    """Collection response for corpus versions."""

    corpus_versions: list[CorpusVersionResponse] = Field(default_factory=list)


class CorpusUploadResponse(BaseModel):
    """Response after a successful corpus upload."""

    version_id: str
    source_set: str
    released_at: str
    chunk_count: int
    chunk_ids: list[str] = Field(default_factory=list)


class ReevaluationResultResponse(BaseModel):
    """Reevaluation result payload."""

    job_id: str
    feature_id: str
    previous_decision: str
    new_decision: str
    regressed: bool
    details: dict = Field(default_factory=dict)
    created_at: str


class ReevaluationResultListResponse(BaseModel):
    """Collection response for reevaluation results."""

    results: list[ReevaluationResultResponse] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe endpoint."""
    return {"status": "ok"}


@app.get("/v1/features", response_model=FeatureListResponse)
def list_features() -> FeatureListResponse:
    """Return active features merged with latest evaluation metadata."""
    store = _get_store()
    return FeatureListResponse(features=store.list_active_features_with_latest())


@app.get("/v1/features/{feature_id}", response_model=FeatureDetailResponse)
def get_feature_detail(feature_id: str) -> FeatureDetailResponse:
    """Return one active feature and its evaluation history."""
    store = _get_store()
    spec = store.get_latest_feature_spec(feature_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {feature_id}")
    payload = spec["parsed_payload"]
    feature = FeatureWithLatestDecisionResponse(
        feature_id=payload.get("feature_id", feature_id),
        feature_name=payload.get("feature_name", feature_id),
        owner_team=payload.get("owner_team", "unknown"),
        data_classification=payload.get("data_classification", "internal"),
        jurisdictions=payload.get("jurisdictions", []),
        controls=payload.get("controls", []),
        change_summary=payload.get("change_summary", ""),
        spec_version=spec["spec_version"],
        active=spec["active"],
        created_at=spec["created_at"],
        path=spec["path"],
    )
    evaluations = store.list_evaluations(feature_id=feature_id, limit=200)
    return FeatureDetailResponse(feature=feature, evaluations=evaluations)


@app.get("/v1/evaluations", response_model=EvaluationsListResponse)
def list_evaluations(
    limit: int = 100,
    offset: int = 0,
    feature_id: str | None = None,
) -> EvaluationsListResponse:
    """Return evaluation history, globally or for one feature."""
    store = _get_store()
    rows = store.list_evaluations(limit=limit, offset=offset, feature_id=feature_id)
    return EvaluationsListResponse(evaluations=rows)


@app.get("/v1/corpus-versions", response_model=CorpusVersionListResponse)
def list_corpus_versions(limit: int = 100) -> CorpusVersionListResponse:
    """Return known corpus versions, newest first."""
    store = _get_store()
    return CorpusVersionListResponse(corpus_versions=store.list_corpus_versions(limit=limit))


@app.post("/v1/corpus-versions/upload", response_model=CorpusUploadResponse)
async def upload_corpus(file: UploadFile = File(..., description="Corpus YAML file")) -> CorpusUploadResponse:
    """
    Upload a corpus YAML file. The file must define version_id, source_set, and chunks.

    Example format:
        version_id: v2
        source_set: "User uploaded"
        chunks:
          - chunk_id: REG-001
            title: Regulation title
            text: Regulation body text.
            tags: [US, KYC]
    """
    if not file.filename or not (file.filename.endswith(".yml") or file.filename.endswith(".yaml")):
        raise HTTPException(
            status_code=400,
            detail="File must be a YAML file (.yml or .yaml)",
        )
    size = 0
    chunks_list: list[bytes] = []
    max_size = 500_000  # 500KB
    while chunk := await file.read(8192):
        size += len(chunk)
        if size > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"Corpus file exceeds maximum size of {max_size // 1024}KB",
            )
        chunks_list.append(chunk)
    raw = b"".join(chunks_list).decode("utf-8", errors="replace")
    try:
        parsed = parse_corpus_yaml(raw)
    except CorpusValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    store = _get_store()
    chunk_dicts = [
        {
            "chunk_id": c.chunk_id,
            "title": c.title,
            "text": c.text,
            "tags": list(c.tags),
        }
        for c in parsed.chunks
    ]
    store.upsert_corpus_version_with_chunks(
        version_id=parsed.version_id,
        source_set=parsed.source_set,
        chunks=chunk_dicts,
    )
    meta = store.get_corpus_version(parsed.version_id)
    released_at = meta["released_at"] if meta else ""
    return CorpusUploadResponse(
        version_id=parsed.version_id,
        source_set=parsed.source_set,
        released_at=released_at,
        chunk_count=len(parsed.chunks),
        chunk_ids=[c.chunk_id for c in parsed.chunks],
    )


@app.get("/v1/reevaluation-results", response_model=ReevaluationResultListResponse)
def list_reevaluation_results(
    job_id: str | None = None,
    regressed_only: bool = False,
    limit: int = 200,
) -> ReevaluationResultListResponse:
    """Return reevaluation results for one job or globally."""
    store = _get_store()
    if job_id:
        rows = store.list_reevaluation_results(job_id)
    else:
        rows = store.list_reevaluation_results_all(regressed_only=regressed_only, limit=limit)
    return ReevaluationResultListResponse(results=rows)


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
    corpus = _get_corpus_for_evaluation()
    for changed_spec in payload.specs:
        try:
            parsed = parse_feature_spec_yaml(changed_spec.spec_yaml)
            evaluation = evaluate_feature_spec(parsed, corpus=corpus)
            deterministic_confidence = max(0.0, min(1.0, 1.0 - (evaluation.risk_score / 100.0)))
            final_decision = evaluation.decision
            llm_observation: dict | None = None
            fusion_observation: dict | None = None
            if llm_enabled:
                evidence_chunks = retrieve_relevant_chunks(parsed, corpus=corpus, limit=10)
                llm_result = evaluate_with_groq(
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
                    llm_model=os.environ.get("COMPLIANCE_GROQ_MODEL", "llama-3.3-70b") if llm_observation else None,
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
