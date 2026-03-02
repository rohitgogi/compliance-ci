"""Tests for YAML spec parsing, validation, and normalization."""

from __future__ import annotations

import pytest

from app.parser import SpecValidationError, parse_feature_spec_yaml


def test_valid_spec_parses_and_normalizes() -> None:
    raw_yaml = """
feature_id: PAYMENTS_CARD_CAPTURE
feature_name: Card Capture
owner_team: payments-platform
data_classification: Confidential
jurisdictions:
  - us
  - eu
  - US
controls:
  - id: KYC-001
    description: Verify identity before enabling transfers
    status: Implemented
change_summary: Added card capture endpoint with KYC check.
"""
    parsed = parse_feature_spec_yaml(raw_yaml)

    # Normalization checks.
    assert parsed.feature_id == "payments_card_capture"
    assert parsed.data_classification == "confidential"
    assert parsed.jurisdictions == ["US", "EU"]
    assert parsed.controls[0].status == "implemented"


def test_missing_required_field_returns_structured_error() -> None:
    raw_yaml = """
feature_name: Card Capture
owner_team: payments-platform
data_classification: confidential
jurisdictions: [US]
controls:
  - id: KYC-001
    description: Verify identity before enabling transfers
    status: implemented
change_summary: Added card capture endpoint with KYC check.
"""
    with pytest.raises(SpecValidationError) as exc_info:
        parse_feature_spec_yaml(raw_yaml)

    assert exc_info.value.message == "Spec schema validation failed"
    assert exc_info.value.details
    assert any(err["loc"] == ("feature_id",) for err in exc_info.value.details)


def test_wrong_type_returns_structured_error() -> None:
    raw_yaml = """
feature_id: PAYMENTS_CARD_CAPTURE
feature_name: Card Capture
owner_team: payments-platform
data_classification: confidential
jurisdictions: [US]
controls:
  - id: KYC-001
    description: Verify identity before enabling transfers
    status: implemented
change_summary:
  - this-should-be-a-string
"""
    with pytest.raises(SpecValidationError) as exc_info:
        parse_feature_spec_yaml(raw_yaml)

    assert any(err["loc"] == ("change_summary",) for err in exc_info.value.details)


def test_unknown_field_is_rejected() -> None:
    raw_yaml = """
feature_id: PAYMENTS_CARD_CAPTURE
feature_name: Card Capture
owner_team: payments-platform
data_classification: confidential
jurisdictions: [US]
controls:
  - id: KYC-001
    description: Verify identity before enabling transfers
    status: implemented
change_summary: Added card capture endpoint with KYC check.
unexpected_field: should_fail
"""
    with pytest.raises(SpecValidationError) as exc_info:
        parse_feature_spec_yaml(raw_yaml)

    assert any(err["loc"] == ("unexpected_field",) for err in exc_info.value.details)


def test_invalid_yaml_syntax_fails_cleanly() -> None:
    raw_yaml = "feature_id: [unterminated"
    with pytest.raises(SpecValidationError) as exc_info:
        parse_feature_spec_yaml(raw_yaml)
    assert exc_info.value.message == "Invalid YAML syntax"


def test_non_mapping_yaml_is_rejected() -> None:
    raw_yaml = """
- feature_id: one
- feature_id: two
"""
    with pytest.raises(SpecValidationError) as exc_info:
        parse_feature_spec_yaml(raw_yaml)
    assert exc_info.value.message == "YAML must decode to a mapping/object at the top level"
