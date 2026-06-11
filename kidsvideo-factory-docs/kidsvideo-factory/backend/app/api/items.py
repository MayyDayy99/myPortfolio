"""Item routes (CONTRACTS §13).

Item creation assigns ``position`` (1-based), ``slug`` and the on-disk
``<NN>-<slug>`` directory. Reorder rewrites both ``position`` and the NN
directory names so DB and filesystem stay consistent. The long-running
operations (generate-image, cutout, clean-audio, render-segment) enqueue a job
and return ``{"job_id": int}``; regenerate / re-cutout invalidate the downstream
item status and remove stale assets so the UI reflects a fresh pipeline.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app import storage
from app.db import get_connection
from app.models import (
    Item,
    ItemCreate,
    ItemStatus,
    ItemUpdate,
    JobKind,
)

router = APIRouter(tags=["items"])

# Module-level upload marker (avoids a call in argument defaults; ruff B008).
_UPLOAD_FILE = File(...)


# --------------------------------------------------------------------------- #
# Row <-> model + lookup helpers
# --------------------------------------------------------------------------- #
def item_from_row(row: sqlite3.Row) -> Item:
    """Convert an ``item`` DB row into an :class:`Item` model."""

    return Item(
        id=row["id"],
        topic_id=row["topic_id"],
        position=row["position"],
        slug=row["slug"],
        name=row["name"],
        prompt=row["prompt"],
        seed=row["seed"],
        sfx_path=row["sfx_path"],
        status=row["status"],
    )


def get_item_row(item_id: int) -> sqlite3.Row:
    """Fetch an item row or raise 404."""

    conn = get_connection()
    row = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Az elem nem található.")
    return row


def _topic_slug(topic_id: int) -> str:
    conn = get_connection()
    row = conn.execute("SELECT slug FROM topic WHERE id = ?", (topic_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="A téma nem található.")
    return row["slug"]


def item_dir_for_row(row: sqlite3.Row) -> Path:
    """Absolute on-disk directory for an item row."""

    slug = _topic_slug(row["topic_id"])
    return storage.item_dir(slug, row["position"], row["slug"])


# --------------------------------------------------------------------------- #
# Functions shared with topics.py (topic-scoped create / reorder)
# --------------------------------------------------------------------------- #
def create_item_for_topic(topic_id: int, payload: ItemCreate) -> Item:
    """Create an item under ``topic_id`` with a server-assigned position/slug/dir."""

    conn = get_connection()
    if conn.execute("SELECT 1 FROM topic WHERE id = ?", (topic_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="A téma nem található.")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="A megnevezés nem lehet üres.")

    # Next position = current max + 1 (1-based, gap-free for fresh topics).
    row = conn.execute(
        "SELECT COALESCE(MAX(position), 0) AS maxpos FROM item WHERE topic_id = ?",
        (topic_id,),
    ).fetchone()
    position = int(row["maxpos"]) + 1
    slug = storage.slugify(name) or f"elem-{position}"

    cur = conn.execute(
        "INSERT INTO item(topic_id, position, slug, name, prompt, seed, sfx_path, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')",
        (topic_id, position, slug, name, payload.prompt, payload.seed, payload.sfx_path),
    )
    conn.commit()

    # Create the NN-dir on disk.
    topic_slug = _topic_slug(topic_id)
    storage.item_dir(topic_slug, position, slug).mkdir(parents=True, exist_ok=True)

    new_row = conn.execute("SELECT * FROM item WHERE id = ?", (cur.lastrowid,)).fetchone()
    return item_from_row(new_row)


def reorder_items_for_topic(topic_id: int, order: list[int]) -> list[Item]:
    """Apply a new item order; keep ``position`` and the NN directories aligned.

    ``order`` is the full list of item ids in their new order. The directories
    are renamed from ``<oldNN>-<slug>`` to ``<newNN>-<slug>`` so the filesystem
    matches the DB. Renames go through a temporary suffix to avoid collisions
    when two items swap positions.
    """

    conn = get_connection()
    if conn.execute("SELECT 1 FROM topic WHERE id = ?", (topic_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="A téma nem található.")

    existing = conn.execute(
        "SELECT * FROM item WHERE topic_id = ? ORDER BY position", (topic_id,)
    ).fetchall()
    existing_ids = {r["id"] for r in existing}

    if set(order) != existing_ids or len(order) != len(existing):
        raise HTTPException(
            status_code=422,
            detail="A sorrend-lista pontosan a téma elemeinek azonosítóit kell tartalmazza.",
        )

    by_id = {r["id"]: r for r in existing}
    topic_slug = _topic_slug(topic_id)

    # Phase 1: move every item directory aside to a unique temp name and bump
    # positions out of the valid range, so the UNIQUE(topic_id, position) and
    # directory names never collide mid-shuffle.
    for r in existing:
        old_dir = storage.item_dir(topic_slug, r["position"], r["slug"])
        if old_dir.exists():
            tmp = old_dir.with_name(f"__tmp_{r['id']}-{r['slug']}")
            old_dir.rename(tmp)
        conn.execute(
            "UPDATE item SET position = ? WHERE id = ?",
            (-1000 - r["id"], r["id"]),
        )

    # Phase 2: assign final 1-based positions and rename temp dirs into place.
    for new_position, item_id in enumerate(order, start=1):
        r = by_id[item_id]
        conn.execute(
            "UPDATE item SET position = ? WHERE id = ?", (new_position, item_id)
        )
        tmp = storage.item_dir(topic_slug, 0, "x").with_name(
            f"__tmp_{item_id}-{r['slug']}"
        )
        new_dir = storage.item_dir(topic_slug, new_position, r["slug"])
        if tmp.exists():
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            tmp.rename(new_dir)
    conn.commit()

    rows = conn.execute(
        "SELECT * FROM item WHERE topic_id = ? ORDER BY position", (topic_id,)
    ).fetchall()
    return [item_from_row(r) for r in rows]


# --------------------------------------------------------------------------- #
# Downstream-invalidation helper (regenerate / re-cutout, 02-plan T5/T6)
# --------------------------------------------------------------------------- #
def _invalidate_downstream(row: sqlite3.Row, *, from_status: ItemStatus) -> None:
    """Reset the item status and drop stale downstream assets + the cache hash.

    ``from_status`` is the new baseline the item drops back to (e.g. regenerate
    sends the item back to ``draft``; re-cutout keeps the image but drops the
    segment). Removing ``meta.json`` invalidates the segment cache so assemble
    re-renders it (01-BLUEPRINT §6.3).
    """

    conn = get_connection()
    conn.execute(
        "UPDATE item SET status = ? WHERE id = ?", (from_status.value, row["id"])
    )
    conn.commit()

    item_dir = item_dir_for_row(row)
    # Assets that become invalid once the upstream input changes.
    downstream = {
        ItemStatus.draft: ["cutout.png", "silhouette.png", "segment.mp4", "meta.json"],
        ItemStatus.image_ok: ["segment.mp4", "meta.json"],
        ItemStatus.audio_ok: ["segment.mp4", "meta.json"],
    }.get(from_status, [])
    for name in downstream:
        target = storage.item_asset(item_dir, name)
        if target.exists():
            target.unlink()


# --------------------------------------------------------------------------- #
# Item CRUD
# --------------------------------------------------------------------------- #
@router.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int) -> Item:
    return item_from_row(get_item_row(item_id))


@router.patch("/items/{item_id}", response_model=Item)
def update_item(item_id: int, payload: ItemUpdate) -> Item:
    row = get_item_row(item_id)
    conn = get_connection()

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return item_from_row(row)

    sets = []
    values: list[object] = []
    for key, value in fields.items():
        sets.append(f"{key} = ?")
        values.append(value.value if hasattr(value, "value") else value)
    values.append(item_id)
    conn.execute(f"UPDATE item SET {', '.join(sets)} WHERE id = ?", values)
    conn.commit()
    return item_from_row(get_item_row(item_id))


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_item(item_id: int) -> None:
    get_item_row(item_id)  # 404 if missing
    conn = get_connection()
    conn.execute("DELETE FROM item WHERE id = ?", (item_id,))
    conn.commit()


# --------------------------------------------------------------------------- #
# Pipeline operations (enqueue jobs)
# --------------------------------------------------------------------------- #
@router.post("/items/{item_id}/generate-image")
def generate_image(item_id: int, new_seed: int | None = None) -> dict[str, int]:
    row = get_item_row(item_id)
    conn = get_connection()

    if new_seed is not None:
        conn.execute("UPDATE item SET seed = ? WHERE id = ?", (new_seed, item_id))
        conn.commit()

    # Regenerating the image invalidates cutout/silhouette/segment downstream.
    _invalidate_downstream(row, from_status=ItemStatus.draft)

    from app import jobs  # lazy import

    job_id = jobs.enqueue(JobKind.generate_image, item_id)
    return {"job_id": job_id}


@router.post("/items/{item_id}/cutout")
def cutout(item_id: int) -> dict[str, int]:
    row = get_item_row(item_id)
    # Re-cutout keeps the generated image but drops the segment + cache hash.
    _invalidate_downstream(row, from_status=ItemStatus.image_ok)

    from app import jobs  # lazy import

    job_id = jobs.enqueue(JobKind.cutout, item_id)
    return {"job_id": job_id}


@router.post("/items/{item_id}/narration/{slot}", response_model=Item)
async def upload_narration(
    item_id: int, slot: str, file: UploadFile = _UPLOAD_FILE
) -> Item:
    if slot not in ("a", "b"):
        raise HTTPException(status_code=422, detail="A slot csak 'a' vagy 'b' lehet.")
    row = get_item_row(item_id)

    item_dir = item_dir_for_row(row)
    item_dir.mkdir(parents=True, exist_ok=True)
    # Raw upload is stored as the .webm asset (the schema's raw narration name).
    dest = storage.item_asset(item_dir, f"narration_{slot}.webm")
    data = await file.read()
    dest.write_bytes(data)
    return item_from_row(get_item_row(item_id))


@router.post("/items/{item_id}/clean-audio/{slot}")
def clean_audio(item_id: int, slot: str) -> dict[str, int]:
    if slot not in ("a", "b"):
        raise HTTPException(status_code=422, detail="A slot csak 'a' vagy 'b' lehet.")
    row = get_item_row(item_id)

    item_dir = item_dir_for_row(row)
    raw = storage.item_asset(item_dir, f"narration_{slot}.webm")
    if not raw.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Nincs nyers felvétel a(z) '{slot}' sávhoz — előbb tölts fel hangot.",
        )

    from app import jobs  # lazy import

    # The slot is encoded into the job log/handler via a composite ref; the
    # handler reads the slot from disk presence, so the bare item ref suffices.
    job_id = jobs.enqueue(JobKind.clean_audio, item_id)
    return {"job_id": job_id}


@router.post("/items/{item_id}/render-segment")
def render_segment(item_id: int) -> dict[str, int]:
    get_item_row(item_id)  # 404 if missing

    from app import jobs  # lazy import

    job_id = jobs.enqueue(JobKind.render_segment, item_id)
    return {"job_id": job_id}
