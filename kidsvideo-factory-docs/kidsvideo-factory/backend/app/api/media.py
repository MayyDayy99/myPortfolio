"""Media / SFX listing route (CONTRACTS §13).

The actual asset bytes are served by the read-only ``/media`` StaticFiles mount
declared in ``main.py``. This router only lists the shared SFX library so the
``SfxPicker`` UI can offer them for preview + assignment.
"""

from __future__ import annotations

from fastapi import APIRouter

from app import storage

router = APIRouter(tags=["media"])

# Audio extensions we treat as selectable sound effects.
_SFX_EXTENSIONS = {".wav", ".mp3", ".ogg", ".m4a", ".aac", ".flac"}


@router.get("/sfx")
def list_sfx() -> list[dict[str, str]]:
    """List the files under ``data/sfx``.

    Each entry exposes the filename, a ``/media``-relative URL for preview, and
    the storage-relative ``sfx_path`` to persist on an item.
    """

    sfx_root = storage.sfx_dir()
    if not sfx_root.is_dir():
        return []

    data_root = storage.data_root()
    entries: list[dict[str, str]] = []
    for path in sorted(sfx_root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _SFX_EXTENSIONS:
            continue
        rel = path.relative_to(data_root).as_posix()
        entries.append(
            {
                "name": path.name,
                "sfx_path": rel,
                "media_url": f"/media/{rel}",
            }
        )
    return entries
