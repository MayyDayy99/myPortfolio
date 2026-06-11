"""Tests for ``storage`` path helpers (CONTRACTS §3).

The autouse ``isolated_data_dir`` fixture guarantees DATA_DIR is a tmp path, so
these tests never touch a real ``/data``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import storage


def test_data_root_is_tmp(isolated_data_dir: Path) -> None:
    # Both resolve the symlinks/8.3 names so the comparison is robust on Windows.
    assert storage.data_root() == isolated_data_dir.resolve()


def test_fixed_path_helpers_under_data_root(isolated_data_dir: Path) -> None:
    root = storage.data_root()
    assert storage.db_path() == root / "db.sqlite3"
    assert storage.sfx_dir() == root / "sfx"
    assert storage.models_dir() == root / "models"
    assert storage.branding_dir() == root / "branding"


def test_topic_and_item_dir_layout(isolated_data_dir: Path) -> None:
    topic_slug = storage.slugify("Háziállatok")
    assert topic_slug == "haziallatok"

    tdir = storage.topic_dir(topic_slug)
    assert tdir == storage.data_root() / "projects" / "haziallatok"

    item_slug = storage.slugify("tehén")
    idir = storage.item_dir(topic_slug, 1, item_slug)
    assert idir == tdir / "items" / "01-tehen"

    # Position zero-pads to 2 digits.
    idir9 = storage.item_dir(topic_slug, 9, item_slug)
    assert idir9.name == "09-tehen"
    idir12 = storage.item_dir(topic_slug, 12, storage.slugify("tűzoltó autó"))
    assert idir12.name == "12-tuzolto-auto"

    assert storage.render_dir(topic_slug) == tdir / "render"


def test_ensure_tree_creates_fixed_dirs(isolated_data_dir: Path) -> None:
    storage.ensure_tree()
    assert storage.sfx_dir().is_dir()
    assert storage.models_dir().is_dir()
    assert storage.branding_dir().is_dir()
    assert (storage.data_root() / "projects").is_dir()
    # Idempotent: a second call does not raise.
    storage.ensure_tree()


def test_creating_topic_item_dirs_yields_expected_structure(isolated_data_dir: Path) -> None:
    storage.ensure_tree()
    topic_slug = storage.slugify("Az ÉG!")
    assert topic_slug == "az-eg"
    idir = storage.item_dir(topic_slug, 3, storage.slugify("tehén"))
    idir.mkdir(parents=True, exist_ok=True)

    # The directory tree exists exactly as projects/<slug>/items/<NN>-<slug>.
    assert idir.is_dir()
    rel = idir.relative_to(storage.data_root())
    assert rel == Path("projects") / "az-eg" / "items" / "03-tehen"


def test_item_asset_validates_name(isolated_data_dir: Path) -> None:
    idir = storage.item_dir("haziallatok", 1, "tehen")
    assert storage.item_asset(idir, "generated.png") == idir / "generated.png"
    assert storage.item_asset(idir, "narration_a.clean.wav") == idir / "narration_a.clean.wav"
    assert storage.item_asset(idir, "meta.json") == idir / "meta.json"

    with pytest.raises(ValueError):
        storage.item_asset(idir, "not-an-asset.txt")
