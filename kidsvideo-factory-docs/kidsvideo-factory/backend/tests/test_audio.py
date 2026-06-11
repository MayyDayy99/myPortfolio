"""Tests for the audio cleanup pipeline (CONTRACTS §10) — real ffmpeg.

These tests synthesize WAVs with ffmpeg (sine + anoisesrc) in a tmp dir, run
the R2/R3 chains for real, and probe the results with ffprobe. They require
ffmpeg/ffprobe on PATH (present on the dev box) and skip cleanly otherwise.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.pipeline import audio
from tests.conftest import requires_ffmpeg


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _synthesize_noisy_speech(path: Path, seconds: float = 2.0) -> Path:
    """Create a synthetic "noisy narration" WAV (sine tone mixed with noise).

    Uses ffmpeg lavfi: a 220 Hz sine stands in for voice, ``anoisesrc`` adds
    broadband hiss the R2 chain should clean up. Stereo/44.1k on purpose so the
    chain has real format conversion + denoise + silence-trim work to do.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=220:duration={seconds}:sample_rate=44100",
        "-f",
        "lavfi",
        "-i",
        f"anoisesrc=amplitude=0.05:duration={seconds}:sample_rate=44100",
        "-filter_complex",
        "[0:a][1:a]amix=inputs=2:normalize=0[out]",
        "-map",
        "[out]",
        "-ac",
        "2",
        "-ar",
        "44100",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"synthetic WAV generation failed:\n{proc.stderr[-500:]}")
    return path


def _probe_audio(path: Path) -> dict[str, str]:
    """Return {channels, sample_rate, codec_name} for the first audio stream."""

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=channels,sample_rate,codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=0",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    info: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            info[key.strip()] = value.strip()
    return info


# --------------------------------------------------------------------------- #
# clean_narration — the headline R2 test (contract-mandated assertions)
# --------------------------------------------------------------------------- #
@requires_ffmpeg
def test_clean_narration_produces_mono_48k_and_loudnorm_report(tmp_path: Path) -> None:
    raw = _synthesize_noisy_speech(tmp_path / "narration_a.wav", seconds=2.0)
    clean = tmp_path / "narration_a.clean.wav"

    report = audio.clean_narration(raw, clean)

    # Output exists and is non-empty.
    assert clean.is_file()
    assert clean.stat().st_size > 0

    # ffprobe reports mono, 48000 Hz.
    info = _probe_audio(clean)
    assert info["channels"] == "1"
    assert info["sample_rate"] == "48000"

    # The parsed loudnorm report contains the required measurement keys.
    assert "input_i" in report
    assert "output_i" in report
    # And the values are parseable as floats (real measurements, not "N/A").
    float(report["input_i"])
    float(report["output_i"])


@requires_ffmpeg
def test_clean_narration_with_sine_only_input(tmp_path: Path, make_wav) -> None:
    # A plain sine WAV (the shared fixture) also runs through the chain cleanly.
    raw = make_wav(tmp_path / "sine.wav", seconds=1.5, freq=330, rate=44100)
    clean = tmp_path / "sine.clean.wav"

    report = audio.clean_narration(raw, clean)

    assert clean.is_file()
    info = _probe_audio(clean)
    assert info["channels"] == "1"
    assert info["sample_rate"] == "48000"
    assert "input_i" in report and "output_i" in report


@requires_ffmpeg
def test_clean_narration_is_idempotent(tmp_path: Path) -> None:
    raw = _synthesize_noisy_speech(tmp_path / "raw.wav", seconds=1.0)
    clean = tmp_path / "out.clean.wav"

    audio.clean_narration(raw, clean)
    assert clean.is_file()

    # Re-running over an existing output overwrites it and still returns a report.
    report2 = audio.clean_narration(raw, clean)
    assert clean.is_file()
    assert "input_i" in report2 and "output_i" in report2
    info = _probe_audio(clean)
    assert info["channels"] == "1"
    assert info["sample_rate"] == "48000"


# --------------------------------------------------------------------------- #
# normalize_sfx — R3
# --------------------------------------------------------------------------- #
@requires_ffmpeg
def test_normalize_sfx_produces_stereo_48k(tmp_path: Path, make_wav) -> None:
    raw = make_wav(tmp_path / "sfx_raw.wav", seconds=1.0, freq=600, rate=44100)
    out = tmp_path / "sfx.wav"

    audio.normalize_sfx(raw, out)

    assert out.is_file()
    info = _probe_audio(out)
    assert info["channels"] == "2"
    assert info["sample_rate"] == "48000"


# --------------------------------------------------------------------------- #
# duration_seconds — ffprobe
# --------------------------------------------------------------------------- #
@requires_ffmpeg
def test_duration_seconds_matches_synthesized_length(tmp_path: Path, make_wav) -> None:
    raw = make_wav(tmp_path / "len.wav", seconds=1.5, rate=48000)
    dur = audio.duration_seconds(raw)
    assert dur == pytest.approx(1.5, abs=0.05)


# --------------------------------------------------------------------------- #
# Error handling — Hungarian messages, no live ffmpeg run needed
# --------------------------------------------------------------------------- #
def test_clean_narration_missing_input_raises_hungarian(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="nem létezik"):
        audio.clean_narration(tmp_path / "nope.wav", tmp_path / "out.wav")


def test_normalize_sfx_missing_input_raises_hungarian(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="nem létezik"):
        audio.normalize_sfx(tmp_path / "nope.wav", tmp_path / "out.wav")


def test_duration_seconds_missing_input_raises_hungarian(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="nem létezik"):
        audio.duration_seconds(tmp_path / "nope.wav")


@requires_ffmpeg
def test_clean_narration_bad_input_raises_with_stderr_tail(tmp_path: Path) -> None:
    # A file that is not valid audio: ffmpeg fails, we surface a Hungarian error.
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"this is not audio data at all")
    with pytest.raises(RuntimeError, match="ffmpeg"):
        audio.clean_narration(bad, tmp_path / "out.wav")
