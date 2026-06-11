"""Job status routes (CONTRACTS §13).

The UI polls ``GET /api/jobs/{id}`` every 2 seconds for progress + log. This
router stays read-only: jobs are created by the topic/item routes via
``jobs.enqueue`` and advanced by the worker loop.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models import Job

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: int) -> Job:
    from app import jobs  # lazy import keeps this module light to import

    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="A feladat nem található.")
    return job
