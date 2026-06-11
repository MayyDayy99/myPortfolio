"""API tests via FastAPI ``TestClient`` (CONTRACTS §13, §14).

These tests exercise the thin route layer and ``main.py`` wiring WITHOUT running
the real job worker or any heavy pipeline handler (no rembg / ComfyUI / ffmpeg).
``jobs.py`` is a sibling module written in parallel and may be absent at run
time, so we inject a faithful in-memory fake matching the CONTRACTS §6 public
API (``enqueue`` / ``get_job`` / ``register`` / ``resume_pending`` /
``worker_loop``). ``enqueue`` writes a real ``job`` row, so "a job row exists"
is genuinely asserted; the worker loop is an inert no-op so nothing executes.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Fake jobs module: enqueue persists a real row; the worker never runs.
# --------------------------------------------------------------------------- #
def _install_fake_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install ``app.jobs`` as a controlled fake for the duration of a test."""

    from app.db import get_connection
    from app.models import Job, JobKind

    fake = types.ModuleType("app.jobs")
    fake._registry = {}  # type: ignore[attr-defined]

    def _now() -> str:
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()

    def enqueue(kind, ref_id):
        kind_value = kind.value if hasattr(kind, "value") else str(kind)
        conn = get_connection()
        ts = _now()
        cur = conn.execute(
            "INSERT INTO job(kind, ref_id, state, progress, log, created_at, updated_at) "
            "VALUES (?, ?, 'queued', 0, '', ?, ?)",
            (kind_value, ref_id, ts, ts),
        )
        conn.commit()
        return cur.lastrowid

    def get_job(job_id):
        conn = get_connection()
        row = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return Job(
            id=row["id"],
            kind=row["kind"],
            ref_id=row["ref_id"],
            state=row["state"],
            progress=row["progress"],
            log=row["log"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def register(kind, fn):
        fake._registry[kind] = fn  # type: ignore[attr-defined]

    async def resume_pending():
        return None

    async def worker_loop():
        # Inert: never pick up work during tests.
        return None

    fake.enqueue = enqueue  # type: ignore[attr-defined]
    fake.get_job = get_job  # type: ignore[attr-defined]
    fake.register = register  # type: ignore[attr-defined]
    fake.resume_pending = resume_pending  # type: ignore[attr-defined]
    fake.worker_loop = worker_loop  # type: ignore[attr-defined]
    fake.JobKind = JobKind  # type: ignore[attr-defined]

    # Override BOTH lookup paths: ``sys.modules['app.jobs']`` (for fresh
    # ``import app.jobs``) and the ``app`` package attribute (for the already
    # common ``from app import jobs``, which reads the bound package attribute
    # once the real sibling module has been imported by another test). This
    # guarantees no real worker loop runs and job rows stay ``queued``.
    import app as app_pkg

    monkeypatch.setitem(sys.modules, "app.jobs", fake)
    monkeypatch.setattr(app_pkg, "jobs", fake, raising=False)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """A TestClient with the fake jobs module installed and lifespan run."""

    _install_fake_jobs(monkeypatch)

    # Import main only after the fake is in place so its lazy lifespan imports
    # resolve to the fake. The module itself imports without the fake too.
    from app.main import app

    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_healthz_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_topic_returns_200_and_creates_dir(
    client: TestClient, isolated_data_dir: Path
) -> None:
    from app import storage

    resp = client.post("/api/topics", json={"title": "Háziállatok"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "haziallatok"
    assert body["title"] == "Háziállatok"
    assert body["status"] == "draft"

    # The project directory tree was materialized under the tmp data root.
    assert storage.topic_dir("haziallatok").is_dir()
    assert (storage.topic_dir("haziallatok") / "items").is_dir()
    assert storage.render_dir("haziallatok").is_dir()


def test_create_item_assigns_position_slug_and_nn_dir(
    client: TestClient, isolated_data_dir: Path
) -> None:
    from app import storage

    topic = client.post("/api/topics", json={"title": "Háziállatok"}).json()
    topic_id = topic["id"]

    first = client.post(
        f"/api/topics/{topic_id}/items", json={"name": "tehén"}
    ).json()
    assert first["position"] == 1
    assert first["slug"] == "tehen"
    assert storage.item_dir("haziallatok", 1, "tehen").is_dir()

    second = client.post(
        f"/api/topics/{topic_id}/items", json={"name": "tűzoltó autó"}
    ).json()
    assert second["position"] == 2
    assert second["slug"] == "tuzolto-auto"
    assert storage.item_dir("haziallatok", 2, "tuzolto-auto").name == "02-tuzolto-auto"
    assert storage.item_dir("haziallatok", 2, "tuzolto-auto").is_dir()


def test_generate_image_returns_job_id_and_job_row_exists(
    client: TestClient, isolated_data_dir: Path
) -> None:
    from app.db import get_connection

    topic = client.post("/api/topics", json={"title": "Háziállatok"}).json()
    item = client.post(
        f"/api/topics/{topic['id']}/items", json={"name": "tehén"}
    ).json()

    resp = client.post(f"/api/items/{item['id']}/generate-image")
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert isinstance(job_id, int)

    # A real job row was persisted by enqueue.
    conn = get_connection()
    row = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    assert row is not None
    assert row["kind"] == "generate_image"
    assert row["ref_id"] == item["id"]
    assert row["state"] == "queued"


def test_get_job_endpoint_returns_job(
    client: TestClient, isolated_data_dir: Path
) -> None:
    topic = client.post("/api/topics", json={"title": "Háziállatok"}).json()
    item = client.post(
        f"/api/topics/{topic['id']}/items", json={"name": "tehén"}
    ).json()
    job_id = client.post(f"/api/items/{item['id']}/cutout").json()["job_id"]

    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["kind"] == "cutout"
    assert body["state"] == "queued"

    # Unknown job id -> 404 with a Hungarian message.
    missing = client.get("/api/jobs/999999")
    assert missing.status_code == 404


def test_reorder_keeps_nn_dirs_consistent(
    client: TestClient, isolated_data_dir: Path
) -> None:
    from app import storage

    topic = client.post("/api/topics", json={"title": "Háziállatok"}).json()
    topic_id = topic["id"]
    a = client.post(f"/api/topics/{topic_id}/items", json={"name": "tehén"}).json()
    b = client.post(f"/api/topics/{topic_id}/items", json={"name": "kutya"}).json()

    # Sanity: initial NN-dirs exist.
    assert storage.item_dir("haziallatok", 1, "tehen").is_dir()
    assert storage.item_dir("haziallatok", 2, "kutya").is_dir()

    # Swap order: [b, a].
    resp = client.post(
        f"/api/topics/{topic_id}/items/reorder", json=[b["id"], a["id"]]
    )
    assert resp.status_code == 200
    ordered = resp.json()
    assert [it["id"] for it in ordered] == [b["id"], a["id"]]
    assert ordered[0]["position"] == 1
    assert ordered[1]["position"] == 2

    # Filesystem NN-dirs followed the new positions.
    assert storage.item_dir("haziallatok", 1, "kutya").is_dir()
    assert storage.item_dir("haziallatok", 2, "tehen").is_dir()
    assert not storage.item_dir("haziallatok", 2, "kutya").exists()
