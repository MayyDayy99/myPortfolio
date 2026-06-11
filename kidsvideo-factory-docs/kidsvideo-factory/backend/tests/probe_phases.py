"""ffprobe helpers for the segment golden test (CONTRACTS §11, §19).

These functions wrap ``ffprobe`` so the golden test can assert phase boundaries
and the total duration to within ±1 frame, plus the basic stream format. They
contain NO hardcoded second-values — the test compares against ``timing.py``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.pipeline import timing as T


class ProbeError(RuntimeError):
    """Raised when ffprobe is missing or returns an error."""


def _ffprobe_bin() -> str:
    exe = shutil.which("ffprobe")
    if exe is None:  # pragma: no cover - environment guard
        raise ProbeError("Az ffprobe nem található a PATH-on.")
    return exe


def _run_ffprobe(args: list[str]) -> str:
    proc = subprocess.run(
        [_ffprobe_bin(), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        raise ProbeError(f"ffprobe hiba:\n{tail}")
    return proc.stdout


def probe_format(path: Path) -> dict:
    """Return the full ffprobe ``format`` + ``streams`` JSON for ``path``."""

    out = _run_ffprobe(
        [
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    return json.loads(out)


def total_duration(path: Path) -> float:
    """Container duration in seconds (the segment's total length)."""

    out = _run_ffprobe(
        [
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(path),
        ]
    )
    text = out.strip()
    if not text:
        raise ProbeError(f"Nem olvasható időtartam: {path}")
    return float(text)


def video_stream(info: dict) -> dict:
    """Return the first video stream dict from a :func:`probe_format` result."""

    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    raise ProbeError("Nincs videó-stream a fájlban.")


def audio_stream(info: dict) -> dict | None:
    """Return the first audio stream dict, or ``None`` if there is none."""

    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            return stream
    return None


def has_audio_stream(info: dict) -> bool:
    """True if the file contains at least one audio stream."""

    return audio_stream(info) is not None


def frame_rate(info: dict) -> float:
    """Average frame rate of the first video stream as a float."""

    stream = video_stream(info)
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    num, _, den = rate.partition("/")
    den_f = float(den) if den else 1.0
    if den_f == 0:
        return 0.0
    return float(num) / den_f


def dimensions(info: dict) -> tuple[int, int]:
    """``(width, height)`` of the first video stream."""

    stream = video_stream(info)
    return int(stream["width"]), int(stream["height"])


def pixel_format(info: dict) -> str:
    """Pixel format of the first video stream (e.g. ``yuv420p``)."""

    return str(video_stream(info).get("pix_fmt", ""))


def frames_of(seconds: float) -> int:
    """Convenience: whole frames for ``seconds`` at the project FPS."""

    return T.frames(seconds)


def within_one_frame(measured: float, expected: float) -> bool:
    """True if ``measured`` and ``expected`` differ by <= one frame (+ epsilon)."""

    return abs(measured - expected) <= (1.0 / T.FPS) + 1e-6
