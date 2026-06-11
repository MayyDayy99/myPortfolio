# 06 — Állapot és átadás (handoff)

> **Ezt olvasd el ELŐSZÖR, ha más gépen / más agentként folytatod a fejlesztést.**
> Ez a fájl a projekt *pillanatnyi* állapotát, a teljes fájltérképet (tényleges
> szignatúrákkal), a hátralévő munkát és a Mac-felállítás checklistáját rögzíti.
> Készült: **2026-06-11**, egy Windows dev gépen (multi-agent build + verifikáció).
> A koncepció Macre készült; a kód platform-független — lásd a Mac-szakaszt.

## 0. TL;DR — hol tart a projekt

A **teljes nem-Mac-specifikus MVP kód kész és verifikált.** Backend (FastAPI +
SQLite + asyncio job-sor + a teljes pipeline), teljes React+Vite+TS frontend,
F0 spike-ok (S1–S4), ComfyUI workflow-sablon, tesztek. A render-mag valódi
ffmpeg-gel bizonyítva (frame-pontos). **Hátra:** a host-/Mac-specifikus
integráció (rembg telepítés, natív ComfyUI, checkpoint, Cloudflare tunnel), az
éles E2E (T12), és néhány bekötési hiányosság (lásd §6).

| Bizonyíték | Eredmény |
|---|---|
| `cd backend && python -m pytest -q` | **77 passed, 1 skipped** (a skip a valódi rembg-teszt) |
| Golden segment-teszt (valódi ffmpeg+ffprobe) | fázishosszak **±1 frame** a `timing.py` ellen |
| `python spike/s3_segment.py` (end-to-end render) | várt **8.400 s == mért 8.400 s**, playable mp4 |
| `python -c "import app.main"` | OK, **27 route** |
| `cd frontend && npm run build` | tiszta `tsc -b && vite build`, `dist/` kész |

## 1. Gyors start másik gépen (a folytató agentnek)

1. **Vidd át a repót.** Nincs még git inicializálva — ajánlott:
   ```bash
   cd kidsvideo-factory
   git init && git add -A && git commit -m "Handoff: verified MVP (non-Mac parts)"
   ```
   A `.gitignore` már kész (kizárja `.env`, `data/`, `node_modules/`,
   `frontend/dist/`). A `data/` és a `.env` NEM kerül a repóba — ezeket a cél
   gépen hozod létre.
2. **Olvasási sorrend** (mind a repo gyökerében/`docs`-ban):
   - `CLAUDE.md` — a 10 aranyszabály + architektúra (Claude Code automatikusan betölti).
   - **`CONTRACTS.md`** — a kötelező interfész-szerződés; MINDEN modul ezt követi.
     Ha új kódot írsz, ehhez illeszd a szignatúrákat, hogy a részek továbbra is összeálljanak.
   - `docs/01-BLUEPRINT.md` … `05-DECISIONS.md` — rendszer, terv, videó-spec, runbook, ADR-ek.
   - **ez a fájl (`06-STATUS.md`)** — állapot + fájltérkép + hátralévő munka.
3. **Dev-környezet** (lásd §5 a részletekért): Python 3.12, Node 20+, ffmpeg+ffprobe
   a PATH-on. Majd:
   ```bash
   cd backend && python -m pip install -r requirements-dev.txt   # rembg nehéz; lásd §5
   python -m pytest -q                                            # elvárt: 77 passed, ~1-3 skipped
   cd ../frontend && npm install && npm run build
   ```
4. **Futtatás** (helyi, gyors iteráció):
   ```bash
   cd backend && uvicorn app.main:app --reload --port 8000   # http://localhost:8000
   ```
   A backend kiszolgálja a `frontend/dist`-et a gyökéren; ha nincs buildelve,
   magyar placeholder jelenik meg. Frontend dev-szerver külön: `cd frontend && npm run dev`.
5. **A munkamódszer** változatlan: a feladatok a `docs/02-IMPLEMENTATION-PLAN.md`-ből
   jönnek sorrendben, minden feladatnak „Kész, ha" kritériuma van — zárásnál
   bizonyítsd (teszt fut / parancs kimenete). Nagyobb feladatnál előbb terv.

## 2. Architektúra-emlékeztető (1 perc)

- **app (Docker):** FastAPI backend + React build kiszolgálva + ffmpeg + rembg +
  SQLite + `/data` kötet. Minden render/hangtisztítás itt.
- **ComfyUI:** NATÍVAN a macOS hoston (Metal GPU), headless `:8188`; a konténer
  `host.docker.internal:8188`-on hívja (ADR-2 — SOHA nem compose-ba, SOHA nem tunnelre).
- **cloudflared (Docker):** Cloudflare Tunnel, kizárólag az app-ot engedi ki,
  előtte Cloudflare Access (ADR-6).
- **Adat:** fájlrendszer (`/data`) + SQLite (meta + job-sor). Nincs Postgres/Redis.

A build egy koordinációs szerződés (`CONTRACTS.md`) köré épült, hogy a párhuzamosan
írt modulok illeszkedjenek; ezt tartsd fenn a folytatásnál is.

---

## 3. Teljes fájltérkép és publikus felület

> Ez a szakasz a **tényleges** kódból van leltározva (nem a tervből). A
> szignatúrák szó szerint a forrásból. Útvonalak a ROOT-hoz
> (`.../kidsvideo-factory`) képest.

### 3.1 Backend modulok (`backend/app/`)

Minden modul `from __future__ import annotations`; hibaüzenetek magyarul, kód angolul.

**`config.py`** — beállítások env-ből (CONTRACTS §2). `os.environ`-alapú, szándékosan
`pydantic-settings` nélkül.
- `@dataclass(frozen=True) class Settings` — `comfyui_url="http://host.docker.internal:8188"`,
  `data_dir="/data"`, `tz="Europe/Budapest"`.
- `@lru_cache(maxsize=1) def get_settings() -> Settings` — env: `COMFYUI_URL`,
  `DATA_DIR`, `TZ`. Tesztben `get_settings.cache_clear()` kell.

**`storage.py`** — útvonalak + slugify (CONTRACTS §3). Minden helper abszolút `Path`-t
ad `data_root()` alól; futásidőben csak ide írunk.
- `ITEM_ASSET_NAMES: frozenset` — engedélyezett asset-nevek (generated.png, cutout.png,
  silhouette.png, narration_a/b.webm, narration_a/b.clean.wav, segment.mp4, meta.json).
- `slugify(text) -> str` — magyar ékezet-fold + NFKD + ascii; `"tehén"→"tehen"`,
  `"tűzoltó autó"→"tuzolto-auto"`, `"Az ÉG!"→"az-eg"`.
- `data_root()`, `db_path()`, `topic_dir(slug)`, `item_dir(slug, position, item_slug)`
  (`<NN>-<slug>`, NN 2-jegyű 1-based), `render_dir(slug)`, `sfx_dir()`, `models_dir()`,
  `branding_dir()`, `ensure_tree()` (idempotens), `item_asset(item_dir, name)` (név-whitelist → ValueError).

**`db.py`** — SQLite kapcsolat + séma (CONTRACTS §4). Egy folyamatszintű kapcsolat
(`check_same_thread=False`), WAL, `foreign_keys=ON`, `sqlite3.Row`.
- `get_connection() -> sqlite3.Connection`, `reset_connection() -> None` (tesztekhez),
  `init_db() -> None` (idempotens DDL: `topic`, `item`, `job`).

**`models.py`** — pydantic v2 (CONTRACTS §5). Enumok `str`-alapúak.
- `TopicStatus(draft|in_progress|done)`, `ItemStatus(draft|image_ok|audio_ok|segment_ok)`,
  `JobKind(generate_image|cutout|clean_audio|render_segment|assemble)`, `JobState(queued|running|done|error)`.
- `Topic/TopicCreate/TopicUpdate`, `Item/ItemCreate/ItemUpdate`, `Job` (progress `Field(ge=0,le=1)`).

**`jobs.py`** — SQLite job-sor + egy asyncio worker (CONTRACTS §6). **Konkurencia:**
`_GPU_SLOT=generate_image` és egy közös `_CPU_SLOT` (sentinel: `cutout`) →
egyszerre **max 1 GPU + 1 CPU** job; minden DB-mutáció `_DB_LOCK`-kal sorosítva; a
wake-event a futó loophoz lustán kötve.
- `register(kind, fn)`, `enqueue(kind, ref_id) -> int`, `get_job(id) -> Job`,
  `async resume_pending()` (running→queued), `async worker_loop()` (lifespan-task;
  `CancelledError` = tiszta leállás). Handler-aláírás:
  `fn(job_id, ref_id, set_progress: Callable[[float],None], log: Callable[[str],None]) -> None`,
  szinkron, thread-poolban fut; bármilyen kivétel → `state=error` + magyar log; a loop sosem hal meg.

**`handlers.py`** — JobKind → pipeline hívás (CONTRACTS §6). MINDEN nehéz importot
(rembg, websocket-client, pipeline) **lustán**, a függvénytörzsben → `main.py` import
nem igényli ezeket.
- `handle_generate_image` (→ `image_ok`), `handle_cutout` (státuszt NEM állít),
  `handle_clean_audio` (loudnorm-riport a logba; → `audio_ok`), `handle_render_segment`
  (timing+segment; meta.json hash; → `segment_ok`), `handle_assemble` (→ topic `done`).
- `register_all()` — minden handler bekötése `jobs.register`-be induláskor.

**`pipeline/timing.py`** — időzítés, **egyetlen kódbeli forrás** (CONTRACTS §7,
03-VIDEO-SPEC §2). Sehol máshol nincs beégetett másodperc.
- Konstansok: `FPS=30`, `ENTRY=0.8`, `RIDDLE_PAD=0.4`, `BEAT=0.4`, `SFX_MIN=1.2`,
  `REVEAL=0.6`, `NAMING_PAD=0.5`, `HOLD=1.2`, `XFADE=0.6`, `INTRO=OUTRO=4.0`.
- `@dataclass(frozen=True) SegmentTiming` (entry,riddle,beat,sfx,reveal,naming,hold)
  + property-k: `sil_section`, `rev_section`, `xfade_offset`, `total`, `narr_a_at`,
  `sfx_at`, `narr_b_at`.
- `compute_timing(len_a, len_sfx, len_b)`, `frames(s)`, `quantize(s)`.

**`pipeline/comfy.py`** — ComfyUI-híd (CONTRACTS §8, comfyui-bridge skill). Node-id-k a
workflow `*.meta.json` sidecarból.
- `ComfyError(RuntimeError)`, `COMFY_UNREACHABLE` (magyar üzenet).
- `class ComfyClient`: `load_workflow(path)`, `generate(workflow, *, prompt_text, seed,
  prompt_node, seed_node, timeout_s=300) -> bytes` (POST `/prompt` → WS `executing/node=None`
  → `/history`+`/view`).
- `generate_image(*, prompt_text, seed, out_path, workflow_path, meta_path, base_url=None) -> None`.

**`pipeline/cutout.py`** — kivágás + sziluett (CONTRACTS §9). **rembg lazy-import**
(modul betöltéskor SOHA nem importálja; u2net session modulszintű singleton).
- `cutout(generated_path, cutout_path, silhouette_path, alpha_threshold=128) -> None`,
  `make_silhouette(img, alpha_threshold=128) -> Image` (tiszta PIL, RGB feketére, alfa binarizálva),
  `bounding_box(cutout_path) -> tuple[int,int,int,int]`.

**`pipeline/audio.py`** — hangtisztítás, valódi ffmpeg (CONTRACTS §10). Loudnorm-célok:
narráció `I=-16`, SFX `I=-18`, `TP=-1.5`, `LRA=11`, 48k.
- `clean_narration(raw_path, clean_path) -> dict` (R2 lánc; loudnorm JSON-riport),
  `normalize_sfx(raw_path, out_path) -> None` (R3), `duration_seconds(path) -> float` (ffprobe).

**`pipeline/segment.py`** — szegmens-renderer, a mag (CONTRACTS §11, ffmpeg-recipes R4).
Egyetlen ffmpeg-hívás; nincs beégetett másodperc (minden `timing`-ből, `quantize`-olva).
- `SegmentRenderError`, `class Placement`,
  `render_segment(*, background: Path|None, silhouette, cutout, narration_a, sfx: Path|None,
  narration_b, out_path, timing: SegmentTiming, canvas=(1920,1080), bg_color="#EAF4FF") -> None`,
  `segment_inputs_hash(...) -> str` (sha256 a fájl-digestekből + quantizált timing).

**`pipeline/assemble.py`** — összefűzés (CONTRACTS §12, R5). concat demuxer `-c copy`;
bukásra R1 re-encode fallback + magyar warning.
- `assemble(*, intro: Path|None, segments: list[Path], outro: Path|None, out_path, list_file,
  log=None) -> None`, `needs_rerender(item_dir, current_hash) -> bool` (a tárolt hasht a
  `meta.get("inputs_hash")` kulcsból olvassa — **lásd §6 ismert hiba**).

### 3.2 HTTP API (`backend/app/api/` + `main.py`)

`api_router = APIRouter(prefix="/api")` includeolja a topics/items/jobs/**media** alroutereket.
Hosszú művelet mindig `jobs.enqueue(...)` → `{"job_id": int}`.

| Method | Path | Request | Response | Job? |
|---|---|---|---|---|
| GET | `/api/topics` | — | `list[Topic]` | nem |
| POST | `/api/topics` | `TopicCreate` (üres cím→422); `status 200` | `Topic` | nem |
| GET | `/api/topics/{id}` | path | `Topic` (404) | nem |
| PATCH | `/api/topics/{id}` | `TopicUpdate` | `Topic` | nem |
| DELETE | `/api/topics/{id}` | path | 204 (lemezt nem törli) | nem |
| POST | `/api/topics/{id}/background` | multipart `file` → `background.png` | `Topic` | nem |
| GET | `/api/topics/{id}/items` | path | `list[Item]` | nem |
| POST | `/api/topics/{id}/items` | `ItemCreate` (auto position+slug+NN-dir) | `Item` | nem |
| POST | `/api/topics/{id}/items/reorder` | body `int[]` (teljes id-lista; eltérés→422) | `list[Item]` | nem |
| POST | `/api/topics/{id}/assemble` | path | `{job_id}` | **igen** |
| GET | `/api/items/{id}` | path | `Item` (404) | nem |
| PATCH | `/api/items/{id}` | `ItemUpdate` | `Item` | nem |
| DELETE | `/api/items/{id}` | path | 204 | nem |
| POST | `/api/items/{id}/generate-image` | query `new_seed?` ; invalidál `draft`-ra | `{job_id}` | **igen** |
| POST | `/api/items/{id}/cutout` | path; invalidál `image_ok`-ra | `{job_id}` | **igen** |
| POST | `/api/items/{id}/narration/{slot}` | `slot∈{a,b}`; multipart `file`→`narration_{slot}.webm` | `Item` | nem |
| POST | `/api/items/{id}/clean-audio/{slot}` | `slot∈{a,b}`; nincs nyers→409 | `{job_id}` | **igen** |
| POST | `/api/items/{id}/render-segment` | path | `{job_id}` | **igen** |
| GET | `/api/jobs/{id}` | path (UI 2 mp poll) | `Job` (404) | nem |
| GET | `/api/sfx` | — | `list[{name, sfx_path, media_url}]` | nem |

`main.py`: `GET /healthz` → `{"status":"ok"}`; lifespan: `ensure_tree`→`init_db`→
`resume_pending`→`register_all`→`worker_loop` (cancel-lel záródik). Mount-sorrend
**számít**: `api_router` → `/media` (read-only StaticFiles a `data_root()` felett,
`check_dir=False`) → frontend `dist` a `/`-on (`html=True`) vagy magyar placeholder —
LEGUTOLJÁRA, hogy ne árnyékolja a `/api`-t/`/media`-t.

### 3.3 Frontend (`frontend/`)

React 18 + Vite 5 + TS (strict). Nincs router, nincs külön state-lib — `fetch`-alapú
`api.ts` + `useState/useEffect`. Dev-proxy: `/api` és `/media` → `localhost:8000`.

Komponensek (`src/components/`): `TopicList`, `TopicEditor` (cím/háttér/render-beállítások,
„Videó elkészítése" + letöltő link), `ItemList` (CRUD + fel/le + reorder), `ItemEditor`
(név/prompt/seed, képgen+cutout, triptichon, narráció+hangtisztítás, SFX, szegmens-render —
minden hosszú művelet `JobProgress`-szel), `ImageTriptych` (3 kép `/media`-ról),
`SfxPicker`, `NarrationRecorder` (MediaRecorder `audio/webm;codecs=opus`, A/B felvétel
+ fájl-fallback), `JobProgress` (2 mp polling, terminál állapotnál leáll).
`api.ts`: tipizált kliens minden endpointra + `mediaUrl(path)` helper. `types.ts`:
a backend enumok/modellek TS-tükre + `TopicSettings` (fps/xfade/bg_color/music/prompt_prefix).

### 3.4 Tesztek (`backend/tests/`)

pytest (pytest-asyncio NÉLKÜL; a job-teszt saját `asyncio.run`-t használ). ffmpeg-függő
tesztek a `@requires_ffmpeg` markerrel skippelnek; a valódi rembg `pytest.importorskip`-pel.

| Fájl | Mit ellenőriz | Külső dep | Skip? |
|---|---|---|---|
| `test_slug.py` | slugify (magyar ékezet, kötőjel, idempotencia) | none | nem |
| `test_storage.py` | path-helperek, NN-zero-pad, ensure_tree, asset-whitelist | none | nem |
| `test_timing.py` | timing matek; total==fázisok összege; quantize ±1 frame | none | nem |
| `test_cutout.py` | import rembg nélkül; make_silhouette; bounding_box; (rembg-út) | PIL / rembg | csak a rembg-teszt |
| `test_audio.py` | clean_narration (mono 48k + loudnorm report), normalize_sfx, hibák | ffmpeg | igen (3 hiba-teszt fut nélküle is) |
| `test_assemble.py` | concat összhossz, relatív utak, re-encode fallback, needs_rerender | ffmpeg | igen (cache-tesztek nélküle is) |
| `test_comfy.py` | generate_image fake HTTP+WS ellen; magyar hibák | none | nem |
| `test_jobs.py` | FIFO, error-túlélés, resume_pending, GPU+CPU slot | none | nem |
| `test_segment.py` | **GOLDEN** + reveal-sync + no-sfx + bg + hash + hiányzó-input | ffmpeg | igen (ffmpeg-esek) |
| `test_api.py` | TestClient + main.py wiring (fake `jobs`) | none | nem |

A **golden** teszt (`test_segment_golden_solid_bg`) szintetikus assetekből renderel, és
ffprobe-bal ±1 frame-en belül egyezteti a `timing.py`-ból derivált hosszt — **egyetlen
beégetett másodperc sincs a tesztben**. `conftest.py`: autouse fixture `DATA_DIR`-t tmp-be
irányítja (sosem ér valódi `/data`-hoz), reseteli a settings/DB cache-t; `make_png`/`make_wav`
asset-gyárak; `requires_ffmpeg` marker. `probe_phases.py` az ffprobe-segéd (nem teszt).

### 3.5 Spike-ok, workflow-sablon, infra

- `spike/s1_comfy.py "<prompt>" [--seed N] [--base-url URL]` — kép a ComfyUI-ból (**Mac/ComfyUI kell**).
- `spike/s2_cutout.py <input.png>` — cutout+sziluett (**rembg kell**).
- `spike/s3_segment.py [out_dir]` — szegmens szintetikus assetekből (**csak ffmpeg kell**; dev gépen fut).
- `spike/s4_record/index.html` — statikus MediaRecorder-felvevő, multipart upload az
  `/api/items/{id}/narration/{slot}`-ra (**HTTPS/secure context kell** — tunnel vagy localhost).
- `workflows/item-image.json` — minimál SD txt2img „API format" gráf. Node-id-k:
  `"3"` KSampler (seed), `"4"` CheckpointLoaderSimple (**`ckpt_name="model.safetensors"` placeholder!**),
  `"5"` EmptyLatentImage 768×768, `"6"` pozitív CLIPTextEncode (prompt), `"7"` negatív,
  `"8"` VAEDecode, `"9"` SaveImage. `item-image.meta.json`:
  `{"prompt_node":"6","seed_node":"3","save_node":"9"}`.
- `backend/Dockerfile` — `python:3.12-slim` + apt `ffmpeg`; pip `requirements.txt`; `COPY app`;
  opcionálisan a Vite buildet `app/static/`-ba; CMD `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `docker-compose.yml` — `app` (build `./backend`, `./data:/data`, `127.0.0.1:8000:8000`) +
  `cloudflared` (TUNNEL_TOKEN). ComfyUI tudatosan NINCS benne (ADR-2).
- **Függőségek** — runtime: `fastapi, uvicorn[standard], python-multipart, websocket-client,
  pillow, rembg`. dev: `+ pytest, pytest-cov, httpx, ruff`. Rendszer: `ffmpeg/ffprobe`
  (Dockerben aptból), rembg futás közben letölti a **u2net** modellt.

---

## 4. Verifikáció — mi futott le tényleg ezen a gépen

- `python -m pytest -q` → **77 passed, 1 skipped** (a skip a valódi rembg-teszt; ffmpeg
  jelen volt, így a render/audio/assemble/golden tesztek FUTOTTAK, nem skippeltek).
- `spike/s3_segment.py` → valódi `segment.mp4`, várt 8.400 s == mért 8.400 s (frame-pontos).
- `import app.main` → OK (27 route). `npm run build` → tiszta tsc+vite, `dist/` kész.
- Aranyszabály-grepek: nincs beégetett másodperc a `timing.py`-on kívül; loudnorm-célok
  spec szerint; nincs commitolt `.env`/token.

> **Fontos:** ffmpeg/ffprobe NÉLKÜL a render-garanciát adó tesztek **némán skippelnek**
> (a skip nem failure). Egy új gépen/CI-ben győződj meg róla, hogy ffmpeg a PATH-on van,
> különben a `pytest` „zöld" lehet úgy is, hogy a magot valójában le sem tesztelte.

---

## 5. Környezet-felállítás új gépen

### 5.1 Cross-platform (dev, bármilyen OS)
- **Python 3.12**, **Node 20+/npm**, **ffmpeg + ffprobe** a PATH-on.
- Backend: `cd backend && python -m pip install -r requirements-dev.txt`.
  - A `rembg` **nehéz** (onnxruntime + modell). Ha csak a nem-cutout részen dolgozol,
    kihagyhatod (a kód lazy-importál); a `test_cutout` rembg-ága ilyenkor skippel.
    Cutout-fejlesztéshez: `python -m pip install rembg` (első futáskor letölti a u2net-et).
- Frontend: `cd frontend && npm install && npm run build` (vagy `npm run dev`).
- Teszt: `cd backend && python -m pytest -q` (elvárt: 77 passed; rembg nélkül +1 skip).

### 5.2 Mac-specifikus checklista (a cél-üzemmód — runbook: `docs/04`)
Ezek a részek **szándékosan nincsenek kódban** — a Macen kell beállítani:

1. **rembg + modell:** `pip install rembg` a backend image-be már bekerül; natív
   futtatásnál a u2net modell első híváskor töltődik a `data/models` alá.
2. **ComfyUI natívan (Metal GPU):** telepítés külön venv-be, indítás
   `python main.py --listen 127.0.0.1 --port 8188` (csak gépen belülről!), launchd-vel
   háttérszolgáltatásként — a plist-sablon a `docs/04` §1.3-ban. Füstteszt:
   `docker compose run app curl -s http://host.docker.internal:8188/system_stats`, majd
   `python spike/s1_comfy.py "egy piros alma"`.
3. **SD checkpoint:** tedd a `~/comfy/ComfyUI/models/checkpoints` alá, és írd be a
   tényleges fájlnevét a `workflows/item-image.json` `"4"` node `ckpt_name` mezőjébe
   (most `model.safetensors` placeholder). A modell **licencét** kereskedelmi (monetizált
   YouTube) használat előtt ellenőrizd, és jegyezd be az **ADR-7** licenc-jegyzékbe (`docs/05`).
4. **Cloudflare Tunnel + Access:** a tunnel tokent a `.env` `TUNNEL_TOKEN`-jébe; public
   hostname → `http://app:8000`; Access-policy csak a saját e-mailedre; a 8188 SOHA nem
   publikus (ADR-6). Részletek: `docs/04` §2.
5. **Alvás/üzemmód:** `docs/04` §1.4 (ajánlott: fedél nyitva, kijelző sötét, tápon).
6. **Linux hoston** (ha valaha): a `docker-compose.yml` `app` service-éhez fel kell oldani
   az `extra_hosts: ["host.docker.internal:host-gateway"]` sort (most kommentben).

---

## 6. Ismert hiányosságok és következő lépések (prioritizált)

> Ezek az adversariális kód-leltár során derültek ki. A tesztek zöldek, de ezek a
> bekötési/finomítási pontok hátravannak. Sorrend: hatás szerint.

### P1 — Szegmens-cache nincs bekötve (T11 „Kész, ha" még nem teljesül)
- **Tünet:** a „csak a változott szegmens renderelődik újra" elv (01-BLUEPRINT §6.3,
  T11) nem működik.
- **Ok 1 (kulcs-eltérés):** `handlers.handle_render_segment` a `meta.json`-t
  `{"segment_hash": ...}` kulccsal írja, de `assemble.needs_rerender` a
  `meta.get("inputs_hash")` kulcsból olvas → mindig `True`-t adna.
- **Ok 2 (nincs hívva):** `needs_rerender` sehol nincs meghívva; `handle_render_segment`
  feltétel nélkül mindig újrarendel, az `assemble` pedig a meglévő `segment.mp4`-eket fűzi.
- **Teendő:** (a) egységesítsd a meta-kulcsot (`inputs_hash` mindkét oldalon) és írd be a
  `segment_inputs_hash(...)` eredményét; (b) a render-segment job (vagy egy orchestrációs
  réteg az assemble-ben) hívja `needs_rerender`-t és skippelje a változatlan elemet;
  (c) golden-jellegű teszt: elem narrációjának cseréje után CSAK az az egy szegmens renderelődik (T11).

### P2 — UI-szöveg aranyszabály (#9) inkonzisztencia
- `frontend/src/components/ItemEditor.tsx` ~134. sor: a státusz-chip a nyers angol enumot
  írja ki (`image_ok`), míg az `ItemList` magyar `ITEM_STATUS_LABELS`-t használ.
- **Teendő:** használd ugyanazt a magyar címke-térképet az `ItemEditor`-ban is.

### P3 — clean-audio job a slotot nem hordozza
- A `clean-audio/{slot}` route „bare item" ref-et enqueue-ol; `handle_clean_audio`
  a lemezen talált MINDKÉT nyers sávot tisztítja, a `slot`-ot figyelmen kívül hagyva.
- **Teendő (ha per-slot kell):** add át a slotot a job-nak (pl. `ref_id` mellé egy kis
  payload, vagy külön JobKind/konvenció), és a handler csak azt tisztítsa.

### P4 — Narráció-feltöltés mindig `.webm` kiterjesztéssel ment
- `api/items.py upload_narration`: a feltöltés `narration_{slot}.webm`-ként landol a
  tényleges formátumtól függetlenül (wav is). A tisztítólánc ffmpeg-gel tartalom alapján
  dolgozik, így működik, de a fájlnév félrevezető (a séma `narration_a.(webm|wav)`).
- **Teendő:** a kiterjesztést a feltöltött MIME/fájlnévből vezesd le.

### P5 — Apróságok / megfontolások
- `requirements.txt` **nincs verzió-pinelve** → nem reprodukálható build. Az első sikeres
  Mac-telepítés után érdemes `pip freeze`-ből pinelni (és az ADR-7-be a verziókat).
- `handle_cutout` nem állít elem-státuszt (a state-gépben nincs „cutout" állapot — ez rendben
  lehet, de tudatos döntés legyen).
- `comfy.ComfyClient.generate` a history-ból az ELSŐ képet veszi; a `save_node`-ot csak
  létezésre ellenőrzi. Egy SaveImage node-nál OK; több esetén nem determinisztikus.
- A frontend (`ImageTriptych`, `finalVideoUrl`) a storage-layoutot a kliensen kódolja le
  (a backend nem ad per-asset URL-t) — ha a `CONTRACTS §3` layout változik, némán törik.
- `timing.XFADE/INTRO/OUTRO` definiált, de a segment/assemble nem használja: az elemek
  közti átmenet jelenleg **vágás** (concat), nem xfade; az intro/outro fix branding-klippek.
  Az elemek közti xfade az F2 körébe tartozik (03-VIDEO-SPEC §1: „crossfade VAGY vágás").
- `delete_topic`/`delete_item` a lemezt nem takarítja (árva mappák maradhatnak a `/data`-ban).

### Roadmap-emlékeztető (a `docs/02`-ből, ami még hátra)
- **T12 — E2E éles videó:** egy valódi 8–10 elemes téma végigvitele a rendszeren, a
  03-VIDEO-SPEC §7 ellenőrzőlistájával; final.mp4 unlisted YouTube-ra. (Macen, a §5.2 után.)
- **F2** — gyártósor-nézet, háttérzene+ducking (R6), intro/outro-szerkesztő, szegmens-előnézet,
  prompt-stílus sablonok. **F3** — YouTube-feltöltés (Data API), TTS, Shorts 9:16.

---

## 7. Konvenciók a folytatáshoz (ne sértsd meg)

- A 10 aranyszabály: `CLAUDE.md`. Az interfész-szerződés: `CONTRACTS.md` — új kódot ehhez illessz.
- **Időzítés/dramaturgia** csak `docs/03-VIDEO-SPEC.md` + `pipeline/timing.py`; sehol beégetett másodperc.
- **ffmpeg** csak az `.claude/skills/ffmpeg-recipes` mintáiból; **ComfyUI** csak az
  `.claude/skills/comfyui-bridge` mintából. Új recept → vissza a skillbe.
- Hosszú művelet mindig **job** (sosem blokkol HTTP-t). Futásidőben csak `/data` alá írunk.
- UI **magyar**, kód/komment **angol**. Titok csak `.env` (gitignore-olva).
- Új függőség/modell/SFX → az **ADR-7** licenc-jegyzék (`docs/05`) frissül UGYANABBAN a változtatásban.
- Teszt-fegyelem: minden „Kész, ha"-t bizonyíts; a render-magot ffmpeg-es teszt védi
  (győződj meg, hogy ffmpeg a PATH-on van, különben a tesztek némán skippelnek).
