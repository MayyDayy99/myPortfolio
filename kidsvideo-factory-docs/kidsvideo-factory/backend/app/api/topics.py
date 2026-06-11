"""Topic routes (CONTRACTS §13).

Thin handlers: validate, touch the DB through ``db.get_connection`` and create
directories through ``storage``. The single long-running topic operation —
assemble — is enqueued as a job and returns ``{"job_id": int}``.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app import storage
from app.db import get_connection
from app.models import (
    Item,
    ItemCreate,
    JobKind,
    Topic,
    TopicCreate,
    TopicUpdate,
)

router = APIRouter(tags=["topics"])

# Module-level upload marker (avoids a call in argument defaults; ruff B008).
_UPLOAD_FILE = File(...)


# --------------------------------------------------------------------------- #
# Row <-> model helpers (shared with items.py)
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    """Current UTC timestamp as an ISO-8601 string (CONTRACTS §4)."""

    return datetime.now(UTC).isoformat()


def topic_from_row(row: sqlite3.Row) -> Topic:
    """Convert a ``topic`` DB row into a :class:`Topic` model."""

    return Topic(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        status=row["status"],
        background_path=row["background_path"],
        settings_json=row["settings_json"],
        created_at=row["created_at"],
    )


def get_topic_row(topic_id: int) -> sqlite3.Row:
    """Fetch a topic row or raise 404."""

    conn = get_connection()
    row = conn.execute("SELECT * FROM topic WHERE id = ?", (topic_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="A téma nem található.")
    return row


def _unique_topic_slug(conn: sqlite3.Connection, base: str) -> str:
    """Return a topic slug unique across the ``topic`` table.

    Falls back to ``<base>`` then ``<base>-2``, ``<base>-3`` … on collision.
    """

    base = base or "tema"
    candidate = base
    suffix = 2
    while conn.execute("SELECT 1 FROM topic WHERE slug = ?", (candidate,)).fetchone():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("/topics", response_model=list[Topic])
def list_topics() -> list[Topic]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM topic ORDER BY id").fetchall()
    return [topic_from_row(r) for r in rows]


@router.post("/topics", response_model=Topic, status_code=status.HTTP_200_OK)
def create_topic(payload: TopicCreate) -> Topic:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="A cím nem lehet üres.")

    conn = get_connection()
    slug = _unique_topic_slug(conn, storage.slugify(title))
    created_at = _now_iso()
    cur = conn.execute(
        "INSERT INTO topic(slug, title, status, settings_json, created_at) "
        "VALUES (?, ?, 'draft', ?, ?)",
        (slug, title, payload.settings_json, created_at),
    )
    conn.commit()

    # Materialize the project directory tree so later asset writes have a home.
    storage.ensure_tree()
    storage.topic_dir(slug).mkdir(parents=True, exist_ok=True)
    (storage.topic_dir(slug) / "items").mkdir(parents=True, exist_ok=True)
    storage.render_dir(slug).mkdir(parents=True, exist_ok=True)

    row = conn.execute("SELECT * FROM topic WHERE id = ?", (cur.lastrowid,)).fetchone()
    return topic_from_row(row)


@router.get("/topics/{topic_id}", response_model=Topic)
def get_topic(topic_id: int) -> Topic:
    return topic_from_row(get_topic_row(topic_id))


@router.patch("/topics/{topic_id}", response_model=Topic)
def update_topic(topic_id: int, payload: TopicUpdate) -> Topic:
    row = get_topic_row(topic_id)
    conn = get_connection()

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return topic_from_row(row)

    sets = []
    values: list[object] = []
    for key, value in fields.items():
        # Enum values serialize to their string form for SQLite.
        sets.append(f"{key} = ?")
        values.append(value.value if hasattr(value, "value") else value)
    values.append(topic_id)
    conn.execute(f"UPDATE topic SET {', '.join(sets)} WHERE id = ?", values)
    conn.commit()

    return topic_from_row(get_topic_row(topic_id))


@router.delete(
    "/topics/{topic_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_topic(topic_id: int) -> None:
    get_topic_row(topic_id)  # 404 if missing
    conn = get_connection()
    conn.execute("DELETE FROM topic WHERE id = ?", (topic_id,))
    conn.commit()
    # NOTE: on-disk assets are left in place intentionally — destructive disk
    # cleanup is out of scope for the thin route layer.


@router.post("/topics/{topic_id}/background", response_model=Topic)
async def upload_background(
    topic_id: int, file: UploadFile = _UPLOAD_FILE
) -> Topic:
    row = get_topic_row(topic_id)
    slug = row["slug"]

    storage.ensure_tree()
    tdir = storage.topic_dir(slug)
    tdir.mkdir(parents=True, exist_ok=True)
    dest = tdir / "background.png"
    data = await file.read()
    dest.write_bytes(data)

    # Store a /media-relative path so the frontend can preview it.
    rel = dest.relative_to(storage.data_root()).as_posix()
    conn = get_connection()
    conn.execute("UPDATE topic SET background_path = ? WHERE id = ?", (rel, topic_id))
    conn.commit()
    return topic_from_row(get_topic_row(topic_id))


@router.get("/topics/{topic_id}/items", response_model=list[Item])
def list_topic_items(topic_id: int) -> list[Item]:
    get_topic_row(topic_id)  # 404 if missing
    from app.api.items import item_from_row  # local import avoids a cycle

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM item WHERE topic_id = ? ORDER BY position", (topic_id,)
    ).fetchall()
    return [item_from_row(r) for r in rows]


@router.post("/topics/{topic_id}/items", response_model=Item)
def create_topic_item(topic_id: int, payload: ItemCreate) -> Item:
    # Delegated to items.py to keep item-creation logic in one place.
    from app.api.items import create_item_for_topic

    return create_item_for_topic(topic_id, payload)


@router.post("/topics/{topic_id}/items/reorder", response_model=list[Item])
def reorder_topic_items(topic_id: int, order: list[int]) -> list[Item]:
    from app.api.items import reorder_items_for_topic

    return reorder_items_for_topic(topic_id, order)


@router.post("/topics/{topic_id}/assemble")
def assemble_topic(topic_id: int) -> dict[str, int]:
    get_topic_row(topic_id)  # 404 if missing
    from app import jobs  # lazy: keeps importing this module light

    job_id = jobs.enqueue(JobKind.assemble, topic_id)
    return {"job_id": job_id}
