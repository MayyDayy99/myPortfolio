"""Spike S3 — build a segment.mp4 from synthetic/placeholder assets.

Proof that ``pipeline.segment.render_segment`` runs end-to-end on THIS dev box
(ffmpeg present; rembg / ComfyUI NOT required — this spike touches neither).

It synthesizes:
  * a silhouette PNG (solid-black opaque blob on a transparent frame),
  * a cutout PNG (the same blob, coloured) — identical alpha so the reveal lines
    up exactly,
  * three short WAVs (narration A, sfx, narration B) via ffmpeg,
then renders one segment with a SOLID background colour and reports the result.

Run:  python spike/s3_segment.py [out_dir]
Writes everything under a temp/work dir (never the repo tree at runtime beyond
this throwaway spike output, which defaults to the system temp dir).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

# Make ``app`` importable when run from the repo root or the spike/ dir.
_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.pipeline import timing as T  # noqa: E402
from app.pipeline.segment import render_segment  # noqa: E402


def _make_silhouette_and_cutout(sil_path: Path, cut_path: Path) -> None:
    """Draw an opaque blob; silhouette is black, cutout is coloured (same alpha)."""

    from PIL import Image, ImageDraw

    w, h = 900, 1200
    # Cutout: a coloured rounded rectangle ("body") + circle ("head") on alpha.
    cut = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(cut)
    d.rounded_rectangle([200, 500, 700, 1150], radius=80, fill=(230, 120, 60, 255))
    d.ellipse([280, 150, 620, 490], fill=(245, 200, 120, 255))
    cut.save(cut_path, "PNG")

    # Silhouette: same shapes, fully black, alpha copied from the cutout so the
    # geometry is pixel-identical (render_segment relies on this).
    alpha = cut.getchannel("A")
    sil = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    black = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    sil = Image.composite(black, sil, alpha)
    sil.save(sil_path, "PNG")


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


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else Path(tempfile.mkdtemp(prefix="s3_segment_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    sil = out_dir / "silhouette.png"
    cut = out_dir / "cutout.png"
    narr_a = out_dir / "narration_a.wav"
    sfx = out_dir / "sfx.wav"
    narr_b = out_dir / "narration_b.wav"
    out_mp4 = out_dir / "segment.mp4"

    # Known asset lengths -> deterministic timing from the SINGLE source.
    len_a, len_sfx, len_b = 2.0, 0.7, 1.3
    _make_silhouette_and_cutout(sil, cut)
    _make_wav(narr_a, len_a, freq=330)
    _make_wav(sfx, len_sfx, freq=880)
    _make_wav(narr_b, len_b, freq=440)

    timing = T.compute_timing(len_a, len_sfx, len_b)

    render_segment(
        background=None,
        silhouette=sil,
        cutout=cut,
        narration_a=narr_a,
        sfx=sfx,
        narration_b=narr_b,
        out_path=out_mp4,
        timing=timing,
    )

    size = out_mp4.stat().st_size
    expected_total = T.quantize(timing.total)
    print("S3 segment spike OK")
    print(f"  output      : {out_mp4}")
    print(f"  size        : {size} bytes")
    print(f"  expected len: {expected_total:.3f} s "
          f"(entry={timing.entry} riddle={timing.riddle} beat={timing.beat} "
          f"sfx={timing.sfx} reveal={timing.reveal} naming={timing.naming} "
          f"hold={timing.hold})")

    # Report the measured duration too (uses ffprobe via the test helper if
    # available; otherwise a direct ffprobe call).
    try:
        from tests.probe_phases import total_duration  # type: ignore

        measured = total_duration(out_mp4)
    except Exception:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(out_mp4)],
            capture_output=True, text=True,
        )
        measured = float(proc.stdout.strip()) if proc.returncode == 0 else float("nan")
    print(f"  measured len: {measured:.3f} s")

    if size == 0:
        print("ERROR: output file is empty", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
