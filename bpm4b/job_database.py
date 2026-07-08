"""
Local Database-Backed Conversion Logs (Job History)

Stores job metadata, conversion speed histories, and output file paths
locally so users can track or re-manage previously processed audiobook collections.

Feature #10 from the BPM4B v13 feature set.
"""

import os
import json
import sqlite3
import logging
import threading
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

from .path_utils import data_dir, ensure_dir

logger = logging.getLogger(__name__)


# ─── Database Schema ────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    job_type        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running',
    source_path     TEXT,
    source_name     TEXT,
    output_path     TEXT,
    output_name     TEXT,
    file_size_bytes INTEGER,
    duration_seconds REAL,
    processing_time_seconds REAL,
    bitrate         TEXT,
    files_processed INTEGER DEFAULT 1,
    metadata        TEXT,  -- JSON blob
    error_message   TEXT,
    created_at      REAL NOT NULL,
    completed_at    REAL,
    updated_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);
"""


# ─── Job Database ───────────────────────────────────────────

class JobDatabase:
    """
    Lightweight SQLite-backed job history database.
    Thread-safe with connection-per-operation pattern.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(data_dir('bpm4b') / 'jobs.db')
        ensure_dir(os.path.dirname(db_path))
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self) -> None:
        """Initialize the database schema."""
        try:
            conn = self._get_conn()
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        except Exception as e:
            logger.error(f"Database init failed: {e}")

    def create_job(self, job_id: str, job_type: str, source_path: str = '',
                   output_path: str = '', metadata: Optional[Dict] = None) -> str:
        """Create a new job entry."""
        now = time.time()
        source_name = os.path.basename(source_path) if source_path else ''
        output_name = os.path.basename(output_path) if output_path else ''

        try:
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO jobs
                   (id, job_type, status, source_path, source_name,
                    output_path, output_name, metadata, created_at, updated_at)
                   VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, job_type, source_path, source_name,
                 output_path, output_name,
                 json.dumps(metadata or {}), now, now)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to create job: {e}")

        return job_id

    def complete_job(self, job_id: str, output_path: str = '',
                     duration_seconds: float = 0.0,
                     processing_time_seconds: float = 0.0,
                     bitrate: str = '',
                     files_processed: int = 1,
                     file_size_bytes: int = 0) -> None:
        """Mark a job as completed."""
        now = time.time()
        try:
            conn = self._get_conn()
            conn.execute(
                """UPDATE jobs SET
                   status = 'complete', output_path = ?,
                   output_name = ?, duration_seconds = ?,
                   processing_time_seconds = ?, bitrate = ?,
                   files_processed = ?, file_size_bytes = ?,
                   completed_at = ?, updated_at = ?
                   WHERE id = ?""",
                (output_path, os.path.basename(output_path) if output_path else '',
                 duration_seconds, processing_time_seconds, bitrate,
                 files_processed, file_size_bytes, now, now, job_id)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to complete job: {e}")

    def fail_job(self, job_id: str, error_message: str) -> None:
        """Mark a job as failed."""
        now = time.time()
        try:
            conn = self._get_conn()
            conn.execute(
                """UPDATE jobs SET
                   status = 'error', error_message = ?,
                   completed_at = ?, updated_at = ?
                   WHERE id = ?""",
                (error_message, now, now, job_id)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to fail job: {e}")

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID."""
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row:
                return self._row_to_dict(row)
        except Exception as e:
            logger.error(f"Failed to get job: {e}")
        return None

    def list_jobs(self, limit: int = 50, offset: int = 0,
                  status: Optional[str] = None,
                  job_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List jobs with optional filters."""
        query = "SELECT * FROM jobs"
        params = []
        conditions = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if job_type:
            conditions.append("job_type = ?")
            params.append(job_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        try:
            conn = self._get_conn()
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list jobs: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get job history statistics."""
        try:
            conn = self._get_conn()
            total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            complete = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'complete'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'error'"
            ).fetchone()[0]
            running = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'running'"
            ).fetchone()[0]

            total_duration = conn.execute(
                "SELECT COALESCE(SUM(duration_seconds), 0) FROM jobs WHERE status = 'complete'"
            ).fetchone()[0]

            total_files = conn.execute(
                "SELECT COALESCE(SUM(files_processed), 0) FROM jobs WHERE status = 'complete'"
            ).fetchone()[0]

            jobs_by_type = {}
            for row in conn.execute(
                "SELECT job_type, COUNT(*) as cnt FROM jobs GROUP BY job_type"
            ).fetchall():
                jobs_by_type[row['job_type']] = row['cnt']

            return {
                'total_jobs': total,
                'completed': complete,
                'failed': failed,
                'running': running,
                'total_duration_seconds': total_duration,
                'total_files_processed': total_files,
                'jobs_by_type': jobs_by_type,
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    def delete_job(self, job_id: str) -> bool:
        """Delete a job entry."""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete job: {e}")
            return False

    def clear_history(self) -> int:
        """Clear all job history. Returns number of deleted rows."""
        try:
            conn = self._get_conn()
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            conn.execute("DELETE FROM jobs")
            conn.commit()
            return count
        except Exception as e:
            logger.error(f"Failed to clear history: {e}")
            return 0

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a sqlite3.Row to a dict with parsed metadata."""
        d = dict(row)
        # Parse metadata JSON
        if d.get('metadata'):
            try:
                d['metadata'] = json.loads(d['metadata'])
            except (json.JSONDecodeError, TypeError):
                pass
        # Convert timestamps to ISO format for display
        for key in ('created_at', 'completed_at', 'updated_at'):
            if d.get(key):
                try:
                    d[f'{key}_iso'] = datetime.fromtimestamp(
                        d[key]
                    ).isoformat()
                except (ValueError, OSError):
                    pass
        return d


# ─── Global Singleton ────────────────────────────────────────

_default_db: Optional[JobDatabase] = None


def get_db() -> JobDatabase:
    """Get or create the default job database singleton."""
    global _default_db
    if _default_db is None:
        _default_db = JobDatabase()
    return _default_db
