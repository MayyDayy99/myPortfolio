import { useEffect, useState } from "react";
import { listSfx, mediaUrl } from "../api";
import type { Item, SfxEntry } from "../types";

interface SfxPickerProps {
  item: Item;
  /** Persists the chosen sfx path onto the item (null clears it). */
  onAssign: (sfxPath: string | null) => Promise<void> | void;
}

/** Resolve a playable URL for an sfx entry (prefer an explicit url field). */
function sfxPreviewUrl(entry: SfxEntry): string {
  return entry.url ?? mediaUrl(entry.path) ?? "";
}

/**
 * Lists the shared sound-effect library (data/sfx), lets the user preview each
 * one and assign / clear it for the current item.
 */
export default function SfxPicker({ item, onAssign }: SfxPickerProps) {
  const [entries, setEntries] = useState<SfxEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listSfx()
      .then((list) => {
        if (!cancelled) {
          setEntries(list);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "A hangeffekt-könyvtár nem tölthető be.",
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

  const assign = async (path: string | null) => {
    setBusy(true);
    setError(null);
    try {
      await onAssign(path);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "A hozzárendelés nem sikerült.",
      );
    } finally {
      setBusy(false);
    }
  };

  // Match by path; the item stores a storage-relative or absolute sfx_path.
  const isAssigned = (entry: SfxEntry): boolean => {
    if (!item.sfx_path) {
      return false;
    }
    return (
      item.sfx_path === entry.path ||
      item.sfx_path.replace(/\\/g, "/").endsWith(entry.name)
    );
  };

  return (
    <div className="stack">
      <div className="row between">
        <h3 style={{ margin: 0 }}>Hangeffekt</h3>
        {item.sfx_path && (
          <button
            className="danger icon-btn"
            disabled={busy}
            onClick={() => void assign(null)}
          >
            Hozzárendelés törlése
          </button>
        )}
      </div>
      <p className="muted">
        Csak jogtiszta hangokat tölts be a könyvtárba (forrás/licenc
        megőrzésével).
      </p>
      {error && <div className="error-box">{error}</div>}
      {loading ? (
        <p className="muted">Betöltés…</p>
      ) : entries.length === 0 ? (
        <p className="muted">
          A hangeffekt-könyvtár üres (data/sfx). Tölts fel hangokat a Mac
          gépen.
        </p>
      ) : (
        <div className="sfx-list">
          {entries.map((entry) => {
            const assigned = isAssigned(entry);
            return (
              <div
                key={entry.path}
                className={`sfx-row${assigned ? " assigned" : ""}`}
              >
                <span className="sfx-name">{entry.name}</span>
                <audio controls preload="none" src={sfxPreviewUrl(entry)} />
                <button
                  className={assigned ? "" : "primary"}
                  disabled={busy || assigned}
                  onClick={() => void assign(entry.path)}
                >
                  {assigned ? "Hozzárendelve" : "Hozzárendelés"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
