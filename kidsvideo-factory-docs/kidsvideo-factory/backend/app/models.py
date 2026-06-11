"""Pydantic v2 schemas and enums (CONTRACTS §5).

Enums are ``str``-based so they serialize to plain strings in JSON and compare
equal to the values stored in SQLite. ``*Create`` / ``*Update`` models carry
only the fields a client may send; the storage/api layer maps DB rows to the
full ``Topic`` / ``Item`` / ``Job`` models.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TopicStatus(str, Enum):
    """Lifecycle of a topic (video project)."""

    draft = "draft"
    in_progress = "in_progress"
    done = "done"


class ItemStatus(str, Enum):
    """Item state machine (01-BLUEPRINT §3)."""

    draft = "draft"
    image_ok = "image_ok"
    audio_ok = "audio_ok"
    segment_ok = "segment_ok"


class JobKind(str, Enum):
    """The kinds of background jobs the pipeline runs."""

    generate_image = "generate_image"
    cutout = "cutout"
    clean_audio = "clean_audio"
    render_segment = "render_segment"
    assemble = "assemble"


class JobState(str, Enum):
    """Lifecycle of a queued job."""

    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


# --------------------------------------------------------------------------- #
# Topic
# --------------------------------------------------------------------------- #
class Topic(BaseModel):
    """A video project (full representation)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    status: TopicStatus = TopicStatus.draft
    background_path: str | None = None
    settings_json: str = "{}"
    created_at: str


class TopicCreate(BaseModel):
    """Client payload to create a topic."""

    title: str
    settings_json: str = "{}"


class TopicUpdate(BaseModel):
    """Client payload to patch a topic (all fields optional)."""

    title: str | None = None
    status: TopicStatus | None = None
    settings_json: str | None = None


# --------------------------------------------------------------------------- #
# Item
# --------------------------------------------------------------------------- #
class Item(BaseModel):
    """A single item within a topic (full representation)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    position: int
    slug: str
    name: str
    prompt: str = ""
    seed: int | None = None
    sfx_path: str | None = None
    status: ItemStatus = ItemStatus.draft


class ItemCreate(BaseModel):
    """Client payload to create an item (position/slug/dir are server-assigned)."""

    name: str
    prompt: str = ""
    seed: int | None = None
    sfx_path: str | None = None


class ItemUpdate(BaseModel):
    """Client payload to patch an item (all fields optional)."""

    name: str | None = None
    prompt: str | None = None
    seed: int | None = None
    sfx_path: str | None = None
    status: ItemStatus | None = None


# --------------------------------------------------------------------------- #
# Job
# --------------------------------------------------------------------------- #
class Job(BaseModel):
    """A background job row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: JobKind
    ref_id: int | None = None
    state: JobState = JobState.queued
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    log: str = ""
    created_at: str
    updated_at: str
