"""Tests for the SQLite job queue + asyncio worker (CONTRACTS §6).

The suite uses no ``pytest-asyncio`` plugin (it is not a dependency): each test
drives the worker through a small ``asyncio.run`` helper that starts
``worker_loop`` as a background task, waits until the relevant jobs reach a
terminal state, then cancels the loop cleanly.
"""

from __future__ import annotations

import asyncio

import pytest

from app import db, jobs
from app.models import JobKind, JobState


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def fresh_jobs_state() -> None:
    """Init the schema and clear the module-level handler registry per test."""

    db.init_db()
    jobs._REGISTRY.clear()
    yield
    jobs._REGISTRY.clear()


async def _drive_until(
    predicate, *, timeout: float = 5.0, poll: float = 0.01
) -> None:
    """Run ``worker_loop`` until ``predicate()`` is true, then cancel it.

    ``predicate`` is a plain callable returning a bool, re-evaluated every
    ``poll`` seconds. Raises ``TimeoutError`` if it never becomes true within
    ``timeout`` seconds (so a hung worker fails loudly instead of blocking).
    """

    worker = asyncio.create_task(jobs.worker_loop())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        while not predicate():
            if worker.done():
                # The loop must never die on its own; surface why if it did.
                worker.result()
                raise AssertionError("worker_loop exited before predicate was met")
            if loop.time() > deadline:
                raise TimeoutError("timed out waiting for jobs to settle")
            await asyncio.sleep(poll)
    finally:
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker


def _all_terminal(job_ids: list[int]) -> bool:
    """True once every job in ``job_ids`` is ``done`` or ``error``."""

    terminal = {JobState.done, JobState.error}
    return all(jobs.get_job(jid).state in terminal for jid in job_ids)


# --------------------------------------------------------------------------- #
# 1. Three jobs: queued -> running -> done, in FIFO order.
# --------------------------------------------------------------------------- #
def test_three_jobs_run_to_done_in_order() -> None:
    started_order: list[int] = []
    observed_running_state: list[JobState] = []

    def handler(job_id, ref_id, set_progress, log):
        # Record the order in which jobs begin executing.
        started_order.append(ref_id)
        # While the handler runs, the job's own row must read ``running``.
        observed_running_state.append(jobs.get_job(job_id).state)
        set_progress(0.5)
        log(f"feldolgozás: {ref_id}")
        set_progress(1.0)

    jobs.register(JobKind.cutout, handler)

    # Enqueue three CPU-kind jobs; the shared CPU slot serializes them in FIFO.
    ids = [jobs.enqueue(JobKind.cutout, ref) for ref in (10, 20, 30)]

    # Before the worker runs, every job is queued (the first transition state).
    assert [jobs.get_job(i).state for i in ids] == [JobState.queued] * 3

    asyncio.run(_drive_until(lambda: _all_terminal(ids)))

    # Final state: all done, full progress, transition queued->running->done
    # proven (queued asserted above, running observed inside the handler).
    for i in ids:
        job = jobs.get_job(i)
        assert job.state == JobState.done
        assert job.progress == 1.0
        assert job.log.strip() != ""
    assert observed_running_state == [JobState.running] * 3

    # FIFO ordering: jobs started in enqueue order (10, 20, 30).
    assert started_order == [10, 20, 30]


# --------------------------------------------------------------------------- #
# 2. A raising handler -> state=error with a non-empty log.
# --------------------------------------------------------------------------- #
def test_raising_handler_marks_error_with_log() -> None:
    def boom(job_id, ref_id, set_progress, log):
        raise RuntimeError("A feldolgozás megszakadt egy hibával.")

    jobs.register(JobKind.render_segment, boom)
    job_id = jobs.enqueue(JobKind.render_segment, 99)

    asyncio.run(_drive_until(lambda: _all_terminal([job_id])))

    job = jobs.get_job(job_id)
    assert job.state == JobState.error
    assert job.log.strip() != ""
    # The exception's (Hungarian) message reaches the log.
    assert "A feldolgozás megszakadt egy hibával." in job.log


def test_worker_survives_error_and_runs_next_job() -> None:
    """A failing job must not kill the loop; a later good job still completes."""

    def boom(job_id, ref_id, set_progress, log):
        raise ValueError("Szándékos hiba a teszthez.")

    def ok(job_id, ref_id, set_progress, log):
        set_progress(1.0)
        log("rendben")

    jobs.register(JobKind.render_segment, boom)
    jobs.register(JobKind.cutout, ok)

    bad = jobs.enqueue(JobKind.render_segment, 1)
    good = jobs.enqueue(JobKind.cutout, 2)

    asyncio.run(_drive_until(lambda: _all_terminal([bad, good])))

    assert jobs.get_job(bad).state == JobState.error
    assert jobs.get_job(good).state == JobState.done


# --------------------------------------------------------------------------- #
# 3. resume_pending resets a stuck running job back to queued.
# --------------------------------------------------------------------------- #
def test_resume_pending_resets_stuck_running_to_queued() -> None:
    # Simulate a job left ``running`` by a crashed previous process.
    job_id = jobs.enqueue(JobKind.assemble, 7)
    conn = db.get_connection()
    conn.execute(
        "UPDATE job SET state = ?, progress = ? WHERE id = ?",
        (JobState.running.value, 0.4, job_id),
    )
    conn.commit()
    assert jobs.get_job(job_id).state == JobState.running

    asyncio.run(jobs.resume_pending())

    job = jobs.get_job(job_id)
    assert job.state == JobState.queued
    assert job.progress == 0.0


def test_resumed_job_runs_to_completion() -> None:
    """After resume, the requeued job is actually picked up and finishes."""

    def handler(job_id, ref_id, set_progress, log):
        set_progress(1.0)
        log("kész")

    jobs.register(JobKind.assemble, handler)

    job_id = jobs.enqueue(JobKind.assemble, 7)
    conn = db.get_connection()
    conn.execute(
        "UPDATE job SET state = ? WHERE id = ?", (JobState.running.value, job_id)
    )
    conn.commit()

    async def scenario():
        await jobs.resume_pending()
        await _drive_until(lambda: _all_terminal([job_id]))

    asyncio.run(scenario())
    assert jobs.get_job(job_id).state == JobState.done


# --------------------------------------------------------------------------- #
# 4. Concurrency: one GPU + one CPU job may overlap; never two of a kind.
# --------------------------------------------------------------------------- #
def test_gpu_and_cpu_jobs_overlap_but_kinds_do_not() -> None:
    # Two thread-blocking gates let each handler announce it is active and wait
    # for the other, proving the GPU and CPU slots run concurrently.
    gpu_active, cpu_active = _Gate(), _Gate()
    concurrent_seen = {"value": False}

    def gpu_handler(job_id, ref_id, set_progress, log):
        gpu_active.set()
        # If the CPU job also becomes active while we are still here, the two
        # slots overlapped.
        if cpu_active.wait_threadsafe(timeout=2.0):
            concurrent_seen["value"] = True

    def cpu_handler(job_id, ref_id, set_progress, log):
        cpu_active.set()
        gpu_active.wait_threadsafe(timeout=2.0)

    jobs.register(JobKind.generate_image, gpu_handler)
    jobs.register(JobKind.cutout, cpu_handler)

    gpu = jobs.enqueue(JobKind.generate_image, 1)
    cpu = jobs.enqueue(JobKind.cutout, 2)

    asyncio.run(_drive_until(lambda: _all_terminal([gpu, cpu])))

    assert jobs.get_job(gpu).state == JobState.done
    assert jobs.get_job(cpu).state == JobState.done
    # The GPU and CPU jobs were active at the same time (slots are independent).
    assert concurrent_seen["value"] is True


def test_two_cpu_jobs_never_overlap() -> None:
    active = {"value": 0}
    max_seen = {"value": 0}

    def handler(job_id, ref_id, set_progress, log):
        active["value"] += 1
        max_seen["value"] = max(max_seen["value"], active["value"])
        # Hold the slot briefly so an overlap would be observable.
        import time

        time.sleep(0.05)
        active["value"] -= 1

    jobs.register(JobKind.clean_audio, handler)
    ids = [jobs.enqueue(JobKind.clean_audio, r) for r in (1, 2, 3)]

    asyncio.run(_drive_until(lambda: _all_terminal(ids)))

    assert all(jobs.get_job(i).state == JobState.done for i in ids)
    assert max_seen["value"] == 1


# --------------------------------------------------------------------------- #
# A tiny thread-blocking gate used by the concurrency test. ``threading.Event``
# already does exactly this; we wrap it only to expose ``wait_threadsafe`` with
# a timeout that returns a bool.
# --------------------------------------------------------------------------- #
class _Gate:
    def __init__(self) -> None:
        import threading

        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    def wait_threadsafe(self, timeout: float) -> bool:
        return self._event.wait(timeout)
