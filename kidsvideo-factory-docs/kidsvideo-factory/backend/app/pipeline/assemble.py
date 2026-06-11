"""Final assembly (concat) + cache-rerender check (CONTRACTS §12).

``assemble`` joins ``intro + segments + outro`` with the ffmpeg concat demuxer
using ``-c copy`` (ffmpeg-recipes R5). Every piece is produced with the same R1
encoding parameters, so the copy is lossless. If ``-c copy`` fails (e.g. a stale
cached segment with mismatched parameters), we fall back to an R1 re-encode and
log a Hungarian warning — the *correct* long-term fix is to re-render the
diverging segment (cache hash, 01-BLUEPRINT §6.3), not to silently re-encode.

``needs_rerender`` compares a current input hash against the one stored in an
item's ``meta.json`` so ``assemble`` only re-renders segments whose inputs
changed (01-BLUEPRINT §6.3).

All ffmpeg invocations follow the ffmpeg-recipes skill; ffmpeg/ffprobe come from
PATH. Runtime code writes ONLY under the data dir — callers pass ``out_path`` and
``list_file`` that already live under ``data_root()`` (CLAUDE.md #7).
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# R1 — global encoding parameters (ffmpeg-recipes R1). Identical for every video
# output so the concat demuxer can copy losslessly; only used as the re-encode
# fallback here. These are codec settings, not phase durations — the single
# source of second-values stays ``pipeline/timing.py`` (CLAUDE.md #4).
_R1_OUTPUT_ARGS: tuple[str, ...] = (
    "-r", "30",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "18",
    "-pix_fmt", "yuv420p",
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "48000",
    "-ac", "2",
    "-movflags", "+faststart",
)

# Hungarian warning logged when the lossless copy fails and we fall back to a
# re-encode (the proper fix is re-rendering the diverging segment).
_FALLBACK_WARNING = (
    "A veszteségmentes összefűzés (-c copy) nem sikerült — eltérő paraméterű "
    "szegmens lehet a listában. Újrakódolásra váltok (R1). A helyes megoldás az "
    "eltérő szegmens újrarenderelése (cache-hash, 01-BLUEPRINT 6.3), nem a néma "
    "újrakódolás."
)


def _quote_concat_path(path: str) -> str:
    """Escape a path for a concat-demuxer ``file`` directive.

    The concat demuxer treats single quotes specially; the canonical escape for
    an embedded ``'`` is ``'\\''``. Backslashes are also escaped so Windows
    paths survive verbatim.
    """

    escaped = path.replace("\\", "\\\\").replace("'", "'\\''")
    return f"file '{escaped}'"


def _write_concat_list(parts: list[Path], list_file: Path) -> None:
    """Write the concat ``list.txt`` with paths relative to ``list_file``.

    The concat demuxer resolves relative ``file`` entries against the directory
    containing the list file (ffmpeg-recipes buktató-lista). We therefore store
    each part relative to ``list_file``'s parent when possible, falling back to
    an absolute path when no relative route exists (e.g. a different Windows
    drive).
    """

    base = list_file.parent.resolve()
    lines: list[str] = []
    for part in parts:
        resolved = Path(part).resolve()
        try:
            rel = resolved.relative_to(base)
            entry = rel.as_posix()
        except ValueError:
            try:
                # ``walk_up`` (Python 3.12+) handles ``..`` segments when the
                # part lives outside the list dir but on the same drive.
                rel = resolved.relative_to(base, walk_up=True)
                entry = rel.as_posix()
            except ValueError:
                # Different drive / no common root → keep the absolute path.
                entry = resolved.as_posix()
        lines.append(_quote_concat_path(entry))

    list_file.parent.mkdir(parents=True, exist_ok=True)
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run an ffmpeg command, capturing output as text."""

    return subprocess.run(cmd, capture_output=True, text=True)


def _ffmpeg_tail(stderr: str, lines: int = 12) -> str:
    """Return the last few lines of ffmpeg stderr for log messages."""

    return "\n".join(stderr.strip().splitlines()[-lines:])


def _is_decodable(path: Path) -> bool:
    """True if ``path`` decodes cleanly end-to-end.

    The concat demuxer's ``-c copy`` returns success even when it stitches
    parameter-mismatched segments together, producing a file that *looks* valid
    but is actually corrupt (ffmpeg-recipes R5: ``-c copy`` „hibázik VAGY hibás
    fájlt ad"). A full decode pass to the null muxer surfaces that corruption:
    a non-zero exit code means the stream copy did not in fact stitch cleanly.
    """

    proc = _run_ffmpeg(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"]
    )
    return proc.returncode == 0


def assemble(
    *,
    intro: Path | None,
    segments: list[Path],
    outro: Path | None,
    out_path: Path,
    list_file: Path,
    log: Callable[[str], None] | None = None,
) -> None:
    """Concatenate ``intro + segments + outro`` into ``out_path`` (R5).

    A ``list.txt`` is written at ``list_file`` with each part resolved relative
    to the list file's own location. We first try a lossless concat with
    ``-c copy``; on failure we log a Hungarian warning and re-encode with the R1
    parameters.

    Parameters
    ----------
    intro, outro:
        Optional branding clips placed first / last. ``None`` to omit.
    segments:
        Ordered item segment clips (must be non-empty).
    out_path:
        Destination ``final.mp4`` (under the data dir).
    list_file:
        Where the concat ``list.txt`` is written (under the data dir).
    log:
        Optional sink for human-readable Hungarian progress / warning messages
        (e.g. the job log). Messages also go to the module logger.
    """

    def _emit(message: str) -> None:
        logger.warning(message)
        if log is not None:
            log(message)

    if not segments:
        raise ValueError("Legalább egy szegmens kell az összefűzéshez.")

    parts: list[Path] = []
    if intro is not None:
        parts.append(intro)
    parts.extend(segments)
    if outro is not None:
        parts.append(outro)

    missing = [str(p) for p in parts if not Path(p).is_file()]
    if missing:
        raise FileNotFoundError(
            "Hiányzó bemeneti fájl(ok) az összefűzéshez: " + ", ".join(missing)
        )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_concat_list(parts, Path(list_file))

    base_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(Path(list_file).resolve()),
    ]

    # 1) Lossless copy (the happy path — every part is R1-encoded). We accept it
    #    only if ffmpeg exited cleanly AND the result decodes end-to-end: the
    #    concat demuxer can return success while emitting a corrupt file when a
    #    part's parameters diverge (R5).
    copy_cmd = [*base_cmd, "-c", "copy", str(out_path)]
    proc = _run_ffmpeg(copy_cmd)
    copy_ok = (
        proc.returncode == 0
        and out_path.is_file()
        and out_path.stat().st_size > 0
    )
    if copy_ok and _is_decodable(out_path):
        return

    # 2) Fallback: re-encode with R1. Log a Hungarian warning + ffmpeg context.
    _emit(_FALLBACK_WARNING)
    tail = _ffmpeg_tail(proc.stderr)
    if tail:
        _emit("ffmpeg (-c copy) hibakimenet:\n" + tail)

    reencode_cmd = [*base_cmd, *_R1_OUTPUT_ARGS, str(out_path)]
    proc2 = _run_ffmpeg(reencode_cmd)
    if proc2.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
        raise RuntimeError(
            "Az összefűzés újrakódolással (R1) is meghiúsult.\n"
            + _ffmpeg_tail(proc2.stderr)
        )


def needs_rerender(item_dir: Path, current_hash: str) -> bool:
    """Return True if ``item_dir``'s segment must be re-rendered (§6.3).

    Compares ``current_hash`` against the ``inputs_hash`` stored in the item's
    ``meta.json``. A segment needs re-rendering when:

    * the segment file itself is missing, or
    * ``meta.json`` is missing / unreadable / lacks a stored hash, or
    * the stored hash differs from ``current_hash``.

    The item's input hash is produced by ``segment.segment_inputs_hash`` and
    written into ``meta.json`` after a successful render.
    """

    item_dir = Path(item_dir)
    segment_file = item_dir / "segment.mp4"
    if not segment_file.is_file():
        return True

    meta_file = item_dir / "meta.json"
    if not meta_file.is_file():
        return True

    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True

    stored_hash = meta.get("inputs_hash") if isinstance(meta, dict) else None
    if not stored_hash:
        return True

    return stored_hash != current_hash
