import { useState } from "react";
import { createItem, deleteItem, reorderItems } from "../api";
import type { Item, ItemStatus } from "../types";

const ITEM_STATUS_LABELS: Record<ItemStatus, string> = {
  draft: "Piszkozat",
  image_ok: "Kép kész",
  audio_ok: "Hang kész",
  segment_ok: "Szegmens kész",
};

interface ItemListProps {
  topicId: number;
  items: Item[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  /** Re-fetch the item list after a create/delete/reorder. */
  onChanged: (items: Item[]) => void;
}

/**
 * Item CRUD list with add, up/down reordering and delete. Reordering posts the
 * new id order to the backend, which keeps `position` and the NN-folder in
 * sync (CONTRACTS §13).
 */
export default function ItemList({
  topicId,
  items,
  selectedId,
  onSelect,
  onChanged,
}: ItemListProps) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sorted = [...items].sort((a, b) => a.position - b.position);

  const wrap = async (fn: () => Promise<Item[]>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await fn();
      onChanged(next);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "A művelet nem sikerült.",
      );
    } finally {
      setBusy(false);
    }
  };

  const addItem = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    await wrap(async () => {
      const created = await createItem(topicId, { name: trimmed });
      setName("");
      return [...items, created];
    });
  };

  const removeItem = async (id: number) => {
    await wrap(async () => {
      await deleteItem(id);
      return items.filter((it) => it.id !== id);
    });
  };

  const move = async (index: number, delta: number) => {
    const order = sorted.map((it) => it.id);
    const target = index + delta;
    if (target < 0 || target >= order.length) {
      return;
    }
    const a = order[index];
    const b = order[target];
    if (a === undefined || b === undefined) {
      return;
    }
    order[index] = b;
    order[target] = a;
    await wrap(() => reorderItems(topicId, order));
  };

  return (
    <div className="stack">
      <div className="row between">
        <h3 style={{ margin: 0 }}>Elemek ({sorted.length})</h3>
        <span className="muted">Ajánlott: 8–10 elem</span>
      </div>

      <form className="row" onSubmit={addItem}>
        <input
          type="text"
          value={name}
          placeholder="Új elem neve (pl. tehén)"
          onChange={(e) => setName(e.target.value)}
        />
        <button
          type="submit"
          className="primary"
          disabled={busy || name.trim().length === 0}
        >
          Hozzáadás
        </button>
      </form>

      {error && <div className="error-box">{error}</div>}

      {sorted.length === 0 ? (
        <p className="muted">Még nincs elem. Adj hozzá egyet fent.</p>
      ) : (
        <div className="stack">
          {sorted.map((item, index) => (
            <div
              key={item.id}
              className={`item-row${item.id === selectedId ? " active" : ""}`}
            >
              <span className="pos">{String(item.position).padStart(2, "0")}</span>
              <button className="name" onClick={() => onSelect(item.id)}>
                {item.name}
              </button>
              <span className={`chip ${item.status}`}>
                {ITEM_STATUS_LABELS[item.status]}
              </span>
              <button
                className="icon-btn"
                title="Feljebb"
                disabled={busy || index === 0}
                onClick={() => void move(index, -1)}
              >
                ↑
              </button>
              <button
                className="icon-btn"
                title="Lejjebb"
                disabled={busy || index === sorted.length - 1}
                onClick={() => void move(index, 1)}
              >
                ↓
              </button>
              <button
                className="icon-btn danger"
                title="Törlés"
                disabled={busy}
                onClick={() => void removeItem(item.id)}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
