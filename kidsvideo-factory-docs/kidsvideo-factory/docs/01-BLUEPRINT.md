# 01 — Technikai blueprint

## 1. Rendszerkép

```
 [Te, másik gép] ── böngésző (HTTPS) ──► Cloudflare (Access: csak te)
                                              │  Tunnel
                  ┌───────────── M5 MacBook Pro (csukva, tápon) ─────────────┐
                  │  Docker Desktop                                          │
                  │  ┌──────────────┐      ┌──────────────────────────────┐  │
                  │  │ cloudflared  │ ───► │ app  (FastAPI + React build) │  │
                  │  └──────────────┘      │  • ffmpeg (vágás, hang)      │  │
                  │                        │  • rembg (kivágás/sziluett)  │  │
                  │                        │  • SQLite (meta + jobok)     │  │
                  │                        │  • /data kötet               │  │
                  │                        └───────────────┬──────────────┘  │
                  │                         host.docker.internal:8188        │
                  │                                        ▼                 │
                  │            ComfyUI — NATÍV macOS folyamat (Metal GPU)    │
                  └──────────────────────────────────────────────────────────┘
```

Kulcsdöntés: a ComfyUI **nem** konténerben fut, mert Dockerben a Macen nincs
Metal GPU-hozzáférés (ADR-2). Minden más a compose-ban él. A tunnelen kizárólag
az `app` látszik; a ComfyUI a gépen belül marad.

## 2. Komponensek és felelősségek

| Komponens | Technológia | Felelősség |
|---|---|---|
| frontend | React 18 + Vite + TS | téma/elem-szerkesztő, mikrofonos felvétel (MediaRecorder), előnézet, job-progress |
| backend | Python 3.12 + FastAPI + uvicorn | API, statikus frontend kiszolgálása, job-sor, pipeline hívása |
| pipeline | Python modulok | comfy-híd, kivágás+sziluett, hangtisztítás, szegmens-render, összefűzés |
| render | ffmpeg (konténerben) | szegmensek és végső MP4 előállítása, audió-lánc |
| képgen | ComfyUI (natív, host) | SD képgenerálás workflow-sablonból, API-n át |
| kivágás | rembg + u2net (ONNX) | háttér eltávolítása → cutout (RGBA) → sziluett |
| tárolás | fájlrendszer + SQLite | assetek a /data alatt; metaadat + jobok DB-ben |
| kijárat | cloudflared + CF Access | HTTPS URL, hitelesítés a tulajnak |

## 3. Adatmodell

SQLite (a `/data/db.sqlite3` fájlban):

- **topic** — `id, slug, title, status, background_path, settings_json, created_at`
  - `settings_json`: időzítés-felülbírálások, fps, zene be/ki stb. (alap a 03-VIDEO-SPEC)
- **item** — `id, topic_id, position, slug, name, prompt, seed, sfx_path, status`
  - státuszgép: `draft → image_ok → audio_ok → segment_ok`
- **job** — `id, kind(generate_image|cutout|clean_audio|render_segment|assemble),
  ref_id, state(queued|running|done|error), progress, log, created_at, updated_at`

Fájlséma (`/data` kötet):
```
data/
  projects/<topic-slug>/
    background.png                # opcionális téma-háttér
    items/<NN>-<item-slug>/
      generated.png               # ComfyUI nyers kimenet
      cutout.png                  # rembg: RGBA kivágás
      silhouette.png              # fekete kitöltés a cutout alfájából
      narration_a.(webm|wav)      # nyers felvétel (körülírás)
      narration_a.clean.wav       # tisztított, normalizált
      narration_b.(webm|wav)      # nyers (név + mondat)
      narration_b.clean.wav
      segment.mp4                 # az elem kész szegmense
      meta.json                   # hash-ek a cache-hez (lásd 6.3)
    render/final.mp4              # a kész videó
  sfx/                            # saját SFX-könyvtár (licenc: ADR-7)
  models/                         # rembg modell-cache
  db.sqlite3
```

## 4. API-vázlat (a véglegesítés T3 feladat)

```
GET/POST/PATCH   /api/topics, /api/topics/{id}
GET/POST/PATCH   /api/topics/{id}/items, /api/items/{id}
POST   /api/items/{id}/generate-image      → job (ComfyUI)
POST   /api/items/{id}/cutout              → job (rembg + sziluett)
POST   /api/items/{id}/narration/{a|b}     → multipart feltöltés (webm/wav)
POST   /api/items/{id}/clean-audio/{a|b}   → job (ffmpeg lánc)
POST   /api/items/{id}/render-segment      → job
POST   /api/topics/{id}/assemble           → job (teljes videó)
GET    /api/jobs/{id}                      → állapot + progress + log
GET    /media/...                          → /data kiszolgálás (előnézetek)
```

## 5. A három fő pipeline

**(P1) Kép → kivágás → sziluett**
1. prompt + seed → `pipeline/comfy.py` beküldi a workflow-sablont
   (`workflows/item-image.json`, `POST /prompt`), websocketen várja a végét,
   `/history` + `/view` útvonalon letölti a PNG-t → `generated.png`.
2. `pipeline/cutout.py`: rembg(u2net) → `cutout.png` (RGBA); a sziluett a
   cutout alfa-csatornájának fekete kitöltése → `silhouette.png`.
   A rembg session **singleton** (egyszer töltődik a modell).

**(P2) Narráció → tisztított hang**
Böngészőből MediaRecorder (`audio/webm;codecs=opus`) → feltöltés → ffmpeg lánc:
felbontás-egységesítés (48 kHz mono) → zajszűrés → csend-vágás az elejéről/
végéről → loudnorm. Pontos parancsok: `ffmpeg-recipes` skill.

**(P3) Szegmens-render → összefűzés**
`pipeline/segment.py` a 03-VIDEO-SPEC idővonala szerint, az elem assetjeiből
megépíti a `segment.mp4`-et (azonos kódolási paraméterekkel!). Az `assemble.py`
intro + szegmensek + outro sorrendben, concat demuxerrel fűzi össze →
`render/final.mp4` (YouTube-kész H.264).

## 6. Keresztmetszeti kérdések

**6.1 Job-rendszer** — egy asyncio worker-loop a backend folyamatban; a jobok
SQLite-ban perzisztálnak (újraindítás-állók); egyszerre 1 GPU-igényes job
(képgen) + 1 CPU-job (render) futhat. Progress a `job.progress` mezőben, a UI
2 mp-enként pollozza (v2: SSE).

**6.2 Hibakezelés** — minden job-hiba ember által olvasható magyar üzenetet kap
a `job.log`-ba (pl. „A ComfyUI nem érhető el — fut a Macen? (8188-as port)").

**6.3 Szegmens-cache** — a `meta.json` tartalmazza a bemenetek hash-ét
(kép + 2 hang + sfx + időzítés-config). Az `assemble` csak azokat a
szegmenseket rendereli újra, amelyek hash-e változott. Így egy elem javítása
nem jelent teljes újrarenderelést.

**6.4 Biztonság** — kifelé csak a tunnel; előtte Cloudflare Access (e-mail OTP,
csak a tulaj). A ComfyUI (8188) és a backend portja (8000) nem publikált a
LAN felé sem (compose: `127.0.0.1:8000:8000` csak debugra). Mikrofon: a tunnel
HTTPS-t ad, így a `getUserMedia` működik.

**6.5 Kimeneti formátum** — 1920×1080, 30 fps, H.264 (libx264, CRF 18, high),
yuv420p, AAC 192 kbps 48 kHz sztereó, `+faststart`. Részletek: ffmpeg-recipes.

## 7. Stack és licencek (a teljes jegyzék: 05-DECISIONS / ADR-7)

| Csomag | Licenc | Megjegyzés |
|---|---|---|
| FastAPI, uvicorn, React, Vite | MIT/BSD | — |
| rembg | MIT | u2net modell: Apache-2.0 ✔ |
| ffmpeg (libx264-gyel) | GPL | belső szerver-használat — nem terjesztjük |
| ComfyUI | GPL-3.0 | külön natív folyamat, API-n át hívva |
| SD checkpoint (felhasználó választja) | OpenRAIL-jellegű | kereskedelmi használat előtt a konkrét modell licencét ellenőrizni KELL |
| SFX-könyvtár | — | csak redistribution/sync jogú hangok kerülhetnek a data/sfx alá |
