/**
 * Typed fetch client for every backend endpoint in CONTRACTS §13.
 *
 * Long-running operations return `{ job_id }` (JobRef); the caller polls
 * `getJob` (the JobProgress component does this every 2s). All request/response
 * shapes come from types.ts, the TS mirror of the backend pydantic models.
 */

import type {
  Item,
  ItemCreate,
  ItemUpdate,
  Job,
  JobRef,
  NarrationSlot,
  SfxEntry,
  Topic,
  TopicCreate,
  TopicUpdate,
} from "./types";

/** Raised for any non-2xx response, carrying the backend's Hungarian detail. */
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(res: Response): Promise<never> {
  let detail = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") {
      detail = body.detail;
    } else if (body && Array.isArray(body.detail)) {
      // FastAPI validation errors: collect the messages.
      detail = body.detail
        .map((e: { msg?: string }) => e.msg ?? "")
        .filter(Boolean)
        .join("; ");
    }
  } catch {
    // Body was not JSON; keep the status-based message.
  }
  throw new ApiError(res.status, detail);
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    return parseError(res);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

async function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

async function sendJson<T>(
  path: string,
  method: "POST" | "PATCH",
  body: unknown,
): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function sendForm<T>(path: string, form: FormData): Promise<T> {
  // Do not set Content-Type; the browser adds the multipart boundary.
  return request<T>(path, { method: "POST", body: form });
}

// --------------------------------------------------------------------------- //
// Media URL helpers
// --------------------------------------------------------------------------- //

/**
 * Build a `/media/...` URL for a storage-relative path returned by the backend
 * (e.g. an item's `sfx_path` or a topic's `background_path`). The backend
 * serves data_root() at `/media`, so we just normalise separators and prefix.
 */
export function mediaUrl(storagePath: string | null | undefined): string | null {
  if (!storagePath) {
    return null;
  }
  // Backend may store either an absolute data-root path or a relative one;
  // we only ever need the tail after the data root. Normalise Windows slashes
  // and strip a leading "/media" or "/data" if the backend already added one.
  let p = storagePath.replace(/\\/g, "/");
  p = p.replace(/^\/?(media|data)\//, "");
  p = p.replace(/^\/+/, "");
  return `/media/${p}`;
}

// --------------------------------------------------------------------------- //
// Topics
// --------------------------------------------------------------------------- //

export function listTopics(): Promise<Topic[]> {
  return getJson<Topic[]>("/api/topics");
}

export function createTopic(payload: TopicCreate): Promise<Topic> {
  return sendJson<Topic>("/api/topics", "POST", payload);
}

export function getTopic(id: number): Promise<Topic> {
  return getJson<Topic>(`/api/topics/${id}`);
}

export function updateTopic(id: number, payload: TopicUpdate): Promise<Topic> {
  return sendJson<Topic>(`/api/topics/${id}`, "PATCH", payload);
}

export function deleteTopic(id: number): Promise<void> {
  return request<void>(`/api/topics/${id}`, { method: "DELETE" });
}

export function uploadBackground(id: number, file: File): Promise<Topic> {
  const form = new FormData();
  form.append("file", file);
  return sendForm<Topic>(`/api/topics/${id}/background`, form);
}

export function assembleTopic(id: number): Promise<JobRef> {
  return request<JobRef>(`/api/topics/${id}/assemble`, { method: "POST" });
}

// --------------------------------------------------------------------------- //
// Items
// --------------------------------------------------------------------------- //

export function listItems(topicId: number): Promise<Item[]> {
  return getJson<Item[]>(`/api/topics/${topicId}/items`);
}

export function createItem(
  topicId: number,
  payload: ItemCreate,
): Promise<Item> {
  return sendJson<Item>(`/api/topics/${topicId}/items`, "POST", payload);
}

export function reorderItems(
  topicId: number,
  itemIds: number[],
): Promise<Item[]> {
  return sendJson<Item[]>(
    `/api/topics/${topicId}/items/reorder`,
    "POST",
    itemIds,
  );
}

export function getItem(id: number): Promise<Item> {
  return getJson<Item>(`/api/items/${id}`);
}

export function updateItem(id: number, payload: ItemUpdate): Promise<Item> {
  return sendJson<Item>(`/api/items/${id}`, "PATCH", payload);
}

export function deleteItem(id: number): Promise<void> {
  return request<void>(`/api/items/${id}`, { method: "DELETE" });
}

export function generateImage(id: number, newSeed = false): Promise<JobRef> {
  const query = newSeed ? "?new_seed=true" : "";
  return request<JobRef>(`/api/items/${id}/generate-image${query}`, {
    method: "POST",
  });
}

export function cutoutItem(id: number): Promise<JobRef> {
  return request<JobRef>(`/api/items/${id}/cutout`, { method: "POST" });
}

export function uploadNarration(
  id: number,
  slot: NarrationSlot,
  blob: Blob,
  filename: string,
): Promise<Item> {
  const form = new FormData();
  form.append("file", blob, filename);
  return sendForm<Item>(`/api/items/${id}/narration/${slot}`, form);
}

export function cleanAudio(
  id: number,
  slot: NarrationSlot,
): Promise<JobRef> {
  return request<JobRef>(`/api/items/${id}/clean-audio/${slot}`, {
    method: "POST",
  });
}

export function renderSegment(id: number): Promise<JobRef> {
  return request<JobRef>(`/api/items/${id}/render-segment`, { method: "POST" });
}

// --------------------------------------------------------------------------- //
// Jobs
// --------------------------------------------------------------------------- //

export function getJob(id: number): Promise<Job> {
  return getJson<Job>(`/api/jobs/${id}`);
}

// --------------------------------------------------------------------------- //
// SFX library
// --------------------------------------------------------------------------- //

export function listSfx(): Promise<SfxEntry[]> {
  return getJson<SfxEntry[]>("/api/sfx");
}
