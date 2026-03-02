"""Pydantic models for parsing and validating feature compliance specs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Control(BaseModel):
    """A required/implemented control attached to a feature."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    status: str = Field(min_length=1, max_length=32)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Restrict status values to a safe finite set for deterministic behavior."""
        allowed = {"planned", "implemented", "verified"}
        normalized = value.lower()
        if normalized not in allowed:
            raise ValueError(f"status must be one of: {sorted(allowed)}")
        return normalized


class FeatureComplianceSpec(BaseModel):
    """Normalized feature-level compliance spec."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    feature_id: str = Field(min_length=1, max_length=128)
    feature_name: str = Field(min_length=1, max_length=256)
    owner_team: str = Field(min_length=1, max_length=128)
    data_classification: str = Field(min_length=1, max_length=32)
    jurisdictions: list[str] = Field(min_length=1, max_length=25)
    controls: list[Control] = Field(min_length=1, max_length=100)
    change_summary: str = Field(min_length=1, max_length=4000)

    @field_validator("feature_id")
    @classmethod
    def validate_feature_id(cls, value: str) -> str:
        """Keep identifiers compact and predictable for storage/indexing keys."""
        if " " in value:
            raise ValueError("feature_id must not contain spaces")
        return value.lower()

    @field_validator("data_classification")
    @classmethod
    def validate_data_classification(cls, value: str) -> str:
        """Normalize classification so downstream policy rules stay simple."""
        allowed = {"public", "internal", "confidential", "restricted"}
        normalized = value.lower()
        if normalized not in allowed:
            raise ValueError(f"data_classification must be one of: {sorted(allowed)}")
        return normalized

    @field_validator("jurisdictions")
    @classmethod
    def validate_jurisdictions(cls, values: list[str]) -> list[str]:
        """Drop duplicates while preserving order and reject empty entries."""
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip().upper()
            if not normalized:
                raise ValueError("jurisdictions must not include empty values")
            if normalized not in seen:
                deduped.append(normalized)
                seen.add(normalized)
        return deduped
