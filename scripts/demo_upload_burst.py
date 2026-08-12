"""Uploads several dummy files against the live API, polls each job to a
terminal state, and prints a summary — evidence that the upload -> Spaces ->
Postgres queue -> worker -> DO Serverless Inference pipeline works end to end
against the real deployed system, and that the injected fail/hang behavior
is actually handled (retried or cleanly dead-lettered) rather than lost.

Usage: python3 demo_upload_burst.py <base_url> [num_jobs]
"""

import io
import sys
import time
import urllib.request

N_JOBS = int(sys.argv[2]) if len(sys.argv) > 2 else 6
BASE_URL = sys.argv[1].rstrip("/")


def upload_one(i: int) -> int:
    boundary = "----demo-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="contract-{i}.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
        f"dummy contract contents {i}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        import json
        return json.load(resp)["job_id"]


def get_job(job_id: int) -> dict:
    import json
    with urllib.request.urlopen(f"{BASE_URL}/jobs/{job_id}", timeout=30) as resp:
        return json.load(resp)


def main():
    print(f"Uploading {N_JOBS} jobs to {BASE_URL} ...")
    job_ids = [upload_one(i) for i in range(N_JOBS)]
    print(f"Job IDs: {job_ids}")

    pending = set(job_ids)
    results = {}
    start = time.time()
    timeout_s = 15 * 60

    while pending and time.time() - start < timeout_s:
        for job_id in list(pending):
            job = get_job(job_id)
            if job["status"] in ("succeeded", "failed"):
                results[job_id] = job
                pending.discard(job_id)
                elapsed = round(time.time() - start)
                print(f"[{elapsed}s] job {job_id}: {job['status']} (attempts={job['attempts']})"
                      + (f" error={job['last_error']!r}" if job.get("last_error") else ""))
        if pending:
            time.sleep(10)

    print("\n--- summary ---")
    succeeded = [j for j in results.values() if j["status"] == "succeeded"]
    failed = [j for j in results.values() if j["status"] == "failed"]
    print(f"succeeded: {len(succeeded)}, failed (dead-lettered after max attempts): {len(failed)}, "
          f"still pending after timeout: {len(pending)}")
    for job_id in pending:
        print(f"  still pending: job {job_id}")


if __name__ == "__main__":
    main()
