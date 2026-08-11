"""Background worker: claims jobs from Postgres, simulates the contract-extraction
workload Dana described, and calls DO Serverless Inference once per job.

Three resilience mechanisms live here, each answering a specific incident in
Dana's note:
  - run_with_deadline()   -> "the model call sometimes just hangs" (decision #4)
  - fault injection       -> reproduces that hang/fail on demand for the demo
  - reclaim_stale_jobs()  -> a hung/crashed worker's job isn't lost, it's
                             reclaimed by another worker after the lease
                             expires (decision #4, closes the gap decision #3
                             opened by moving the queue into Postgres)
  - SIGTERM handling      -> deploys don't need to kill jobs mid-flight
                             (decision #6); anything that IS killed abruptly
                             falls back to the reclaim sweep above, not lost.
"""

import logging
import os
import random
import signal
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

import db
import inference

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
log = logging.getLogger("worker")

WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "2"))
LEASE_SECONDS = int(os.environ.get("LEASE_SECONDS", "300"))
RECLAIM_INTERVAL_SECONDS = int(os.environ.get("RECLAIM_INTERVAL_SECONDS", "60"))

SLEEP_MIN_SECONDS = float(os.environ.get("SLEEP_MIN_SECONDS", "20"))
SLEEP_MAX_SECONDS = float(os.environ.get("SLEEP_MAX_SECONDS", "240"))

CALL_TIMEOUT_SECONDS = float(os.environ.get("CALL_TIMEOUT_SECONDS", "90"))
HANG_SLEEP_SECONDS = float(os.environ.get("HANG_SLEEP_SECONDS", "180"))
FAULT_HANG_PROBABILITY = float(os.environ.get("FAULT_HANG_PROBABILITY", "0.10"))
FAULT_FAIL_PROBABILITY = float(os.environ.get("FAULT_FAIL_PROBABILITY", "0.10"))

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="model-call")
_shutting_down = False


def _handle_shutdown(signum, _frame):
    global _shutting_down
    log.info("received signal %s, finishing in-flight job then exiting", signum)
    _shutting_down = True


def run_with_deadline(fn, *args, timeout, **kwargs):
    """Enforce a wall-clock deadline around fn regardless of *why* it's slow.

    Note: a thread stuck in a genuine hang (or our simulated one) keeps
    running in the background after this raises — Python threads can't be
    force-killed. That's an accepted tradeoff: the job is never stuck waiting
    on it (the queue moves on immediately), and a stray leftover model call
    is harmless. Process-level cancellation would avoid the leak but isn't
    worth the added complexity at this scale.
    """
    future = _executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        raise TimeoutError(f"model call exceeded {timeout}s deadline")


def simulate_model_call(prompt: str) -> str:
    """Makes the one real model call per job, but injects the fail/hang
    behavior Dana described so the resilience path is exercised reliably
    rather than hoping the real endpoint misbehaves on its own."""
    roll = random.random()
    if roll < FAULT_HANG_PROBABILITY:
        time.sleep(HANG_SLEEP_SECONDS)  # deliberately longer than CALL_TIMEOUT_SECONDS
        return inference.call_model(prompt)
    if roll < FAULT_HANG_PROBABILITY + FAULT_FAIL_PROBABILITY:
        raise RuntimeError("simulated extraction failure")
    return inference.call_model(prompt)


def process_job(job: dict) -> None:
    job_id = job["id"]
    try:
        duration = random.uniform(SLEEP_MIN_SECONDS, SLEEP_MAX_SECONDS)
        log.info("job %s: processing (simulated %.1fs)", job_id, duration)
        time.sleep(duration)

        content = run_with_deadline(
            simulate_model_call,
            f"Stand-in extraction call for job {job_id}. Reply with a short acknowledgement.",
            timeout=CALL_TIMEOUT_SECONDS,
        )
        db.mark_succeeded(job_id, {"extraction": content, "simulated_seconds": duration})
        log.info("job %s: succeeded", job_id)
    except Exception as exc:
        db.mark_finished_with_error(job_id, str(exc), job["max_attempts"], job["attempts"])
        log.warning("job %s: failed attempt %s/%s (%s)", job_id, job["attempts"], job["max_attempts"], exc)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    db.init_pool()
    log.info("worker %s started", WORKER_ID)

    last_reclaim = 0.0
    while not _shutting_down:
        now = time.monotonic()
        if now - last_reclaim > RECLAIM_INTERVAL_SECONDS:
            reclaimed = db.reclaim_stale_jobs(LEASE_SECONDS)
            if reclaimed:
                log.warning("reclaimed %s stale job(s) past the %ss lease", reclaimed, LEASE_SECONDS)
            last_reclaim = now

        job = db.claim_job(WORKER_ID)
        if job is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        process_job(job)

    log.info("worker %s shut down cleanly", WORKER_ID)
    db.close_pool()


if __name__ == "__main__":
    main()
