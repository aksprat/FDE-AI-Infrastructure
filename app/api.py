"""API service: accepts uploads, exposes job status, and a real health check.

/health deliberately checks DB connectivity rather than just returning 200 —
App Platform only routes traffic to (and only kills the old version in favor
of) an instance that passes this check, so a shallow check would make the
zero-downtime deploy story (decision #6) fake.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse

import db
import storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()
    yield
    db.close_pool()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    try:
        db.health_check()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"db unreachable: {exc}")
    return {"status": "ok"}


@app.post("/upload")
async def upload(file: UploadFile):
    key = storage.upload(file.file, file.filename)
    job_id = db.enqueue_job(key)
    return {"job_id": job_id, "status": "pending"}


@app.get("/jobs/{job_id}")
def get_job(job_id: int):
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse(content=_serialize(job))


@app.get("/admin/queue-stats")
def queue_stats():
    """The signal decision #5's capacity plan runs on: is the backlog
    growing, and how stale is the oldest pending job. Not wired to any
    paging system on purpose (decision #7) — this is meant to be checked,
    not to page anyone at 3am."""
    return db.queue_stats()


def _serialize(job: dict) -> dict:
    return {
        **job,
        "created_at": job["created_at"].isoformat(),
        "updated_at": job["updated_at"].isoformat(),
    }
