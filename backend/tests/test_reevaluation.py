"""Tests for corpus update jobs and regression report behavior."""

from __future__ import annotations

from pathlib import Path

from app.reevaluation import build_regression_report, is_regression, trigger_corpus_update
from app.storage import ComplianceStore


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


def test_trigger_corpus_update_respects_scope(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    plan = trigger_corpus_update(
        store,
        target_corpus_version="v3",
        source_set="core-regulations-v3",
        scope=["feature_z"],
    )
    assert plan.feature_ids == ["feature_z"]


def test_regression_logic_and_report_generation(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    assert is_regression("PASS", "REVIEW_REQUIRED") is True
    assert is_regression("PASS", "FAIL") is True
    assert is_regression("REVIEW_REQUIRED", "PASS") is False
    assert is_regression("FAIL", "FAIL") is False

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
        ],
    )

    assert report["total_features"] == 2
    assert report["regressions"] == 1
    assert any(row["regressed"] is True for row in report["rows"])
