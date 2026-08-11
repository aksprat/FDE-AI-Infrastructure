-- Postgres is the job queue as well as the datastore (decision: no Redis).
-- Workers claim rows with `SELECT ... FOR UPDATE SKIP LOCKED` (see worker.py).
-- locked_at drives the lease-timeout reclaim sweep: a job whose lock is older
-- than the lease window is treated as abandoned (hung/crashed worker) and
-- made claimable again, without ever declaring the job itself lost.

CREATE TABLE IF NOT EXISTS jobs (
    id            BIGSERIAL PRIMARY KEY,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'processing', 'succeeded', 'failed')),
    spaces_key    TEXT NOT NULL,
    attempts      INT NOT NULL DEFAULT 0,
    max_attempts  INT NOT NULL DEFAULT 3,
    locked_at     TIMESTAMPTZ,
    locked_by     TEXT,
    last_error    TEXT,
    result        JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Supports the claim query's WHERE status = 'pending' ORDER BY created_at scan.
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs (status, created_at)
    WHERE status = 'pending';

-- Supports the reclaim sweep's WHERE status = 'processing' AND locked_at < ... scan.
CREATE INDEX IF NOT EXISTS idx_jobs_locked_at ON jobs (locked_at)
    WHERE status = 'processing';
