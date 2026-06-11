"""API package: the thin route layer (CONTRACTS §13).

``api_router`` carries the ``/api`` prefix and includes every sub-router. The
``/media`` static mount lives in ``main.py`` (it is a StaticFiles mount, not a
router). Routes here validate input and delegate to ``storage`` / ``jobs``;
long-running work is always enqueued as a job and the route returns
``{"job_id": int}``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import items, jobs, media, topics

api_router = APIRouter(prefix="/api")
api_router.include_router(topics.router)
api_router.include_router(items.router)
api_router.include_router(jobs.router)
api_router.include_router(media.router)

__all__ = ["api_router"]
