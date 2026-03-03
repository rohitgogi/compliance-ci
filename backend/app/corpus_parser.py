"""Parser for uploaded corpus YAML files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from app.evaluator import CorpusChunk


@dataclass
class ParsedCorpus:
    """Result of parsing a corpus YAML file."""

    version_id: str
    source_set: str
    chunks: tuple[CorpusChunk, ...]


class CorpusValidationError(Exception):
    """Raised when corpus YAML is invalid or fails validation."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


def parse_corpus_yaml(raw_yaml: str) -> ParsedCorpus:
    """
    Parse and validate corpus YAML.

    Expected format:
        version_id: v2
        source_set: "User uploaded - 2025"
        chunks:
          - chunk_id: REG-001
            title: Regulation title
            text: Regulation body text.
            tags: [US, KYC, DATA]

    Uses yaml.safe_load to avoid arbitrary object construction.
    """
    try:
        payload = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise CorpusValidationError("Invalid YAML syntax") from exc

    if not isinstance(payload, dict):
        raise CorpusValidationError("Corpus YAML must be a mapping at the top level")

    version_id = payload.get("version_id")
    if not version_id or not str(version_id).strip():
        raise CorpusValidationError("version_id is required and must be non-empty")
    version_id = str(version_id).strip()

    source_set = payload.get("source_set", "Uploaded corpus")
    source_set = str(source_set).strip() or "Uploaded corpus"

    chunks_raw = payload.get("chunks")
    if not isinstance(chunks_raw, list):
        raise CorpusValidationError(
            "chunks must be a list of chunk objects",
            details={"found_type": type(chunks_raw).__name__},
        )

    chunks: list[CorpusChunk] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(chunks_raw):
        if not isinstance(item, dict):
            raise CorpusValidationError(
                f"chunk at index {i} must be an object",
                details={"index": i, "found_type": type(item).__name__},
            )
        chunk_id = str(item.get("chunk_id", "")).strip()
        if not chunk_id:
            raise CorpusValidationError(
                f"chunk at index {i} has no chunk_id",
                details={"index": i},
            )
        if chunk_id in seen_ids:
            raise CorpusValidationError(
                f"duplicate chunk_id: {chunk_id}",
                details={"chunk_id": chunk_id},
            )
        seen_ids.add(chunk_id)

        title = str(item.get("title", "")).strip()
        text = str(item.get("text", "")).strip()
        tags_raw = item.get("tags", [])
        if isinstance(tags_raw, list):
            tags = tuple(str(t).strip() for t in tags_raw if t)
        else:
            tags = ()

        chunks.append(
            CorpusChunk(
                chunk_id=chunk_id,
                title=title,
                text=text,
                tags=tags,
                corpus_version=version_id,
            )
        )

    if not chunks:
        raise CorpusValidationError("At least one chunk is required")

    return ParsedCorpus(version_id=version_id, source_set=source_set, chunks=tuple(chunks))
