"""SQLite persistence for Compliance CI state and history."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    """UTC timestamp in stable ISO format for audit records."""
    return datetime.now(tz=UTC).isoformat()


@dataclass(frozen=True)
class EvaluationRecord:
    """Evaluation write payload persisted as immutable audit entry."""

    feature_id: str
    spec_version: str
    corpus_version: str
    risk_score: int
    decision: str
    evidence_chunk_ids: list[str]
    reasoning_summary: str
    commit_sha: str


class ComplianceStore:
    """Typed data-access wrapper with parameterized SQL only."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS feature_specs (
                    feature_id TEXT NOT NULL,
                    spec_version TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    path TEXT NOT NULL,
                    parsed_payload TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (feature_id, spec_version)
                );

                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feature_id TEXT NOT NULL,
                    spec_version TEXT NOT NULL,
                    corpus_version TEXT NOT NULL,
                    risk_score INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    evidence_chunk_ids TEXT NOT NULL,
                    reasoning_summary TEXT NOT NULL,
                    commit_sha TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    UNIQUE(feature_id, spec_version, corpus_version, commit_sha),
                    FOREIGN KEY (feature_id, spec_version)
                        REFERENCES feature_specs(feature_id, spec_version)
                );

                CREATE TABLE IF NOT EXISTS corpus_versions (
                    version_id TEXT PRIMARY KEY,
                    source_set TEXT NOT NULL,
                    released_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reevaluation_jobs (
                    job_id TEXT PRIMARY KEY,
                    target_corpus_version TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    status TEXT NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    error_summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reevaluation_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    feature_id TEXT NOT NULL,
                    previous_decision TEXT NOT NULL,
                    new_decision TEXT NOT NULL,
                    regressed INTEGER NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(job_id, feature_id),
                    FOREIGN KEY (job_id) REFERENCES reevaluation_jobs(job_id)
                );
                """
            )

    def upsert_feature_spec(
        self,
        *,
        feature_id: str,
        spec_version: str,
        content_hash: str,
        path: str,
        parsed_payload: dict[str, Any],
        active: bool = True,
    ) -> None:
        """Insert or update a versioned spec and keep one active version per feature."""
        now = utc_now_iso()
        with self._connect() as conn:
            if active:
                conn.execute(
                    "UPDATE feature_specs SET active = 0 WHERE feature_id = ?",
                    (feature_id,),
                )
            conn.execute(
                """
                INSERT INTO feature_specs (
                    feature_id, spec_version, content_hash, path, parsed_payload, active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feature_id, spec_version)
                DO UPDATE SET
                    content_hash = excluded.content_hash,
                    path = excluded.path,
                    parsed_payload = excluded.parsed_payload,
                    active = excluded.active
                """,
                (
                    feature_id,
                    spec_version,
                    content_hash,
                    path,
                    json.dumps(parsed_payload, sort_keys=True),
                    1 if active else 0,
                    now,
                ),
            )

    def get_latest_feature_spec(self, feature_id: str) -> dict[str, Any] | None:
        """Return currently active feature spec."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT feature_id, spec_version, content_hash, path, parsed_payload, active, created_at
                FROM feature_specs
                WHERE feature_id = ? AND active = 1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (feature_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "feature_id": row["feature_id"],
                "spec_version": row["spec_version"],
                "content_hash": row["content_hash"],
                "path": row["path"],
                "parsed_payload": json.loads(row["parsed_payload"]),
                "active": bool(row["active"]),
                "created_at": row["created_at"],
            }

    def get_feature_history(self, feature_id: str) -> list[dict[str, Any]]:
        """Return all stored versions of a feature, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT feature_id, spec_version, content_hash, path, parsed_payload, active, created_at
                FROM feature_specs
                WHERE feature_id = ?
                ORDER BY created_at DESC
                """,
                (feature_id,),
            ).fetchall()
            return [
                {
                    "feature_id": row["feature_id"],
                    "spec_version": row["spec_version"],
                    "content_hash": row["content_hash"],
                    "path": row["path"],
                    "parsed_payload": json.loads(row["parsed_payload"]),
                    "active": bool(row["active"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def record_evaluation(self, record: EvaluationRecord) -> None:
        """Store immutable evaluation result for audit and trend analysis."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO evaluations (
                    feature_id, spec_version, corpus_version, risk_score, decision,
                    evidence_chunk_ids, reasoning_summary, commit_sha, evaluated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.feature_id,
                    record.spec_version,
                    record.corpus_version,
                    record.risk_score,
                    record.decision,
                    json.dumps(record.evidence_chunk_ids, sort_keys=True),
                    record.reasoning_summary,
                    record.commit_sha,
                    utc_now_iso(),
                ),
            )

    def get_latest_decision(self, feature_id: str) -> str | None:
        """Return latest known decision for feature, if present."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT decision
                FROM evaluations
                WHERE feature_id = ?
                ORDER BY evaluated_at DESC, id DESC
                LIMIT 1
                """,
                (feature_id,),
            ).fetchone()
            return None if row is None else str(row["decision"])

    def get_evaluations(self, feature_id: str) -> list[dict[str, Any]]:
        """Return evaluation history for a feature, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT spec_version, corpus_version, risk_score, decision, evidence_chunk_ids,
                       reasoning_summary, commit_sha, evaluated_at
                FROM evaluations
                WHERE feature_id = ?
                ORDER BY evaluated_at DESC, id DESC
                """,
                (feature_id,),
            ).fetchall()
            return [
                {
                    "spec_version": row["spec_version"],
                    "corpus_version": row["corpus_version"],
                    "risk_score": int(row["risk_score"]),
                    "decision": row["decision"],
                    "evidence_chunk_ids": json.loads(row["evidence_chunk_ids"]),
                    "reasoning_summary": row["reasoning_summary"],
                    "commit_sha": row["commit_sha"],
                    "evaluated_at": row["evaluated_at"],
                }
                for row in rows
            ]

    def register_corpus_version(self, version_id: str, source_set: str) -> None:
        """Store corpus release metadata with idempotent upsert semantics."""
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO corpus_versions (version_id, source_set, released_at)
                VALUES (?, ?, ?)
                ON CONFLICT(version_id)
                DO UPDATE SET
                    source_set = excluded.source_set
                """,
                (version_id, source_set, now),
            )

    def get_corpus_version(self, version_id: str) -> dict[str, Any] | None:
        """Return corpus version metadata by ID."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT version_id, source_set, released_at
                FROM corpus_versions
                WHERE version_id = ?
                LIMIT 1
                """,
                (version_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "version_id": row["version_id"],
                "source_set": row["source_set"],
                "released_at": row["released_at"],
            }

    def create_reevaluation_job(
        self,
        *,
        job_id: str,
        target_corpus_version: str,
        scope: list[str],
        status: str = "pending",
    ) -> bool:
        """Create a reevaluation job exactly once; return False if duplicate."""
        now = utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO reevaluation_jobs (
                    job_id, target_corpus_version, scope, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, target_corpus_version, json.dumps(scope), status, now, now),
            )
            return cursor.rowcount == 1

    def get_reevaluation_job(self, job_id: str) -> dict[str, Any] | None:
        """Return reevaluation job metadata by ID."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT job_id, target_corpus_version, scope, status,
                       success_count, failure_count, error_summary, created_at, updated_at
                FROM reevaluation_jobs
                WHERE job_id = ?
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "job_id": row["job_id"],
                "target_corpus_version": row["target_corpus_version"],
                "scope": json.loads(row["scope"]),
                "status": row["status"],
                "success_count": int(row["success_count"]),
                "failure_count": int(row["failure_count"]),
                "error_summary": row["error_summary"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def update_reevaluation_job_status(
        self,
        *,
        job_id: str,
        status: str,
        success_count: int | None = None,
        failure_count: int | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Update reevaluation job status and aggregate counters."""
        with self._connect() as conn:
            current = conn.execute(
                """
                SELECT success_count, failure_count, error_summary
                FROM reevaluation_jobs
                WHERE job_id = ?
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if current is None:
                raise ValueError(f"Unknown reevaluation job: {job_id}")
            conn.execute(
                """
                UPDATE reevaluation_jobs
                SET status = ?,
                    success_count = ?,
                    failure_count = ?,
                    error_summary = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    int(success_count if success_count is not None else current["success_count"]),
                    int(failure_count if failure_count is not None else current["failure_count"]),
                    error_summary if error_summary is not None else current["error_summary"],
                    utc_now_iso(),
                    job_id,
                ),
            )

    def list_active_feature_ids(self) -> list[str]:
        """List all active feature IDs to target reevaluation runs."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT feature_id
                FROM feature_specs
                WHERE active = 1
                ORDER BY feature_id
                """
            ).fetchall()
            return [str(row["feature_id"]) for row in rows]

    def get_reevaluation_result(self, job_id: str, feature_id: str) -> dict[str, Any] | None:
        """Return a previously stored reevaluation result for resume support."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT job_id, feature_id, previous_decision, new_decision, regressed, details, created_at
                FROM reevaluation_results
                WHERE job_id = ? AND feature_id = ?
                LIMIT 1
                """,
                (job_id, feature_id),
            ).fetchone()
            if row is None:
                return None
            return {
                "job_id": row["job_id"],
                "feature_id": row["feature_id"],
                "previous_decision": row["previous_decision"],
                "new_decision": row["new_decision"],
                "regressed": bool(row["regressed"]),
                "details": json.loads(row["details"]),
                "created_at": row["created_at"],
            }

    def list_reevaluation_results(self, job_id: str) -> list[dict[str, Any]]:
        """List reevaluation results for a job in deterministic order."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT job_id, feature_id, previous_decision, new_decision, regressed, details, created_at
                FROM reevaluation_results
                WHERE job_id = ?
                ORDER BY feature_id
                """,
                (job_id,),
            ).fetchall()
            return [
                {
                    "job_id": row["job_id"],
                    "feature_id": row["feature_id"],
                    "previous_decision": row["previous_decision"],
                    "new_decision": row["new_decision"],
                    "regressed": bool(row["regressed"]),
                    "details": json.loads(row["details"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def record_regression(
        self,
        *,
        job_id: str,
        feature_id: str,
        previous_decision: str,
        new_decision: str,
        regressed: bool,
        details: dict[str, Any],
    ) -> None:
        """Persist reevaluation comparison result idempotently per (job, feature)."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reevaluation_results (
                    job_id, feature_id, previous_decision, new_decision, regressed, details, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, feature_id)
                DO UPDATE SET
                    previous_decision = excluded.previous_decision,
                    new_decision = excluded.new_decision,
                    regressed = excluded.regressed,
                    details = excluded.details
                """,
                (
                    job_id,
                    feature_id,
                    previous_decision,
                    new_decision,
                    1 if regressed else 0,
                    json.dumps(details, sort_keys=True),
                    utc_now_iso(),
                ),
            )
