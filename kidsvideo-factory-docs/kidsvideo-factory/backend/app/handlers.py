"""Job handlers: JobKind -> pipeline call (CONTRACTS §6, 01-BLUEPRINT §5).

Every handler matches the registry signature
``fn(job_id, ref_id, set_progress, log) -> None`` and performs ALL heavy imports
(``rembg``, ``websocket-client``, the ffmpeg-driven pipeline modules) LAZILY,
inside the function body. Importing this module — and therefore ``main.py`` —
never requires ``rembg`` or a live ComfyUI.

``register_all()`` wires each kind into ``jobs.register`` at app startup.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app import storage
from app.db import get_connection
from app.models import ItemStatus, JobKind, TopicStatus

# Handler protocol: (job_id, ref_id, set_progress, log) -> None.
SetProgress = Callable[[float], None]
Log = Callable[[str], None]


# --------------------------------------------------------------------------- #
# Small DB helpers (handlers run in a worker thread; reuse the shared conn).
# --------------------------------------------------------------------------- #
def _item_row(item_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"Az elem nem található (id={item_id}).")
    return row


def _topic_row(topic_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM topic WHERE id = ?", (topic_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"A téma nem található (id={topic_id}).")
    return row


def _item_dir(item_row) -> Path:
    topic = _topic_row(item_row["topic_id"])
    return storage.item_dir(topic["slug"], item_row["position"], item_row["slug"])


def _set_item_status(item_id: int, status: ItemStatus) -> None:
    conn = get_connection()
    conn.execute("UPDATE item SET status = ? WHERE id = ?", (status.value, item_id))
    conn.commit()


# --------------------------------------------------------------------------- #
# generate_image — ComfyUI (P1, T5)
# --------------------------------------------------------------------------- #
def handle_generate_image(
    job_id: int, ref_id: int, set_progress: SetProgress, log: Log
) -> None:
    from app.config import get_settings
    from app.pipeline import comfy  # lazy: pulls websocket-client

    row = _item_row(ref_id)
    item_dir = _item_dir(row)
    item_dir.mkdir(parents=True, exist_ok=True)
    out_path = storage.item_asset(item_dir, "generated.png")

    # Workflow template + meta live at the repo's workflows/ (read-only inputs).
    repo_root = Path(__file__).resolve().parents[2]
    workflow_path = repo_root / "workflows" / "item-image.json"
    meta_path = repo_root / "workflows" / "item-image.meta.json"

    prompt_text = row["prompt"] or row["name"]
    seed = row["seed"] if row["seed"] is not None else 0

    log(f"Képgenerálás indítása (seed={seed}).")
    set_progress(0.1)
    comfy.generate_image(
        prompt_text=prompt_text,
        seed=seed,
        out_path=out_path,
        workflow_path=workflow_path,
        meta_path=meta_path,
        base_url=get_settings().comfyui_url,
    )
    set_progress(0.9)
    _set_item_status(ref_id, ItemStatus.image_ok)
    log("Kép elkészült.")
    set_progress(1.0)


# --------------------------------------------------------------------------- #
# cutout — rembg + silhouette (P1, T6)
# --------------------------------------------------------------------------- #
def handle_cutout(
    job_id: int, ref_id: int, set_progress: SetProgress, log: Log
) -> None:
    from app.pipeline import cutout as cutout_mod  # lazy: pulls rembg

    row = _item_row(ref_id)
    item_dir = _item_dir(row)
    generated = storage.item_asset(item_dir, "generated.png")
    if not generated.exists():
        raise RuntimeError("Nincs generált kép — előbb generálj képet az elemhez.")

    cutout_path = storage.item_asset(item_dir, "cutout.png")
    silhouette_path = storage.item_asset(item_dir, "silhouette.png")

    log("Háttér eltávolítása és sziluett előállítása.")
    set_progress(0.2)
    cutout_mod.cutout(generated, cutout_path, silhouette_path)
    set_progress(0.95)
    log("Kivágás és sziluett kész.")
    set_progress(1.0)


# --------------------------------------------------------------------------- #
# clean_audio — ffmpeg narration cleanup (P2, T8)
# --------------------------------------------------------------------------- #
def handle_clean_audio(
    job_id: int, ref_id: int, set_progress: SetProgress, log: Log
) -> None:
    from app.pipeline import audio  # lazy

    row = _item_row(ref_id)
    item_dir = _item_dir(row)

    cleaned_any = False
    for index, slot in enumerate(("a", "b")):
        raw = storage.item_asset(item_dir, f"narration_{slot}.webm")
        if not raw.exists():
            continue
        clean = storage.item_asset(item_dir, f"narration_{slot}.clean.wav")
        log(f"'{slot}' sáv tisztítása.")
        report = audio.clean_narration(raw, clean)
        # The loudnorm report goes into the job log for verification.
        log(f"'{slot}' loudnorm: {json.dumps(report, ensure_ascii=False)}")
        set_progress(0.4 + 0.4 * index)
        cleaned_any = True

    if not cleaned_any:
        raise RuntimeError("Nincs nyers narráció ehhez az elemhez.")

    # Both narration tracks present and cleaned => audio_ok (if image already ok).
    if row["status"] in (ItemStatus.image_ok.value, ItemStatus.audio_ok.value):
        _set_item_status(ref_id, ItemStatus.audio_ok)
    log("Hangtisztítás kész.")
    set_progress(1.0)


# --------------------------------------------------------------------------- #
# render_segment — the core (P3, T10)
# --------------------------------------------------------------------------- #
def handle_render_segment(
    job_id: int, ref_id: int, set_progress: SetProgress, log: Log
) -> None:
    from app.pipeline import audio, segment, timing  # lazy

    row = _item_row(ref_id)
    item_dir = _item_dir(row)

    silhouette = storage.item_asset(item_dir, "silhouette.png")
    cutout_img = storage.item_asset(item_dir, "cutout.png")
    narration_a = storage.item_asset(item_dir, "narration_a.clean.wav")
    narration_b = storage.item_asset(item_dir, "narration_b.clean.wav")
    for required in (silhouette, cutout_img, narration_a, narration_b):
        if not required.exists():
            raise RuntimeError(f"Hiányzó bemenet a szegmenshez: {required.name}")

    # Optional SFX assigned on the item (storage-relative path).
    sfx: Path | None = None
    if row["sfx_path"]:
        candidate = storage.data_root() / row["sfx_path"]
        if candidate.exists():
            sfx = candidate

    # Optional topic background.
    topic = _topic_row(row["topic_id"])
    background: Path | None = None
    if topic["background_path"]:
        bg_candidate = storage.data_root() / topic["background_path"]
        if bg_candidate.exists():
            background = bg_candidate

    log("Hossz-mérés és időzítés számítása.")
    set_progress(0.15)
    len_a = audio.duration_seconds(narration_a)
    len_b = audio.duration_seconds(narration_b)
    len_sfx = audio.duration_seconds(sfx) if sfx is not None else 0.0
    seg_timing = timing.compute_timing(len_a, len_sfx, len_b)

    out_path = storage.item_asset(item_dir, "segment.mp4")
    log("Szegmens renderelése.")
    set_progress(0.3)
    segment.render_segment(
        background=background,
        silhouette=silhouette,
        cutout=cutout_img,
        narration_a=narration_a,
        sfx=sfx,
        narration_b=narration_b,
        out_path=out_path,
        timing=seg_timing,
    )
    set_progress(0.9)

    # Persist the cache hash into meta.json (01-BLUEPRINT §6.3).
    try:
        seg_hash = segment.segment_inputs_hash(
            background=background,
            silhouette=silhouette,
            cutout=cutout_img,
            narration_a=narration_a,
            sfx=sfx,
            narration_b=narration_b,
            timing=seg_timing,
        )
        meta_path = storage.item_asset(item_dir, "meta.json")
        meta_path.write_text(
            json.dumps({"segment_hash": seg_hash}, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:  # hash is a cache optimisation, never fatal
        log(f"Figyelem: a szegmens-hash nem készült el ({exc}).")

    _set_item_status(ref_id, ItemStatus.segment_ok)
    log("Szegmens kész.")
    set_progress(1.0)


# --------------------------------------------------------------------------- #
# assemble — concat into the final video (T11)
# --------------------------------------------------------------------------- #
def handle_assemble(
    job_id: int, ref_id: int, set_progress: SetProgress, log: Log
) -> None:
    from app.pipeline import assemble as assemble_mod  # lazy

    topic = _topic_row(ref_id)
    conn = get_connection()
    item_rows = conn.execute(
        "SELECT * FROM item WHERE topic_id = ? ORDER BY position", (ref_id,)
    ).fetchall()
    if not item_rows:
        raise RuntimeError("A témának nincs eleme — nincs mit összefűzni.")

    segments: list[Path] = []
    for r in item_rows:
        idir = storage.item_dir(topic["slug"], r["position"], r["slug"])
        seg = storage.item_asset(idir, "segment.mp4")
        if not seg.exists():
            raise RuntimeError(
                f"A(z) '{r['name']}' elemnek nincs kész szegmense — előbb rendereld."
            )
        segments.append(seg)

    # Optional branding intro/outro.
    branding = storage.branding_dir()
    intro = branding / "intro.mp4"
    outro = branding / "outro.mp4"
    intro_arg = intro if intro.exists() else None
    outro_arg = outro if outro.exists() else None

    render_dir = storage.render_dir(topic["slug"])
    render_dir.mkdir(parents=True, exist_ok=True)
    out_path = render_dir / "final.mp4"
    list_file = render_dir / "concat.txt"

    log(f"{len(segments)} szegmens összefűzése.")
    set_progress(0.3)
    assemble_mod.assemble(
        intro=intro_arg,
        segments=segments,
        outro=outro_arg,
        out_path=out_path,
        list_file=list_file,
    )
    set_progress(0.95)

    conn.execute("UPDATE topic SET status = ? WHERE id = ?", (TopicStatus.done.value, ref_id))
    conn.commit()
    log("A végső videó elkészült.")
    set_progress(1.0)


# --------------------------------------------------------------------------- #
# Registry wiring
# --------------------------------------------------------------------------- #
_HANDLERS = {
    JobKind.generate_image: handle_generate_image,
    JobKind.cutout: handle_cutout,
    JobKind.clean_audio: handle_clean_audio,
    JobKind.render_segment: handle_render_segment,
    JobKind.assemble: handle_assemble,
}


def register_all() -> None:
    """Register every handler with the job system (called at app startup)."""

    from app import jobs  # lazy: jobs is a sibling module written in parallel

    for kind, fn in _HANDLERS.items():
        jobs.register(kind, fn)
