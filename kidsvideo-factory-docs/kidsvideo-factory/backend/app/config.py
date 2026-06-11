"""Application settings (CONTRACTS §2).

Settings are read from environment variables. We deliberately avoid the
``pydantic-settings`` dependency: a tiny ``os.environ``-based reader is enough
and keeps the runtime footprint minimal. ``DATA_DIR`` is overridden to a tmp
path by the test suite, so NEVER hardcode ``/data`` anywhere else — always go
through ``get_settings().data_dir``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """Runtime configuration resolved from environment variables."""

    comfyui_url: str = "http://host.docker.internal:8188"  # env COMFYUI_URL
    data_dir: str = "/data"  # env DATA_DIR
    tz: str = "Europe/Budapest"  # env TZ


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached settings read from the environment.

    The cache is what makes this a singleton. Tests that change ``DATA_DIR``
    must clear it via ``get_settings.cache_clear()`` (the conftest fixture does
    this) so the new tmp path is picked up.
    """

    return Settings(
        comfyui_url=os.environ.get("COMFYUI_URL", "http://host.docker.internal:8188"),
        data_dir=os.environ.get("DATA_DIR", "/data"),
        tz=os.environ.get("TZ", "Europe/Budapest"),
    )
