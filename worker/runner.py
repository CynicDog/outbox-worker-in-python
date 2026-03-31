"""Job dispatch to thread pool.

submit() is the bridge from the asyncio world to the thread world.
Every function prefixed with _run_* executes in a worker thread —
blocking I/O and CPU-bound work are both safe here.
"""

from worker import pool, store
from core.transform import double_values

import config as cfg


def submit(job: dict) -> None:
    pool.acquire(job["id"])
    pool.submit(_run_job, job)


def _run_job(job: dict) -> None:
    job_id = job["id"]
    payload = job["values"]
    sleep_secs = job.get("sleep_secs", 1.0)
    print(f"[worker] starting  job={job_id}  input={payload}  sleep={sleep_secs}s")
    try:
        result = double_values(payload, sleep_secs=sleep_secs)
        store.complete(job_id, result)
        print(f"[worker] completed job={job_id}  result={result}")
    except Exception as exc:
        print(f"[worker] failed    job={job_id}  error={exc}")
        store.fail(job_id, str(exc))
    finally:
        pool.release(job_id)
