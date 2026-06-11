# workflows/ — ComfyUI „Save (API format)" sablonok

A `comfy.py` (CONTRACTS §8) ezeket a sablonokat tölti be és patcheli a futtatandó
node-azonosítók (`*.meta.json`) alapján.

## item-image.json — minimal SD txt2img sablon

Gráf: `CheckpointLoaderSimple → 2× CLIPTextEncode (pozitív/negatív) →
EmptyLatentImage (768×768) → KSampler → VAEDecode → SaveImage`.
A node-kulcsok stringek (`"3"`, `"4"`, …), ahogy a ComfyUI „Save (API format)"
exportja adja.

`item-image.meta.json` nevezi meg a patchelendő node-okat:

```json
{ "prompt_node": "6", "seed_node": "3", "save_node": "9" }
```

- `prompt_node` (`"6"`) — a pozitív `CLIPTextEncode`; ide kerül a prompt szövege.
- `seed_node` (`"3"`) — a `KSampler`; ide kerül a seed.
- `save_node` (`"9"`) — a `SaveImage`; ennek az outputjából töltjük le a PNG-t.

## FONTOS — checkpoint-cseré a Macen (ADR-7)

A `"4"` node `ckpt_name` mezője **placeholder**: `"model.safetensors"`. A Macen
a tényleges, telepített SD-checkpoint nevére kell cserélni (a ComfyUI
`models/checkpoints/` mappájában lévő fájl neve). A KONKRÉT modell licencét
kereskedelmi (monetizált YouTube) használat előtt ellenőrizni kell, és az
ADR-7 licenc-jegyzékbe be kell jegyezni (modellnév + licenc + dátum).
