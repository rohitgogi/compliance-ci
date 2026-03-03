"""Tests for frontend read endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import app
from app.storage import ComplianceStore, EvaluationRecord

client = TestClient(app)


def _seed_data(db_path: Path) -> None:
    store = ComplianceStore(db_path)
    store.upsert_feature_spec(
        feature_id="feature_a",
        spec_version="v1",
        content_hash="hash-a",
        path="backend/features/feature_a.yaml",
        parsed_payload={
            "feature_id": "feature_a",
            "feature_name": "Feature A",
            "owner_team": "risk",
            "data_classification": "confidential",
            "jurisdictions": ["US"],
            "controls": [{"id": "KYC-001", "description": "KYC", "status": "implemented"}],
            "change_summary": "seed",
        },
    )
    store.record_evaluation(
        EvaluationRecord(
            feature_id="feature_a",
            spec_version="v1",
            corpus_version="v1",
            risk_score=25,
            decision="PASS",
            evidence_chunk_ids=["REG-1"],
            reasoning_summary="ok",
            commit_sha="abcdef1",
        )
    )
    store.register_corpus_version("v1", source_set="core-v1")
    store.create_reevaluation_job(
        job_id="reeval-v1",
        target_corpus_version="v1",
        scope=["feature_a"],
    )
    store.record_regression(
        job_id="reeval-v1",
        feature_id="feature_a",
        previous_decision="PASS",
        new_decision="REVIEW_REQUIRED",
        regressed=True,
        details={"risk_score": 45},
    )


def test_read_endpoints_return_expected_payloads(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "frontend_reads.db"
    monkeypatch.setenv("COMPLIANCE_DB_PATH", str(db_path))
    from app.api import _get_store

    _get_store.cache_clear()
    _seed_data(db_path)

    features = client.get("/v1/features")
    assert features.status_code == 200
    body = features.json()
    assert len(body["features"]) == 1
    assert body["features"][0]["feature_id"] == "feature_a"
    assert body["features"][0]["latest_decision"] == "PASS"

    detail = client.get("/v1/features/feature_a")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["feature"]["feature_name"] == "Feature A"
    assert len(detail_body["evaluations"]) == 1

    evaluations = client.get("/v1/evaluations")
    assert evaluations.status_code == 200
    assert evaluations.json()["evaluations"][0]["feature_id"] == "feature_a"

    corpus_versions = client.get("/v1/corpus-versions")
    assert corpus_versions.status_code == 200
    assert corpus_versions.json()["corpus_versions"][0]["version_id"] == "v1"

    reevals = client.get("/v1/reevaluation-results?regressed_only=true")
    assert reevals.status_code == 200
    assert reevals.json()["results"][0]["feature_id"] == "feature_a"


def test_feature_detail_returns_404_for_unknown_feature(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "empty.db"
    monkeypatch.setenv("COMPLIANCE_DB_PATH", str(db_path))
    from app.api import _get_store

    _get_store.cache_clear()
    ComplianceStore(db_path)
    response = client.get("/v1/features/does-not-exist")
    assert response.status_code == 404
