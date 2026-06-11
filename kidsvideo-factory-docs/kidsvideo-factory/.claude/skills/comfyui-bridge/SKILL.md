---
name: comfyui-bridge
description: A headless ComfyUI hívása a natív macOS hostról (host.docker.internal:8188) — prompt beküldése, websocket-várakozás, kép letöltése, workflow-sablon kezelés, hibakezelés. Használd minden képgenerálással, ComfyUI-jal, workflow JSON-nal, /prompt vagy 8188 porttal kapcsolatos feladatnál. (ComfyUI, image generation, Stable Diffusion, prompt, workflow, websocket)
---

# ComfyUI-híd — kanonikus minta

## Architektúra-emlékeztető (MIÉRT így)
A ComfyUI **natívan** fut a Macen (Metal GPU), mert Dockerben macOS-en nincs
GPU-passthrough (ADR-2). A konténerből a cím: `http://host.docker.internal:8188`
(env: `COMFYUI_URL`). A ComfyUI-t SOHA ne tedd a compose-ba, SOHA ne engedd ki
a tunnelen (ADR-6) — ha ilyen kérés merül fel, állj meg és hivatkozz az ADR-re.

## A folyamat (ADR-5)
1. **Sablon**: a workflow a UI-ból „Save (API format)"-tal exportált JSON, a
   repo `workflows/` mappájában (pl. `item-image.json`). A sablonban a
   módosítandó node-okat ID szerint érjük el; a node-ID-k a sablon részei.
2. **Beküldés**: `POST {COMFYUI_URL}/prompt` body:
   `{"prompt": <workflow-json>, "client_id": "<uuid>"}` → válasz: `prompt_id`.
3. **Várakozás**: WS `ws://.../ws?clientId=<uuid>` — a futás végét az jelzi,
   hogy `executing` üzenet érkezik `node: null` + a mi `prompt_id`-nkkal.
4. **Letöltés**: `GET /history/{prompt_id}` → a SaveImage node outputjából
   `filename/subfolder/type` → `GET /view?filename=...&subfolder=...&type=...`
   → PNG-bájtok.

## Kanonikus kliens (pipeline/comfy.py magja)

```python
import json, uuid, urllib.request, urllib.parse, copy
import websocket  # websocket-client csomag

class ComfyClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")           # http://host.docker.internal:8188
        self.ws_base = self.base.replace("http", "ws", 1)

    def load_workflow(self, path: str) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def generate(self, workflow: dict, *, prompt_text: str, seed: int,
                 prompt_node: str, seed_node: str, timeout_s: int = 300) -> bytes:
        wf = copy.deepcopy(workflow)
        wf[prompt_node]["inputs"]["text"] = prompt_text     # pozitív prompt node
        wf[seed_node]["inputs"]["seed"] = seed              # KSampler node
        client_id = str(uuid.uuid4())

        req = urllib.request.Request(
            f"{self.base}/prompt",
            data=json.dumps({"prompt": wf, "client_id": client_id}).encode(),
            headers={"Content-Type": "application/json"})
        prompt_id = json.loads(urllib.request.urlopen(req, timeout=15).read())["prompt_id"]

        ws = websocket.WebSocket()
        ws.connect(f"{self.ws_base}/ws?clientId={client_id}", timeout=timeout_s)
        try:
            while True:
                msg = ws.recv()
                if isinstance(msg, str):
                    m = json.loads(msg)
                    if (m.get("type") == "executing"
                            and m["data"].get("node") is None
                            and m["data"].get("prompt_id") == prompt_id):
                        break                                # kész
        finally:
            ws.close()

        hist = json.loads(urllib.request.urlopen(
            f"{self.base}/history/{prompt_id}", timeout=15).read())[prompt_id]
        img = next(im for node in hist["outputs"].values()
                   for im in node.get("images", []))
        q = urllib.parse.urlencode({"filename": img["filename"],
                                    "subfolder": img["subfolder"],
                                    "type": img["type"]})
        return urllib.request.urlopen(f"{self.base}/view?{q}", timeout=30).read()
```

A node-ID-k (`prompt_node`, `seed_node`) sablononként mások — a sablon mellé
tegyél egy `item-image.meta.json`-t, ami megnevezi őket; a kód onnan olvassa.

## Hibakezelés (kötelező viselkedés)
- **ConnectionRefused / timeout a /prompt-on** → job-hiba magyar üzenettel:
  „A ComfyUI nem érhető el — fut a Macen? (Runbook: docs/04, 6. pont)".
- **WS-timeout** (lassú generálás) → a `timeout_s` paraméterezhető; lejártakor
  a job `error`, a log tartalmazza a prompt_id-t (kézzel visszakereshető).
- **Üres `images` a historyban** → a workflow-ban nincs SaveImage node, vagy a
  futás ComfyUI-oldalon hibázott → a history `status` mezőjét írd a logba.
- Egyszerre **1 generálás** fut (a job-rendszer konkurencia-szabálya) — a
  ComfyUI-nak saját sora van, de a kiszámítható progress miatt mi adagolunk.

## Gyorstesztek
```bash
curl -s $COMFYUI_URL/system_stats | head -c 200      # él-e
curl -s $COMFYUI_URL/object_info | head -c 200       # node-katalógus (sablonkészítéshez)
```

## Új workflow felvétele (folyamat)
1. UI-ban összerakod → dev mode → **Save (API format)** → `workflows/<név>.json`
2. Meta-fájl a módosítandó node-ID-kkel (`<név>.meta.json`)
3. Füstteszt: `python spike/s1_comfy.py` mintájára egy hívás
4. ADR-7 licenc-jegyzék frissítése, ha új modell/custom node kell hozzá
