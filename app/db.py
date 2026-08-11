"""Postgres access: application data plus the job queue (SKIP LOCKED pattern).

Kept as plain SQL rather than an ORM — the schema is small (one table) and the
claim/reclaim queries below are the whole point of this design, so hiding them
behind an abstraction would make the thing we most need to explain harder to see.
"""

import os
from contextlib import contextmanager

from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def init_pool() -> None:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(conninfo=os.environ["DATABASE_URL"], min_size=1, max_size=5, open=True)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_conn():
    if _pool is None:
        init_pool()
    with _pool.connection() as conn:
        yield conn


def health_check() -> bool:
    with get_conn() as conn:
        conn.execute("SELECT 1").fetchone()
    return True


def enqueue_job(spaces_key: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO jobs (spaces_key) VALUES (%s) RETURNING id",
            (spaces_key,),
        ).fetchone()
        return row[0]


def get_job(job_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, status, spaces_key, attempts, max_attempts, last_error,
                      result, created_at, updated_at
               FROM jobs WHERE id = %s""",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        cols = ["id", "status", "spaces_key", "attempts", "max_attempts",
                "last_error", "result", "created_at", "updated_at"]
        return dict(zip(cols, row))


def queue_stats() -> dict:
    with get_conn() as conn:
        counts = dict(conn.execute(
            "SELECT status, count(*) FROM jobs GROUP BY status"
        ).fetchall())
        oldest = conn.execute(
            """SELECT extract(epoch FROM now() - min(created_at))
               FROM jobs WHERE status = 'pending'"""
        ).fetchone()[0]
    return {
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "succeeded": counts.get("succeeded", 0),
        "failed": counts.get("failed", 0),
        "oldest_pending_seconds": float(oldest) if oldest is not None else None,
    }


def claim_job(worker_id: str) -> dict | None:
    """Atomically claim the oldest pending job. SKIP LOCKED means concurrent
    workers never block on or double-claim the same row."""
    with get_conn() as conn:
        row = conn.execute(
            """UPDATE jobs SET status = 'processing', locked_at = now(),
                              locked_by = %s, attempts = attempts + 1
               WHERE id = (
                   SELECT id FROM jobs
                   WHERE status = 'pending'
                   ORDER BY created_at
                   FOR UPDATE SKIP LOCKED
                   LIMIT 1
               )
               RETURNING id, spaces_key, attempts, max_attempts""",
            (worker_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(zip(["id", "spaces_key", "attempts", "max_attempts"], row))


def mark_succeeded(job_id: int, result: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE jobs SET status = 'succeeded', result = %s, updated_at = now()
               WHERE id = %s""",
            (psycopg_json(result), job_id),
        )


def mark_finished_with_error(job_id: int, error: str, max_attempts: int, attempts: int) -> None:
    """Retry (back to pending) if attempts remain, else dead-letter as failed."""
    next_status = "pending" if attempts < max_attempts else "failed"
    with get_conn() as conn:
        conn.execute(
            """UPDATE jobs SET status = %s, last_error = %s, locked_at = NULL,
                              locked_by = NULL, updated_at = now()
               WHERE id = %s""",
            (next_status, error, job_id),
        )


def reclaim_stale_jobs(lease_seconds: int) -> int:
    """Jobs stuck 'processing' past the lease window are treated as abandoned
    (hung or crashed worker) and returned to the pool. This is what makes
    Postgres-as-queue safe against a worker that hangs rather than crashes."""
    with get_conn() as conn:
        rows = conn.execute(
            """UPDATE jobs SET status = 'pending', locked_at = NULL, locked_by = NULL
               WHERE status = 'processing'
                 AND locked_at < now() - (%s || ' seconds')::interval
               RETURNING id""",
            (lease_seconds,),
        ).fetchall()
        return len(rows)


def psycopg_json(value: dict):
    from psycopg.types.json import Json
    return Json(value)
