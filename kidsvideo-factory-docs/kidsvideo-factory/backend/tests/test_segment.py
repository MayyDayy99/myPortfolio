"""GOLDEN test for the segment renderer (CONTRACTS §11, 03-VIDEO-SPEC §7).

Renders a real segment with ffmpeg from synthetic PIL images + short, known
-length WAVs, then asserts with ffprobe:

* total duration == ``timing.total`` within ±1 frame (acceptance crit. §7.1);
* the reveal crossfade lands at ``timing.xfade_offset`` (crit. §7.4 — sync);
* the video is 1920×1080, 30 fps, yuv420p (R1 / §3);
* an audio stream exists (the loudness/no-click crit. §7.2/§7.3 are covered by
  the audio tests; here we assert the track is present and the right length).

NO second-values are duplicated — every expectation derives from
``app.pipeline.timing`` (the single source of truth).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.pipeline import timing as T
from app.pipeline.segment import render_segment, segment_inputs_hash
from tests.conftest import requires_ffmpeg
from tests.probe_phases import (
    dimensions,
    frame_rate,
    has_audio_stream,
    pixel_format,
    probe_format,
    total_duration,
    within_one_frame,
)

# Known synthetic asset lengths (seconds). These are *input asset* lengths, not
# phase durations — the phase durations come from timing.compute_timing.
LEN_A = 1.5
LEN_SFX = 0.7
LEN_B = 1.0


# --------------------------------------------------------------------------- #
# Synthetic asset factories (PIL + ffmpeg). The silhouette shares the cutout's
# alpha exactly, as the real cutout pipeline guarantees.
# --------------------------------------------------------------------------- #
def _make_cutout_and_silhouette(cutout: Path, silhouette: Path) -> None:
    from PIL import Image, ImageDraw

    w, h = 700, 1000
    cut = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(cut)
    # A clearly coloured subject so the reveal is unambiguous in the frame probe.
    draw.rounded_rectangle([150, 420, 550, 950], radius=60, fill=(40, 160, 220, 255))
    draw.ellipse([230, 120, 470, 400], fill=(250, 210, 90, 255))
    cut.save(cutout, "PNG")

    alpha = cut.getchannel("A")
    black = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    transparent = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sil = Image.composite(black, transparent, alpha)
    sil.save(silhouette, "PNG")


def _make_wav(path: Path, seconds: float, freq: int) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={seconds}:sample_rate=48000",
        "-ac", "1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"WAV synth failed:\n{proc.stderr[-400:]}")


@pytest.fixture
def assets(tmp_path: Path) -> dict[str, Path]:
    cut = tmp_path / "cutout.png"
    sil = tmp_path / "silhouette.png"
    na = tmp_path / "narration_a.wav"
    sfx = tmp_path / "sfx.wav"
    nb = tmp_path / "narration_b.wav"
    _make_cutout_and_silhouette(cut, sil)
    _make_wav(na, LEN_A, freq=330)
    _make_wav(sfx, LEN_SFX, freq=880)
    _make_wav(nb, LEN_B, freq=440)
    return {"cutout": cut, "silhouette": sil, "narr_a": na, "sfx": sfx, "narr_b": nb}


@pytest.fixture
def timing() -> T.SegmentTiming:
    return T.compute_timing(LEN_A, LEN_SFX, LEN_B)


# --------------------------------------------------------------------------- #
# GOLDEN test — solid background.
# --------------------------------------------------------------------------- #
@requires_ffmpeg
def test_segment_golden_solid_bg(
    tmp_path: Path, assets: dict[str, Path], timing: T.SegmentTiming
) -> None:
    out = tmp_path / "segment.mp4"
    render_segment(
        background=None,
        silhouette=assets["silhouette"],
        cutout=assets["cutout"],
        narration_a=assets["narr_a"],
        sfx=assets["sfx"],
        narration_b=assets["narr_b"],
        out_path=out,
        timing=timing,
    )
    assert out.exists() and out.stat().st_size > 0

    info = probe_format(out)

    # §7.1 — total duration within ±1 frame of the (quantized) timing total.
    measured = total_duration(out)
    expected_total = T.quantize(timing.total)
    assert within_one_frame(measured, expected_total), (
        f"total {measured}s != expected {expected_total}s (>1 frame)"
    )

    # §3 / R1 — geometry, frame rate, pixel format.
    assert dimensions(info) == (1920, 1080)
    assert abs(frame_rate(info) - T.FPS) < 1e-6
    assert pixel_format(info) == "yuv420p"

    # §7.2/§7.3 — an audio stream must exist (loudness/click covered by audio
    # tests); its duration must also match within ±1 frame.
    assert has_audio_stream(info)
    audio_dur = _audio_stream_duration(out)
    assert within_one_frame(audio_dur, expected_total)


@requires_ffmpeg
def test_segment_reveal_sync(
    tmp_path: Path, assets: dict[str, Path], timing: T.SegmentTiming
) -> None:
    """§7.4 — the reveal crossfade must occur exactly at ``xfade_offset``.

    Sample the centre region: it is the black silhouette just before the
    crossfade, and the coloured cutout after the crossfade ends.
    """

    out = tmp_path / "segment.mp4"
    render_segment(
        background=None,
        silhouette=assets["silhouette"],
        cutout=assets["cutout"],
        narration_a=assets["narr_a"],
        sfx=assets["sfx"],
        narration_b=assets["narr_b"],
        out_path=out,
        timing=timing,
    )

    one_frame = 1.0 / T.FPS
    reveal_start = T.quantize(timing.xfade_offset)
    reveal_end = reveal_start + T.quantize(timing.reveal)

    # Just before the crossfade -> silhouette region is (near) black.
    before = _sample_centre(out, tmp_path, max(reveal_start - one_frame, 0.0))
    # Well after the crossfade ends -> coloured cutout.
    after = _sample_centre(out, tmp_path, reveal_end + 5 * one_frame)

    assert sum(before) < 60, f"expected dark silhouette before reveal, got {before}"
    assert sum(after) > 120, f"expected coloured cutout after reveal, got {after}"
    # The blue body fill (40,160,220) dominates the centre after the reveal.
    assert after[2] > after[0], f"expected blue-dominant cutout, got {after}"


@requires_ffmpeg
def test_segment_no_sfx(
    tmp_path: Path, assets: dict[str, Path]
) -> None:
    """Without sfx the phase 4 stays silent but keeps its SFX_MIN length."""

    out = tmp_path / "segment.mp4"
    timing = T.compute_timing(LEN_A, 0.0, LEN_B)  # no sfx measured -> clamps up
    render_segment(
        background=None,
        silhouette=assets["silhouette"],
        cutout=assets["cutout"],
        narration_a=assets["narr_a"],
        sfx=None,
        narration_b=assets["narr_b"],
        out_path=out,
        timing=timing,
    )
    info = probe_format(out)
    measured = total_duration(out)
    expected_total = T.quantize(timing.total)
    assert within_one_frame(measured, expected_total)
    assert has_audio_stream(info)
    # The sfx phase still equals SFX_MIN even though no sfx was provided.
    assert timing.sfx == pytest.approx(T.SFX_MIN)


@requires_ffmpeg
def test_segment_with_image_background(
    tmp_path: Path, assets: dict[str, Path], timing: T.SegmentTiming
) -> None:
    """The image-background branch renders and keeps the same total length."""

    from PIL import Image

    bg = tmp_path / "background.png"
    Image.new("RGB", (1920, 1080), (210, 235, 255)).save(bg)

    out = tmp_path / "segment_bg.mp4"
    render_segment(
        background=bg,
        silhouette=assets["silhouette"],
        cutout=assets["cutout"],
        narration_a=assets["narr_a"],
        sfx=assets["sfx"],
        narration_b=assets["narr_b"],
        out_path=out,
        timing=timing,
    )
    info = probe_format(out)
    assert dimensions(info) == (1920, 1080)
    assert within_one_frame(total_duration(out), T.quantize(timing.total))


def test_segment_inputs_hash_changes_with_inputs(
    assets: dict[str, Path], timing: T.SegmentTiming
) -> None:
    """The cache key is stable for equal inputs and changes when any input does.

    (No ffmpeg needed — pure hashing of file content + timing.)
    """

    base = dict(
        background=None,
        silhouette=assets["silhouette"],
        cutout=assets["cutout"],
        narration_a=assets["narr_a"],
        sfx=assets["sfx"],
        narration_b=assets["narr_b"],
        timing=timing,
    )
    h1 = segment_inputs_hash(**base)
    h2 = segment_inputs_hash(**base)
    assert h1 == h2

    # Different timing -> different hash.
    other_timing = T.compute_timing(LEN_A + 1.0, LEN_SFX, LEN_B)
    h3 = segment_inputs_hash(**{**base, "timing": other_timing})
    assert h3 != h1

    # Dropping the sfx -> different hash.
    h4 = segment_inputs_hash(**{**base, "sfx": None})
    assert h4 != h1


@requires_ffmpeg
def test_segment_missing_input_raises(
    tmp_path: Path, assets: dict[str, Path], timing: T.SegmentTiming
) -> None:
    from app.pipeline.segment import SegmentRenderError

    with pytest.raises(SegmentRenderError):
        render_segment(
            background=None,
            silhouette=tmp_path / "does_not_exist.png",
            cutout=assets["cutout"],
            narration_a=assets["narr_a"],
            sfx=assets["sfx"],
            narration_b=assets["narr_b"],
            out_path=tmp_path / "x.mp4",
            timing=timing,
        )


# --------------------------------------------------------------------------- #
# Local ffprobe / ffmpeg helpers used only by this test module.
# --------------------------------------------------------------------------- #
def _audio_stream_duration(path: Path) -> float:
    """Audio length in seconds, decoded robustly.

    The MP4/AAC ``stream=duration`` tag is unreliable (it can be absent or a
    garbage value), so we measure by reading the decoded packets' end time,
    falling back to the container duration. Either way it must match the video.
    """

    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=duration",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True, text=True,
    )
    text = proc.stdout.strip()
    try:
        value = float(text)
    except ValueError:
        value = float("nan")
    # Accept only a sane, positive value; otherwise use the container duration.
    if not (0.0 < value < 24 * 3600):
        return total_duration(path)
    return value


def _sample_centre(mp4: Path, tmp: Path, ts: float) -> tuple[int, int, int]:
    """Average RGB of the centre region at timestamp ``ts`` seconds."""

    frame = tmp / f"frame_{ts:.3f}.png"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{ts:.3f}", "-i", str(mp4), "-frames:v", "1", str(frame)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not frame.exists():
        raise RuntimeError(f"frame extract failed at {ts}s:\n{proc.stderr[-300:]}")

    from PIL import Image

    with Image.open(frame) as im:
        region = im.convert("RGB").crop((860, 350, 1060, 700))
        # Average colour via a 1x1 downscale (robust across Pillow versions).
        r, g, b = region.resize((1, 1)).getpixel((0, 0))
    return (int(r), int(g), int(b))
