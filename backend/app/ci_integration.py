"""Helpers used by GitHub Action to call backend safely."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

TRANSIENT_STATUS_CODES = {500, 502, 503, 504}


class FeatureResultContract(BaseModel):
    """Contract for per-feature responses consumed by CI gate logic."""

    model_config = ConfigDict(extra="forbid")

    path: str
    feature_id: str | None = None
    decision: str | None = None
    risk_score: int | None = None
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    reasoning_summary: str | None = None
    deterministic_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    llm_observation: dict[str, Any] | None = None
    fusion_observation: dict[str, Any] | None = None
    error: str | None = None
    validation_details: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str | None) -> str | None:
        if value is None:
            return value
        allowed = {"PASS", "REVIEW_REQUIRED", "FAIL"}
        if value not in allowed:
            raise ValueError(f"decision must be one of {sorted(allowed)}")
        return value

    @field_validator("risk_score")
    @classmethod
    def validate_risk_score(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if not 0 <= value <= 100:
            raise ValueError("risk_score must be within 0-100")
        return value

    @field_validator("llm_observation")
    @classmethod
    def validate_llm_observation(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        required = {"decision", "confidence", "fallback", "attempts"}
        missing = required - set(value.keys())
        if missing:
            raise ValueError(f"llm_observation missing required keys: {sorted(missing)}")
        decision = str(value["decision"]).upper()
        if decision not in {"PASS", "REVIEW_REQUIRED", "FAIL"}:
            raise ValueError("llm_observation decision invalid")
        confidence = float(value["confidence"])
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError("llm_observation confidence must be within 0-1")
        attempts = int(value["attempts"])
        if attempts < 1 or attempts > 10:
            raise ValueError("llm_observation attempts must be 1-10")
        value["decision"] = decision
        value["confidence"] = confidence
        value["attempts"] = attempts
        value["fallback"] = bool(value["fallback"])
        return value

    @field_validator("fusion_observation")
    @classmethod
    def validate_fusion_observation(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value
        required = {"final_decision", "fused_confidence", "reason_codes", "explanation", "remediation_hints"}
        missing = required - set(value.keys())
        if missing:
            raise ValueError(f"fusion_observation missing required keys: {sorted(missing)}")
        final_decision = str(value["final_decision"]).upper()
        if final_decision not in {"PASS", "REVIEW_REQUIRED", "FAIL"}:
            raise ValueError("fusion_observation final_decision invalid")
        fused_confidence = float(value["fused_confidence"])
        if fused_confidence < 0.0 or fused_confidence > 1.0:
            raise ValueError("fusion_observation fused_confidence must be within 0-1")
        if not isinstance(value["reason_codes"], list):
            raise ValueError("fusion_observation reason_codes must be a list")
        if not isinstance(value["remediation_hints"], list):
            raise ValueError("fusion_observation remediation_hints must be a list")
        value["final_decision"] = final_decision
        value["fused_confidence"] = fused_confidence
        return value


class EvaluationResponseContract(BaseModel):
    """Contract for backend response consumed by GitHub workflow."""

    model_config = ConfigDict(extra="forbid")

    repo: str
    pr_number: int
    commit_sha: str
    final_gate: str
    comment_markdown: str
    llm_adapter_enabled: bool = False
    results: list[FeatureResultContract]

    @field_validator("final_gate")
    @classmethod
    def validate_final_gate(cls, value: str) -> str:
        allowed = {"PASS", "REVIEW_REQUIRED", "FAIL"}
        if value not in allowed:
            raise ValueError(f"final_gate must be one of {sorted(allowed)}")
        return value

    @field_validator("results")
    @classmethod
    def validate_results_contract(cls, values: list[FeatureResultContract]) -> list[FeatureResultContract]:
        for item in values:
            if item.error:
                continue
            if item.decision is None or item.risk_score is None:
                raise ValueError("result must include decision and risk_score when error is absent")
        return values


def filter_changed_spec_paths(changed_paths: list[str]) -> list[str]:
    """Allow only feature spec files under backend/features directory."""
    filtered_set: set[str] = set()
    for raw_path in changed_paths:
        normalized = raw_path.strip()
        if not normalized:
            continue
        if ".." in normalized:
            # Skip suspicious paths to avoid accidental path traversal reads.
            continue
        if normalized.startswith("backend/features/") and (
            normalized.endswith(".yml") or normalized.endswith(".yaml")
        ):
            filtered_set.add(normalized)
    return sorted(filtered_set)


def build_evaluate_payload(
    repo: str,
    pr_number: int,
    commit_sha: str,
    base_dir: Path,
    changed_paths: list[str],
) -> dict:
    """Read changed YAML files from repo and construct evaluator payload."""
    specs = []
    for relative_path in filter_changed_spec_paths(changed_paths):
        full_path = base_dir / relative_path
        if not full_path.exists():
            # Ignore deleted files; evaluator should run only on currently present specs.
            continue
        try:
            spec_yaml = full_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to read changed spec file: {relative_path}") from exc
        if not spec_yaml.strip():
            raise RuntimeError(f"Spec file is empty: {relative_path}")

        specs.append(
            {
                "path": relative_path,
                "spec_yaml": spec_yaml,
            }
        )

    return {
        "payload_version": "v1",
        "repo": repo,
        "pr_number": pr_number,
        "commit_sha": commit_sha,
        "specs": specs,
    }


def validate_evaluation_response(response: dict[str, Any]) -> dict[str, Any]:
    """Validate backend contract and return normalized dictionary."""
    try:
        model = EvaluationResponseContract.model_validate(response)
    except ValidationError as exc:
        raise RuntimeError(
            f"Backend response contract validation failed: {exc.errors(include_url=False)}"
        ) from exc
    return model.model_dump()


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_STATUS_CODES
    return False


def submit_evaluation(
    backend_url: str,
    payload: dict,
    timeout_seconds: float = 10.0,
    max_retries: int = 2,
    backoff_seconds: float = 0.2,
) -> dict:
    """
    Submit payload to backend with bounded retries for transient failures.

    4xx errors fail immediately because they represent caller-side contract errors.
    """
    attempts = max_retries + 1
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.post(f"{backend_url.rstrip('/')}/v1/evaluate-pr", json=payload)
                response.raise_for_status()
                parsed = response.json()
                return validate_evaluation_response(parsed)
        except httpx.HTTPStatusError as exc:
            if not _is_retryable_exception(exc):
                raise RuntimeError(
                    f"Failed to call compliance backend: non-retryable status {exc.response.status_code}"
                ) from exc
            last_exc = exc
        except httpx.HTTPError as exc:
            if not _is_retryable_exception(exc):
                raise RuntimeError(f"Failed to call compliance backend: {exc}") from exc
            last_exc = exc
        except RuntimeError:
            # Contract validation failures are non-retryable.
            raise

        if attempt < attempts:
            time.sleep(backoff_seconds * attempt)

    raise RuntimeError(f"Failed to call compliance backend after {attempts} attempts: {last_exc}")
