"""FastAPI application entrypoint (CONTRACTS §14).

Lifespan startup: ``ensure_tree`` → ``init_db`` → ``resume_pending`` →
``register_all`` → launch the ``worker_loop`` background task. Shutdown cancels
the worker cleanly. ``/healthz`` is a trivial liveness probe. ``/media`` is a
read-only StaticFiles mount over ``data_root()`` for asset previews. The API
router and ``/media`` are wired BEFORE the catch-all frontend static mount so
they always resolve first.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import storage
from app.api import api_router


def _frontend_dist() -> Path:
    """Absolute path to the built frontend (``frontend/dist`` at the repo root)."""

    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "frontend" / "dist"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize storage + DB + job system, then run the worker loop."""

    from app import jobs  # lazy: sibling module written in parallel
    from app.db import init_db
    from app.handlers import register_all

    # Filesystem + schema must exist before anything else touches them.
    storage.ensure_tree()
    init_db()

    # Re-queue jobs that were mid-flight at the last shutdown (CONTRACTS §6).
    await jobs.resume_pending()

    # Wire JobKind -> handler, then start the single background worker.
    register_all()
    worker_task = asyncio.create_task(jobs.worker_loop(), name="job-worker-loop")

    try:
        yield
    finally:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task


app = FastAPI(title="Már ezt is tudom — videógyár", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe."""

    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Routes/mounts — ORDER MATTERS: /api and /media before the catch-all static.
# --------------------------------------------------------------------------- #
app.include_router(api_router)

# Read-only media mount over the data root (asset previews). ``check_dir=False``
# so the app still starts before the directory is created; ``ensure_tree`` in
# the lifespan guarantees it exists by request time.
app.mount(
    "/media",
    StaticFiles(directory=str(storage.data_root()), check_dir=False),
    name="media",
)

# Frontend: serve the Vite build at "/" when present, else a placeholder. The
# mount is added LAST so it cannot shadow /api or /media.
_dist = _frontend_dist()
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
else:

    @app.get("/", response_class=HTMLResponse)
    def frontend_placeholder() -> str:
        """Placeholder shown until the frontend is built (``npm run build``)."""

        return (
            "<!doctype html><html lang='hu'><head><meta charset='utf-8'>"
            "<title>Már ezt is tudom</title></head><body>"
            "<h1>A frontend még nincs buildelve.</h1>"
            "<p>Futtasd: <code>cd frontend &amp;&amp; npm install &amp;&amp; "
            "npm run build</code>.</p>"
            "<p>Az API elérhető a <code>/api</code> útvonalon, az állapot a "
            "<code>/healthz</code> címen.</p>"
            "</body></html>"
        )
