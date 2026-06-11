"""Audio cleanup pipeline (P2) — real ffmpeg (CONTRACTS §10).

Implements the canonical ffmpeg recipes:

* ``clean_narration`` runs the **R2** narration-cleanup chain (48k mono ->
  highpass -> afftdn denoise -> leading/trailing silence trim -> loudnorm
  ``I=-16:TP=-1.5:LRA=11``) and returns the parsed ``loudnorm`` JSON report so
  the caller can write it into the job log (03-VIDEO-SPEC §7.2 acceptance).
* ``normalize_sfx`` runs the **R3** one-shot SFX normalization
  (``loudnorm I=-18``), ~2 dB quieter than narration (03-VIDEO-SPEC §4).
* ``duration_seconds`` queries ffprobe for the media duration in seconds.

All loudness/dramaturgy *second* values live in ``pipeline/timing.py`` and the
03-VIDEO-SPEC; the only literals here are the **R2/R3 ffmpeg recipe knobs**
(filter coefficients and silence thresholds copied verbatim from the
ffmpeg-recipes skill), which are encoding parameters, not segment dramaturgy.

ffmpeg/ffprobe are taken from PATH. Every subprocess call checks the return
code and raises a Hungarian-language error that includes the last lines of the
ffmpeg stderr. The functions are idempotent: re-running over an existing output
simply overwrites it (``ffmpeg -y``), so the result never degrades.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

# --------------------------------------------------------------------------- #
# Loudness targets (03-VIDEO-SPEC §4) — these are loudness levels in LUFS/dB,
# NOT dramaturgy seconds, so they belong with the R2/R3 recipes, not timing.py.
# --------------------------------------------------------------------------- #
_NARRATION_TARGET_I = -16  # LUFS — YouTube-friendly speech loudness.
_SFX_TARGET_I = -18        # LUFS — ~2 dB quieter than narration.
_TARGET_TP = -1.5          # dBTP — true-peak ceiling.
_TARGET_LRA = 11           # LU — loudness range.

# Working sample rate (03-VIDEO-SPEC §4: 48 kHz working format).
_SAMPLE_RATE = 48000

# How many trailing stderr lines to surface in an error message.
_STDERR_TAIL_LINES = 12


# --------------------------------------------------------------------------- #
# R2 — narration cleanup filter chain.
#
# Recipe knobs (ffmpeg-recipes R2, copied verbatim):
#   highpass f=80          — remove sub-bass rumble.
#   afftdn nr=12:nf=-30    — FFT denoise.
#   silenceremove ...      — trim leading/trailing silence below -45 dB,
#                            keeping 0.15 s of air in front and 0.25 s behind
#                            (the areverse trick mirrors the front trim onto
#                            the tail). These 0.15/0.25 values are silence-gate
#                            air windows, not segment dramaturgy.
#   loudnorm ...           — single-pass loudness normalization with a JSON
#                            measurement report on stderr.
# --------------------------------------------------------------------------- #
_R2_FILTER = (
    f"aformat=sample_rates={_SAMPLE_RATE}:channel_layouts=mono,"
    "highpass=f=80,"
    "afftdn=nr=12:nf=-30,"
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.25,"
    "areverse,"
    f"loudnorm=I={_NARRATION_TARGET_I}:TP={_TARGET_TP}:LRA={_TARGET_LRA}"
    ":print_format=json"
)

# R3 — SFX normalization (stereo working layout, quieter target).
_R3_FILTER = (
    f"aformat=sample_rates={_SAMPLE_RATE}:channel_layouts=stereo,"
    f"loudnorm=I={_SFX_TARGET_I}:TP={_TARGET_TP}:LRA={_TARGET_LRA}"
)


def _stderr_tail(stderr: str) -> str:
    """Return the last few non-empty lines of an ffmpeg stderr blob."""

    lines = [ln for ln in stderr.splitlines() if ln.strip()]
    return "\n".join(lines[-_STDERR_TAIL_LINES:])


def _run_checked(cmd: list[str], *, action: str) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` and raise a Hungarian error (with stderr tail) on failure.

    ``action`` is a short Hungarian noun phrase describing what failed, e.g.
    ``"A narráció tisztítása"``.
    """

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        # ffmpeg/ffprobe is not on PATH.
        raise RuntimeError(
            f"{action} nem sikerült: a(z) '{cmd[0]}' nem található a PATH-on. "
            "Telepítve van az ffmpeg?"
        ) from exc

    if proc.returncode != 0:
        tail = _stderr_tail(proc.stderr)
        raise RuntimeError(
            f"{action} nem sikerült (ffmpeg kód {proc.returncode}).\n"
            f"Az ffmpeg utolsó sorai:\n{tail}"
        )
    return proc


def _parse_loudnorm_report(stderr: str) -> dict:
    """Extract the ``loudnorm`` ``print_format=json`` block from ffmpeg stderr.

    ffmpeg prints the JSON report after the ``[Parsed_loudnorm_...]`` marker as
    a pretty-printed object. We grab the first balanced ``{...}`` block and
    parse it.
    """

    start = stderr.find("{")
    if start == -1:
        raise RuntimeError(
            "A loudnorm riport nem található az ffmpeg kimenetében "
            "(hiányzó JSON blokk).\n"
            f"Az ffmpeg utolsó sorai:\n{_stderr_tail(stderr)}"
        )

    # Walk braces to find the matching close for a balanced JSON object.
    depth = 0
    end = -1
    for idx in range(start, len(stderr)):
        ch = stderr[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    if end == -1:
        raise RuntimeError(
            "A loudnorm JSON riport csonka az ffmpeg kimenetében.\n"
            f"Az ffmpeg utolsó sorai:\n{_stderr_tail(stderr)}"
        )

    block = stderr[start:end]
    try:
        report = json.loads(block)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"A loudnorm JSON riport nem értelmezhető: {exc}.\n"
            f"Nyers blokk:\n{block}"
        ) from exc

    if "input_i" not in report or "output_i" not in report:
        raise RuntimeError(
            "A loudnorm riport hiányos (nincs 'input_i'/'output_i' kulcs).\n"
            f"Riport: {report}"
        )
    return report


def clean_narration(raw_path: Path, clean_path: Path) -> dict:
    """Clean a raw narration recording into a 48 kHz mono ``*.clean.wav``.

    Runs the R2 chain and returns the parsed ``loudnorm`` measurement report
    (a dict containing ``input_i``, ``output_i``, ``input_tp`` … keys). The
    caller is expected to write this report into the job log. Idempotent:
    re-running overwrites ``clean_path``.
    """

    raw_path = Path(raw_path)
    clean_path = Path(clean_path)
    if not raw_path.is_file():
        raise RuntimeError(
            f"A narráció tisztítása nem sikerült: a bemeneti fájl nem létezik: {raw_path}"
        )
    clean_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-af",
        _R2_FILTER,
        "-ar",
        str(_SAMPLE_RATE),
        "-ac",
        "1",
        str(clean_path),
    ]
    proc = _run_checked(cmd, action="A narráció tisztítása")
    return _parse_loudnorm_report(proc.stderr)


def normalize_sfx(raw_path: Path, out_path: Path) -> None:
    """Normalize an SFX file to the R3 target (48 kHz stereo, I=-18 LUFS).

    Idempotent: re-running overwrites ``out_path``.
    """

    raw_path = Path(raw_path)
    out_path = Path(out_path)
    if not raw_path.is_file():
        raise RuntimeError(
            f"Az SFX normalizálása nem sikerült: a bemeneti fájl nem létezik: {raw_path}"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-af",
        _R3_FILTER,
        "-ar",
        str(_SAMPLE_RATE),
        str(out_path),
    ]
    _run_checked(cmd, action="Az SFX normalizálása")


def duration_seconds(path: Path) -> float:
    """Return the media duration of ``path`` in seconds via ffprobe."""

    path = Path(path)
    if not path.is_file():
        raise RuntimeError(
            f"A hossz lekérdezése nem sikerült: a fájl nem létezik: {path}"
        )

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
    proc = _run_checked(cmd, action="A hossz lekérdezése")

    raw = proc.stdout.strip()
    # ffprobe can emit "N/A" for streams without a known duration.
    match = re.search(r"[-+]?\d*\.?\d+", raw)
    if not match:
        raise RuntimeError(
            f"A hossz lekérdezése nem sikerült: az ffprobe nem adott számot ({raw!r})."
        )
    return float(match.group(0))
