"""Segment timing — the single code source of 03-VIDEO-SPEC §2 (CONTRACTS §7).

There are NO hardcoded second-values anywhere else in the codebase (CLAUDE.md
#4). Every phase length flows from the constants below. The renderer works on
frame-quantized values so the golden test lands within ±1 frame at 30 fps.
"""

from __future__ import annotations

from dataclasses import dataclass

FPS = 30

# Phase constants (03-VIDEO-SPEC §2) — seconds.
ENTRY = 0.8       # 1. entry: silhouette fade + scale-in (0.95 -> 1.0)
RIDDLE_PAD = 0.4  # 2. riddle: len(A) + 0.4
BEAT = 0.4        # 3. beat pause
SFX_MIN = 1.2     # 4. sound effect: max(len(SFX), 1.2)
REVEAL = 0.6      # 5. reveal crossfade (silhouette -> cutout)
NAMING_PAD = 0.5  # 6. naming: len(B) + 0.5
HOLD = 1.2        # 7. hold

XFADE = 0.6       # transition between items (topic settings may override)
INTRO = 4.0
OUTRO = 4.0


@dataclass(frozen=True)
class SegmentTiming:
    """Resolved per-phase durations (seconds) for one item segment."""

    entry: float
    riddle: float
    beat: float
    sfx: float
    reveal: float
    naming: float
    hold: float

    @property
    def sil_section(self) -> float:
        """Visible silhouette span: up to the END of the reveal crossfade."""

        return self.entry + self.riddle + self.beat + self.sfx + self.reveal

    @property
    def rev_section(self) -> float:
        """Visible cutout span: from the START of the reveal crossfade."""

        return self.reveal + self.naming + self.hold

    @property
    def xfade_offset(self) -> float:
        """Time at which the reveal crossfade begins."""

        return self.entry + self.riddle + self.beat + self.sfx

    @property
    def total(self) -> float:
        """Total segment duration."""

        return self.xfade_offset + self.reveal + self.naming + self.hold

    # --- audio offsets (seconds) ---------------------------------------- #
    @property
    def narr_a_at(self) -> float:
        """Start of narration A (the riddle)."""

        return self.entry

    @property
    def sfx_at(self) -> float:
        """Start of the sound effect."""

        return self.entry + self.riddle + self.beat

    @property
    def narr_b_at(self) -> float:
        """Start of narration B (the naming) — at the end of the reveal."""

        return self.xfade_offset + self.reveal


def compute_timing(len_a: float, len_sfx: float, len_b: float) -> SegmentTiming:
    """Build a :class:`SegmentTiming` from measured asset durations (seconds).

    ``riddle = len_a + RIDDLE_PAD``, ``sfx = max(len_sfx, SFX_MIN)``,
    ``naming = len_b + NAMING_PAD``. Fixed phases come from the constants.
    """

    return SegmentTiming(
        entry=ENTRY,
        riddle=len_a + RIDDLE_PAD,
        beat=BEAT,
        sfx=max(len_sfx, SFX_MIN),
        reveal=REVEAL,
        naming=len_b + NAMING_PAD,
        hold=HOLD,
    )


def frames(seconds: float) -> int:
    """Convert seconds to a whole frame count at :data:`FPS`."""

    return round(seconds * FPS)


def quantize(seconds: float) -> float:
    """Snap a duration to the frame grid (seconds)."""

    return frames(seconds) / FPS
