import { useEffect, useState } from "react";
import {
  cleanAudio,
  cutoutItem,
  generateImage,
  getItem,
  renderSegment,
  updateItem,
} from "../api";
import type { Item, Job, NarrationSlot, Topic } from "../types";
import ImageTriptych from "./ImageTriptych";
import JobProgress from "./JobProgress";
import NarrationRecorder from "./NarrationRecorder";
import SfxPicker from "./SfxPicker";

interface ItemEditorProps {
  topic: Topic;
  item: Item;
  /** Bubble an updated item up so the list and editor stay in sync. */
  onItemChanged: (item: Item) => void;
}

/** A single active job tracked in this editor. */
interface ActiveJob {
  jobId: number;
  label: string;
}

/**
 * Per-item workspace: name/prompt/seed fields, image generation + cutout,
 * the raw/cutout/silhouette triptych, narration A/B recorder + audio cleanup,
 * the SFX picker and the segment render — each long op tracked via JobProgress.
 */
export default function ItemEditor({
  topic,
  item,
  onItemChanged,
}: ItemEditorProps) {
  const [name, setName] = useState(item.name);
  const [prompt, setPrompt] = useState(item.prompt);
  const [seed, setSeed] = useState<string>(
    item.seed === null ? "" : String(item.seed),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<ActiveJob | null>(null);
  const [imageRefresh, setImageRefresh] = useState(0);

  // Re-sync local field state when a different item is selected.
  useEffect(() => {
    setName(item.name);
    setPrompt(item.prompt);
    setSeed(item.seed === null ? "" : String(item.seed));
    setJob(null);
    setError(null);
  }, [item.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty =
    name !== item.name ||
    prompt !== item.prompt ||
    seed !== (item.seed === null ? "" : String(item.seed));

  const saveFields = async () => {
    setSaving(true);
    setError(null);
    try {
      const seedValue =
        seed.trim() === "" ? null : Number.parseInt(seed.trim(), 10);
      if (seedValue !== null && Number.isNaN(seedValue)) {
        throw new Error("A seed csak egész szám lehet.");
      }
      const updated = await updateItem(item.id, {
        name: name.trim(),
        prompt,
        seed: seedValue,
      });
      onItemChanged(updated);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "A mentés nem sikerült.",
      );
    } finally {
      setSaving(false);
    }
  };

  const runJob = async (
    label: string,
    starter: () => Promise<{ job_id: number }>,
  ) => {
    setError(null);
    try {
      const { job_id } = await starter();
      setJob({ jobId: job_id, label });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "A művelet nem indítható.",
      );
    }
  };

  const onJobFinished = (finished: Job) => {
    // Bust the image cache and refresh the item so status chips update.
    setImageRefresh((n) => n + 1);
    // Re-fetch the item to pull the new status/seed/sfx the backend set.
    void (async () => {
      try {
        const fresh = await getItem(item.id);
        onItemChanged(fresh);
      } catch {
        // Non-fatal; the chips will refresh on next navigation.
      }
    })();
    if (finished.state === "error") {
      setError("A háttérművelet hibával zárult — lásd a job naplóját.");
    }
  };

  const assignSfx = async (sfxPath: string | null) => {
    const updated = await updateItem(item.id, { sfx_path: sfxPath });
    onItemChanged(updated);
  };

  const onNarrationUploaded = (updated: Item) => {
    onItemChanged(updated);
  };

  return (
    <div className="panel stack">
      <div className="row between">
        <h2 style={{ margin: 0 }}>
          {String(item.position).padStart(2, "0")} — {item.name}
        </h2>
        <span className={`chip ${item.status}`}>{item.status}</span>
      </div>

      {error && <div className="error-box">{error}</div>}

      {/* Basic fields */}
      <div className="field-grid">
        <div>
          <label htmlFor="item-name">Elem neve</label>
          <input
            id="item-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="item-seed">Seed (üres = automatikus)</label>
          <input
            id="item-seed"
            type="number"
            value={seed}
            placeholder="auto"
            onChange={(e) => setSeed(e.target.value)}
          />
        </div>
      </div>
      <div>
        <label htmlFor="item-prompt">
          Kép-prompt (csak a tárgyat írd le; a stílus-prefix a témából jön)
        </label>
        <textarea
          id="item-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
      </div>
      <div className="row">
        <button
          className="primary"
          disabled={!dirty || saving || name.trim().length === 0}
          onClick={() => void saveFields()}
        >
          {saving ? "Mentés…" : "Mentés"}
        </button>
      </div>

      {/* Image pipeline */}
      <h3>Kép</h3>
      <div className="row">
        <button
          className="primary"
          onClick={() =>
            void runJob("Képgenerálás", () => generateImage(item.id, false))
          }
        >
          Generálás
        </button>
        <button
          onClick={() =>
            void runJob("Újragenerálás (új seed)", () =>
              generateImage(item.id, true),
            )
          }
        >
          Újragenerálás (új seed)
        </button>
        <button
          onClick={() => void runJob("Kivágás és sziluett", () => cutoutItem(item.id))}
        >
          Kivágás + sziluett
        </button>
      </div>
      <ImageTriptych topic={topic} item={item} refreshKey={imageRefresh} />

      {/* Narration */}
      <NarrationRecorder item={item} onUploaded={onNarrationUploaded} />
      <div className="row">
        <button
          onClick={() =>
            void runJob("Hangtisztítás (A)", () =>
              cleanAudio(item.id, "a" as NarrationSlot),
            )
          }
        >
          A narráció tisztítása
        </button>
        <button
          onClick={() =>
            void runJob("Hangtisztítás (B)", () =>
              cleanAudio(item.id, "b" as NarrationSlot),
            )
          }
        >
          B narráció tisztítása
        </button>
      </div>

      {/* SFX */}
      <SfxPicker item={item} onAssign={assignSfx} />

      {/* Segment render */}
      <h3>Szegmens</h3>
      <div className="row">
        <button
          className="primary"
          onClick={() =>
            void runJob("Szegmens renderelése", () => renderSegment(item.id))
          }
        >
          Szegmens renderelése
        </button>
      </div>

      {/* Active job tracker */}
      {job && (
        <JobProgress
          key={job.jobId}
          jobId={job.jobId}
          label={job.label}
          onFinished={onJobFinished}
        />
      )}
    </div>
  );
}
