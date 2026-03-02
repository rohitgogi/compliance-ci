"""Persistence-layer tests for versioned specs and evaluations."""

from __future__ import annotations

from pathlib import Path

from app.storage import ComplianceStore, EvaluationRecord


def test_store_create_read_latest_and_history(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    feature_id = "payments_card_capture"

    store.upsert_feature_spec(
        feature_id=feature_id,
        spec_version="v1",
        content_hash="hash-v1",
        path="backend/features/payments/card_capture.yaml",
        parsed_payload={"feature_id": feature_id, "controls": [{"id": "KYC-001"}]},
    )
    store.upsert_feature_spec(
        feature_id=feature_id,
        spec_version="v2",
        content_hash="hash-v2",
        path="backend/features/payments/card_capture.yaml",
        parsed_payload={"feature_id": feature_id, "controls": [{"id": "KYC-001"}, {"id": "AUDIT-001"}]},
    )

    latest = store.get_latest_feature_spec(feature_id)
    assert latest is not None
    assert latest["spec_version"] == "v2"

    history = store.get_feature_history(feature_id)
    assert len(history) == 2
    assert {item["spec_version"] for item in history} == {"v1", "v2"}


def test_evaluation_writes_are_idempotent_for_same_commit(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    feature_id = "payments_transfer"
    store.upsert_feature_spec(
        feature_id=feature_id,
        spec_version="v1",
        content_hash="hash-v1",
        path="backend/features/payments/transfer.yaml",
        parsed_payload={"feature_id": feature_id},
    )

    record = EvaluationRecord(
        feature_id=feature_id,
        spec_version="v1",
        corpus_version="v1",
        risk_score=40,
        decision="REVIEW_REQUIRED",
        evidence_chunk_ids=["REG-US-KYC-001"],
        reasoning_summary="Missing verified control",
        commit_sha="abcdef1",
    )
    store.record_evaluation(record)
    store.record_evaluation(record)

    evaluations = store.get_evaluations(feature_id)
    assert len(evaluations) == 1
    assert evaluations[0]["decision"] == "REVIEW_REQUIRED"
