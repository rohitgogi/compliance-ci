"""Tests for corpus upload endpoint and parser."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import api
from app.api import app
from app.corpus_parser import CorpusValidationError, parse_corpus_yaml

client = TestClient(app)


# --- Parser tests ---

def test_parse_corpus_yaml_valid() -> None:
    yaml_content = """
version_id: v2
source_set: Test corpus
chunks:
  - chunk_id: REG-001
    title: KYC requirements
    text: Verify identity before fund movement.
    tags: [US, KYC]
  - chunk_id: REG-002
    title: GDPR
    text: Lawful basis required.
    tags: [EU, GDPR]
"""
    parsed = parse_corpus_yaml(yaml_content)
    assert parsed.version_id == "v2"
    assert parsed.source_set == "Test corpus"
    assert len(parsed.chunks) == 2
    assert parsed.chunks[0].chunk_id == "REG-001"
    assert parsed.chunks[0].corpus_version == "v2"
    assert parsed.chunks[1].tags == ("EU", "GDPR")


def test_parse_corpus_yaml_invalid_yaml() -> None:
    import pytest

    with pytest.raises(CorpusValidationError, match="Invalid YAML"):
        parse_corpus_yaml("not: valid: yaml: [")


def test_parse_corpus_yaml_missing_version_id() -> None:
    import pytest

    with pytest.raises(CorpusValidationError, match="version_id"):
        parse_corpus_yaml("source_set: x\nchunks: []")


def test_parse_corpus_yaml_empty_chunks() -> None:
    import pytest

    with pytest.raises(CorpusValidationError, match="At least one chunk"):
        parse_corpus_yaml("version_id: v1\nsource_set: x\nchunks: []")


def test_parse_corpus_yaml_duplicate_chunk_id() -> None:
    import pytest

    yaml_content = """
version_id: v1
source_set: x
chunks:
  - chunk_id: R1
    title: T
    text: B
    tags: []
  - chunk_id: R1
    title: T2
    text: B2
    tags: []
"""
    with pytest.raises(CorpusValidationError, match="duplicate"):
        parse_corpus_yaml(yaml_content)


# --- API tests (require tmp_path + monkeypatch for isolated DB) ---

def test_upload_corpus_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPLIANCE_DB_PATH", str(tmp_path / "compliance.db"))
    api._get_store.cache_clear()

    corpus_yaml = """
version_id: v-uploaded
source_set: Uploaded test corpus
chunks:
  - chunk_id: UPL-001
    title: Uploaded regulation
    text: This was uploaded via the API.
    tags: [UPLOAD, TEST]
"""
    files = {"file": ("corpus.yaml", corpus_yaml.encode(), "application/x-yaml")}
    response = client.post("/v1/corpus-versions/upload", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["version_id"] == "v-uploaded"
    assert body["source_set"] == "Uploaded test corpus"
    assert body["chunk_count"] == 1
    assert body["chunk_ids"] == ["UPL-001"]
    assert "released_at" in body


def test_upload_corpus_rejects_non_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPLIANCE_DB_PATH", str(tmp_path / "compliance.db"))
    api._get_store.cache_clear()

    files = {"file": ("data.json", b'{"x": 1}', "application/json")}
    response = client.post("/v1/corpus-versions/upload", files=files)
    assert response.status_code == 400
    assert "YAML" in response.json().get("detail", "")


def test_upload_corpus_invalid_content(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMPLIANCE_DB_PATH", str(tmp_path / "compliance.db"))
    api._get_store.cache_clear()

    files = {"file": ("corpus.yaml", b"chunks: []\nversion_id: v1", "application/x-yaml")}
    response = client.post("/v1/corpus-versions/upload", files=files)
    assert response.status_code == 400
    assert "chunk" in response.json().get("detail", "").lower()
