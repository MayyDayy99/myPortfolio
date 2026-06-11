import { useEffect, useRef, useState } from "react";
import {
  assembleTopic,
  deleteTopic,
  listItems,
  mediaUrl,
  updateTopic,
  uploadBackground,
} from "../api";
import type { Item, Topic, TopicSettings, TopicStatus } from "../types";
import ItemList from "./ItemList";
import ItemEditor from "./ItemEditor";
import JobProgress from "./JobProgress";

const TOPIC_STATUS_LABELS: Record<TopicStatus, string> = {
  draft: "Piszkozat",
  in_progress: "Folyamatban",
  done: "Kész",
};

interface TopicEditorProps {
  topic: Topic;
  /** Bubble up an updated/deleted topic so the list refreshes. */
  onTopicChanged: (topic: Topic) => void;
  onTopicDeleted: (id: number) => void;
}

function parseSettings(json: string): TopicSettings {
  try {
    const parsed = JSON.parse(json);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

/**
 * Topic-level editor: title, status, background upload, render settings
 * (fps / xfade / colour / music / prompt prefix), the item list + the selected
 * item's editor, and the "make video" assemble action with download link.
 */
export default function TopicEditor({
  topic,
  onTopicChanged,
  onTopicDeleted,
}: TopicEditorProps) {
  const [items, setItems] = useState<Item[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [title, setTitle] = useState(topic.title);
  const [status, setStatus] = useState<TopicStatus>(topic.status);
  const [settings, setSettings] = useState<TopicSettings>(
    parseSettings(topic.settings_json),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assembleJobId, setAssembleJobId] = useState<number | null>(null);
  const [assembleDone, setAssembleDone] = useState(false);
  const bgInputRef = useRef<HTMLInputElement | null>(null);

  // Load items when the topic changes.
  useEffect(() => {
    let cancelled = false;
    setTitle(topic.title);
    setStatus(topic.status);
    setSettings(parseSettings(topic.settings_json));
    setSelectedItemId(null);
    setAssembleJobId(null);
    setAssembleDone(false);
    listItems(topic.id)
      .then((list) => {
        if (!cancelled) {
          setItems(list);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Az elemek nem tölthetők be.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [topic.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedItem = items.find((it) => it.id === selectedItemId) ?? null;

  const saveTopic = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateTopic(topic.id, {
        title: title.trim(),
        status,
        settings_json: JSON.stringify(settings),
      });
      onTopicChanged(updated);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "A téma mentése nem sikerült.",
      );
    } finally {
      setSaving(false);
    }
  };

  const onBackgroundSelected = async (file: File | undefined) => {
    if (!file) {
      return;
    }
    setError(null);
    try {
      const updated = await uploadBackground(topic.id, file);
      onTopicChanged(updated);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "A háttér feltöltése nem sikerült.",
      );
    } finally {
      if (bgInputRef.current) {
        bgInputRef.current.value = "";
      }
    }
  };

  const removeTopic = async () => {
    if (!window.confirm(`Biztosan törlöd a(z) „${topic.title}” témát?`)) {
      return;
    }
    setError(null);
    try {
      await deleteTopic(topic.id);
      onTopicDeleted(topic.id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "A téma törlése nem sikerült.",
      );
    }
  };

  const startAssemble = async () => {
    setError(null);
    setAssembleDone(false);
    try {
      const { job_id } = await assembleTopic(topic.id);
      setAssembleJobId(job_id);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Az összefűzés nem indítható.",
      );
    }
  };

  const onItemChanged = (updated: Item) => {
    setItems((prev) => prev.map((it) => (it.id === updated.id ? updated : it)));
  };

  const setSetting = <K extends keyof TopicSettings>(
    key: K,
    value: TopicSettings[K],
  ) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const backgroundUrl = mediaUrl(topic.background_path);
  // The assembled video lives at projects/<slug>/render/final.mp4.
  const finalVideoUrl = mediaUrl(`projects/${topic.slug}/render/final.mp4`);

  return (
    <div className="stack">
      <div className="panel stack">
        <div className="row between">
          <h2 style={{ margin: 0 }}>Téma szerkesztése</h2>
          <button className="danger" onClick={() => void removeTopic()}>
            Téma törlése
          </button>
        </div>

        {error && <div className="error-box">{error}</div>}

        <div className="field-grid">
          <div>
            <label htmlFor="topic-title">Cím</label>
            <input
              id="topic-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="topic-status">Státusz</label>
            <select
              id="topic-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as TopicStatus)}
            >
              {(Object.keys(TOPIC_STATUS_LABELS) as TopicStatus[]).map((s) => (
                <option key={s} value={s}>
                  {TOPIC_STATUS_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
        </div>

        <h3>Beállítások</h3>
        <div className="field-grid">
          <div>
            <label htmlFor="topic-fps">Képkocka/mp (fps)</label>
            <input
              id="topic-fps"
              type="number"
              value={settings.fps ?? ""}
              placeholder="30 (alapértelmezett)"
              onChange={(e) =>
                setSetting(
                  "fps",
                  e.target.value === ""
                    ? undefined
                    : Number.parseInt(e.target.value, 10),
                )
              }
            />
          </div>
          <div>
            <label htmlFor="topic-xfade">Elemek közti átmenet (mp)</label>
            <input
              id="topic-xfade"
              type="number"
              step="0.1"
              value={settings.xfade ?? ""}
              placeholder="alapértelmezett"
              onChange={(e) =>
                setSetting(
                  "xfade",
                  e.target.value === ""
                    ? undefined
                    : Number.parseFloat(e.target.value),
                )
              }
            />
          </div>
          <div>
            <label htmlFor="topic-bgcolor">Háttérszín (kép nélkül)</label>
            <input
              id="topic-bgcolor"
              type="text"
              value={settings.bg_color ?? ""}
              placeholder="#EAF4FF"
              onChange={(e) =>
                setSetting("bg_color", e.target.value || undefined)
              }
            />
          </div>
          <div>
            <label htmlFor="topic-music">Háttérzene</label>
            <div className="row" style={{ paddingTop: 6 }}>
              <input
                id="topic-music"
                type="checkbox"
                checked={settings.music ?? false}
                style={{ width: "auto" }}
                onChange={(e) => setSetting("music", e.target.checked)}
              />
              <span className="muted">Bekapcsolva</span>
            </div>
          </div>
        </div>
        <div>
          <label htmlFor="topic-prefix">Prompt stílus-prefix</label>
          <input
            id="topic-prefix"
            type="text"
            value={settings.prompt_prefix ?? ""}
            placeholder="pl. flat illustration, soft colors, white background"
            onChange={(e) =>
              setSetting("prompt_prefix", e.target.value || undefined)
            }
          />
        </div>

        <h3>Háttér</h3>
        <div className="row">
          <label
            className="muted"
            style={{ margin: 0, cursor: "pointer" }}
          >
            Háttérkép feltöltése (1920×1080)
            <input
              ref={bgInputRef}
              type="file"
              accept="image/png,image/jpeg"
              style={{ display: "none" }}
              onChange={(e) => void onBackgroundSelected(e.target.files?.[0])}
            />
          </label>
        </div>
        {backgroundUrl && (
          <div className="image-frame" style={{ maxWidth: 320, aspectRatio: "16 / 9" }}>
            <img src={backgroundUrl} alt="Háttér előnézet" />
          </div>
        )}

        <div className="row">
          <button
            className="primary"
            disabled={saving}
            onClick={() => void saveTopic()}
          >
            {saving ? "Mentés…" : "Téma mentése"}
          </button>
        </div>
      </div>

      <div className="panel stack">
        <ItemList
          topicId={topic.id}
          items={items}
          selectedId={selectedItemId}
          onSelect={setSelectedItemId}
          onChanged={setItems}
        />
      </div>

      {selectedItem && (
        <ItemEditor
          topic={topic}
          item={selectedItem}
          onItemChanged={onItemChanged}
        />
      )}

      <div className="panel stack">
        <h2 style={{ margin: 0 }}>Videó elkészítése</h2>
        <p className="muted">
          Intro + a szegmensek + outro összefűzése. Először rendereld le minden
          elem szegmensét.
        </p>
        <div className="row">
          <button
            className="primary"
            disabled={items.length === 0}
            onClick={() => void startAssemble()}
          >
            Videó elkészítése
          </button>
          {assembleDone && finalVideoUrl && (
            <a
              className="button"
              href={`${finalVideoUrl}?v=${assembleJobId ?? 0}`}
              download
            >
              Kész videó letöltése
            </a>
          )}
        </div>
        {assembleJobId && (
          <JobProgress
            key={assembleJobId}
            jobId={assembleJobId}
            label="Videó összefűzése"
            onFinished={(job) => {
              if (job.state === "done") {
                setAssembleDone(true);
              }
            }}
          />
        )}
      </div>
    </div>
  );
}
