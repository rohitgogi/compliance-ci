"""Tests for corpus update jobs and regression report behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.reevaluation import (
    build_regression_report,
    execute_reevaluation_job,
    is_regression,
    trigger_corpus_update,
)
from app.storage import ComplianceStore, EvaluationRecord


def test_trigger_corpus_update_creates_single_idempotent_job(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    store.upsert_feature_spec(
        feature_id="feature_a",
        spec_version="v1",
        content_hash="hash-a",
        path="backend/features/a.yaml",
        parsed_payload={"feature_id": "feature_a"},
    )
    store.upsert_feature_spec(
        feature_id="feature_b",
        spec_version="v1",
        content_hash="hash-b",
        path="backend/features/b.yaml",
        parsed_payload={"feature_id": "feature_b"},
    )

    first = trigger_corpus_update(
        store,
        target_corpus_version="v2",
        source_set="core-regulations-v2",
    )
    second = trigger_corpus_update(
        store,
        target_corpus_version="v2",
        source_set="core-regulations-v2",
    )
    assert first.created is True
    assert second.created is False
    assert first.feature_ids == ["feature_a", "feature_b"]
    job = store.get_reevaluation_job("reeval-v2")
    assert job is not None
    assert job["scope"] == ["feature_a", "feature_b"]


def test_trigger_corpus_update_respects_scope(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    plan = trigger_corpus_update(
        store,
        target_corpus_version="v3",
        source_set="core-regulations-v3",
        scope=["feature_z"],
    )
    assert plan.feature_ids == ["feature_z"]


def test_trigger_default_scope_excludes_inactive_features(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    store.upsert_feature_spec(
        feature_id="feature_inactive",
        spec_version="v1",
        content_hash="hash-1",
        path="backend/features/x.yaml",
        parsed_payload={"feature_id": "feature_inactive"},
        active=False,
    )
    store.upsert_feature_spec(
        feature_id="feature_active",
        spec_version="v1",
        content_hash="hash-2",
        path="backend/features/y.yaml",
        parsed_payload={"feature_id": "feature_active"},
        active=True,
    )
    plan = trigger_corpus_update(
        store,
        target_corpus_version="v8",
        source_set="core-v8",
    )
    assert plan.feature_ids == ["feature_active"]


def test_regression_logic_and_report_generation(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    assert is_regression("PASS", "REVIEW_REQUIRED") is True
    assert is_regression("PASS", "FAIL") is True
    assert is_regression("REVIEW_REQUIRED", "PASS") is False
    assert is_regression("FAIL", "FAIL") is False
    assert is_regression(None, "PASS") is False

    store.create_reevaluation_job(
        job_id="reeval-v9",
        target_corpus_version="v9",
        scope=["feature_a", "feature_b"],
    )
    report = build_regression_report(
        store,
        job_id="reeval-v9",
        evaluations=[
            {
                "feature_id": "feature_a",
                "previous_decision": "PASS",
                "new_decision": "REVIEW_REQUIRED",
                "risk_score": 50,
            },
            {
                "feature_id": "feature_b",
                "previous_decision": "REVIEW_REQUIRED",
                "new_decision": "PASS",
                "risk_score": 25,
            },
            {
                "feature_id": "feature_c",
                "previous_decision": None,
                "new_decision": "PASS",
                "risk_score": 10,
            },
        ],
    )

    assert report["total_features"] == 3
    assert report["regressions"] == 1
    assert [row["feature_id"] for row in report["rows"]] == ["feature_a", "feature_b", "feature_c"]
    assert any(row["regressed"] is True for row in report["rows"])
    stored = store.list_reevaluation_results("reeval-v9")
    assert len(stored) == 3
    assert stored[-1]["feature_id"] == "feature_c"
    assert stored[-1]["previous_decision"] == "UNKNOWN"

    # Determinism: same input set reordered should produce stable row order.
    report_again = build_regression_report(
        store,
        job_id="reeval-v9",
        evaluations=[
            {
                "feature_id": "feature_c",
                "previous_decision": None,
                "new_decision": "PASS",
                "risk_score": 10,
            },
            {
                "feature_id": "feature_a",
                "previous_decision": "PASS",
                "new_decision": "REVIEW_REQUIRED",
                "risk_score": 50,
            },
            {
                "feature_id": "feature_b",
                "previous_decision": "REVIEW_REQUIRED",
                "new_decision": "PASS",
                "risk_score": 25,
            },
        ],
    )
    assert [row["feature_id"] for row in report_again["rows"]] == ["feature_a", "feature_b", "feature_c"]


def _seed_feature_with_prior_decision(store: ComplianceStore, feature_id: str, prior_decision: str) -> None:
    store.upsert_feature_spec(
        feature_id=feature_id,
        spec_version="v1",
        content_hash=f"hash-{feature_id}",
        path=f"backend/features/{feature_id}.yaml",
        parsed_payload={
            "feature_id": feature_id,
            "feature_name": feature_id,
            "owner_team": "risk",
            "data_classification": "confidential",
            "jurisdictions": ["US"],
            "controls": [{"id": "KYC-001", "description": "KYC", "status": "implemented"}],
            "change_summary": "seed",
        },
    )
    store.record_evaluation(
        record=EvaluationRecord(
            feature_id=feature_id,
            spec_version="v1",
            corpus_version="v1",
            risk_score=10 if prior_decision == "PASS" else 50,
            decision=prior_decision,
            evidence_chunk_ids=[],
            reasoning_summary="seed prior",
            commit_sha="seed-sha",
        )
    )


def test_execute_reevaluation_job_happy_path(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    _seed_feature_with_prior_decision(store, "feature_a", "PASS")
    _seed_feature_with_prior_decision(store, "feature_b", "REVIEW_REQUIRED")
    plan = trigger_corpus_update(store, target_corpus_version="v2", source_set="core-v2")

    logs: list[dict] = []

    def fake_reevaluator(payload: dict, target_version: str) -> dict:
        if payload["feature_id"] == "feature_a":
            return {"decision": "REVIEW_REQUIRED", "risk_score": 45, "reasoning_summary": "stricter", "evidence_chunk_ids": ["REG-1"]}
        return {"decision": "PASS", "risk_score": 20, "reasoning_summary": "improved", "evidence_chunk_ids": ["REG-2"]}

    summary = execute_reevaluation_job(
        store,
        job_id=plan.job_id,
        target_corpus_version="v2",
        reevaluate_feature=fake_reevaluator,
        commit_sha="reeval-sha",
        correlation_id="corr-1",
        logger=logs.append,
    )
    assert summary.status == "completed"
    assert summary.success_count == 2
    assert summary.failure_count == 0
    assert summary.regressions == 1
    job = store.get_reevaluation_job(plan.job_id)
    assert job is not None
    assert job["status"] == "completed"
    assert job["success_count"] == 2
    assert job["failure_count"] == 0
    assert any(log["event"] == "reevaluation.completed" for log in logs)


def test_execute_reevaluation_job_partial_failure_and_resume(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    _seed_feature_with_prior_decision(store, "feature_a", "PASS")
    _seed_feature_with_prior_decision(store, "feature_b", "PASS")
    plan = trigger_corpus_update(store, target_corpus_version="v3", source_set="core-v3")
    logs: list[dict] = []

    def failing_once(payload: dict, target_version: str) -> dict:
        if payload["feature_id"] == "feature_b":
            raise RuntimeError("transient issue")
        return {"decision": "PASS", "risk_score": 15, "reasoning_summary": "ok", "evidence_chunk_ids": []}

    first = execute_reevaluation_job(
        store,
        job_id=plan.job_id,
        target_corpus_version="v3",
        reevaluate_feature=failing_once,
        commit_sha="reeval-sha-1",
        correlation_id="corr-2",
        logger=logs.append,
    )
    assert first.status == "completed_with_errors"
    assert first.failure_count == 1
    assert any(log["event"] == "reevaluation.feature_failed" for log in logs)

    def now_success(payload: dict, target_version: str) -> dict:
        return {"decision": "REVIEW_REQUIRED", "risk_score": 60, "reasoning_summary": "fixed", "evidence_chunk_ids": []}

    second = execute_reevaluation_job(
        store,
        job_id=plan.job_id,
        target_corpus_version="v3",
        reevaluate_feature=now_success,
        commit_sha="reeval-sha-2",
    )
    # Resume should process only previously failed feature, without duplicating existing result rows.
    assert second.success_count == 2
    assert second.failure_count == 0
    assert second.status == "completed"
    results = store.list_reevaluation_results(plan.job_id)
    assert len(results) == 2
    assert all("error" not in row["details"] for row in results)


def test_e2e_idempotent_retrigger_does_not_duplicate_jobs_or_results(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    _seed_feature_with_prior_decision(store, "feature_x", "PASS")
    first_plan = trigger_corpus_update(store, target_corpus_version="v4", source_set="core-v4")
    second_plan = trigger_corpus_update(store, target_corpus_version="v4", source_set="core-v4")
    assert first_plan.job_id == second_plan.job_id
    assert second_plan.created is False

    def stable_eval(payload: dict, target_version: str) -> dict:
        return {"decision": "PASS", "risk_score": 20, "reasoning_summary": "stable", "evidence_chunk_ids": []}

    execute_reevaluation_job(
        store,
        job_id=first_plan.job_id,
        target_corpus_version="v4",
        reevaluate_feature=stable_eval,
        commit_sha="sha-1",
    )
    execute_reevaluation_job(
        store,
        job_id=first_plan.job_id,
        target_corpus_version="v4",
        reevaluate_feature=stable_eval,
        commit_sha="sha-1",
    )
    results = store.list_reevaluation_results(first_plan.job_id)
    assert len(results) == 1


@pytest.mark.parametrize(
    ("previous_decision", "new_decision", "expected"),
    [
        ("PASS", "PASS", False),
        ("PASS", "REVIEW_REQUIRED", True),
        ("PASS", "FAIL", True),
        ("REVIEW_REQUIRED", "PASS", False),
        ("REVIEW_REQUIRED", "REVIEW_REQUIRED", False),
        ("REVIEW_REQUIRED", "FAIL", True),
        ("FAIL", "PASS", False),
        ("FAIL", "REVIEW_REQUIRED", False),
        ("FAIL", "FAIL", False),
    ],
)
def test_regression_transition_matrix(previous_decision: str, new_decision: str, expected: bool) -> None:
    assert is_regression(previous_decision, new_decision) is expected
