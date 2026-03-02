"""Corpus update trigger and regression-report logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.storage import ComplianceStore, EvaluationRecord


@dataclass(frozen=True)
class ReevaluationPlan:
    """Represents created/reused reevaluation job context."""

    job_id: str
    target_corpus_version: str
    feature_ids: list[str]
    created: bool


@dataclass(frozen=True)
class ReevaluationSummary:
    """Execution summary for a corpus-triggered reevaluation job."""

    job_id: str
    target_corpus_version: str
    total_features: int
    success_count: int
    failure_count: int
    regressions: int
    status: str


def trigger_corpus_update(
    store: ComplianceStore,
    *,
    target_corpus_version: str,
    source_set: str,
    scope: list[str] | None = None,
) -> ReevaluationPlan:
    """
    Register corpus version and create a deterministic reevaluation job.

    Job ID is stable by target version to make retries idempotent.
    """
    store.register_corpus_version(target_corpus_version, source_set=source_set)
    feature_ids = sorted(scope if scope is not None else store.list_active_feature_ids())
    job_id = f"reeval-{target_corpus_version}"
    created = store.create_reevaluation_job(
        job_id=job_id,
        target_corpus_version=target_corpus_version,
        scope=feature_ids,
        status="pending",
    )
    return ReevaluationPlan(
        job_id=job_id,
        target_corpus_version=target_corpus_version,
        feature_ids=feature_ids,
        created=created,
    )


def is_regression(previous_decision: str | None, new_decision: str) -> bool:
    """Return True when decision gets stricter after reevaluation."""
    if previous_decision is None:
        return False
    severity = {"PASS": 0, "REVIEW_REQUIRED": 1, "FAIL": 2}
    if previous_decision not in severity or new_decision not in severity:
        return False
    return severity[new_decision] > severity[previous_decision]


def is_confidence_regression(
    previous_decision: str | None,
    new_decision: str,
    previous_confidence: float | None,
    new_confidence: float | None,
    pass_threshold: float = 0.75,
) -> bool:
    """Flag regression when PASS remains PASS but confidence crosses below threshold."""
    if previous_decision != "PASS" or new_decision != "PASS":
        return False
    if previous_confidence is None or new_confidence is None:
        return False
    return previous_confidence >= pass_threshold and new_confidence < pass_threshold


def build_regression_report(
    store: ComplianceStore,
    *,
    job_id: str,
    evaluations: list[dict],
) -> dict:
    """
    Compare previous and new decisions and persist per-feature outcomes.

    `evaluations` is expected to include:
    - feature_id
    - previous_decision
    - new_decision
    - risk_score
    """
    report_rows = []
    regressions = 0
    for row in sorted(evaluations, key=lambda item: item["feature_id"]):
        previous_decision = row.get("previous_decision")
        new_decision = row["new_decision"]
        previous_confidence = row.get("previous_fused_confidence")
        new_confidence = row.get("new_fused_confidence")
        regressed = is_regression(previous_decision, new_decision) or is_confidence_regression(
            previous_decision,
            new_decision,
            previous_confidence,
            new_confidence,
        )
        if regressed:
            regressions += 1
        details = {
            "risk_score": row["risk_score"],
            "target_decision": new_decision,
            "previous_fused_confidence": previous_confidence,
            "new_fused_confidence": new_confidence,
            "fused_reason_codes": row.get("fused_reason_codes", []),
            "remediation_hints": row.get("remediation_hints", []),
        }
        store.record_regression(
            job_id=job_id,
            feature_id=row["feature_id"],
            previous_decision=previous_decision if previous_decision is not None else "UNKNOWN",
            new_decision=new_decision,
            regressed=regressed,
            details=details,
        )
        report_rows.append(
            {
                "feature_id": row["feature_id"],
                "previous_decision": previous_decision,
                "new_decision": new_decision,
                "regressed": regressed,
                "risk_score": row["risk_score"],
            }
        )

    return {
        "job_id": job_id,
        "total_features": len(report_rows),
        "regressions": regressions,
        "rows": report_rows,
    }


def execute_reevaluation_job(
    store: ComplianceStore,
    *,
    job_id: str,
    target_corpus_version: str,
    reevaluate_feature: Callable[[dict[str, Any], str], dict[str, Any]],
    commit_sha: str,
    correlation_id: str = "reevaluation",
    logger: Callable[[dict[str, Any]], None] | None = None,
) -> ReevaluationSummary:
    """
    Execute reevaluation across job scope with retry-safe resume semantics.

    The `reevaluate_feature` callable should return:
    - decision (PASS/REVIEW_REQUIRED/FAIL)
    - risk_score (0-100)
    - reasoning_summary
    - evidence_chunk_ids (optional list)
    """
    job = store.get_reevaluation_job(job_id)
    if job is None:
        raise ValueError(f"Unknown reevaluation job: {job_id}")

    feature_ids = sorted(job["scope"])
    existing_results = {
        row["feature_id"]: row
        for row in store.list_reevaluation_results(job_id)
    }
    store.update_reevaluation_job_status(job_id=job_id, status="running")

    local_rows: list[dict[str, Any]] = []
    for feature_id in feature_ids:
        existing = existing_results.get(feature_id)
        if existing is not None and "error" not in existing["details"]:
            continue

        previous_evaluation = store.get_latest_evaluation(feature_id)
        previous_decision = previous_evaluation["decision"] if previous_evaluation else None
        try:
            latest_spec = store.get_latest_feature_spec(feature_id)
            if latest_spec is None:
                raise RuntimeError("active feature spec not found")
            result = reevaluate_feature(latest_spec["parsed_payload"], target_corpus_version)
            decision = result["decision"]
            risk_score = int(result["risk_score"])
            reasoning_summary = str(result.get("reasoning_summary", "Reevaluation completed"))
            evidence_chunk_ids = list(result.get("evidence_chunk_ids", []))
            deterministic_confidence = result.get("deterministic_confidence")
            llm_decision = result.get("llm_decision")
            llm_confidence = result.get("llm_confidence")
            llm_fallback = result.get("llm_fallback")
            llm_error_type = result.get("llm_error_type")
            llm_model = result.get("llm_model")
            llm_attempts = result.get("llm_attempts")
            fused_confidence = result.get("fused_confidence")
            fused_reason_codes = result.get("fused_reason_codes", [])
            fused_explanation = result.get("fused_explanation")
            remediation_hints = result.get("remediation_hints", [])

            store.record_evaluation(
                EvaluationRecord(
                    feature_id=feature_id,
                    spec_version=latest_spec["spec_version"],
                    corpus_version=target_corpus_version,
                    risk_score=risk_score,
                    decision=decision,
                    evidence_chunk_ids=evidence_chunk_ids,
                    reasoning_summary=reasoning_summary,
                    commit_sha=commit_sha,
                    deterministic_confidence=deterministic_confidence,
                    llm_decision=llm_decision,
                    llm_confidence=llm_confidence,
                    llm_fallback=llm_fallback,
                    llm_error_type=llm_error_type,
                    llm_model=llm_model,
                    llm_attempts=llm_attempts,
                    fused_confidence=fused_confidence,
                    fused_reason_codes=fused_reason_codes,
                    fused_explanation=fused_explanation,
                    remediation_hints=remediation_hints,
                )
            )
            local_rows.append(
                {
                    "feature_id": feature_id,
                    "previous_decision": previous_decision,
                    "new_decision": decision,
                    "risk_score": risk_score,
                    "previous_fused_confidence": previous_evaluation["fused_confidence"] if previous_evaluation else None,
                    "new_fused_confidence": fused_confidence,
                    "fused_reason_codes": fused_reason_codes,
                    "remediation_hints": remediation_hints,
                }
            )
        except Exception as exc:  # noqa: BLE001 - feature-level error should not abort entire job.
            store.record_regression(
                job_id=job_id,
                feature_id=feature_id,
                previous_decision=previous_decision if previous_decision is not None else "UNKNOWN",
                new_decision=previous_decision if previous_decision is not None else "UNKNOWN",
                regressed=False,
                details={"error": str(exc), "sanitized": True},
            )
            if logger is not None:
                logger(
                    {
                        "event": "reevaluation.feature_failed",
                        "correlation_id": correlation_id,
                        "job_id": job_id,
                        "feature_id": feature_id,
                        "error": str(exc),
                        "sanitized": True,
                    }
                )

    build_regression_report(store, job_id=job_id, evaluations=local_rows)
    all_results = store.list_reevaluation_results(job_id)
    success_count = sum(1 for row in all_results if "error" not in row["details"])
    failure_count = len(all_results) - success_count
    regressions = sum(1 for row in all_results if row["regressed"])
    final_status = "completed" if failure_count == 0 else "completed_with_errors"
    store.update_reevaluation_job_status(
        job_id=job_id,
        status=final_status,
        success_count=success_count,
        failure_count=failure_count,
        error_summary=None if failure_count == 0 else "one or more feature reevaluations failed",
    )
    if logger is not None:
        logger(
            {
                "event": "reevaluation.completed",
                "correlation_id": correlation_id,
                "job_id": job_id,
                "target_corpus_version": target_corpus_version,
                "scope_size": len(feature_ids),
                "success_count": success_count,
                "failure_count": failure_count,
                "regressions": regressions,
            }
        )
    return ReevaluationSummary(
        job_id=job_id,
        target_corpus_version=target_corpus_version,
        total_features=len(feature_ids),
        success_count=success_count,
        failure_count=failure_count,
        regressions=regressions,
        status=final_status,
    )
