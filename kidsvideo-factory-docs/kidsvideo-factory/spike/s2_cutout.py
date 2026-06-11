#!/usr/bin/env python3
"""S2 spike — cutout + silhouette from a generated PNG (CONTRACTS §17, F0).

Usage:
    python spike/s2_cutout.py <input.png> [--out-dir <dir>] [--alpha-threshold N]

Runs ``pipeline.cutout.cutout`` on the given image and writes ``cutout.png`` +
``silhouette.png`` under the data dir (``DATA_DIR``, default per config), in a
``spike-s2`` subfolder — never into the repo working tree (CLAUDE.md #7). Also
prints the cutout's alpha bounding box and timing.

Requires rembg (the dev box does not have it; this spike is meant to run on the
Mac where rembg + the u2net model are installed). All paths are absolute.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make ``app`` importable when running the spike from the repo root.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.pipeline import cutout as cutout_mod  # noqa: E402
from app.storage import data_root  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S2 spike: cutout + silhouette")
    parser.add_argument("input", help="path to the generated PNG")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="output directory (default: <DATA_DIR>/spike-s2)",
    )
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=128,
        help="alpha binarization threshold for the silhouette (0-255)",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        print(f"Hiba: a bemeneti fájl nem található: {input_path}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir).resolve() if args.out_dir else (data_root() / "spike-s2")
    out_dir.mkdir(parents=True, exist_ok=True)

    cutout_path = out_dir / "cutout.png"
    silhouette_path = out_dir / "silhouette.png"

    print(f"Bemenet:   {input_path}")
    print(f"Kimenet:   {out_dir}")

    started = time.perf_counter()
    try:
        cutout_mod.cutout(
            input_path,
            cutout_path,
            silhouette_path,
            alpha_threshold=args.alpha_threshold,
        )
    except ModuleNotFoundError as exc:
        # rembg missing — expected on the dev box; this spike runs on the Mac.
        print(
            "Hiba: a rembg nincs telepítve — ez a spike a Macen fut "
            f"(rembg + u2net modell kell). ({exc})",
            file=sys.stderr,
        )
        return 3
    elapsed = time.perf_counter() - started

    box = cutout_mod.bounding_box(cutout_path)
    print(f"cutout.png:     {cutout_path}")
    print(f"silhouette.png: {silhouette_path}")
    print(f"alpha bbox:     {box}")
    print(f"idő:            {elapsed:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
