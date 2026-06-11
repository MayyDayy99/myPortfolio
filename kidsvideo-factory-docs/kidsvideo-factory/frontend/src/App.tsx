import { useEffect, useState } from "react";
import { listTopics } from "./api";
import type { Topic } from "./types";
import TopicList from "./components/TopicList";
import TopicEditor from "./components/TopicEditor";

/**
 * Root view: a two-column layout with the topic list on the left and the
 * selected topic's editor (settings + items + assemble) on the right.
 */
export default function App() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshTopics = async (): Promise<Topic[]> => {
    const list = await listTopics();
    setTopics(list);
    return list;
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listTopics()
      .then((list) => {
        if (!cancelled) {
          setTopics(list);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "A témák nem tölthetők be. Fut a backend?",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedTopic = topics.find((t) => t.id === selectedId) ?? null;

  const onTopicCreated = (topic: Topic) => {
    setTopics((prev) => [...prev, topic]);
    setSelectedId(topic.id);
  };

  const onTopicChanged = (topic: Topic) => {
    setTopics((prev) => prev.map((t) => (t.id === topic.id ? topic : t)));
  };

  const onTopicDeleted = (id: number) => {
    setTopics((prev) => prev.filter((t) => t.id !== id));
    if (selectedId === id) {
      setSelectedId(null);
    }
  };

  return (
    <>
      <header className="app-header">
        <h1>Már ezt is tudom</h1>
        <span className="subtitle">videógyár</span>
      </header>

      <div className="app-body">
        <aside>
          {error && <div className="error-box">{error}</div>}
          <TopicList
            topics={topics}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onCreated={onTopicCreated}
          />
        </aside>

        <main>
          {loading ? (
            <div className="panel">
              <p className="muted">Betöltés…</p>
            </div>
          ) : selectedTopic ? (
            <TopicEditor
              topic={selectedTopic}
              onTopicChanged={onTopicChanged}
              onTopicDeleted={(id) => {
                onTopicDeleted(id);
                void refreshTopics();
              }}
            />
          ) : (
            <div className="panel">
              <h2>Válassz vagy hozz létre egy témát</h2>
              <p className="muted">
                A bal oldali listából válassz egy témát, vagy hozz létre egy
                újat. Egy videó 8–10 elemből áll: minden elemhez sziluett,
                narráció, hangeffekt és reveal-kép tartozik.
              </p>
            </div>
          )}
        </main>
      </div>
    </>
  );
}
