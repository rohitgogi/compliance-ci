"""Tests for OpenAI LLM adapter contracts and failure handling."""

from __future__ import annotations

import json

import httpx
import pytest

from app.llm_adapter import (
    LLMEvaluationOutput,
    LLMEvaluationRequest,
    OpenAIConfig,
    build_llm_prompt,
    evaluate_with_openai,
    fallback_llm_result,
    load_openai_config,
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


def test_load_openai_config_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        load_openai_config()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "-1")
    with pytest.raises(RuntimeError, match="OPENAI_TIMEOUT_SECONDS"):
        load_openai_config()

    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "8")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    cfg = load_openai_config()
    assert cfg.model == "gpt-4.1-mini"
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
    assert "OPENAI_API_KEY" not in prompt_a


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
        model="gpt-4.1-mini",
        attempts=3,
        error_type="provider_error",
        diagnostic="upstream timeout",
        latency_ms=40,
    )
    b = fallback_llm_result(
        model="gpt-4.1-mini",
        attempts=3,
        error_type="provider_error",
        diagnostic="upstream timeout",
        latency_ms=40,
    )
    assert a.model_dump() == b.model_dump()
    assert a.fallback is True
    assert a.decision == "REVIEW_REQUIRED"


def test_evaluate_with_openai_success_and_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    logs: list[dict] = []
    request = LLMEvaluationRequest(feature=make_feature(), evidence_chunks=[], correlation_id="corr-2")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "output_text": json.dumps(
                    {
                        "decision": "PASS",
                        "confidence": 0.91,
                        "summary": "Compliant",
                        "findings": [],
                        "remediation_hints": [],
                        "evidence_chunk_ids": ["REG-1"],
                    }
                )
            }

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, headers: dict, json: dict):
            assert json["model"] == "gpt-4.1-mini"
            return FakeResponse()

    result = evaluate_with_openai(
        request,
        config=OpenAIConfig(
            api_key="sk-test",
            model="gpt-4.1-mini",
            base_url="https://api.openai.com/v1",
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


def test_evaluate_with_openai_retry_and_non_retryable_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    request = LLMEvaluationRequest(feature=make_feature(), evidence_chunks=[], correlation_id="corr-3")

    class RetryClient:
        calls = 0

        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, headers: dict, json: dict):
            RetryClient.calls += 1
            if RetryClient.calls == 1:
                raise httpx.TimeoutException("timed out")
            return type(
                "Resp",
                (),
                {
                    "raise_for_status": lambda self: None,
                    "json": lambda self: {
                        "output_text": json_module.dumps(
                            {
                                "decision": "REVIEW_REQUIRED",
                                "confidence": 0.4,
                                "summary": "Needs manual review",
                                "findings": [],
                                "remediation_hints": ["Clarify control evidence"],
                                "evidence_chunk_ids": [],
                            }
                        )
                    },
                },
            )()

    json_module = json
    result = evaluate_with_openai(
        request,
        config=OpenAIConfig(
            api_key="sk-test",
            model="gpt-4.1-mini",
            base_url="https://api.openai.com/v1",
            timeout_seconds=1,
            max_retries=2,
            backoff_seconds=0,
        ),
        client_factory=RetryClient,
    )
    assert result.fallback is False
    assert RetryClient.calls == 2

    class NonRetryableClient:
        calls = 0

        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, headers: dict, json: dict):
            NonRetryableClient.calls += 1
            req = httpx.Request("POST", url)
            resp = httpx.Response(400, request=req)
            raise httpx.HTTPStatusError("bad request", request=req, response=resp)

    fallback = evaluate_with_openai(
        request,
        config=OpenAIConfig(
            api_key="sk-test",
            model="gpt-4.1-mini",
            base_url="https://api.openai.com/v1",
            timeout_seconds=1,
            max_retries=3,
            backoff_seconds=0,
        ),
        client_factory=NonRetryableClient,
    )
    assert fallback.fallback is True
    assert NonRetryableClient.calls == 1


def test_evaluate_with_openai_supports_responses_api_output_shape() -> None:
    request = LLMEvaluationRequest(feature=make_feature(), evidence_chunks=[], correlation_id="corr-shape")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "output": [
                    {
                        "content": [
                            {
                                "text": json.dumps(
                                    {
                                        "decision": "PASS",
                                        "confidence": 0.83,
                                        "summary": "shape ok",
                                        "findings": [],
                                        "remediation_hints": [],
                                        "evidence_chunk_ids": ["REG-1"],
                                    }
                                )
                            }
                        ]
                    }
                ]
            }

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, headers: dict, json: dict):
            return FakeResponse()

    result = evaluate_with_openai(
        request,
        config=OpenAIConfig(
            api_key="sk",
            model="gpt-4.1-mini",
            base_url="https://api.openai.com/v1",
            timeout_seconds=1,
            max_retries=0,
            backoff_seconds=0,
        ),
        client_factory=FakeClient,
    )
    assert result.decision == "PASS"
    assert result.fallback is False


def test_failure_logs_do_not_leak_prompt_content() -> None:
    request = LLMEvaluationRequest(feature=make_feature(), evidence_chunks=[], correlation_id="corr-redact")
    logs: list[dict] = []

    class AlwaysBadClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, headers: dict, json: dict):
            req = httpx.Request("POST", url)
            resp = httpx.Response(400, request=req)
            raise httpx.HTTPStatusError("bad request", request=req, response=resp)

    result = evaluate_with_openai(
        request,
        config=OpenAIConfig(
            api_key="sk-secret-value",
            model="gpt-4.1-mini",
            base_url="https://api.openai.com/v1",
            timeout_seconds=1,
            max_retries=0,
            backoff_seconds=0,
        ),
        logger=logs.append,
        client_factory=AlwaysBadClient,
    )
    assert result.fallback is True
    assert logs
    serialized = json.dumps(logs)
    assert "OPENAI_API_KEY" not in serialized
    assert "Adds card capture endpoint." not in serialized
