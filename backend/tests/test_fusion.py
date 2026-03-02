"""Tests for conservative decision/confidence fusion policy."""

from __future__ import annotations

import random

import pytest

from app.fusion import Decision, FusionInput, FusionReason, compute_fused_confidence, fuse_decision, normalize_confidence_percent


def make_input(
    *,
    det_decision: Decision,
    det_conf: float,
    llm_decision: Decision,
    llm_conf: float,
    llm_fallback: bool = False,
):
    return FusionInput(
        deterministic_decision=det_decision,
        deterministic_confidence=det_conf,
        llm_decision=llm_decision,
        llm_confidence=llm_conf,
        llm_fallback=llm_fallback,
        llm_findings=[],
        llm_remediation_hints=[],
    )


def test_percent_normalization() -> None:
    assert normalize_confidence_percent(75) == 0.75
    assert normalize_confidence_percent(0) == 0.0
    assert normalize_confidence_percent(100) == 1.0
    with pytest.raises(ValueError):
        normalize_confidence_percent(-1)
    with pytest.raises(ValueError):
        normalize_confidence_percent(101)


def test_fused_confidence_formula_and_clamp() -> None:
    assert compute_fused_confidence(0.5, 1.0) == pytest.approx(0.8)
    assert compute_fused_confidence(-10, 10) == 1.0
    assert compute_fused_confidence(-5, -2) == 0.0


@pytest.mark.parametrize(
    ("det", "llm", "expected"),
    [
        (Decision.PASS, Decision.PASS, Decision.PASS),
        (Decision.PASS, Decision.FAIL, Decision.REVIEW_REQUIRED),
        (Decision.PASS, Decision.REVIEW_REQUIRED, Decision.REVIEW_REQUIRED),
        (Decision.FAIL, Decision.PASS, Decision.REVIEW_REQUIRED),
        (Decision.REVIEW_REQUIRED, Decision.PASS, Decision.REVIEW_REQUIRED),
        (Decision.FAIL, Decision.FAIL, Decision.FAIL),
        (Decision.FAIL, Decision.REVIEW_REQUIRED, Decision.REVIEW_REQUIRED),
        (Decision.REVIEW_REQUIRED, Decision.FAIL, Decision.REVIEW_REQUIRED),
        (Decision.REVIEW_REQUIRED, Decision.REVIEW_REQUIRED, Decision.REVIEW_REQUIRED),
    ],
)
def test_decision_matrix(det: Decision, llm: Decision, expected: Decision) -> None:
    output = fuse_decision(
        make_input(
            det_decision=det,
            det_conf=0.9,
            llm_decision=llm,
            llm_conf=0.9,
        )
    )
    assert output.final_decision == expected
    assert output.reason_codes
    assert output.explanation


def test_pass_threshold_boundaries() -> None:
    below = fuse_decision(
        make_input(
            det_decision=Decision.PASS,
            det_conf=0.75,
            llm_decision=Decision.PASS,
            llm_conf=0.74,
        )
    )
    exact = fuse_decision(
        make_input(
            det_decision=Decision.PASS,
            det_conf=0.75,
            llm_decision=Decision.PASS,
            llm_conf=0.75,
        )
    )
    above = fuse_decision(
        make_input(
            det_decision=Decision.PASS,
            det_conf=0.76,
            llm_decision=Decision.PASS,
            llm_conf=0.76,
        )
    )
    assert below.final_decision == Decision.REVIEW_REQUIRED
    assert FusionReason.PASS_THRESHOLD_MISS in below.reason_codes
    assert exact.final_decision == Decision.PASS
    assert FusionReason.PASS_THRESHOLD_MET in exact.reason_codes
    assert above.final_decision == Decision.PASS


def test_fallback_never_autopasses() -> None:
    output = fuse_decision(
        make_input(
            det_decision=Decision.PASS,
            det_conf=1.0,
            llm_decision=Decision.PASS,
            llm_conf=1.0,
            llm_fallback=True,
        )
    )
    assert output.final_decision == Decision.REVIEW_REQUIRED
    assert FusionReason.LLM_FALLBACK_CONSERVATIVE in output.reason_codes


def test_reason_codes_and_hints_are_deterministic_and_deduped() -> None:
    input_data = make_input(
        det_decision=Decision.PASS,
        det_conf=0.6,
        llm_decision=Decision.REVIEW_REQUIRED,
        llm_conf=0.8,
    )
    # add duplicate hints to ensure dedupe path is covered
    input_data.llm_remediation_hints = ["Add stronger evidence", "Add stronger evidence"]
    output_a = fuse_decision(input_data)
    output_b = fuse_decision(input_data)
    assert output_a.model_dump() == output_b.model_dump()
    assert output_a.remediation_hints.count("Add stronger evidence") == 1


def test_invariants_randomized() -> None:
    rng = random.Random(42)
    decisions = [Decision.PASS, Decision.REVIEW_REQUIRED, Decision.FAIL]
    for _ in range(250):
        det = rng.choice(decisions)
        llm = rng.choice(decisions)
        det_conf = rng.random()
        llm_conf = rng.random()
        output = fuse_decision(
            make_input(
                det_decision=det,
                det_conf=det_conf,
                llm_decision=llm,
                llm_conf=llm_conf,
                llm_fallback=rng.choice([True, False]),
            )
        )
        assert 0.0 <= output.fused_confidence <= 1.0
        if FusionReason.LLM_FALLBACK_CONSERVATIVE in output.reason_codes:
            assert output.final_decision != Decision.PASS


def test_import_and_call_has_no_side_effects() -> None:
    output = fuse_decision(
        make_input(
            det_decision=Decision.REVIEW_REQUIRED,
            det_conf=0.2,
            llm_decision=Decision.REVIEW_REQUIRED,
            llm_conf=0.2,
        )
    )
    assert output.final_decision == Decision.REVIEW_REQUIRED


def test_double_fail_reason_path() -> None:
    output = fuse_decision(
        make_input(
            det_decision=Decision.FAIL,
            det_conf=0.9,
            llm_decision=Decision.FAIL,
            llm_conf=0.9,
        )
    )
    assert output.final_decision == Decision.FAIL
    assert output.reason_codes == [FusionReason.DOUBLE_FAIL]


def test_conservative_default_path_for_review_fail_mix() -> None:
    output = fuse_decision(
        make_input(
            det_decision=Decision.REVIEW_REQUIRED,
            det_conf=0.6,
            llm_decision=Decision.FAIL,
            llm_conf=0.7,
        )
    )
    assert output.final_decision == Decision.REVIEW_REQUIRED
    assert FusionReason.CONSERVATIVE_DEFAULT_REVIEW in output.reason_codes
