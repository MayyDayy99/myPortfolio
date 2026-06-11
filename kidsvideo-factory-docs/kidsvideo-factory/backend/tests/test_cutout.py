"""Tests for ``pipeline.cutout`` (CONTRACTS §9, 03-VIDEO-SPEC §3).

The silhouette + bbox path is pure PIL and must work WITHOUT rembg (the dev box
has no rembg). We build a synthetic RGBA PNG with a known opaque rectangle and
assert:

* the silhouette RGB is all-zero where opaque (it is a silhouette, not a
  darkened image),
* the silhouette alpha matches the cutout's alpha (binarized at the threshold),
* the bounding box of the opaque region is correct.

The real rembg cutout path is covered by a separate test gated on
``pytest.importorskip("rembg")`` so it skips cleanly when rembg is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.pipeline import cutout as cutout_mod


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _make_shape_png(
    path: Path,
    size: tuple[int, int] = (64, 48),
    box: tuple[int, int, int, int] = (10, 8, 40, 30),
    fill_rgb: tuple[int, int, int] = (200, 120, 30),
    opaque_alpha: int = 255,
) -> tuple[int, int, int, int]:
    """Write an RGBA PNG: transparent everywhere except an opaque ``box``.

    Returns the box as ``(left, top, right, bottom)`` — the exact bbox PIL's
    ``getbbox()`` should report for the opaque region.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    left, top, right, bottom = box
    # Paint an opaque colored rectangle; PIL rectangle is inclusive of both
    # corners, so to get a getbbox() of (left, top, right, bottom) we draw to
    # (right-1, bottom-1).
    region = Image.new("RGBA", (right - left, bottom - top), (*fill_rgb, opaque_alpha))
    img.paste(region, (left, top))
    img.save(path, "PNG")
    return box


# --------------------------------------------------------------------------- #
# Module import / lazy-rembg invariants
# --------------------------------------------------------------------------- #
def test_module_imports_without_rembg() -> None:
    """The module must import and expose its API without rembg installed."""

    assert hasattr(cutout_mod, "cutout")
    assert hasattr(cutout_mod, "make_silhouette")
    assert hasattr(cutout_mod, "bounding_box")
    # The session singleton starts uninitialized (no rembg touched on import).
    assert cutout_mod._session is None


# --------------------------------------------------------------------------- #
# Silhouette path (pure PIL — no rembg)
# --------------------------------------------------------------------------- #
def test_make_silhouette_rgb_black_and_alpha_preserved(tmp_path: Path) -> None:
    box = _make_shape_png(tmp_path / "cutout.png")
    with Image.open(tmp_path / "cutout.png") as src:
        cut = src.convert("RGBA")

    silhouette = cutout_mod.make_silhouette(cut, alpha_threshold=128)

    assert silhouette.mode == "RGBA"
    assert silhouette.size == cut.size

    r, g, b, a = silhouette.split()
    cut_alpha = cut.getchannel("A")

    left, top, right, bottom = box
    width, height = silhouette.size
    for y in range(height):
        for x in range(width):
            opaque = left <= x < right and top <= y < bottom
            # RGB is fully black everywhere (silhouette, not darkened image).
            assert r.getpixel((x, y)) == 0
            assert g.getpixel((x, y)) == 0
            assert b.getpixel((x, y)) == 0
            # Alpha is preserved (binarized): opaque -> 255, transparent -> 0.
            expected_alpha = 255 if cut_alpha.getpixel((x, y)) >= 128 else 0
            assert a.getpixel((x, y)) == expected_alpha
            assert a.getpixel((x, y)) == (255 if opaque else 0)


def test_make_silhouette_threshold_binarizes_alpha() -> None:
    # A horizontal gradient of alpha values across an opaque-colored image.
    width, height = 256, 4
    cut = Image.new("RGBA", (width, height))
    for x in range(width):
        for y in range(height):
            cut.putpixel((x, y), (170, 80, 40, x))  # alpha == x (0..255)

    threshold = 128
    silhouette = cutout_mod.make_silhouette(cut, alpha_threshold=threshold)
    alpha = silhouette.getchannel("A")

    # Pixels below the threshold are fully transparent, at/above fully opaque.
    assert alpha.getpixel((threshold - 1, 0)) == 0
    assert alpha.getpixel((threshold, 0)) == 255
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((255, 0)) == 255

    # RGB stays black regardless of the source color.
    r, g, b, _ = silhouette.split()
    assert r.getextrema() == (0, 0)
    assert g.getextrema() == (0, 0)
    assert b.getextrema() == (0, 0)


# --------------------------------------------------------------------------- #
# Bounding box
# --------------------------------------------------------------------------- #
def test_bounding_box_matches_opaque_region(tmp_path: Path) -> None:
    box = _make_shape_png(
        tmp_path / "cutout.png",
        size=(80, 60),
        box=(12, 9, 50, 41),
    )
    assert cutout_mod.bounding_box(tmp_path / "cutout.png") == box


def test_bounding_box_full_canvas_when_fully_transparent(tmp_path: Path) -> None:
    path = tmp_path / "empty.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (32, 24), (0, 0, 0, 0)).save(path, "PNG")
    # getbbox() is None for a fully transparent image -> fall back to full rect.
    assert cutout_mod.bounding_box(path) == (0, 0, 32, 24)


# --------------------------------------------------------------------------- #
# Real rembg cutout path (skips when rembg is not installed)
# --------------------------------------------------------------------------- #
def test_cutout_with_rembg(tmp_path: Path) -> None:
    pytest.importorskip("rembg")

    # A solid subject on a contrasting background; rembg should keep some of it.
    src = Image.new("RGBA", (128, 128), (20, 180, 60, 255))
    src.paste(Image.new("RGBA", (40, 40), (240, 240, 240, 255)), (44, 44))
    generated = tmp_path / "generated.png"
    src.save(generated, "PNG")

    cutout_path = tmp_path / "cutout.png"
    silhouette_path = tmp_path / "silhouette.png"

    cutout_mod.cutout(generated, cutout_path, silhouette_path, alpha_threshold=128)

    assert cutout_path.is_file()
    assert silhouette_path.is_file()

    with Image.open(cutout_path) as cut_img:
        cut = cut_img.convert("RGBA")
    with Image.open(silhouette_path) as sil_img:
        silhouette = sil_img.convert("RGBA")

    assert cut.size == src.size
    assert silhouette.size == src.size

    # The silhouette RGB must be fully black wherever it is opaque.
    sr, sg, sb, sa = silhouette.split()
    assert sr.getextrema() == (0, 0)
    assert sg.getextrema() == (0, 0)
    assert sb.getextrema() == (0, 0)

    # The silhouette alpha is the binarized cutout alpha.
    cut_alpha = cut.getchannel("A")
    for x in range(0, src.width, 7):
        for y in range(0, src.height, 7):
            expected = 255 if cut_alpha.getpixel((x, y)) >= 128 else 0
            assert sa.getpixel((x, y)) == expected
