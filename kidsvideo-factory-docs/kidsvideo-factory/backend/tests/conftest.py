"""Shared pytest fixtures and asset factories.

The autouse ``isolated_data_dir`` fixture forces ``DATA_DIR`` to a per-test tmp
directory and resets cached state (settings + db connection) so NO test ever
touches a real ``/data``. Reusable factories build synthetic PNGs (PIL) and
WAVs (ffmpeg) for the pipeline tests; ``ffmpeg_available`` / ``requires_ffmpeg``
let ffmpeg-dependent tests skip cleanly when ffmpeg is absent.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# Isolation: redirect DATA_DIR to a tmp path and reset cached singletons.
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point DATA_DIR at a fresh tmp dir and reset settings + db per test."""

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    # Import lazily so the env var is set before anything reads it, and clear
    # the cached settings + any open db connection from a previous test.
    from app import db
    from app.config import get_settings

    get_settings.cache_clear()
    db.reset_connection()

    yield data_dir

    # Tear down: drop the connection so WAL files are released before tmp_path
    # is cleaned up, and clear the settings cache for the next test.
    db.reset_connection()
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# ffmpeg availability
# --------------------------------------------------------------------------- #
def ffmpeg_available() -> bool:
    """True if both ffmpeg and ffprobe are on PATH."""

    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


# Decorator other test modules can apply: ``@requires_ffmpeg``.
requires_ffmpeg = pytest.mark.skipif(
    not ffmpeg_available(), reason="ffmpeg/ffprobe not available on PATH"
)


@pytest.fixture
def has_ffmpeg() -> bool:
    """Fixture form of :func:`ffmpeg_available`."""

    return ffmpeg_available()


# --------------------------------------------------------------------------- #
# Asset factories
# --------------------------------------------------------------------------- #
def _make_png(path: Path, size: tuple[int, int], color: tuple[int, int, int, int]) -> Path:
    """Write an RGBA PNG of ``size`` filled with ``color``."""

    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", size, color)
    img.save(path, "PNG")
    return path


def _make_wav(path: Path, seconds: float, freq: int = 440, rate: int = 48000) -> Path:
    """Generate a mono sine WAV of ``seconds`` length via ffmpeg."""

    if not ffmpeg_available():
        pytest.skip("ffmpeg not available to synthesize WAV")
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={freq}:duration={seconds}:sample_rate={rate}",
        "-ac",
        "1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg WAV generation failed:\n{proc.stderr[-500:]}")
    return path


@pytest.fixture
def make_png():
    """Return the PNG factory ``make_png(path, size=(w,h), color=(r,g,b,a))``."""

    def factory(
        path: Path,
        size: tuple[int, int] = (256, 256),
        color: tuple[int, int, int, int] = (255, 0, 0, 255),
    ) -> Path:
        return _make_png(path, size, color)

    return factory


@pytest.fixture
def make_wav():
    """Return the WAV factory ``make_wav(path, seconds, freq=440, rate=48000)``."""

    def factory(path: Path, seconds: float, freq: int = 440, rate: int = 48000) -> Path:
        return _make_wav(path, seconds, freq, rate)

    return factory
