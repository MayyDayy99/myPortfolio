"""Background removal + silhouette (P1, CONTRACTS §9, 03-VIDEO-SPEC §3).

Pipeline P1 step 2: take the ComfyUI ``generated.png`` and produce

* ``cutout.png``    — RGBA with the background removed (rembg / u2net),
* ``silhouette.png``— the cutout alpha filled fully BLACK (RGB 0,0,0, alpha
  preserved). NOT a darkened image: the texture must be unrecognizable so the
  silhouette works as a riddle (03-VIDEO-SPEC §3).

``rembg`` is heavy (onnxruntime + the u2net model) and is NOT installed on the
dev box. It is therefore lazy-imported INSIDE the functions that need it, so the
whole backend still imports cleanly without rembg. The u2net session is a
module-level singleton, created once and reused for every cutout.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PIL import Image

# Fully-black RGB used to fill the silhouette; alpha is taken from the cutout.
_SILHOUETTE_RGB = (0, 0, 0)

# --------------------------------------------------------------------------- #
# rembg u2net session singleton (lazy).
# --------------------------------------------------------------------------- #
# We never import rembg at module load: the dev box has no rembg, and every
# non-cutout test/import path must work without it. The session is created on
# first use and reused (loading the u2net ONNX model is expensive).
_session = None
_session_lock = threading.Lock()


def _get_session():
    """Return the process-wide rembg ``u2net`` session, creating it once.

    Lazy-imports ``rembg`` inside the function so importing this module never
    requires rembg to be installed.
    """

    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                # Lazy import: keeps the module importable without rembg.
                from rembg import new_session

                _session = new_session("u2net")
    return _session


def cutout(
    generated_path: Path,
    cutout_path: Path,
    silhouette_path: Path,
    alpha_threshold: int = 128,
) -> None:
    """Remove the background and write the cutout + silhouette.

    ``generated_path`` is the raw ComfyUI image. ``cutout_path`` receives the
    RGBA cutout (background removed via rembg/u2net). ``silhouette_path``
    receives the cutout alpha filled fully black (see :func:`make_silhouette`).

    ``alpha_threshold`` binarizes the silhouette alpha: pixels with alpha
    greater than or equal to the threshold become fully opaque, the rest fully
    transparent. This keeps the silhouette edge crisp (03-VIDEO-SPEC §3).

    rembg is lazy-imported here, so importing this module does not require it.
    """

    generated_path = Path(generated_path)
    cutout_path = Path(cutout_path)
    silhouette_path = Path(silhouette_path)

    # Lazy import: rembg.remove is only needed for the actual background removal.
    from rembg import remove

    cutout_path.parent.mkdir(parents=True, exist_ok=True)
    silhouette_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(generated_path) as src:
        rgba_src = src.convert("RGBA")

    # rembg returns an RGBA image with the background made transparent. Reusing
    # the singleton session avoids reloading the u2net model on every call.
    cut = remove(rgba_src, session=_get_session())
    cut = cut.convert("RGBA")
    cut.save(cutout_path, "PNG")

    silhouette = make_silhouette(cut, alpha_threshold=alpha_threshold)
    silhouette.save(silhouette_path, "PNG")


def make_silhouette(cutout_image: Image.Image, alpha_threshold: int = 128) -> Image.Image:
    """Return an RGBA silhouette: black RGB with the cutout's alpha.

    The RGB channels are forced to fully black ``(0, 0, 0)`` everywhere, so the
    original texture is gone (this is a silhouette, not a darkened image). The
    alpha channel is taken from ``cutout_image`` and binarized with
    ``alpha_threshold`` so the contour stays crisp and matches the cutout edge.

    Pure PIL — no rembg required. The renderer scales the silhouette and the
    cutout identically (CONTRACTS §11), so their alphas must line up; we keep the
    same canvas size and a thresholded copy of the cutout alpha here.
    """

    rgba = cutout_image.convert("RGBA")
    alpha = rgba.getchannel("A")
    # Binarize: alpha >= threshold -> 255 (opaque), else 0 (transparent).
    # point() maps each value; using a 0/255 mask keeps a hard silhouette edge.
    binary_alpha = alpha.point(lambda value: 255 if value >= alpha_threshold else 0)

    silhouette = Image.new("RGBA", rgba.size, (*_SILHOUETTE_RGB, 0))
    silhouette.putalpha(binary_alpha)
    return silhouette


def bounding_box(cutout_path: Path) -> tuple[int, int, int, int]:
    """Return the bbox of the non-transparent pixels: ``(left, top, right, bottom)``.

    Uses PIL ``getbbox()`` on the alpha channel. ``segment.py`` uses this to
    scale the cutout/silhouette consistently (CONTRACTS §9, §11). For a fully
    transparent image ``getbbox()`` returns ``None``; we fall back to the full
    image rectangle so callers always get a usable box.
    """

    cutout_path = Path(cutout_path)
    with Image.open(cutout_path) as img:
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        box = alpha.getbbox()
        if box is None:
            # No opaque pixels: fall back to the whole canvas.
            return (0, 0, rgba.width, rgba.height)
        return box
