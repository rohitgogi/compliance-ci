"""Local embedding + pgvector retrieval utilities."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.evaluator import CorpusChunk


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _get_embedder(model_name: str):
    """Return cached local sentence-transformers embedder."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


@dataclass(frozen=True)
class VectorConfig:
    """Runtime config for pgvector-backed local retrieval."""

    dsn: str
    model_name: str


def load_vector_config() -> VectorConfig | None:
    """Load optional vector retrieval config from env."""
    dsn = os.environ.get("COMPLIANCE_PGVECTOR_DSN", "").strip()
    if not dsn:
        return None
    model_name = os.environ.get("COMPLIANCE_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
    if not model_name:
        raise RuntimeError("COMPLIANCE_EMBEDDING_MODEL must be non-empty")
    return VectorConfig(dsn=dsn, model_name=model_name)


class PgVectorCorpusStore:
    """Corpus embedding storage and similarity search using pgvector."""

    def __init__(self, config: VectorConfig) -> None:
        self.config = config

    def _connect(self):
        import psycopg
        from pgvector.psycopg import register_vector

        conn = psycopg.connect(self.config.dsn)
        conn.autocommit = True
        register_vector(conn)
        return conn

    def ensure_schema(self, vector_dim: int) -> None:
        """Create pgvector extension/table if needed."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS compliance_corpus_embeddings (
                    chunk_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    text_body TEXT NOT NULL,
                    tags TEXT[] NOT NULL,
                    corpus_version TEXT NOT NULL,
                    embedding VECTOR({vector_dim}) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

    def ingest_chunks(self, chunks: tuple["CorpusChunk", ...]) -> None:
        """Embed and upsert corpus chunks."""
        if not chunks:
            return
        embedder = _get_embedder(self.config.model_name)
        texts = [
            f"title: {chunk.title}\ntext: {chunk.text}\ntags: {', '.join(chunk.tags)}"
            for chunk in chunks
        ]
        vectors = embedder.encode(texts, normalize_embeddings=True)
        vector_dim = len(vectors[0])
        self.ensure_schema(vector_dim)

        with self._connect() as conn, conn.cursor() as cur:
            for chunk, vector in zip(chunks, vectors):
                cur.execute(
                    """
                    INSERT INTO compliance_corpus_embeddings (
                        chunk_id, title, text_body, tags, corpus_version, embedding, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        text_body = EXCLUDED.text_body,
                        tags = EXCLUDED.tags,
                        corpus_version = EXCLUDED.corpus_version,
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                    """,
                    (
                        chunk.chunk_id,
                        chunk.title,
                        chunk.text,
                        list(chunk.tags),
                        chunk.corpus_version,
                        vector.tolist(),
                    ),
                )

    def search(
        self,
        *,
        query_text: str,
        scope_chunk_ids: list[str],
        limit: int,
    ) -> list["CorpusChunk"]:
        """Run pgvector cosine similarity search constrained to current corpus scope."""
        from app.evaluator import CorpusChunk

        if limit <= 0 or not scope_chunk_ids:
            return []
        embedder = _get_embedder(self.config.model_name)
        query_vector = embedder.encode([query_text], normalize_embeddings=True)[0].tolist()

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_id, title, text_body, tags, corpus_version
                FROM compliance_corpus_embeddings
                WHERE chunk_id = ANY(%s)
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (scope_chunk_ids, query_vector, limit),
            )
            rows = cur.fetchall()
        return [
            CorpusChunk(
                chunk_id=str(row[0]),
                title=str(row[1]),
                text=str(row[2]),
                tags=tuple(row[3] or []),
                corpus_version=str(row[4]),
            )
            for row in rows
        ]
