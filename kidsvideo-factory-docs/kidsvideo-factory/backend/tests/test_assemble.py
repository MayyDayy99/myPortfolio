"""Tests for ``pipeline.assemble`` (CONTRACTS §12, ffmpeg-recipes R5).

Real ffmpeg is used (it is present on the dev box): two short R1-parameter mp4s
are generated, concatenated, and ffprobe verifies the final duration is ~the sum
of the two. Additional tests cover the concat-list path resolution, the
re-encode fallback warning, and ``needs_rerender`` cache logic.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.pipeline import assemble as A
from app.pipeline import timing as T

from .conftest import requires_ffmpeg

# R1 video clips run at this frame rate; durations are chosen off round seconds
# so the sum check is meaningful rather than trivially aligned.
_CLIP_A_SECONDS = 1.0
_CLIP_B_SECONDS = 1.5


def _make_r1_clip(path: Path, seconds: float, *, hue: int) -> Path:
    """Render a short clip with the exact R1 encoding parameters.

    A solid-color test source plus a sine tone gives a real A/V mp4 that the
    concat demuxer can copy losslessly (same codecs/params as production).
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x{hue:06X}:s=320x240:r=30:d={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}:sample_rate=48000",
        # --- R1 output args (ffmpeg-recipes R1) ---
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-shortest",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"R1 clip generation failed:\n{proc.stderr[-600:]}")
    return path


def _probe_duration(path: Path) -> float:
    """Return container duration in seconds via ffprobe."""

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{proc.stderr[-300:]}")
    return float(proc.stdout.strip())


@requires_ffmpeg
def test_assemble_duration_is_sum_of_parts(tmp_path: Path) -> None:
    """The concatenated final duration ~= sum of the two segment durations."""

    seg_a = _make_r1_clip(tmp_path / "segs" / "01" / "segment.mp4", _CLIP_A_SECONDS, hue=0xFF0000)
    seg_b = _make_r1_clip(tmp_path / "segs" / "02" / "segment.mp4", _CLIP_B_SECONDS, hue=0x00FF00)

    out_path = tmp_path / "render" / "final.mp4"
    list_file = tmp_path / "render" / "list.txt"

    A.assemble(
        intro=None,
        segments=[seg_a, seg_b],
        outro=None,
        out_path=out_path,
        list_file=list_file,
    )

    assert out_path.is_file() and out_path.stat().st_size > 0

    final = _probe_duration(out_path)
    expected = _probe_duration(seg_a) + _probe_duration(seg_b)
    # Allow a couple of frames of slack for container/keyframe boundaries.
    tol = 2.0 / T.FPS + 0.05
    assert final == pytest.approx(expected, abs=tol)


@requires_ffmpeg
def test_concat_list_uses_paths_relative_to_list_file(tmp_path: Path) -> None:
    """list.txt entries resolve relative to the list file's own directory."""

    render = tmp_path / "render"
    seg_a = _make_r1_clip(render / "segments" / "01" / "segment.mp4", 0.5, hue=0x112233)
    seg_b = _make_r1_clip(render / "segments" / "02" / "segment.mp4", 0.5, hue=0x445566)

    out_path = render / "final.mp4"
    list_file = render / "list.txt"

    A.assemble(
        intro=None,
        segments=[seg_a, seg_b],
        outro=None,
        out_path=out_path,
        list_file=list_file,
    )

    text = list_file.read_text(encoding="utf-8")
    # Paths are relative (no drive letter / leading slash) and forward-slashed.
    assert "segments/01/segment.mp4" in text
    assert "segments/02/segment.mp4" in text
    assert ":" not in text  # no absolute Windows drive in the relative entries

    # And ffmpeg actually resolved them: the output exists with content.
    assert out_path.is_file() and out_path.stat().st_size > 0


@requires_ffmpeg
def test_intro_and_outro_are_included(tmp_path: Path) -> None:
    """intro + segment + outro all contribute to the final duration/order."""

    intro = _make_r1_clip(tmp_path / "branding" / "intro.mp4", 0.5, hue=0x000000)
    seg = _make_r1_clip(tmp_path / "segs" / "01" / "segment.mp4", 1.0, hue=0xFFFFFF)
    outro = _make_r1_clip(tmp_path / "branding" / "outro.mp4", 0.5, hue=0x808080)

    out_path = tmp_path / "render" / "final.mp4"
    list_file = tmp_path / "render" / "list.txt"

    A.assemble(
        intro=intro,
        segments=[seg],
        outro=outro,
        out_path=out_path,
        list_file=list_file,
    )

    final = _probe_duration(out_path)
    expected = _probe_duration(intro) + _probe_duration(seg) + _probe_duration(outro)
    tol = 3.0 / T.FPS + 0.05
    assert final == pytest.approx(expected, abs=tol)


@requires_ffmpeg
def test_mismatched_segment_falls_back_to_reencode_with_warning(tmp_path: Path) -> None:
    """A non-R1 part breaks ``-c copy`` → R1 re-encode + Hungarian warning."""

    good = _make_r1_clip(tmp_path / "segs" / "01" / "segment.mp4", 1.0, hue=0xAA1100)

    # A deliberately divergent clip: different resolution + codec params so the
    # stream copy concat cannot stitch it onto the first one.
    bad = tmp_path / "segs" / "02" / "segment.mp4"
    bad.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x0011AA:s=640x480:r=25:d=1.0",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=330:duration=1.0:sample_rate=44100",
        "-c:v",
        "mpeg4",  # different codec → copy concat must fail
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "1",
        "-shortest",
        str(bad),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-400:]

    out_path = tmp_path / "render" / "final.mp4"
    list_file = tmp_path / "render" / "list.txt"

    messages: list[str] = []
    A.assemble(
        intro=None,
        segments=[good, bad],
        outro=None,
        out_path=out_path,
        list_file=list_file,
        log=messages.append,
    )

    # A re-encode produced a valid file...
    assert out_path.is_file() and out_path.stat().st_size > 0
    # ...and a Hungarian fallback warning was emitted to the log sink.
    assert any("Újrakódolásra váltok" in m for m in messages)


def test_assemble_requires_at_least_one_segment(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        A.assemble(
            intro=None,
            segments=[],
            outro=None,
            out_path=tmp_path / "final.mp4",
            list_file=tmp_path / "list.txt",
        )


def test_assemble_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        A.assemble(
            intro=None,
            segments=[tmp_path / "does-not-exist.mp4"],
            outro=None,
            out_path=tmp_path / "final.mp4",
            list_file=tmp_path / "list.txt",
        )


# --------------------------------------------------------------------------- #
# needs_rerender — cache hash comparison (01-BLUEPRINT §6.3)
# --------------------------------------------------------------------------- #
def _write_item(item_dir: Path, *, with_segment: bool, meta: dict | None) -> Path:
    item_dir.mkdir(parents=True, exist_ok=True)
    if with_segment:
        (item_dir / "segment.mp4").write_bytes(b"\x00\x00")
    if meta is not None:
        (item_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return item_dir


def test_needs_rerender_missing_segment(tmp_path: Path) -> None:
    item = _write_item(tmp_path / "it", with_segment=False, meta={"inputs_hash": "abc"})
    assert A.needs_rerender(item, "abc") is True


def test_needs_rerender_missing_meta(tmp_path: Path) -> None:
    item = _write_item(tmp_path / "it", with_segment=True, meta=None)
    assert A.needs_rerender(item, "abc") is True


def test_needs_rerender_hash_match(tmp_path: Path) -> None:
    item = _write_item(tmp_path / "it", with_segment=True, meta={"inputs_hash": "abc"})
    assert A.needs_rerender(item, "abc") is False


def test_needs_rerender_hash_mismatch(tmp_path: Path) -> None:
    item = _write_item(tmp_path / "it", with_segment=True, meta={"inputs_hash": "old"})
    assert A.needs_rerender(item, "new") is True


def test_needs_rerender_meta_without_hash(tmp_path: Path) -> None:
    item = _write_item(tmp_path / "it", with_segment=True, meta={"other": 1})
    assert A.needs_rerender(item, "abc") is True


def test_needs_rerender_corrupt_meta(tmp_path: Path) -> None:
    item = tmp_path / "it"
    item.mkdir(parents=True)
    (item / "segment.mp4").write_bytes(b"\x00")
    (item / "meta.json").write_text("{not valid json", encoding="utf-8")
    assert A.needs_rerender(item, "abc") is True
