import { useEffect, useRef, useState } from "react";
import { uploadNarration } from "../api";
import type { Item, NarrationSlot } from "../types";

const MIME_TYPE = "audio/webm;codecs=opus";

interface SlotState {
  recording: boolean;
  /** Object URL of the locally recorded/selected take, for playback. */
  previewUrl: string | null;
  /** The blob to upload (recorded or file-selected). */
  blob: Blob | null;
  uploading: boolean;
  error: string | null;
  /** True once the take has been uploaded to the backend. */
  uploaded: boolean;
}

const emptySlot = (): SlotState => ({
  recording: false,
  previewUrl: null,
  blob: null,
  uploading: false,
  error: null,
  uploaded: false,
});

interface NarrationRecorderProps {
  item: Item;
  /** Called with the updated item after a successful upload. */
  onUploaded: (item: Item) => void;
}

const SLOT_LABELS: Record<NarrationSlot, string> = {
  a: "A narráció — találós (körülírás, NEM mondja ki a nevet)",
  b: "B narráció — megnevezés („Ez a(z) …!”)",
};

/** Pick a supported recording mime type, preferring opus webm. */
function supportedMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") {
    return null;
  }
  if (MediaRecorder.isTypeSupported(MIME_TYPE)) {
    return MIME_TYPE;
  }
  if (MediaRecorder.isTypeSupported("audio/webm")) {
    return "audio/webm";
  }
  return null;
}

/**
 * Records narration takes for slots A and B with the MediaRecorder API
 * (audio/webm;codecs=opus): record → stop → play back → re-record, plus a
 * file-upload fallback. On upload the raw take is POSTed to
 * `/api/items/{id}/narration/{slot}` and the returned item is bubbled up.
 */
export default function NarrationRecorder({
  item,
  onUploaded,
}: NarrationRecorderProps) {
  return (
    <div className="stack">
      <h3 style={{ margin: 0 }}>Narráció felvétele</h3>
      <NarrationSlotEditor item={item} slot="a" onUploaded={onUploaded} />
      <NarrationSlotEditor item={item} slot="b" onUploaded={onUploaded} />
    </div>
  );
}

function NarrationSlotEditor({
  item,
  slot,
  onUploaded,
}: {
  item: Item;
  slot: NarrationSlot;
  onUploaded: (item: Item) => void;
}) {
  const [state, setState] = useState<SlotState>(emptySlot);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  // Revoke the object URL when it changes or the component unmounts.
  useEffect(() => {
    previewUrlRef.current = state.previewUrl;
  }, [state.previewUrl]);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const patch = (next: Partial<SlotState>) =>
    setState((prev) => ({ ...prev, ...next }));

  const setPreview = (blob: Blob | null) => {
    setState((prev) => {
      if (prev.previewUrl) {
        URL.revokeObjectURL(prev.previewUrl);
      }
      return {
        ...prev,
        blob,
        previewUrl: blob ? URL.createObjectURL(blob) : null,
        uploaded: false,
        error: null,
      };
    });
  };

  const startRecording = async () => {
    const mime = supportedMimeType();
    if (!mime) {
      patch({
        error:
          "A böngésző nem támogatja a hangrögzítést. Használd a fájl-feltöltést.",
      });
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      patch({
        error:
          "Nincs mikrofon-hozzáférés (HTTPS és engedély szükséges). Használd a fájl-feltöltést.",
      });
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream, { mimeType: mime });
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mime });
        setPreview(blob);
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      };
      recorderRef.current = recorder;
      recorder.start();
      patch({ recording: true, error: null });
    } catch {
      patch({
        error:
          "A mikrofon nem indítható. Ellenőrizd az engedélyt, vagy tölts fel fájlt.",
      });
    }
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    patch({ recording: false });
  };

  const onFileSelected = (file: File | undefined) => {
    if (!file) {
      return;
    }
    setPreview(file);
  };

  const upload = async () => {
    if (!state.blob) {
      return;
    }
    patch({ uploading: true, error: null });
    try {
      // Choose a filename extension that matches the blob type so the backend
      // routes webm vs. wav correctly.
      const isWebm = state.blob.type.includes("webm");
      const ext = isWebm ? "webm" : state.blob.type.includes("wav") ? "wav" : "webm";
      const filename = `narration_${slot}.${ext}`;
      const updated = await uploadNarration(item.id, slot, state.blob, filename);
      patch({ uploading: false, uploaded: true });
      onUploaded(updated);
    } catch (err) {
      patch({
        uploading: false,
        error:
          err instanceof Error ? err.message : "A feltöltés nem sikerült.",
      });
    }
  };

  return (
    <div className={`recorder-slot${state.recording ? " recording" : ""}`}>
      <label>{SLOT_LABELS[slot]}</label>
      <div className="row">
        {!state.recording ? (
          <button className="primary" onClick={() => void startRecording()}>
            {state.blob ? "Újrafelvétel" : "Felvétel"}
          </button>
        ) : (
          <button className="danger" onClick={stopRecording}>
            <span className="rec-dot" />
            Stop
          </button>
        )}

        <span className="spacer" />

        <label
          className="muted"
          style={{ margin: 0, cursor: "pointer" }}
          title="Fájl feltöltése felvétel helyett"
        >
          Fájl feltöltése
          <input
            type="file"
            accept="audio/webm,audio/wav,audio/x-wav,.webm,.wav"
            style={{ display: "none" }}
            onChange={(e) => onFileSelected(e.target.files?.[0])}
          />
        </label>
      </div>

      {state.previewUrl && (
        <audio controls src={state.previewUrl} />
      )}

      {state.blob && (
        <div className="row" style={{ marginTop: 8 }}>
          <button
            className="primary"
            disabled={state.uploading || state.uploaded}
            onClick={() => void upload()}
          >
            {state.uploaded
              ? "Feltöltve"
              : state.uploading
                ? "Feltöltés…"
                : "Feltöltés a szerverre"}
          </button>
        </div>
      )}

      {state.error && <div className="error-box">{state.error}</div>}
    </div>
  );
}
