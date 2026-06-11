"""Filesystem path helpers and slugify (CONTRACTS §3).

Every helper returns an absolute :class:`pathlib.Path` rooted under the
configured ``data_dir``. Runtime code writes ONLY under ``data_root()`` — never
into the repository working tree (CLAUDE.md #7).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app.config import get_settings

# Hungarian accent map. Long-vowel pairs (ő/ű) and their umlaut bases (ö/ü)
# all fold to the plain ascii vowel, per CONTRACTS §3. Uppercase variants are
# mapped explicitly so we can fold before lowercasing-independent stripping.
_HU_ACCENT_MAP = {
    "á": "a",
    "é": "e",
    "í": "i",
    "ó": "o",
    "ö": "o",
    "ő": "o",
    "ú": "u",
    "ü": "u",
    "ű": "u",
    "Á": "A",
    "É": "E",
    "Í": "I",
    "Ó": "O",
    "Ö": "O",
    "Ő": "O",
    "Ú": "U",
    "Ü": "U",
    "Ű": "U",
}

_HU_TRANSLATION = str.maketrans(_HU_ACCENT_MAP)

# Asset filenames allowed under an item directory (CONTRACTS §3).
ITEM_ASSET_NAMES = frozenset(
    {
        "generated.png",
        "cutout.png",
        "silhouette.png",
        "narration_a.webm",
        "narration_a.clean.wav",
        "narration_b.webm",
        "narration_b.clean.wav",
        "segment.mp4",
        "meta.json",
    }
)


def slugify(text: str) -> str:
    """Return a filesystem-safe slug.

    Steps: map Hungarian accents to ascii, normalize remaining diacritics via
    NFKD + ascii filtering, lowercase, replace runs of non-alphanumerics with a
    single ``-`` and trim leading/trailing ``-``.

    Examples (test-binding): ``"tehén" -> "tehen"``,
    ``"tűzoltó autó" -> "tuzolto-auto"``, ``"Az ÉG!" -> "az-eg"``.
    """

    # 1) Explicit Hungarian fold so ő/ű/ö/ü do not lose to NFKD surprises.
    folded = text.translate(_HU_TRANSLATION)
    # 2) Strip any remaining combining marks (other languages' diacritics).
    normalized = unicodedata.normalize("NFKD", folded)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    # 3) Lowercase, collapse non-alphanumerics to single dash, trim.
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    return ascii_text.strip("-")


def data_root() -> Path:
    """Absolute root of the runtime data directory."""

    return Path(get_settings().data_dir).resolve()


def db_path() -> Path:
    """Path to the SQLite database file: ``<data>/db.sqlite3``."""

    return data_root() / "db.sqlite3"


def topic_dir(topic_slug: str) -> Path:
    """Project directory for a topic: ``<data>/projects/<slug>``."""

    return data_root() / "projects" / topic_slug


def item_dir(topic_slug: str, position: int, item_slug: str) -> Path:
    """Item directory: ``<data>/projects/<slug>/items/<NN>-<item_slug>``.

    ``NN`` is the 2-digit zero-padded ``position`` (1-based).
    """

    return topic_dir(topic_slug) / "items" / f"{position:02d}-{item_slug}"


def render_dir(topic_slug: str) -> Path:
    """Render directory for a topic: ``<data>/projects/<slug>/render``."""

    return topic_dir(topic_slug) / "render"


def sfx_dir() -> Path:
    """Shared sound-effects directory: ``<data>/sfx``."""

    return data_root() / "sfx"


def models_dir() -> Path:
    """Model cache directory (e.g. rembg/u2net): ``<data>/models``."""

    return data_root() / "models"


def branding_dir() -> Path:
    """Branding assets (intro/outro): ``<data>/branding``."""

    return data_root() / "branding"


def ensure_tree() -> None:
    """Create the fixed top-level directories under ``data_root()``.

    Idempotent. Creates ``sfx``, ``models``, ``branding`` and ``projects``.
    """

    data_root().mkdir(parents=True, exist_ok=True)
    sfx_dir().mkdir(parents=True, exist_ok=True)
    models_dir().mkdir(parents=True, exist_ok=True)
    branding_dir().mkdir(parents=True, exist_ok=True)
    (data_root() / "projects").mkdir(parents=True, exist_ok=True)


def item_asset(item_dir: Path, name: str) -> Path:
    """Resolve an asset path inside an item directory.

    ``name`` must be one of :data:`ITEM_ASSET_NAMES`.
    """

    if name not in ITEM_ASSET_NAMES:
        allowed = ", ".join(sorted(ITEM_ASSET_NAMES))
        raise ValueError(f"Unknown item asset name: {name!r}. Allowed: {allowed}")
    return item_dir / name
