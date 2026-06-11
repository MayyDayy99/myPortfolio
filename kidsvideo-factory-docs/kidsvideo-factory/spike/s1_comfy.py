#!/usr/bin/env python3
"""S1 spike — generate one image via ComfyUI (CONTRACTS §17, F0).

Usage:
    python spike/s1_comfy.py "<prompt>" [--seed N] [--base-url URL] [--out PATH]

Submits the ``workflows/item-image.json`` template through
``app.pipeline.comfy.generate_image``, writes the resulting PNG under the data
dir (``DATA_DIR``, default per config) in a ``spike-s1`` subfolder — never into
the repo working tree (CLAUDE.md #7) — and times the generation.

Runs on the Mac where ComfyUI is live on :8188; here the code path is exercised.
All paths are absolute.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make ``app`` importable when running the spike from the repo root.
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.pipeline import comfy as comfy_mod  # noqa: E402
from app.storage import data_root  # noqa: E402

_WORKFLOWS = _ROOT / "workflows"
_WORKFLOW_PATH = _WORKFLOWS / "item-image.json"
_META_PATH = _WORKFLOWS / "item-image.meta.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S1 spike: ComfyUI image generation")
    parser.add_argument("prompt", help="positive prompt text")
    parser.add_argument("--seed", type=int, default=42, help="KSampler seed")
    parser.add_argument(
        "--base-url",
        default=None,
        help="ComfyUI base URL (default: COMFYUI_URL / config)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="output PNG path (default: <DATA_DIR>/spike-s1/generated.png)",
    )
    args = parser.parse_args(argv)

    out_path = (
        Path(args.out).resolve()
        if args.out
        else (data_root() / "spike-s1" / "generated.png")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Prompt:   {args.prompt}")
    print(f"Seed:     {args.seed}")
    print(f"Workflow: {_WORKFLOW_PATH}")
    print(f"Kimenet:  {out_path}")

    started = time.perf_counter()
    try:
        comfy_mod.generate_image(
            prompt_text=args.prompt,
            seed=args.seed,
            out_path=out_path,
            workflow_path=_WORKFLOW_PATH,
            meta_path=_META_PATH,
            base_url=args.base_url,
        )
    except comfy_mod.ComfyError as exc:
        print(f"Hiba: {exc}", file=sys.stderr)
        return 3
    elapsed = time.perf_counter() - started

    size = out_path.stat().st_size
    print(f"Kész:     {out_path} ({size} bájt)")
    print(f"Idő:      {elapsed:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
