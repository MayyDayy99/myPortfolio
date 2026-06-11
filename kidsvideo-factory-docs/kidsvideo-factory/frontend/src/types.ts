/**
 * TypeScript mirror of the backend pydantic enums and models (CONTRACTS §5).
 *
 * String unions match the backend `str, Enum` values 1:1 so JSON round-trips
 * without translation. Keep this file in lockstep with backend/app/models.py.
 */

// --------------------------------------------------------------------------- //
// Enums (string unions + value lists for iteration)
// --------------------------------------------------------------------------- //

export type TopicStatus = "draft" | "in_progress" | "done";
export type ItemStatus = "draft" | "image_ok" | "audio_ok" | "segment_ok";
export type JobKind =
  | "generate_image"
  | "cutout"
  | "clean_audio"
  | "render_segment"
  | "assemble";
export type JobState = "queued" | "running" | "done" | "error";

export const TOPIC_STATUSES: readonly TopicStatus[] = [
  "draft",
  "in_progress",
  "done",
];
export const ITEM_STATUSES: readonly ItemStatus[] = [
  "draft",
  "image_ok",
  "audio_ok",
  "segment_ok",
];
export const JOB_STATES: readonly JobState[] = [
  "queued",
  "running",
  "done",
  "error",
];

/** The two narration slots an item carries (A = riddle, B = naming). */
export type NarrationSlot = "a" | "b";

// --------------------------------------------------------------------------- //
// Models
// --------------------------------------------------------------------------- //

export interface Topic {
  id: number;
  slug: string;
  title: string;
  status: TopicStatus;
  background_path: string | null;
  settings_json: string;
  created_at: string;
}

export interface TopicCreate {
  title: string;
  settings_json?: string;
}

export interface TopicUpdate {
  title?: string;
  status?: TopicStatus;
  settings_json?: string;
}

export interface Item {
  id: number;
  topic_id: number;
  position: number;
  slug: string;
  name: string;
  prompt: string;
  seed: number | null;
  sfx_path: string | null;
  status: ItemStatus;
}

export interface ItemCreate {
  name: string;
  prompt?: string;
  seed?: number | null;
  sfx_path?: string | null;
}

export interface ItemUpdate {
  name?: string;
  prompt?: string;
  seed?: number | null;
  sfx_path?: string | null;
  status?: ItemStatus;
}

export interface Job {
  id: number;
  kind: JobKind;
  ref_id: number | null;
  state: JobState;
  /** Progress in the closed range [0, 1]. */
  progress: number;
  log: string;
  created_at: string;
  updated_at: string;
}

/** A long-running operation returns only the job id; the UI then polls it. */
export interface JobRef {
  job_id: number;
}

/**
 * One entry from `GET /api/sfx` (data/sfx contents). The contract leaves the
 * exact shape to the media route, so we accept the common fields and keep the
 * raw record around for forward compatibility.
 */
export interface SfxEntry {
  /** Filename inside data/sfx, e.g. "moo.wav". */
  name: string;
  /** Storage-relative path (under data_root), used to assign to an item. */
  path: string;
  /** Optional media URL for preview; if absent the client derives one. */
  url?: string;
  /** Optional duration in seconds, if the backend probed it. */
  duration?: number | null;
}

/**
 * Topic-level settings persisted as a JSON string in `settings_json`
 * (03-VIDEO-SPEC §1, §3, §4). All fields optional; the renderer falls back to
 * pipeline/timing.py defaults when unset.
 */
export interface TopicSettings {
  /** Frames per second (default 30; the single source is timing.py). */
  fps?: number;
  /** Element-to-element crossfade in seconds (overrides timing.XFADE). */
  xfade?: number;
  /** Solid background colour (#RRGGBB) when no background image is set. */
  bg_color?: string;
  /** Whether background music is enabled (v2 feature flag). */
  music?: boolean;
  /** Style prefix prepended to each item prompt (03-VIDEO-SPEC §5). */
  prompt_prefix?: string;
}
