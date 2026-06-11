"""Tests for ``pipeline.timing`` against 03-VIDEO-SPEC §2 (CONTRACTS §7).

No second-values are duplicated here: every expectation is derived from the
constants exported by ``timing`` itself, so the test tracks the single source
of truth.
"""

from __future__ import annotations

import math

import pytest

from app.pipeline import timing as T


def _approx(value: float) -> pytest.approx:
    return pytest.approx(value, abs=1e-9)


def test_constants_and_fps() -> None:
    assert T.FPS == 30
    # Sanity: the fixed-phase constants exist and are positive.
    for name in ("ENTRY", "BEAT", "REVEAL", "HOLD", "INTRO", "OUTRO"):
        assert getattr(T, name) > 0


def test_compute_timing_derivations() -> None:
    len_a, len_sfx, len_b = 2.0, 0.5, 1.5
    t = T.compute_timing(len_a, len_sfx, len_b)

    assert t.entry == _approx(T.ENTRY)
    assert t.riddle == _approx(len_a + T.RIDDLE_PAD)
    assert t.beat == _approx(T.BEAT)
    # len_sfx below SFX_MIN clamps up to SFX_MIN.
    assert t.sfx == _approx(T.SFX_MIN)
    assert t.reveal == _approx(T.REVEAL)
    assert t.naming == _approx(len_b + T.NAMING_PAD)
    assert t.hold == _approx(T.HOLD)


def test_sfx_takes_max_when_longer() -> None:
    t = T.compute_timing(1.0, 3.0, 1.0)
    assert t.sfx == _approx(3.0)


def test_total_equals_phase_sum() -> None:
    t = T.compute_timing(2.0, 2.0, 1.5)
    phase_sum = t.entry + t.riddle + t.beat + t.sfx + t.reveal + t.naming + t.hold
    assert t.total == _approx(phase_sum)


def test_section_and_offset_consistency() -> None:
    t = T.compute_timing(2.0, 1.0, 1.0)

    # Silhouette is visible up to the END of the reveal crossfade.
    assert t.sil_section == _approx(t.entry + t.riddle + t.beat + t.sfx + t.reveal)
    # Cutout is visible from the START of the reveal crossfade.
    assert t.rev_section == _approx(t.reveal + t.naming + t.hold)
    # Crossfade begins after entry+riddle+beat+sfx.
    assert t.xfade_offset == _approx(t.entry + t.riddle + t.beat + t.sfx)
    # total == xfade_offset + reveal + naming + hold.
    assert t.total == _approx(t.xfade_offset + t.reveal + t.naming + t.hold)

    # The silhouette section ends exactly where the reveal section's crossfade
    # ends: xfade_offset + reveal.
    assert t.sil_section == _approx(t.xfade_offset + t.reveal)
    # The two sections overlap by exactly the reveal duration.
    assert t.sil_section + t.rev_section == _approx(t.total + t.reveal)


def test_audio_offsets() -> None:
    t = T.compute_timing(2.0, 1.0, 1.0)
    assert t.narr_a_at == _approx(t.entry)
    assert t.sfx_at == _approx(t.entry + t.riddle + t.beat)
    assert t.narr_b_at == _approx(t.xfade_offset + t.reveal)
    # narration B starts exactly when the silhouette section ends.
    assert t.narr_b_at == _approx(t.sil_section)
    # Offsets are monotonically increasing.
    assert t.narr_a_at < t.sfx_at < t.narr_b_at < t.total


def test_frames_rounds_to_30fps() -> None:
    assert T.frames(1.0) == 30
    assert T.frames(0.5) == 15
    assert T.frames(0.8) == 24
    # round() half-to-even at the frame boundary.
    assert T.frames(1.0 / 30) == 1
    assert T.frames(0.0) == 0


def test_quantize_snaps_to_frame_grid() -> None:
    # 0.8 s is exactly 24 frames -> unchanged.
    assert T.quantize(0.8) == _approx(0.8)
    # An off-grid value snaps to the nearest frame.
    q = T.quantize(0.81)
    assert q == _approx(T.frames(0.81) / T.FPS)
    # Every quantized value is an exact multiple of one frame.
    frame = 1.0 / T.FPS
    assert math.isclose((q / frame) - round(q / frame), 0.0, abs_tol=1e-9)


def test_quantized_total_within_one_frame() -> None:
    t = T.compute_timing(2.0, 1.7, 1.3)
    # The renderer snaps each phase; the quantized total must be within ±1 frame
    # of the raw total.
    quant_total = (
        T.quantize(t.entry)
        + T.quantize(t.riddle)
        + T.quantize(t.beat)
        + T.quantize(t.sfx)
        + T.quantize(t.reveal)
        + T.quantize(t.naming)
        + T.quantize(t.hold)
    )
    assert abs(quant_total - t.total) <= (1.0 / T.FPS) + 1e-9
