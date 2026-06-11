"""SQLite-backed job queue and a single asyncio worker loop (CONTRACTS §6).

A persistent job row lives in SQLite (so the queue survives restarts) and a
single ``worker_loop`` coroutine in the backend process drains it. The loop runs
two jobs at most concurrently: one GPU-bound ``generate_image`` and one CPU-bound
job (``cutout | clean_audio | render_segment | assemble``). Handlers are plain
synchronous functions executed in a thread (``asyncio.to_thread``) so they never
block the event loop.

Handler signature (CONTRACTS §6)::

    fn(job_id: int, ref_id: int,
       set_progress: Callable[[float], None],
       log: Callable[[str], None]) -> None

A handler exception turns the job into ``state=error`` and writes a Hungarian
message to the job ``log``; the worker loop NEVER dies because of a job error
(01-BLUEPRINT §6.2). Progress is clamped to ``0..1``.

All timestamps are ISO-8601 UTC strings, matching CONTRACTS §4. This is runtime
code (not a workflow script), so ``datetime.now`` is allowed here.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from app.db import get_connection
from app.models import Job, JobKind, JobState

# --------------------------------------------------------------------------- #
# Types and registry
# --------------------------------------------------------------------------- #
# A handler receives the job id, the referenced row id, a progress callback
# (0..1) and a log-append callback. Synchronous on purpose — run in a thread.
JobHandler = Callable[[int, int | None, Callable[[float], None], Callable[[str], None]], None]

# Handler registry keyed by job kind. Populated at import time by the pipeline
# wiring (api/main layer); tests register their own dummy handlers.
_REGISTRY: dict[JobKind, JobHandler] = {}

# The single GPU-bound kind. Everything else is CPU-bound and shares one slot,
# so at most one GPU job and one CPU job run at the same instant (CONTRACTS §6).
_GPU_KIND: frozenset[JobKind] = frozenset({JobKind.generate_image})

# Slot keys used in the worker's ``running`` map: one for the GPU kind, one
# sentinel standing for "the single CPU slot". Using an existing CPU kind as the
# CPU sentinel keeps the map typed by JobKind.
_GPU_SLOT: JobKind = JobKind.generate_image
_CPU_SLOT: JobKind = JobKind.cutout


def _slot_for(kind: JobKind) -> JobKind:
    """Map a job kind to its concurrency slot (GPU slot vs. shared CPU slot)."""

    return _GPU_SLOT if kind in _GPU_KIND else _CPU_SLOT

# Serialize every DB mutation. The shared sqlite3 connection is opened with
# ``check_same_thread=False`` and is touched from both the event loop and the
# worker thread-pool, so we guard it with a plain lock to avoid interleaving.
_DB_LOCK = threading.Lock()

# Event the worker loop waits on; set whenever new work may be available
# (enqueue, a job finishing, resume_pending) so the loop wakes promptly instead
# of busy-polling. Both the event and its loop are created lazily INSIDE
# ``worker_loop`` so they bind to whatever loop is actually running (an
# ``asyncio.Event`` is pinned to the loop alive when first awaited; binding it at
# import time breaks any later/second loop — e.g. across tests or a restart).
_WAKE: asyncio.Event | None = None
_WAKE_LOOP: asyncio.AbstractEventLoop | None = None

# Generic Hungarian failure message used when an exception carries no text.
_GENERIC_ERROR_HU = "Ismeretlen hiba történt a feladat futtatása közben."


def register(kind: JobKind, fn: JobHandler) -> None:
    """Register the handler ``fn`` for job ``kind`` (overwrites any previous)."""

    _REGISTRY[kind] = fn


def _utcnow() -> str:
    """Current UTC time as an ISO-8601 string (CONTRACTS §4)."""

    return datetime.now(timezone.utc).isoformat()


def _wake() -> None:
    """Signal the worker loop that the queue may have changed.

    Safe to call from any thread: if the worker loop is running we schedule the
    ``set`` on it thread-safely. If the loop is not running yet, there is nothing
    to wake — ``worker_loop`` re-scans the queue before it ever waits, so a job
    enqueued while it is down is still picked up on start.
    """

    loop, event = _WAKE_LOOP, _WAKE
    if loop is not None and event is not None and loop.is_running():
        loop.call_soon_threadsafe(event.set)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def enqueue(kind: JobKind, ref_id: int | None) -> int:
    """Insert a queued job and return its id (CONTRACTS §6)."""

    now = _utcnow()
    with _DB_LOCK:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO job(kind, ref_id, state, progress, log, created_at, updated_at) "
            "VALUES(?, ?, ?, 0, '', ?, ?)",
            (JobKind(kind).value, ref_id, JobState.queued.value, now, now),
        )
        conn.commit()
        job_id = int(cur.lastrowid)
    _wake()
    return job_id


def get_job(job_id: int) -> Job:
    """Return the :class:`Job` for ``job_id`` (raises ``KeyError`` if absent)."""

    with _DB_LOCK:
        conn = get_connection()
        row = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(f"No job with id {job_id}")
    return Job.model_validate(dict(row))


async def resume_pending() -> None:
    """Reset stuck jobs on startup: any ``running`` row → ``queued``.

    A job in ``running`` after a process restart can never have an in-flight
    handler (the worker died with the process), so it is requeued. Already
    ``queued`` jobs are left as-is — they are picked up by the loop anyway.
    """

    now = _utcnow()
    with _DB_LOCK:
        conn = get_connection()
        conn.execute(
            "UPDATE job SET state = ?, progress = 0, updated_at = ? WHERE state = ?",
            (JobState.queued.value, now, JobState.running.value),
        )
        conn.commit()
    _wake()


async def worker_loop() -> None:
    """Drain the job queue forever, honouring the GPU/CPU concurrency limits.

    Started by ``main.py`` as a lifespan background task. Cancellation
    (``asyncio.CancelledError``) is the clean shutdown signal: in-flight job
    tasks are awaited so their DB state is consistent before returning.
    """

    # Create the wake event bound to THIS loop and publish both so cross-thread
    # wakes (enqueue/resume from a request handler or job thread) target it.
    global _WAKE, _WAKE_LOOP
    wake = asyncio.Event()
    _WAKE = wake
    _WAKE_LOOP = asyncio.get_running_loop()

    running: dict[JobKind, asyncio.Task[None]] = {}

    try:
        while True:
            # Reap finished tasks and free their slots.
            for slot in [s for s, t in running.items() if t.done()]:
                task = running.pop(slot)
                # Retrieve the result so the task is not flagged as "never
                # awaited". The handler wrapper records job failures itself and
                # never re-raises, so a non-None exception here would be a bug in
                # the wrapper rather than an ordinary job error.
                exc = task.exception()
                if exc is not None:  # pragma: no cover - defensive
                    pass

            # Try to fill every free slot with the oldest eligible queued job.
            started_any = False
            for job in _claimable_jobs():
                kind = JobKind(job.kind)
                slot = _slot_for(kind)
                if slot in running:
                    continue
                if _mark_running(job.id):
                    running[slot] = asyncio.create_task(_run_job(job.id, kind, job.ref_id))
                    started_any = True

            if started_any:
                # Loop again immediately to try filling the other slot too.
                continue

            if not running:
                # Idle: block until enqueue/resume wakes us.
                wake.clear()
                await wake.wait()
                continue

            # Work in flight but no free slot fillable now: wait for either a
            # task to finish or a wake (a new job that might fit a freed slot).
            wake.clear()
            waiters = list(running.values())
            wake_task = asyncio.ensure_future(wake.wait())
            try:
                await asyncio.wait([*waiters, wake_task], return_when=asyncio.FIRST_COMPLETED)
            finally:
                if not wake_task.done():
                    wake_task.cancel()
    except asyncio.CancelledError:
        # Clean shutdown: let in-flight jobs finish so their rows are coherent.
        if running:
            await asyncio.gather(*running.values(), return_exceptions=True)
        raise
    finally:
        # Release the loop/event references so a later run (e.g. a fresh test
        # loop, or a restarted worker) never wakes this now-finished loop.
        _WAKE = None
        _WAKE_LOOP = None


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _claimable_jobs() -> list[Job]:
    """Return queued jobs, oldest first (FIFO by id)."""

    with _DB_LOCK:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM job WHERE state = ? ORDER BY id ASC",
            (JobState.queued.value,),
        ).fetchall()
    return [Job.model_validate(dict(r)) for r in rows]


def _mark_running(job_id: int) -> bool:
    """Atomically transition ``queued`` → ``running``.

    Returns ``True`` if this call won the transition (so the caller owns the
    job), ``False`` if another path already moved it.
    """

    now = _utcnow()
    with _DB_LOCK:
        conn = get_connection()
        cur = conn.execute(
            "UPDATE job SET state = ?, updated_at = ? WHERE id = ? AND state = ?",
            (JobState.running.value, now, job_id, JobState.queued.value),
        )
        conn.commit()
        return cur.rowcount == 1


def _set_progress(job_id: int, value: float) -> None:
    """Persist a clamped progress value (0..1) for ``job_id``."""

    clamped = 0.0 if value < 0.0 else 1.0 if value > 1.0 else float(value)
    now = _utcnow()
    with _DB_LOCK:
        conn = get_connection()
        conn.execute(
            "UPDATE job SET progress = ?, updated_at = ? WHERE id = ?",
            (clamped, now, job_id),
        )
        conn.commit()


def _append_log(job_id: int, message: str) -> None:
    """Append a line to the job log (newline-separated)."""

    if not message:
        return
    now = _utcnow()
    line = message if message.endswith("\n") else message + "\n"
    with _DB_LOCK:
        conn = get_connection()
        conn.execute(
            "UPDATE job SET log = log || ?, updated_at = ? WHERE id = ?",
            (line, now, job_id),
        )
        conn.commit()


def _finish(job_id: int, state: JobState, progress: float | None = None) -> None:
    """Set the terminal state of a job (and optionally its final progress)."""

    now = _utcnow()
    with _DB_LOCK:
        conn = get_connection()
        if progress is None:
            conn.execute(
                "UPDATE job SET state = ?, updated_at = ? WHERE id = ?",
                (state.value, now, job_id),
            )
        else:
            conn.execute(
                "UPDATE job SET state = ?, progress = ?, updated_at = ? WHERE id = ?",
                (state.value, float(progress), now, job_id),
            )
        conn.commit()


async def _run_job(job_id: int, kind: JobKind, ref_id: int | None) -> None:
    """Execute one job's handler in a thread; never raise to the worker loop.

    On success: ``state=done``, ``progress=1``. On any handler exception:
    ``state=error`` with the exception's (Hungarian) message appended to the
    log. A missing handler is itself reported as an error job, not a crash.
    """

    handler = _REGISTRY.get(kind)
    if handler is None:
        _append_log(
            job_id,
            f"Nincs regisztrált kezelő ehhez a feladattípushoz: {kind.value}.",
        )
        _finish(job_id, JobState.error)
        return

    # Bind the per-job callbacks the handler is given.
    def set_progress(value: float) -> None:
        _set_progress(job_id, value)

    def log(message: str) -> None:
        _append_log(job_id, message)

    try:
        await asyncio.to_thread(handler, job_id, ref_id, set_progress, log)
    except Exception as exc:  # noqa: BLE001 - any handler error becomes a failed job
        # Hungarian, human-readable message into the log (01-BLUEPRINT §6.2).
        message = str(exc).strip() or _GENERIC_ERROR_HU
        _append_log(job_id, f"Hiba: {message}")
        _finish(job_id, JobState.error)
    else:
        _finish(job_id, JobState.done, progress=1.0)
    finally:
        # A finished job may unblock the other slot.
        _wake()
