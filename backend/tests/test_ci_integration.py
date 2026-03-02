"""Tests for GitHub Action integration helper behavior."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.ci_integration import (
    build_evaluate_payload,
    filter_changed_spec_paths,
    submit_evaluation,
    validate_evaluation_response,
)


def test_filter_changed_spec_paths_from_sample_diff() -> None:
    changed_paths = [
        "README.md",
        "backend/features/payments/card_capture.yaml",
        "backend/features/payments/transfer.yml",
        "backend/spec.md",
        "backend/features/../secrets.yaml",
    ]
    filtered = filter_changed_spec_paths(changed_paths)
    assert filtered == [
        "backend/features/payments/card_capture.yaml",
        "backend/features/payments/transfer.yml",
    ]


def test_build_payload_reads_only_existing_spec_files(tmp_path: Path) -> None:
    spec_file = tmp_path / "backend/features/payments/card_capture.yaml"
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.write_text("feature_id: payments_card_capture\n", encoding="utf-8")

    payload = build_evaluate_payload(
        repo="acme/compliance-ci",
        pr_number=42,
        commit_sha="abcdef1",
        base_dir=tmp_path,
        changed_paths=[
            "backend/features/payments/card_capture.yaml",
            "backend/features/payments/deleted.yaml",
        ],
    )

    assert payload["repo"] == "acme/compliance-ci"
    assert payload["payload_version"] == "v1"
    assert len(payload["specs"]) == 1
    assert payload["specs"][0]["path"].endswith("card_capture.yaml")


def test_build_payload_orders_paths_deterministically(tmp_path: Path) -> None:
    for relative_path in [
        "backend/features/payments/z.yaml",
        "backend/features/payments/a.yaml",
    ]:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("feature_id: example\n", encoding="utf-8")

    payload = build_evaluate_payload(
        repo="acme/compliance-ci",
        pr_number=42,
        commit_sha="abcdef1",
        base_dir=tmp_path,
        changed_paths=[
            "backend/features/payments/z.yaml",
            "backend/features/payments/a.yaml",
        ],
    )
    assert [item["path"] for item in payload["specs"]] == [
        "backend/features/payments/a.yaml",
        "backend/features/payments/z.yaml",
    ]


def test_build_payload_empty_spec_file_raises_clear_error(tmp_path: Path) -> None:
    empty_spec = tmp_path / "backend/features/payments/empty.yaml"
    empty_spec.parent.mkdir(parents=True, exist_ok=True)
    empty_spec.write_text(" \n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Spec file is empty"):
        build_evaluate_payload(
            repo="acme/compliance-ci",
            pr_number=1,
            commit_sha="abcdef1",
            base_dir=tmp_path,
            changed_paths=["backend/features/payments/empty.yaml"],
        )


def test_validate_response_contract_accepts_valid_response() -> None:
    response = {
        "repo": "acme/compliance-ci",
        "pr_number": 1,
        "commit_sha": "abcdef1",
        "final_gate": "PASS",
        "comment_markdown": "ok",
        "llm_adapter_enabled": True,
        "results": [
            {
                "path": "backend/features/payments/a.yaml",
                "feature_id": "payments_a",
                "decision": "PASS",
                "risk_score": 12,
                "deterministic_confidence": 0.88,
                "evidence_chunk_ids": [],
                "reasoning_summary": "ok",
                "llm_observation": {"decision": "PASS", "confidence": 0.9},
                "fusion_observation": {"final_decision": "PASS", "fused_confidence": 0.9},
                "error": None,
                "validation_details": [],
            }
        ],
    }
    validated = validate_evaluation_response(response)
    assert validated["final_gate"] == "PASS"


@pytest.mark.parametrize(
    "bad_response",
    [
        {
            "repo": "acme/compliance-ci",
            "pr_number": 1,
            "commit_sha": "abcdef1",
            "final_gate": "PASS",
            "comment_markdown": "ok",
            "results": [{"path": "x", "risk_score": 20, "decision": None}],
        },
        {
            "repo": "acme/compliance-ci",
            "pr_number": 1,
            "commit_sha": "abcdef1",
            "final_gate": "PASS",
            "comment_markdown": "ok",
            "results": [{"path": "x", "decision": "PASS", "risk_score": 101}],
        },
        {
            "repo": "acme/compliance-ci",
            "pr_number": 1,
            "commit_sha": "abcdef1",
            "final_gate": "BAD_GATE",
            "comment_markdown": "ok",
            "results": [],
        },
        {
            "repo": "acme/compliance-ci",
            "pr_number": 1,
            "commit_sha": "abcdef1",
            "final_gate": "PASS",
            "comment_markdown": "ok",
            "results": [{"path": "x", "decision": "PASS", "risk_score": 20, "deterministic_confidence": 1.5}],
        },
    ],
)
def test_validate_response_contract_rejects_invalid_states(bad_response: dict) -> None:
    with pytest.raises(RuntimeError):
        validate_evaluation_response(bad_response)


def test_submit_evaluation_unreachable_backend_raises_runtime_error() -> None:
    payload = {"repo": "acme/compliance-ci", "pr_number": 1, "commit_sha": "abcdef1", "specs": []}
    with pytest.raises(RuntimeError):
        submit_evaluation("http://127.0.0.1:9", payload, timeout_seconds=0.1)


def test_submit_evaluation_retries_on_transient_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, body: dict) -> None:
            self.status_code = status_code
            self._body = body
            self.request = httpx.Request("POST", "http://example/v1/evaluate-pr")

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("error", request=self.request, response=self)

        def json(self) -> dict:
            return self._body

    class FakeClient:
        call_count = 0

        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, json: dict):
            FakeClient.call_count += 1
            if FakeClient.call_count == 1:
                return FakeResponse(503, {"error": "transient"})
            return FakeResponse(
                200,
                {
                    "repo": "acme/compliance-ci",
                    "pr_number": 1,
                    "commit_sha": "abcdef1",
                    "final_gate": "PASS",
                    "comment_markdown": "ok",
                    "results": [],
                },
            )

    monkeypatch.setattr("app.ci_integration.httpx.Client", FakeClient)
    response = submit_evaluation("http://example", {"specs": []}, timeout_seconds=0.1, max_retries=2, backoff_seconds=0)
    assert response["final_gate"] == "PASS"
    assert FakeClient.call_count == 2


def test_submit_evaluation_does_not_retry_non_retryable_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = 400
            self.request = httpx.Request("POST", "http://example/v1/evaluate-pr")

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("error", request=self.request, response=self)

        def json(self) -> dict:
            return {"error": "bad request"}

    class FakeClient:
        call_count = 0

        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, json: dict):
            FakeClient.call_count += 1
            return FakeResponse()

    monkeypatch.setattr("app.ci_integration.httpx.Client", FakeClient)
    with pytest.raises(RuntimeError, match="non-retryable status 400"):
        submit_evaluation("http://example", {"specs": []}, timeout_seconds=0.1, max_retries=3, backoff_seconds=0)
    assert FakeClient.call_count == 1


def test_submit_evaluation_retries_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "repo": "acme/compliance-ci",
                "pr_number": 1,
                "commit_sha": "abcdef1",
                "final_gate": "PASS",
                "comment_markdown": "ok",
                "results": [],
            }

    class FakeClient:
        call_count = 0

        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, json: dict):
            FakeClient.call_count += 1
            if FakeClient.call_count == 1:
                raise httpx.TimeoutException("timed out")
            return FakeResponse()

    monkeypatch.setattr("app.ci_integration.httpx.Client", FakeClient)
    response = submit_evaluation("http://example", {"specs": []}, timeout_seconds=0.1, max_retries=2, backoff_seconds=0)
    assert response["final_gate"] == "PASS"
    assert FakeClient.call_count == 2
