"""Corpus update trigger and regression-report logic."""

from __future__ import annotations

from dataclasses import dataclass

from app.storage import ComplianceStore


@dataclass(frozen=True)
class ReevaluationPlan:
    """Represents created/reused reevaluation job context."""

    job_id: str
    target_corpus_version: str
    feature_ids: list[str]
    created: bool


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


def is_regression(previous_decision: str, new_decision: str) -> bool:
    """Return True when decision gets stricter after reevaluation."""
    severity = {"PASS": 0, "REVIEW_REQUIRED": 1, "FAIL": 2}
    return severity[new_decision] > severity[previous_decision]


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
    for row in evaluations:
        regressed = is_regression(row["previous_decision"], row["new_decision"])
        if regressed:
            regressions += 1
        details = {
            "risk_score": row["risk_score"],
            "target_decision": row["new_decision"],
        }
        store.record_regression(
            job_id=job_id,
            feature_id=row["feature_id"],
            previous_decision=row["previous_decision"],
            new_decision=row["new_decision"],
            regressed=regressed,
            details=details,
        )
        report_rows.append(
            {
                "feature_id": row["feature_id"],
                "previous_decision": row["previous_decision"],
                "new_decision": row["new_decision"],
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
