"""Secure YAML parser and schema validator for feature compliance specs."""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import ValidationError

from app.schemas import FeatureComplianceSpec


class SpecValidationError(Exception):
    """Raised when YAML payload cannot be safely parsed or validated."""

    def __init__(self, message: str, details: list[dict[str, Any]] | None = None) -> None:
        self.message = message
        self.details = details or []
        super().__init__(message)


def parse_feature_spec_yaml(raw_yaml: str) -> FeatureComplianceSpec:
    """
    Parse and validate YAML using SafeLoader only.

    Security notes:
    - Uses yaml.safe_load to block arbitrary object construction.
    - Enforces top-level mapping type to avoid type confusion.
    - Returns normalized pydantic model instead of untyped dictionaries.
    """
    try:
        payload = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise SpecValidationError("Invalid YAML syntax") from exc

    if not isinstance(payload, dict):
        raise SpecValidationError("YAML must decode to a mapping/object at the top level")

    try:
        return FeatureComplianceSpec.model_validate(payload)
    except ValidationError as exc:
        raise SpecValidationError(
            message="Spec schema validation failed",
            details=exc.errors(include_url=False),
        ) from exc
