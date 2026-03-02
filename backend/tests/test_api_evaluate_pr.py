"""API tests for PR evaluation endpoint behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)

VALID_SPEC = """
feature_id: PAYMENTS_CARD_CAPTURE
feature_name: Card Capture
owner_team: payments-platform
data_classification: confidential
jurisdictions: [US]
controls:
  - id: KYC-001
    description: Verify identity before enabling transfers
    status: implemented
  - id: AUDIT-001
    description: Immutable audit trail
    status: verified
change_summary: Added card capture endpoint with KYC and audit checks.
"""


def test_evaluate_single_feature() -> None:
    payload = {
        "repo": "acme/compliance-ci",
        "pr_number": 42,
        "commit_sha": "abcdef1234567",
        "specs": [
            {"path": "backend/features/payments/card_capture.yaml", "spec_yaml": VALID_SPEC}
        ],
    }
    response = client.post("/v1/evaluate-pr", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["decision"] in {"PASS", "REVIEW_REQUIRED", "FAIL"}
    assert body["results"][0]["risk_score"] is not None
    assert body["results"][0]["error"] is None


def test_evaluate_multiple_features() -> None:
    payload = {
        "repo": "acme/compliance-ci",
        "pr_number": 43,
        "commit_sha": "1234567abcdef",
        "specs": [
            {"path": "backend/features/payments/card_capture.yaml", "spec_yaml": VALID_SPEC},
            {
                "path": "backend/features/payments/transfer.yaml",
                "spec_yaml": VALID_SPEC.replace("PAYMENTS_CARD_CAPTURE", "PAYMENTS_TRANSFER"),
            },
        ],
    }
    response = client.post("/v1/evaluate-pr", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 2


def test_malformed_payload_returns_422() -> None:
    # Invalid because `specs` is missing entirely.
    payload = {"repo": "acme/compliance-ci", "pr_number": 44, "commit_sha": "abcdef1"}
    response = client.post("/v1/evaluate-pr", json=payload)
    assert response.status_code == 422


def test_partial_failure_does_not_hide_valid_feature_result() -> None:
    invalid_spec = """
feature_name: Missing feature id
owner_team: payments-platform
data_classification: confidential
jurisdictions: [US]
controls:
  - id: KYC-001
    description: Verify identity before enabling transfers
    status: implemented
change_summary: Missing required field.
"""
    payload = {
        "repo": "acme/compliance-ci",
        "pr_number": 45,
        "commit_sha": "abcdef7654321",
        "specs": [
            {"path": "backend/features/payments/card_capture.yaml", "spec_yaml": VALID_SPEC},
            {"path": "backend/features/payments/broken.yaml", "spec_yaml": invalid_spec},
        ],
    }
    response = client.post("/v1/evaluate-pr", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 2
    valid_result = next(item for item in body["results"] if item["path"].endswith("card_capture.yaml"))
    invalid_result = next(item for item in body["results"] if item["path"].endswith("broken.yaml"))
    assert valid_result["error"] is None
    assert invalid_result["error"] == "Spec schema validation failed"
    assert invalid_result["validation_details"]
