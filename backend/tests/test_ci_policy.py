"""Tests for PR comment rendering and strictest gate logic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ci import (
    COMMENT_MARKER,
    determine_pr_gate,
    map_gate_to_check_conclusion,
    render_pr_comment,
    upsert_comment,
)


def result(
    *,
    path: str,
    decision: str | None = None,
    risk_score: int | None = None,
    evidence_chunk_ids: list[str] | None = None,
    error: str | None = None,
    llm_observation: dict | None = None,
    fusion_observation: dict | None = None,
):
    return SimpleNamespace(
        path=path,
        decision=decision,
        risk_score=risk_score,
        evidence_chunk_ids=evidence_chunk_ids or [],
        error=error,
        llm_observation=llm_observation,
        fusion_observation=fusion_observation,
    )


def test_strictest_gate_matrix() -> None:
    assert determine_pr_gate([result(path="a", decision="PASS")]) == "PASS"
    assert determine_pr_gate([result(path="a", decision="PASS"), result(path="b", decision="REVIEW_REQUIRED")]) == "REVIEW_REQUIRED"
    assert determine_pr_gate([result(path="a", decision="PASS"), result(path="b", decision="FAIL")]) == "FAIL"
    assert determine_pr_gate([result(path="a", error="Spec schema validation failed")]) == "FAIL"


@pytest.mark.parametrize(
    ("decisions", "expected"),
    [
        (["PASS", "PASS"], "PASS"),
        (["PASS", "REVIEW_REQUIRED"], "REVIEW_REQUIRED"),
        (["REVIEW_REQUIRED", "PASS"], "REVIEW_REQUIRED"),
        (["REVIEW_REQUIRED", "REVIEW_REQUIRED"], "REVIEW_REQUIRED"),
        (["PASS", "FAIL"], "FAIL"),
        (["FAIL", "PASS"], "FAIL"),
        (["REVIEW_REQUIRED", "FAIL"], "FAIL"),
        (["FAIL", "REVIEW_REQUIRED"], "FAIL"),
        (["PASS", "PASS", "PASS"], "PASS"),
        (["PASS", "REVIEW_REQUIRED", "FAIL"], "FAIL"),
    ],
)
def test_strictest_gate_exhaustive_combinations(decisions: list[str], expected: str) -> None:
    results = [result(path=f"file-{idx}.yaml", decision=decision) for idx, decision in enumerate(decisions)]
    assert determine_pr_gate(results) == expected


def test_render_pr_comment_contains_marker_and_rows() -> None:
    report = render_pr_comment(
        [
            result(
                path="backend/features/payments/card_capture.yaml",
                decision="PASS",
                risk_score=20,
                evidence_chunk_ids=["REG-US-KYC-001"],
            ),
            result(path="backend/features/payments/broken.yaml", error="Spec schema validation failed"),
        ],
        gate="FAIL",
    )
    assert COMMENT_MARKER in report
    assert "Final Gate: `FAIL`" in report
    assert "card_capture.yaml" in report
    assert "invalid spec" in report


def test_render_pr_comment_includes_fusion_explanation_and_remediation() -> None:
    report = render_pr_comment(
        [
            result(
                path="backend/features/payments/card_capture.yaml",
                decision="REVIEW_REQUIRED",
                risk_score=44,
                evidence_chunk_ids=["REG-US-KYC-001"],
                fusion_observation={
                    "fused_confidence": 0.62,
                    "reason_codes": ["MIXED_SIGNAL_REVIEW"],
                    "explanation": "Signals conflicted so review is required.",
                    "remediation_hints": ["Add control evidence."],
                },
            ),
        ],
        gate="REVIEW_REQUIRED",
    )
    assert "Fusion confidence" in report
    assert "Why: Signals conflicted so review is required." in report
    assert "Remediation: Add control evidence." in report


def test_render_pr_comment_is_deterministic_and_handles_empty_evidence() -> None:
    report = render_pr_comment(
        [
            result(path="backend/features/z.yaml", decision="PASS", risk_score=12, evidence_chunk_ids=[]),
            result(path="backend/features/a.yaml", decision="REVIEW_REQUIRED", risk_score=45),
        ],
        gate="REVIEW_REQUIRED",
    )
    lines = report.splitlines()
    z_idx = next(index for index, value in enumerate(lines) if "z.yaml" in value)
    a_idx = next(index for index, value in enumerate(lines) if "a.yaml" in value)
    assert a_idx < z_idx
    assert "evidence: none" in report


@pytest.mark.parametrize(
    ("gate", "expected"),
    [
        ("PASS", {"conclusion": "success"}),
        ("REVIEW_REQUIRED", {"conclusion": "failure"}),
        ("FAIL", {"conclusion": "failure"}),
    ],
)
def test_map_gate_to_check_conclusion(gate: str, expected: dict[str, str]) -> None:
    status = map_gate_to_check_conclusion(gate)
    assert status["conclusion"] == expected["conclusion"]
    assert status["summary"]


def test_map_gate_to_check_conclusion_rejects_unknown_gate() -> None:
    with pytest.raises(ValueError):
        map_gate_to_check_conclusion("UNKNOWN")


def test_upsert_comment_creates_when_missing_and_updates_when_present() -> None:
    new_body = f"{COMMENT_MARKER}\nnew"
    create_action = upsert_comment(existing_comments=[{"id": 1, "body": "unrelated"}], new_body=new_body)
    assert create_action["action"] == "create"

    update_action = upsert_comment(
        existing_comments=[{"id": 2, "body": f"old\n{COMMENT_MARKER}\nbody"}],
        new_body=new_body,
    )
    assert update_action["action"] == "update"
    assert update_action["comment_id"] == 2
