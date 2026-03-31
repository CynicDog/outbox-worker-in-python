import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException

from api.models import JobRequest, JobResponse
from worker import pool, store
from worker.poller import claim_and_dispatch

router = APIRouter()


@router.post("/jobs", status_code=202)
async def create_job(req: JobRequest) -> JobResponse:
    """Write a PENDING job to the DB, then nudge the engine to pick it up."""
    job_id = str(uuid.uuid4())
    await asyncio.to_thread(store.insert, job_id, req.values, req.sleep_secs)

    # Nudge: fire claim_and_dispatch as a background task so this response
    # returns before the claim round-trip completes.
    asyncio.create_task(claim_and_dispatch())

    return JobResponse(id=job_id, status="PENDING")


@router.post("/nudge")
async def nudge() -> dict:
    """External wake-up call — triggers claim_and_dispatch immediately."""
    asyncio.create_task(claim_and_dispatch())
    return {"ok": True}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JobResponse:
    row = await asyncio.to_thread(store.get, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse(
        id=row.id,
        status=row.status,
        result=json.loads(row.result) if row.result else None,
        error=row.error,
    )


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "active_workers": pool.active_count(),
        "max_workers": pool.max_workers(),
    }


@router.post("/admin/reset-stuck")
async def reset_stuck(stuck_minutes: int = 30, max_retries: int = 3) -> dict:
    count = await asyncio.to_thread(store.reset_stuck, stuck_minutes, max_retries)
    asyncio.create_task(claim_and_dispatch())
    return {"reset": count}
