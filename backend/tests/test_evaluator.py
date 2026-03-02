"""Tests for deterministic RAG retrieval and risk score mapping."""

from __future__ import annotations

from app.evaluator import CorpusChunk, evaluate_feature_spec, map_risk_score_to_decision
from app.schemas import Control, FeatureComplianceSpec


def build_spec() -> FeatureComplianceSpec:
    return FeatureComplianceSpec(
        feature_id="payments_card_capture",
        feature_name="Card Capture",
        owner_team="payments-platform",
        data_classification="confidential",
        jurisdictions=["US", "EU"],
        controls=[
            Control(
                id="KYC-001",
                description="Verify identity before enabling transfers",
                status="implemented",
            ),
            Control(
                id="AUDIT-001",
                description="Immutable event logging",
                status="verified",
            ),
        ],
        change_summary="Add card capture endpoint for transfer funding.",
    )


def test_retrieval_evidence_is_used_in_evaluation() -> None:
    spec = build_spec()
    corpus = (
        CorpusChunk(
            chunk_id="REG-CUSTOM-001",
            title="US KYC controls",
            text="US KYC and card capture controls are required.",
            tags=("US", "KYC"),
            corpus_version="v-test",
        ),
    )

    result = evaluate_feature_spec(spec, corpus=corpus)
    assert result.evidence_chunk_ids == ["REG-CUSTOM-001"]
    assert result.corpus_version == "v-test"
    assert "grounding" in result.reasoning_summary.lower()


def test_score_to_decision_boundary_mapping() -> None:
    assert map_risk_score_to_decision(30) == "PASS"
    assert map_risk_score_to_decision(31) == "REVIEW_REQUIRED"
    assert map_risk_score_to_decision(69) == "REVIEW_REQUIRED"
    assert map_risk_score_to_decision(70) == "FAIL"
