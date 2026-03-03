"""Groq LLM adapter with strict contracts and safe fallback behavior.

Milestone-1 design goals:
- Provide typed request/response contracts.
- Keep deterministic evaluator as source of truth for final gate.
- Treat model output as untrusted input until validated.
- Fail safely with structured fallback objects for observability.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from groq import Groq
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.evaluator import CorpusChunk
from app.schemas import FeatureComplianceSpec

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class LLMFinding(BaseModel):
    """A single concrete issue identified by the model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=256)
    severity: str = Field(min_length=1, max_length=16)
    explanation: str = Field(min_length=1, max_length=4000)
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=25)

    @field_validator("severity")
    @classmethod
    def normalize_severity(cls, value: str) -> str:
        allowed = {"low", "medium", "high", "critical"}
        normalized = value.lower()
        if normalized not in allowed:
            raise ValueError(f"severity must be one of {sorted(allowed)}")
        return normalized


class LLMEvaluationOutput(BaseModel):
    """Strict contract expected from the model JSON output."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: str = Field(min_length=1, max_length=32)
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[LLMFinding] = Field(default_factory=list, max_length=50)
    remediation_hints: list[str] = Field(default_factory=list, max_length=25)
    evidence_chunk_ids: list[str] = Field(default_factory=list, max_length=50)
    summary: str = Field(min_length=1, max_length=5000)

    @field_validator("decision")
    @classmethod
    def normalize_decision(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"PASS", "REVIEW_REQUIRED", "FAIL"}
        if normalized not in allowed:
            raise ValueError(f"decision must be one of {sorted(allowed)}")
        return normalized

    @field_validator("remediation_hints")
    @classmethod
    def clean_hints(cls, values: list[str]) -> list[str]:
        # Stable, deduped remediation list keeps comments deterministic.
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = value.strip()
            if item and item not in seen:
                cleaned.append(item)
                seen.add(item)
        return cleaned

    @field_validator("evidence_chunk_ids")
    @classmethod
    def clean_evidence(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = value.strip()
            if item and item not in seen:
                cleaned.append(item)
                seen.add(item)
        return sorted(cleaned)


class LLMEvaluationRequest(BaseModel):
    """Internal LLM adapter request contract."""

    model_config = ConfigDict(extra="forbid")

    feature: FeatureComplianceSpec
    evidence_chunks: list[CorpusChunk] = Field(default_factory=list, max_length=20)
    correlation_id: str = Field(min_length=1, max_length=128)


class LLMAdapterResult(BaseModel):
    """Normalized adapter output consumed by API layer."""

    model_config = ConfigDict(extra="forbid")

    decision: str
    confidence: float
    findings: list[LLMFinding] = Field(default_factory=list)
    remediation_hints: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    summary: str
    provider: str = "groq"
    model: str
    error_type: str | None = None
    diagnostic: str | None = None
    fallback: bool = False
    attempts: int = Field(ge=1, le=10)
    latency_ms: int = Field(ge=0)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"PASS", "REVIEW_REQUIRED", "FAIL"}:
            raise ValueError("decision must be PASS/REVIEW_REQUIRED/FAIL")
        return normalized


@dataclass(frozen=True)
class GroqConfig:
    """Runtime configuration for Groq adapter."""

    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    max_retries: int
    backoff_seconds: float


def load_groq_config() -> GroqConfig:
    """Load and validate env-backed adapter configuration."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required when LLM adapter is enabled")

    model = os.environ.get("COMPLIANCE_GROQ_MODEL", "llama-3.3-70b").strip()
    if not model:
        raise RuntimeError("COMPLIANCE_GROQ_MODEL must be non-empty")

    base_url = os.environ.get("COMPLIANCE_GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip().rstrip("/")
    timeout_seconds = float(os.environ.get("COMPLIANCE_GROQ_TIMEOUT_SECONDS", "8"))
    max_retries = int(os.environ.get("COMPLIANCE_GROQ_MAX_RETRIES", "2"))
    backoff_seconds = float(os.environ.get("COMPLIANCE_GROQ_BACKOFF_SECONDS", "0.2"))

    if timeout_seconds <= 0:
        raise RuntimeError("COMPLIANCE_GROQ_TIMEOUT_SECONDS must be > 0")
    if max_retries < 0 or max_retries > 5:
        raise RuntimeError("COMPLIANCE_GROQ_MAX_RETRIES must be between 0 and 5")
    if backoff_seconds < 0:
        raise RuntimeError("COMPLIANCE_GROQ_BACKOFF_SECONDS must be >= 0")

    return GroqConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
    )


def build_llm_prompt(request: LLMEvaluationRequest) -> str:
    """Build deterministic prompt with sorted evidence and strict JSON schema request."""
    feature = request.feature
    evidence = sorted(request.evidence_chunks, key=lambda chunk: chunk.chunk_id)

    evidence_blocks = []
    for chunk in evidence:
        evidence_blocks.append(
            f"- chunk_id: {chunk.chunk_id}\n"
            f"  title: {chunk.title}\n"
            f"  tags: {', '.join(chunk.tags)}\n"
            f"  text: {chunk.text}"
        )
    evidence_text = "\n".join(evidence_blocks) if evidence_blocks else "- none"

    # Prompt includes schema constraints to maximize reliable JSON-only responses.
    return (
        "You are a compliance analyst for fintech feature reviews.\n"
        "Return ONLY valid JSON with keys: decision, confidence, summary, findings, remediation_hints, evidence_chunk_ids.\n"
        "Decision must be one of PASS, REVIEW_REQUIRED, FAIL.\n"
        "Confidence must be float 0..1.\n"
        "Do not include markdown.\n\n"
        f"Correlation ID: {request.correlation_id}\n"
        "Feature:\n"
        f"- feature_id: {feature.feature_id}\n"
        f"- feature_name: {feature.feature_name}\n"
        f"- owner_team: {feature.owner_team}\n"
        f"- data_classification: {feature.data_classification}\n"
        f"- jurisdictions: {', '.join(feature.jurisdictions)}\n"
        f"- controls: {', '.join(f'{c.id}:{c.status}' for c in feature.controls)}\n"
        f"- change_summary: {feature.change_summary}\n\n"
        "Evidence chunks:\n"
        f"{evidence_text}\n"
    )


class InvalidLLMOutputError(RuntimeError):
    """Raised when model output is missing/invalid JSON contract."""


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code in TRANSIENT_STATUS_CODES
    return False


def parse_llm_json_output(raw_text: str) -> LLMEvaluationOutput:
    """Parse untrusted model output text into strict contract object."""
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise InvalidLLMOutputError("LLM response was not valid JSON") from exc

    try:
        return LLMEvaluationOutput.model_validate(payload)
    except ValidationError as exc:
        raise InvalidLLMOutputError(
            f"LLM response contract validation failed: {exc.errors(include_url=False)}"
        ) from exc


def _extract_chat_completion_text(response: Any) -> str:
    """Extract assistant text from Groq chat completion object."""
    choices = getattr(response, "choices", None)
    if not choices:
        raise InvalidLLMOutputError("LLM response did not include choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    raise InvalidLLMOutputError("LLM response did not include text output")


def fallback_llm_result(
    *,
    model: str,
    attempts: int,
    error_type: str,
    diagnostic: str,
    latency_ms: int,
) -> LLMAdapterResult:
    """Return deterministic fallback object when provider call fails."""
    return LLMAdapterResult(
        decision="REVIEW_REQUIRED",
        confidence=0.0,
        findings=[],
        remediation_hints=["Manual compliance review required due to LLM unavailability."],
        evidence_chunk_ids=[],
        summary="LLM unavailable; fallback applied for safety.",
        provider="groq",
        model=model,
        error_type=error_type,
        diagnostic=diagnostic,
        fallback=True,
        attempts=attempts,
        latency_ms=latency_ms,
    )


def evaluate_with_groq(
    request: LLMEvaluationRequest,
    *,
    config: GroqConfig | None = None,
    logger: Callable[[dict[str, Any]], None] | None = None,
    client_factory: Callable[..., Any] = Groq,
) -> LLMAdapterResult:
    """Evaluate feature spec with Groq and return normalized adapter result."""
    cfg = config or load_groq_config()
    prompt = build_llm_prompt(request)
    attempts = cfg.max_retries + 1
    started_at = time.perf_counter()
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            parsed: LLMEvaluationOutput | None = None
            for json_attempt in range(2):
                client = client_factory(api_key=cfg.api_key, base_url=cfg.base_url, timeout=cfg.timeout_seconds)
                response = client.chat.completions.create(
                    model=cfg.model,
                    messages=[
                        {"role": "system", "content": "Return strict JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                try:
                    raw_text = _extract_chat_completion_text(response)
                    parsed = parse_llm_json_output(raw_text)
                    break
                except InvalidLLMOutputError as exc:
                    last_exc = exc
                    if json_attempt == 1:
                        raise

            if parsed is None:
                raise InvalidLLMOutputError("LLM response did not produce valid JSON")
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            result = LLMAdapterResult(
                decision=parsed.decision,
                confidence=parsed.confidence,
                findings=parsed.findings,
                remediation_hints=parsed.remediation_hints,
                evidence_chunk_ids=parsed.evidence_chunk_ids,
                summary=parsed.summary,
                provider="groq",
                model=cfg.model,
                attempts=attempt,
                latency_ms=latency_ms,
            )
            if logger is not None:
                logger(
                    {
                        "event": "llm.success",
                        "correlation_id": request.correlation_id,
                        "provider": "groq",
                        "model": cfg.model,
                        "attempts": attempt,
                        "latency_ms": latency_ms,
                    }
                )
            return result
        except Exception as exc:  # noqa: BLE001 - adapter handles all provider-level failures.
            last_exc = exc
            retryable = _is_retryable_exception(exc)
            if logger is not None:
                logger(
                    {
                        "event": "llm.failure",
                        "correlation_id": request.correlation_id,
                            "provider": "groq",
                        "model": cfg.model,
                        "attempt": attempt,
                        "retryable": retryable,
                        # Keep diagnostics short/safe; never log prompt text or API key.
                        "error_type": type(exc).__name__,
                    }
                )
            if not retryable:
                break
            if attempt < attempts:
                time.sleep(cfg.backoff_seconds * attempt)

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    error_type = "invalid_output" if isinstance(last_exc, InvalidLLMOutputError) else "provider_error"
    return fallback_llm_result(
        model=cfg.model,
        attempts=attempts,
        error_type=error_type,
        diagnostic=str(last_exc)[:500] if last_exc is not None else "unknown",
        latency_ms=latency_ms,
    )


def evaluate_with_openai(
    request: LLMEvaluationRequest,
    *,
    config: GroqConfig | None = None,
    logger: Callable[[dict[str, Any]], None] | None = None,
    client_factory: Callable[..., Any] = Groq,
) -> LLMAdapterResult:
    """Backward-compatible alias for older call sites/tests."""
    return evaluate_with_groq(
        request,
        config=config,
        logger=logger,
        client_factory=client_factory,
    )
