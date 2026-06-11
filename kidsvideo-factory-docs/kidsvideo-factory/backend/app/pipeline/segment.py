"""Segment renderer — the factory core (P3, CONTRACTS §11, ffmpeg-recipes R4).

Builds one item segment from its assets with a single ffmpeg invocation:

* background  : image loop or solid colour, the full ``timing.total`` long;
* silhouette  : faded in over ``ENTRY`` (0.8 s) and scaled 0.95 -> 1.0, overlaid
                on the background for the silhouette section;
* cutout      : the *same* scale / overlay coordinates (computed once from the
                cutout's alpha bbox), overlaid for the reveal section;
* the two visual sections are joined by ``xfade=transition=fade`` so the
  silhouette dissolves into the cutout exactly at ``timing.xfade_offset``;
* audio       : narration A / sfx / narration B delayed to their phase offsets
                with a 10 ms ``afade`` (anti-click) and mixed ``normalize=0``.

Output uses the R1 encode parameters so segments concat losslessly (R5).

There are NO hardcoded second-values here — every duration comes from
``app.pipeline.timing`` (CLAUDE.md #4). All timing fed to ffmpeg is snapped to
the frame grid via :func:`timing.quantize` so the golden test lands within
±1 frame.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from app.pipeline import timing as T
from app.pipeline.timing import SegmentTiming

# --------------------------------------------------------------------------- #
# R1 — global encode parameters (ffmpeg-recipes R1). Single source for both the
# segment renderer and the assembler so concat stays lossless.
# --------------------------------------------------------------------------- #
FPS = T.FPS
R1_VIDEO = [
    "-r", str(FPS),
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "18",
    "-pix_fmt", "yuv420p",
]
R1_AUDIO = [
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "48000",
    "-ac", "2",
]
R1_MUX = ["-movflags", "+faststart"]

# Anti-click micro-fade applied to every mixed audio source (03-spec §7.3).
_AFADE_S = 0.010

# Scale endpoints for the silhouette's entry zoom (03-spec §2: 0.95 -> 1.0).
_ENTRY_SCALE_START = 0.95
_ENTRY_SCALE_END = 1.0

# Placement ratios (03-VIDEO-SPEC §3) — *spatial* fractions of the canvas, NOT
# durations, so they legitimately live here rather than in timing.py.
_MAX_H_RATIO = 0.70   # max height = 70 % of canvas height (756 px @ 1080)
_MAX_W_RATIO = 0.60   # max width  = 60 % of canvas width  (1152 px @ 1920)
_BASELINE_RATIO = 0.78  # the subject's baseline sits at ~78 % of canvas height


class SegmentRenderError(RuntimeError):
    """Raised with a Hungarian message when the ffmpeg render fails."""


def _even(value: float) -> int:
    """Round to the nearest even integer >= 2 (libx264 needs even dimensions)."""

    return max((int(round(value)) // 2) * 2, 2)


def _ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise SegmentRenderError(
            "Az ffmpeg nem található a PATH-on — telepítsd vagy add a PATH-hoz."
        )
    return exe


# --------------------------------------------------------------------------- #
# Geometry — computed ONCE from the cutout's alpha bbox (CONTRACTS §11). We do
# NOT import cutout.py; we read the alpha channel directly with PIL.
# --------------------------------------------------------------------------- #
class Placement:
    """Shared scale + overlay geometry for the silhouette and the cutout.

    ``scaled_w`` / ``scaled_h`` are the EVEN dimensions the whole PNG is scaled
    to. ``x`` / ``y`` are the top-left overlay coordinates on the canvas. The
    silhouette and the cutout get identical values so the reveal does not jump.
    """

    def __init__(self, scaled_w: int, scaled_h: int, x: int, y: int) -> None:
        self.scaled_w = scaled_w
        self.scaled_h = scaled_h
        self.x = x
        self.y = y


def _compute_placement(cutout: Path, canvas: tuple[int, int]) -> Placement:
    """Derive :class:`Placement` from the cutout's opaque-pixel bounding box.

    The opaque content is fitted aspect-preserving into the ``(max_w, max_h)``
    box; the whole image is then scaled by that single factor. The image is
    centred horizontally by its content, and its content baseline is placed at
    ``_BASELINE_RATIO`` of the canvas height.
    """

    from PIL import Image

    canvas_w, canvas_h = canvas
    with Image.open(cutout) as im:
        im = im.convert("RGBA")
        img_w, img_h = im.size
        bbox = im.getchannel("A").getbbox()
    if bbox is None:
        # Fully transparent cutout — treat the whole frame as content so we
        # still produce a (blank) segment rather than crashing.
        bbox = (0, 0, img_w, img_h)
    left, top, right, bottom = bbox
    content_w = max(right - left, 1)
    content_h = max(bottom - top, 1)

    max_h = _MAX_H_RATIO * canvas_h
    max_w = _MAX_W_RATIO * canvas_w
    scale = min(max_w / content_w, max_h / content_h)

    scaled_w = _even(img_w * scale)
    scaled_h = _even(img_h * scale)

    # Opaque content position inside the *scaled* image.
    content_left_scaled = left * scale
    content_top_scaled = top * scale
    content_w_scaled = content_w * scale
    content_h_scaled = content_h * scale

    # Horizontal centre: centre the opaque content on the canvas centreline.
    content_centre_x = content_left_scaled + content_w_scaled / 2.0
    x = int(round(canvas_w / 2.0 - content_centre_x))

    # Vertical baseline: the bottom of the opaque content sits at the baseline.
    baseline_y = _BASELINE_RATIO * canvas_h
    content_bottom_scaled = content_top_scaled + content_h_scaled
    y = int(round(baseline_y - content_bottom_scaled))

    return Placement(scaled_w, scaled_h, x, y)


# --------------------------------------------------------------------------- #
# Filtergraph construction.
# --------------------------------------------------------------------------- #
def _hex_to_ffmpeg_color(hex_color: str) -> str:
    """Convert ``#RRGGBB`` to ffmpeg ``0xRRGGBB`` (lavfi ``color`` source)."""

    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise SegmentRenderError(f"Érvénytelen háttérszín: {hex_color!r} (várt: #RRGGBB).")
    return f"0x{h.upper()}"


def _build_filtergraph(
    *,
    has_background: bool,
    has_sfx: bool,
    placement: Placement,
    timing: SegmentTiming,
    canvas: tuple[int, int],
    bg_color: str,
) -> tuple[str, str, str]:
    """Return ``(filter_complex, video_label, audio_label)``.

    Input index layout (the caller adds ``-i`` in this exact order):
        0: background image (only when ``has_background``)
        then: silhouette, cutout, narration_a, [sfx if has_sfx], narration_b
    """

    canvas_w, canvas_h = canvas

    # Frame-quantized durations — every value snaps to the 30 fps grid so the
    # golden test lands within ±1 frame.
    q = T.quantize
    total = q(timing.total)
    sil_section = q(timing.sil_section)
    rev_section = q(timing.rev_section)
    entry = q(timing.entry)
    reveal = q(timing.reveal)
    xfade_offset = q(timing.xfade_offset)

    narr_a_at = q(timing.narr_a_at)
    sfx_at = q(timing.sfx_at)
    narr_b_at = q(timing.narr_b_at)

    sw, sh = placement.scaled_w, placement.scaled_h
    x, y = placement.x, placement.y

    parts: list[str] = []

    # Input index bookkeeping.
    idx = 0
    if has_background:
        bg_in = idx
        idx += 1
    sil_in = idx
    idx += 1
    cut_in = idx
    idx += 1
    narr_a_in = idx
    idx += 1
    if has_sfx:
        sfx_in = idx
        idx += 1
    narr_b_in = idx
    idx += 1

    # --- background canvas (full total length) ----------------------------- #
    if has_background:
        # Image loop input -> scale/cover to canvas, set fps, trim to total.
        parts.append(
            f"[{bg_in}:v]"
            f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,"
            f"crop={canvas_w}:{canvas_h},"
            f"fps={FPS},format=rgba,trim=duration={total:.6f},setpts=PTS-STARTPTS"
            f"[bg]"
        )
    else:
        parts.append(
            f"color=c={_hex_to_ffmpeg_color(bg_color)}:s={canvas_w}x{canvas_h}:"
            f"r={FPS}:d={total:.6f},format=rgba[bg]"
        )

    # The background is reused for both the silhouette and the reveal section,
    # so split it into two independent streams.
    parts.append("[bg]split=2[bg_sil][bg_rev]")

    # --- silhouette layer -------------------------------------------------- #
    # Scaled to the shared placement size, then animated: a per-frame zoom from
    # 0.95 -> 1.0 over the entry phase (held at 1.0 afterwards) plus a fade-in.
    # zoompan keeps the layer the same canvas size; we centre the zoom on the
    # placement box. The fade alpha-fades the silhouette in over ``entry``.
    parts.append(
        f"[{sil_in}:v]"
        f"format=rgba,"
        f"scale={sw}:{sh},"
        f"loop=loop=-1:size=1:start=0,fps={FPS},trim=duration={sil_section:.6f},"
        f"setpts=PTS-STARTPTS,"
        # entry zoom 0.95 -> 1.0: scale the layer by an animated factor.
        f"scale="
        f"w='iw*({_ENTRY_SCALE_START}+({_ENTRY_SCALE_END}-{_ENTRY_SCALE_START})"
        f"*min(t/{entry:.6f}\\,1))':"
        f"h='ih*({_ENTRY_SCALE_START}+({_ENTRY_SCALE_END}-{_ENTRY_SCALE_START})"
        f"*min(t/{entry:.6f}\\,1))':"
        f"eval=frame,"
        f"fade=t=in:st=0:d={entry:.6f}:alpha=1"
        f"[sil_layer]"
    )
    # Overlay the silhouette on its background copy. The animated scale changes
    # the layer size, so we recompute x/y to keep the placement box centred at
    # (x + sw/2, y + sh/2): overlay x = box_centre_x - W/2, y = box_centre_y-H/2.
    box_cx = x + sw / 2.0
    box_cy = y + sh / 2.0
    parts.append(
        f"[bg_sil][sil_layer]"
        f"overlay=x='{box_cx:.3f}-w/2':y='{box_cy:.3f}-h/2':eval=frame:format=auto"
        f"[sil_full]"
    )

    # --- cutout (reveal) layer -------------------------------------------- #
    parts.append(
        f"[{cut_in}:v]"
        f"format=rgba,"
        f"scale={sw}:{sh},"
        f"loop=loop=-1:size=1:start=0,fps={FPS},trim=duration={rev_section:.6f},"
        f"setpts=PTS-STARTPTS"
        f"[cut_layer]"
    )
    parts.append(
        f"[bg_rev][cut_layer]"
        f"overlay=x={x}:y={y}:format=auto"
        f"[rev_full]"
    )

    # --- xfade the two visual sections ------------------------------------ #
    # The silhouette section ends at sil_section; the reveal section starts at
    # the crossfade. xfade offset = xfade_offset, duration = reveal. Both inputs
    # must share fps/format. After xfade, flatten alpha to yuv420p (R1).
    parts.append(
        f"[sil_full][rev_full]"
        f"xfade=transition=fade:duration={reveal:.6f}:offset={xfade_offset:.6f},"
        f"format=yuv420p,fps={FPS}"
        f"[vout]"
    )
    video_label = "[vout]"

    # --- audio mix --------------------------------------------------------- #
    # Each source: pad/format to stereo 48k, delay to its phase offset, apply a
    # 10 ms in/out micro-fade against clicks, then amix with normalize=0.
    afade_ms = _AFADE_S

    def _audio_branch(in_idx: int, label: str, delay_s: float) -> str:
        delay_ms = int(round(delay_s * 1000))
        return (
            f"[{in_idx}:a]"
            f"aformat=sample_rates=48000:channel_layouts=stereo,"
            f"afade=t=in:st=0:d={afade_ms},"
            f"areverse,afade=t=in:st=0:d={afade_ms},areverse,"
            f"adelay={delay_ms}|{delay_ms}:all=1"
            f"[{label}]"
        )

    audio_labels: list[str] = []
    parts.append(_audio_branch(narr_a_in, "a_a", narr_a_at))
    audio_labels.append("[a_a]")
    if has_sfx:
        parts.append(_audio_branch(sfx_in, "a_sfx", sfx_at))
        audio_labels.append("[a_sfx]")
    parts.append(_audio_branch(narr_b_in, "a_b", narr_b_at))
    audio_labels.append("[a_b]")

    n = len(audio_labels)
    # amix mixes to the longest input; pad to total then trim so the audio track
    # exactly matches the video length (the video is the master).
    parts.append(
        "".join(audio_labels)
        + f"amix=inputs={n}:normalize=0:dropout_transition=0,"
        + f"apad,atrim=duration={total:.6f},"
        + "aformat=sample_rates=48000:channel_layouts=stereo"
        + "[aout]"
    )
    audio_label = "[aout]"

    return ";".join(parts), video_label, audio_label


def render_segment(
    *,
    background: Path | None,
    silhouette: Path,
    cutout: Path,
    narration_a: Path,
    sfx: Path | None,
    narration_b: Path,
    out_path: Path,
    timing: SegmentTiming,
    canvas: tuple[int, int] = (1920, 1080),
    bg_color: str = "#EAF4FF",
) -> None:
    """Render one item segment to ``out_path`` (R4 filtergraph, R1 encode).

    All paths are read-only inputs; only ``out_path`` (and its parent) is
    written. Raises :class:`SegmentRenderError` (Hungarian message) on failure.
    """

    silhouette = Path(silhouette)
    cutout = Path(cutout)
    narration_a = Path(narration_a)
    narration_b = Path(narration_b)
    out_path = Path(out_path)
    background = Path(background) if background is not None else None
    sfx = Path(sfx) if sfx is not None else None

    for required in (silhouette, cutout, narration_a, narration_b):
        if not required.exists():
            raise SegmentRenderError(f"Hiányzó bemeneti fájl: {required}")
    if background is not None and not background.exists():
        raise SegmentRenderError(f"Hiányzó háttérkép: {background}")
    if sfx is not None and not sfx.exists():
        raise SegmentRenderError(f"Hiányzó hangeffekt: {sfx}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    has_background = background is not None
    has_sfx = sfx is not None
    placement = _compute_placement(cutout, canvas)

    filter_complex, video_label, audio_label = _build_filtergraph(
        has_background=has_background,
        has_sfx=has_sfx,
        placement=placement,
        timing=timing,
        canvas=canvas,
        bg_color=bg_color,
    )

    total = T.quantize(timing.total)

    cmd: list[str] = [_ffmpeg_bin(), "-y"]
    # Inputs in the exact order the filtergraph indexes them.
    if has_background:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.6f}", "-i", str(background)]
    cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(silhouette)]
    cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(cutout)]
    cmd += ["-i", str(narration_a)]
    if has_sfx:
        cmd += ["-i", str(sfx)]
    cmd += ["-i", str(narration_b)]

    cmd += [
        "-filter_complex", filter_complex,
        "-map", video_label,
        "-map", audio_label,
    ]
    cmd += R1_VIDEO + R1_AUDIO + R1_MUX
    # The video stream is already trimmed to ``total``; cap the mux defensively.
    cmd += ["-t", f"{total:.6f}", str(out_path)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise SegmentRenderError(
            "A szegmens renderelése nem sikerült (ffmpeg). "
            f"Az ffmpeg hibakimenete:\n{tail}"
        )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise SegmentRenderError(
            f"A render lefutott, de a kimeneti fájl üres vagy hiányzik: {out_path}"
        )


# --------------------------------------------------------------------------- #
# Cache key for meta.json (CONTRACTS §11, 01-BLUEPRINT §6.3).
# --------------------------------------------------------------------------- #
def _file_digest(path: Path | None) -> str:
    """Return a short content hash for ``path`` (or ``"-"`` when None/missing)."""

    if path is None:
        return "-"
    p = Path(path)
    if not p.exists():
        return "-"
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def segment_inputs_hash(
    *,
    background: Path | None,
    silhouette: Path,
    cutout: Path,
    narration_a: Path,
    sfx: Path | None,
    narration_b: Path,
    timing: SegmentTiming,
    canvas: tuple[int, int] = (1920, 1080),
    bg_color: str = "#EAF4FF",
) -> str:
    """Stable cache key over the render inputs (file content + timing + params).

    Stored in ``meta.json``; a changed key means the segment must re-render
    (assemble.needs_rerender). Quantized timing is used so a sub-frame jitter in
    measured durations does not needlessly invalidate the cache.
    """

    q = T.quantize
    parts = [
        f"bg:{_file_digest(background)}",
        f"sil:{_file_digest(silhouette)}",
        f"cut:{_file_digest(cutout)}",
        f"na:{_file_digest(narration_a)}",
        f"sfx:{_file_digest(sfx)}",
        f"nb:{_file_digest(narration_b)}",
        f"canvas:{canvas[0]}x{canvas[1]}",
        f"color:{bg_color.upper() if background is None else '-'}",
        # Frame-quantized phase durations (the only timing the render depends on).
        f"entry:{q(timing.entry):.6f}",
        f"riddle:{q(timing.riddle):.6f}",
        f"beat:{q(timing.beat):.6f}",
        f"sfxd:{q(timing.sfx):.6f}",
        f"reveal:{q(timing.reveal):.6f}",
        f"naming:{q(timing.naming):.6f}",
        f"hold:{q(timing.hold):.6f}",
        f"fps:{FPS}",
    ]
    blob = "|".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
