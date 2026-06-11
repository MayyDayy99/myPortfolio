import { useState } from "react";
import { createTopic } from "../api";
import type { Topic, TopicStatus } from "../types";

const TOPIC_STATUS_LABELS: Record<TopicStatus, string> = {
  draft: "Piszkozat",
  in_progress: "Folyamatban",
  done: "Kész",
};

interface TopicListProps {
  topics: Topic[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  /** Called after a new topic is created so the parent can refresh + select. */
  onCreated: (topic: Topic) => void;
}

/** Lists all topics and offers a "new topic" form. */
export default function TopicList({
  topics,
  selectedId,
  onSelect,
  onCreated,
}: TopicListProps) {
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) {
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const topic = await createTopic({ title: trimmed });
      setTitle("");
      onCreated(topic);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "A téma létrehozása nem sikerült.",
      );
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="panel stack">
      <h2>Témák</h2>

      <form className="stack" onSubmit={submit}>
        <div>
          <label htmlFor="new-topic-title">Új téma címe</label>
          <input
            id="new-topic-title"
            type="text"
            value={title}
            placeholder="pl. Háziállatok"
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <button
          type="submit"
          className="primary"
          disabled={creating || title.trim().length === 0}
        >
          {creating ? "Létrehozás…" : "Új téma"}
        </button>
      </form>

      {error && <div className="error-box">{error}</div>}

      {topics.length === 0 ? (
        <p className="muted">Még nincs téma. Hozz létre egyet fent.</p>
      ) : (
        <div className="stack">
          {topics.map((topic) => (
            <button
              key={topic.id}
              className={`topic-list-item${
                topic.id === selectedId ? " active" : ""
              }`}
              onClick={() => onSelect(topic.id)}
            >
              <span className="title">{topic.title}</span>
              <span className={`chip ${topic.status}`}>
                {TOPIC_STATUS_LABELS[topic.status]}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
