"""Tests for Groq LLM adapter contracts and failure handling."""

from __future__ import annotations

import json

import pytest

from app.llm_adapter import (
    LLMEvaluationOutput,
    LLMEvaluationRequest,
    GroqConfig,
    build_llm_prompt,
    evaluate_with_groq,
    fallback_llm_result,
    load_groq_config,
    parse_llm_json_output,
)
from app.schemas import Control, FeatureComplianceSpec


def make_feature() -> FeatureComplianceSpec:
    return FeatureComplianceSpec(
        feature_id="payments_card_capture",
        feature_name="Card Capture",
        owner_team="payments-platform",
        data_classification="confidential",
        jurisdictions=["US"],
        controls=[
            Control(id="KYC-001", description="Verify identity", status="implemented"),
            Control(id="AUDIT-001", description="Audit trail", status="verified"),
        ],
        change_summary="Adds card capture endpoint.",
    )


def test_llm_output_contract_rejects_bad_confidence_and_extra_fields() -> None:
    with pytest.raises(Exception):
        LLMEvaluationOutput.model_validate(
            {
                "decision": "PASS",
                "confidence": 1.5,
                "summary": "ok",
                "findings": [],
                "remediation_hints": [],
                "evidence_chunk_ids": [],
            }
        )

    with pytest.raises(Exception):
        LLMEvaluationOutput.model_validate(
            {
                "decision": "PASS",
                "confidence": 0.8,
                "summary": "ok",
                "findings": [],
                "remediation_hints": [],
                "evidence_chunk_ids": [],
                "extra_field": "not allowed",
            }
        )


def test_load_groq_config_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        load_groq_config()

    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("COMPLIANCE_GROQ_TIMEOUT_SECONDS", "-1")
    with pytest.raises(RuntimeError, match="COMPLIANCE_GROQ_TIMEOUT_SECONDS"):
        load_groq_config()

    monkeypatch.setenv("COMPLIANCE_GROQ_TIMEOUT_SECONDS", "8")
    monkeypatch.delenv("COMPLIANCE_GROQ_MODEL", raising=False)
    cfg = load_groq_config()
    assert cfg.model == "llama-3.3-70b"
    assert cfg.max_retries >= 0


def test_build_llm_prompt_is_deterministic_and_redacted() -> None:
    request = LLMEvaluationRequest(
        feature=make_feature(),
        evidence_chunks=[],
        correlation_id="corr-1",
    )
    prompt_a = build_llm_prompt(request)
    prompt_b = build_llm_prompt(request)
    assert prompt_a == prompt_b
    assert "GROQ_API_KEY" not in prompt_a


def test_parse_llm_json_output_valid_and_invalid() -> None:
    output = parse_llm_json_output(
        json.dumps(
            {
                "decision": "pass",
                "confidence": 0.88,
                "summary": "Looks compliant",
                "findings": [],
                "remediation_hints": ["Add control evidence"],
                "evidence_chunk_ids": ["REG-2", "REG-2", "REG-1"],
            }
        )
    )
    assert output.decision == "PASS"
    assert output.evidence_chunk_ids == ["REG-1", "REG-2"]

    with pytest.raises(RuntimeError, match="valid JSON"):
        parse_llm_json_output("{bad-json")

    with pytest.raises(RuntimeError, match="contract validation failed"):
        parse_llm_json_output(json.dumps({"decision": "PASS"}))


def test_fallback_result_is_stable() -> None:
    a = fallback_llm_result(
        model="llama-3.3-70b",
        attempts=2,
        error_type="provider_error",
        diagnostic="upstream timeout",
        latency_ms=40,
    )
    b = fallback_llm_result(
        model="llama-3.3-70b",
        attempts=2,
        error_type="provider_error",
        diagnostic="upstream timeout",
        latency_ms=40,
    )
    assert a.model_dump() == b.model_dump()
    assert a.fallback is True
    assert a.decision == "REVIEW_REQUIRED"
    assert a.provider == "groq"


def test_evaluate_with_groq_success_and_logging() -> None:
    logs: list[dict] = []
    request = LLMEvaluationRequest(feature=make_feature(), evidence_chunks=[], correlation_id="corr-2")

    class FakeMessage:
        content = json.dumps(
            {
                "decision": "PASS",
                "confidence": 0.91,
                "summary": "Compliant",
                "findings": [],
                "remediation_hints": [],
                "evidence_chunk_ids": ["REG-1"],
            }
        )

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            assert kwargs["model"] == "llama-3.3-70b"
            assert kwargs["temperature"] == 0
            assert kwargs["response_format"] == {"type": "json_object"}
            return FakeResponse()

    result = evaluate_with_groq(
        request,
        config=GroqConfig(
            api_key="gsk-test",
            model="llama-3.3-70b",
            base_url="https://api.groq.com/openai/v1",
            timeout_seconds=1,
            max_retries=1,
            backoff_seconds=0,
        ),
        logger=logs.append,
        client_factory=FakeClient,
    )
    assert result.fallback is False
    assert result.decision == "PASS"
    assert any(log["event"] == "llm.success" for log in logs)


def test_evaluate_with_groq_retries_once_on_invalid_json() -> None:
    request = LLMEvaluationRequest(feature=make_feature(), evidence_chunks=[], correlation_id="corr-json")

    class FakeClient:
        calls = 0

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            FakeClient.calls += 1
            content = "{bad-json" if FakeClient.calls == 1 else json.dumps(
                {
                    "decision": "REVIEW_REQUIRED",
                    "confidence": 0.4,
                    "summary": "Needs manual review",
                    "findings": [],
                    "remediation_hints": ["Clarify control evidence"],
                    "evidence_chunk_ids": [],
                }
            )

            class Msg:
                pass

            class Choice:
                pass

            class Resp:
                pass

            msg = Msg()
            msg.content = content
            choice = Choice()
            choice.message = msg
            resp = Resp()
            resp.choices = [choice]
            return resp

    result = evaluate_with_groq(
        request,
        config=GroqConfig(
            api_key="gsk-test",
            model="llama-3.3-70b",
            base_url="https://api.groq.com/openai/v1",
            timeout_seconds=1,
            max_retries=0,
            backoff_seconds=0,
        ),
        client_factory=FakeClient,
    )
    assert result.fallback is False
    assert FakeClient.calls == 2


def test_evaluate_with_groq_fallback_after_second_invalid_json() -> None:
    request = LLMEvaluationRequest(feature=make_feature(), evidence_chunks=[], correlation_id="corr-invalid")

    class FakeClient:
        calls = 0

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            FakeClient.calls += 1

            class Msg:
                pass

            class Choice:
                pass

            class Resp:
                pass

            msg = Msg()
            msg.content = "{still-bad-json"
            choice = Choice()
            choice.message = msg
            resp = Resp()
            resp.choices = [choice]
            return resp

    result = evaluate_with_groq(
        request,
        config=GroqConfig(
            api_key="gsk-test",
            model="llama-3.3-70b",
            base_url="https://api.groq.com/openai/v1",
            timeout_seconds=1,
            max_retries=0,
            backoff_seconds=0,
        ),
        client_factory=FakeClient,
    )
    assert result.fallback is True
    assert result.decision == "REVIEW_REQUIRED"
    assert FakeClient.calls == 2


def test_failure_logs_do_not_leak_prompt_content() -> None:
    request = LLMEvaluationRequest(feature=make_feature(), evidence_chunks=[], correlation_id="corr-redact")
    logs: list[dict] = []

    class AlwaysBadClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            class ProviderError(Exception):
                status_code = 400

            raise ProviderError("bad request")

    result = evaluate_with_groq(
        request,
        config=GroqConfig(
            api_key="gsk-secret-value",
            model="llama-3.3-70b",
            base_url="https://api.groq.com/openai/v1",
            timeout_seconds=1,
            max_retries=0,
            backoff_seconds=0,
        ),
        logger=logs.append,
        client_factory=AlwaysBadClient,
    )
    assert result.fallback is True
    serialized = json.dumps(logs)
    assert "GROQ_API_KEY" not in serialized
    assert "Adds card capture endpoint." not in serialized
