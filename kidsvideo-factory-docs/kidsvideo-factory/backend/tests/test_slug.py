"""Tests for ``storage.slugify`` (CONTRACTS §3)."""

from __future__ import annotations

import pytest

from app.storage import slugify


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Contract-binding examples.
        ("tehén", "tehen"),
        ("tűzoltó autó", "tuzolto-auto"),
        ("Az ÉG!", "az-eg"),
        # Full Hungarian vowel coverage (long vowels fold to plain ascii).
        ("őzike", "ozike"),
        ("üveg", "uveg"),
        ("Öböl", "obol"),
        ("Űrhajó", "urhajo"),
        ("ÁÉÍÓÖŐÚÜŰ", "aeiooouuu"),
    ],
)
def test_basic_and_hungarian(text: str, expected: str) -> None:
    assert slugify(text) == expected


def test_empty_string() -> None:
    assert slugify("") == ""


def test_only_punctuation_is_empty() -> None:
    assert slugify("!!! ??? ...") == ""


def test_multiple_dashes_collapse() -> None:
    assert slugify("a -- b   c") == "a-b-c"
    assert slugify("tehén!!!autó") == "tehen-auto"


def test_leading_and_trailing_dashes_trimmed() -> None:
    assert slugify("  -tehén-  ") == "tehen"
    assert slugify("---Az ÉG!---") == "az-eg"


def test_digits_preserved() -> None:
    assert slugify("Elem 7 — tehén") == "elem-7-tehen"


def test_already_slug_is_stable() -> None:
    # idempotent on an already-clean slug
    assert slugify("tuzolto-auto") == "tuzolto-auto"
