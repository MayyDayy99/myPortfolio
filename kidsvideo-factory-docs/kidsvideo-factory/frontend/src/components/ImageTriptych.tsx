import { mediaUrl } from "../api";
import type { Item, Topic } from "../types";

interface ImageTriptychProps {
  topic: Topic;
  item: Item;
  /** Bumped by the parent to bust the browser cache after a regenerate. */
  refreshKey?: number;
}

/**
 * Shows the three pipeline images side by side: raw (generated.png), cutout
 * (cutout.png) and silhouette (silhouette.png), served from `/media`.
 *
 * The backend does not return per-asset URLs, but the storage layout is fixed
 * (CONTRACTS §3): assets live at
 *   projects/<topic.slug>/items/<NN>-<item.slug>/<asset>.png
 * so we derive the media path from the topic slug, item position and item slug.
 */
function itemAssetUrl(
  topic: Topic,
  item: Item,
  asset: "generated.png" | "cutout.png" | "silhouette.png",
  refreshKey?: number,
): string {
  const nn = String(item.position).padStart(2, "0");
  const path = `projects/${topic.slug}/items/${nn}-${item.slug}/${asset}`;
  const base = mediaUrl(path) ?? "";
  return refreshKey ? `${base}?v=${refreshKey}` : base;
}

function Frame({ src, caption }: { src: string; caption: string }) {
  // We always render the <img>; if the asset does not exist yet the onError
  // handler swaps in the placeholder text by hiding the broken image.
  return (
    <figure>
      <div className="image-frame">
        <img
          src={src}
          alt={caption}
          onError={(e) => {
            const el = e.currentTarget;
            el.style.display = "none";
            const parent = el.parentElement;
            if (parent && !parent.querySelector(".ph")) {
              const ph = document.createElement("span");
              ph.className = "ph muted";
              ph.textContent = "Még nincs kép";
              parent.appendChild(ph);
            }
          }}
        />
      </div>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

export default function ImageTriptych({
  topic,
  item,
  refreshKey,
}: ImageTriptychProps) {
  return (
    <div className="triptych">
      <Frame
        src={itemAssetUrl(topic, item, "generated.png", refreshKey)}
        caption="Nyers kép"
      />
      <Frame
        src={itemAssetUrl(topic, item, "cutout.png", refreshKey)}
        caption="Kivágás"
      />
      <Frame
        src={itemAssetUrl(topic, item, "silhouette.png", refreshKey)}
        caption="Sziluett"
      />
    </div>
  );
}
