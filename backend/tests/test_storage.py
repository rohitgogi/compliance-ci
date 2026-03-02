"""Persistence-layer tests for versioned specs and evaluations."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlite3

from app.storage import ComplianceStore, EvaluationRecord


def test_schema_bootstrap_has_required_tables_and_is_reentrant(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    store = ComplianceStore(db_path)
    # Re-init should be safe and idempotent.
    ComplianceStore(db_path)

    with store._connect() as conn:  # noqa: SLF001 - used only for schema contract test.
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    table_names = {row["name"] for row in rows}
    assert {"feature_specs", "evaluations", "corpus_versions", "reevaluation_jobs", "reevaluation_results"} <= table_names


def test_schema_constraints_enforce_foreign_keys(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    # evaluation foreign key requires matching feature spec version.
    with pytest.raises(Exception):
        store.record_evaluation(
            EvaluationRecord(
                feature_id="missing_feature",
                spec_version="v1",
                corpus_version="v1",
                risk_score=50,
                decision="REVIEW_REQUIRED",
                evidence_chunk_ids=[],
                reasoning_summary="missing fk",
                commit_sha="sha",
            )
        )


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


def test_evaluation_writes_create_new_rows_for_distinct_commit_or_corpus(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    feature_id = "payments_transfer"
    store.upsert_feature_spec(
        feature_id=feature_id,
        spec_version="v1",
        content_hash="hash-v1",
        path="backend/features/payments/transfer.yaml",
        parsed_payload={"feature_id": feature_id},
    )

    store.record_evaluation(
        EvaluationRecord(
            feature_id=feature_id,
            spec_version="v1",
            corpus_version="v1",
            risk_score=30,
            decision="PASS",
            evidence_chunk_ids=[],
            reasoning_summary="ok",
            commit_sha="sha-1",
        )
    )
    store.record_evaluation(
        EvaluationRecord(
            feature_id=feature_id,
            spec_version="v1",
            corpus_version="v1",
            risk_score=40,
            decision="REVIEW_REQUIRED",
            evidence_chunk_ids=[],
            reasoning_summary="changed commit",
            commit_sha="sha-2",
        )
    )
    store.record_evaluation(
        EvaluationRecord(
            feature_id=feature_id,
            spec_version="v1",
            corpus_version="v2",
            risk_score=50,
            decision="REVIEW_REQUIRED",
            evidence_chunk_ids=[],
            reasoning_summary="changed corpus",
            commit_sha="sha-2",
        )
    )

    evaluations = store.get_evaluations(feature_id)
    assert len(evaluations) == 3


def test_hybrid_evaluation_fields_roundtrip_and_reason_lookup(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    feature_id = "hybrid_feature"
    store.upsert_feature_spec(
        feature_id=feature_id,
        spec_version="v1",
        content_hash="hash-v1",
        path="backend/features/hybrid.yaml",
        parsed_payload={"feature_id": feature_id},
    )
    store.record_evaluation(
        EvaluationRecord(
            feature_id=feature_id,
            spec_version="v1",
            corpus_version="v2",
            risk_score=41,
            decision="REVIEW_REQUIRED",
            evidence_chunk_ids=["REG-1"],
            reasoning_summary="hybrid summary",
            commit_sha="sha-hybrid",
            deterministic_confidence=0.59,
            llm_decision="FAIL",
            llm_confidence=0.82,
            llm_fallback=False,
            llm_error_type=None,
            llm_model="gpt-4.1-mini",
            llm_attempts=1,
            fused_confidence=0.73,
            fused_reason_codes=["MIXED_SIGNAL_REVIEW"],
            fused_explanation="Signals conflict.",
            remediation_hints=["Add stronger controls."],
        )
    )
    latest = store.get_latest_evaluation(feature_id)
    assert latest is not None
    assert latest["deterministic_confidence"] == 0.59
    assert latest["llm_decision"] == "FAIL"
    assert latest["fused_reason_codes"] == ["MIXED_SIGNAL_REVIEW"]
    assert latest["remediation_hints"] == ["Add stronger controls."]

    matched = store.list_evaluations_by_reason_code("MIXED_SIGNAL_REVIEW")
    assert any(item["feature_id"] == feature_id for item in matched)


def test_corpus_version_registration_is_idempotent(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    store.register_corpus_version("v2", source_set="core-a")
    store.register_corpus_version("v2", source_set="core-b")
    version = store.get_corpus_version("v2")
    assert version is not None
    assert version["source_set"] == "core-b"


def test_reevaluation_job_status_and_result_upsert(tmp_path: Path) -> None:
    store = ComplianceStore(tmp_path / "state.db")
    created = store.create_reevaluation_job(
        job_id="reeval-v2",
        target_corpus_version="v2",
        scope=["feature_a"],
    )
    assert created is True

    store.update_reevaluation_job_status(
        job_id="reeval-v2",
        status="running",
        success_count=1,
        failure_count=0,
    )
    job = store.get_reevaluation_job("reeval-v2")
    assert job is not None
    assert job["status"] == "running"
    assert job["success_count"] == 1

    store.record_regression(
        job_id="reeval-v2",
        feature_id="feature_a",
        previous_decision="PASS",
        new_decision="FAIL",
        regressed=True,
        details={"risk_score": 80},
    )
    # Should upsert (not duplicate) for same job+feature.
    store.record_regression(
        job_id="reeval-v2",
        feature_id="feature_a",
        previous_decision="PASS",
        new_decision="REVIEW_REQUIRED",
        regressed=True,
        details={"risk_score": 55},
    )
    results = store.list_reevaluation_results("reeval-v2")
    assert len(results) == 1
    assert results[0]["new_decision"] == "REVIEW_REQUIRED"


def test_migration_adds_hybrid_columns_to_legacy_evaluations_table(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_id TEXT NOT NULL,
            spec_version TEXT NOT NULL,
            corpus_version TEXT NOT NULL,
            risk_score INTEGER NOT NULL,
            decision TEXT NOT NULL,
            evidence_chunk_ids TEXT NOT NULL,
            reasoning_summary TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            evaluated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE feature_specs (
            feature_id TEXT NOT NULL,
            spec_version TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            path TEXT NOT NULL,
            parsed_payload TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            PRIMARY KEY (feature_id, spec_version)
        )
        """
    )
    conn.execute(
        "CREATE TABLE corpus_versions (version_id TEXT PRIMARY KEY, source_set TEXT NOT NULL, released_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE reevaluation_jobs (job_id TEXT PRIMARY KEY, target_corpus_version TEXT NOT NULL, scope TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE reevaluation_results (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, feature_id TEXT NOT NULL, previous_decision TEXT NOT NULL, new_decision TEXT NOT NULL, regressed INTEGER NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

    store = ComplianceStore(db_path)
    with store._connect() as migrated:  # noqa: SLF001
        columns = {
            row["name"]
            for row in migrated.execute("PRAGMA table_info(evaluations)").fetchall()
        }
    assert "fused_confidence" in columns
    assert "llm_decision" in columns
