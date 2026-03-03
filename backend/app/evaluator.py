"""Deterministic compliance evaluator with lightweight retrieval grounding."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import FeatureComplianceSpec
from app.vector_retriever import PgVectorCorpusStore, load_vector_config


@dataclass(frozen=True)
class CorpusChunk:
    """A single indexed regulation chunk with stable identifier."""

    chunk_id: str
    title: str
    text: str
    tags: tuple[str, ...]
    corpus_version: str


@dataclass(frozen=True)
class EvaluationResult:
    """Final output consumed by API/CI layers."""

    feature_id: str
    decision: str
    risk_score: int
    evidence_chunk_ids: list[str]
    reasoning_summary: str
    corpus_version: str


DEFAULT_CORPUS: tuple[CorpusChunk, ...] = (
    CorpusChunk(
        chunk_id="REG-US-KYC-001",
        title="KYC baseline requirements",
        text="US fintech flows must verify user identity before enabling fund movement.",
        tags=("US", "KYC", "IDENTITY"),
        corpus_version="v1",
    ),
    CorpusChunk(
        chunk_id="REG-EU-GDPR-010",
        title="GDPR data minimization and lawful basis",
        text="EU user data processing requires lawful basis, minimization, and retention controls.",
        tags=("EU", "GDPR", "DATA"),
        corpus_version="v1",
    ),
    CorpusChunk(
        chunk_id="REG-GEN-AUDIT-002",
        title="Audit logging and traceability",
        text="Compliance-sensitive operations must generate tamper-evident audit trails.",
        tags=("AUDIT", "TRACEABILITY"),
        corpus_version="v1",
    ),
)


def map_risk_score_to_decision(risk_score: int) -> str:
    """Map score bands to policy decisions used by CI."""
    if risk_score <= 30:
        return "PASS"
    if risk_score <= 69:
        return "REVIEW_REQUIRED"
    return "FAIL"


def retrieve_relevant_chunks(
    spec: FeatureComplianceSpec,
    corpus: tuple[CorpusChunk, ...] = DEFAULT_CORPUS,
    limit: int = 3,
) -> list[CorpusChunk]:
    """
    Retrieve highest-overlap chunks based on deterministic keyword matching.

    This is intentionally simple for MVP: it keeps behavior predictable and testable
    while still grounding decisions in corpus evidence.
    """
    if limit <= 0:
        return []

    query_text = (
        f"feature_name: {spec.feature_name}\n"
        f"data_classification: {spec.data_classification}\n"
        f"jurisdictions: {', '.join(spec.jurisdictions)}\n"
        f"controls: {', '.join(f'{c.id}:{c.status}' for c in spec.controls)}\n"
        f"change_summary: {spec.change_summary}"
    )

    # Primary retrieval path: local embeddings + pgvector.
    vector_config = load_vector_config()
    if vector_config is not None:
        try:
            vector_store = PgVectorCorpusStore(vector_config)
            vector_store.ingest_chunks(corpus)
            vector_matches = vector_store.search(
                query_text=query_text,
                scope_chunk_ids=[chunk.chunk_id for chunk in corpus],
                limit=limit,
            )
            if vector_matches:
                return vector_matches
        except Exception:
            # Safety-first fallback to deterministic retrieval when vector infra is unavailable.
            pass

    search_terms = {
        spec.feature_name.upper(),
        spec.data_classification.upper(),
        *[j.upper() for j in spec.jurisdictions],
        *[control.id.upper() for control in spec.controls],
        *[control.status.upper() for control in spec.controls],
    }

    scored: list[tuple[int, CorpusChunk]] = []
    for chunk in corpus:
        chunk_text = f"{chunk.title} {chunk.text} {' '.join(chunk.tags)}".upper()
        overlap = sum(1 for term in search_terms if term and term in chunk_text)
        scored.append((overlap, chunk))

    scored.sort(key=lambda item: (item[0], item[1].chunk_id), reverse=True)
    return [chunk for score, chunk in scored if score > 0][:limit]


def evaluate_feature_spec(
    spec: FeatureComplianceSpec,
    corpus: tuple[CorpusChunk, ...] = DEFAULT_CORPUS,
) -> EvaluationResult:
    """
    Evaluate compliance risk using explicit rules plus retrieved evidence.

    Security-oriented design:
    - No dynamic code execution.
    - No outbound network calls.
    - Deterministic scoring to reduce model-induced drift in CI gating.
    """
    retrieved = retrieve_relevant_chunks(spec, corpus=corpus, limit=3)
    score = 15
    reasons: list[str] = []

    implemented_controls = [c for c in spec.controls if c.status == "implemented"]
    verified_controls = [c for c in spec.controls if c.status == "verified"]
    has_kyc_control = any("KYC" in c.id.upper() for c in spec.controls)
    has_gdpr_control = any("GDPR" in c.id.upper() for c in spec.controls)
    has_audit_control = any("AUDIT" in c.id.upper() for c in spec.controls)

    if spec.data_classification == "restricted" and not verified_controls:
        score += 50
        reasons.append("Restricted data without verified controls")

    if "US" in spec.jurisdictions and not has_kyc_control:
        score += 30
        reasons.append("US flow without explicit KYC control")

    if "EU" in spec.jurisdictions and not has_gdpr_control:
        score += 25
        reasons.append("EU flow without explicit GDPR control")

    planned_count = sum(1 for c in spec.controls if c.status == "planned")
    if planned_count > 0:
        score += min(20, planned_count * 8)
        reasons.append("Some controls are only planned")

    if not has_audit_control:
        score += 10
        reasons.append("No explicit audit control")

    if implemented_controls and retrieved:
        # Reduce risk modestly only if we have both implementation evidence and grounding.
        score -= 8
        reasons.append("Implemented controls with supporting regulatory grounding")

    final_score = max(0, min(100, score))
    decision = map_risk_score_to_decision(final_score)
    summary = "; ".join(reasons) if reasons else "No major compliance gaps detected"
    corpus_version = retrieved[0].corpus_version if retrieved else corpus[0].corpus_version

    return EvaluationResult(
        feature_id=spec.feature_id,
        decision=decision,
        risk_score=final_score,
        evidence_chunk_ids=[chunk.chunk_id for chunk in retrieved],
        reasoning_summary=summary,
        corpus_version=corpus_version,
    )
