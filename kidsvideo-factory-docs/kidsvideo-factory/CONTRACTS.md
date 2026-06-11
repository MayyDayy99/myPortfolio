# CONTRACTS.md — kötelező interfész-szerződés (build-koordináció)

> Ez a fájl az implementáló agentek közös szerződése. MINDEN modul ezeket a
> jelöléseket, útvonalakat és aláírásokat használja, hogy a párhuzamosan írt
> kódrészek illeszkedjenek. Ütközés esetén: a `docs/` spec nyer, ez a fájl a
> spec konkrét leképezése. Idő mindig másodperc. UI-szöveg magyar, kód angol.

## 0. Repo-gyökér és futtatókörnyezet

- ROOT (Windows dev): `C:\Users\EDTI\KidsVideoFactory\kidsvideo-factory-docs\kidsvideo-factory`
- A projekt Macre költözik; a kód platform-független Python/TS. NE írj
  Mac-specifikus kódot (launchd, pmset, Metal) — az a `docs/04`-ben marad.
- Elérhető a dev gépen: Python 3.12, ffmpeg 8 + ffprobe, Node 24/npm, pytest.
- NEM elérhető: `rembg` (lazy-import!), ComfyUI (:8188), Cloudflare tunnel.

## 1. Fájlfa (cél)

```
backend/
  Dockerfile
  requirements.txt
  requirements-dev.txt
  pyproject.toml            # csak [tool.pytest.ini_options] + ruff config
  app/
    __init__.py
    main.py                 # FastAPI app, static serve, /healthz, routerek
    config.py               # Settings (env → COMFYUI_URL, DATA_DIR, TZ)
    storage.py              # útvonal-helperek, slugify, séma-init a /data alatt
    db.py                   # sqlite3 connection + DDL + migrációs init
    models.py               # pydantic sémák + enumok (TopicStatus, ItemStatus, JobKind, JobState)
    jobs.py                 # SQLite job-sor + asyncio worker + handler-registry
    api/
      __init__.py           # api_router = APIRouter(); minden alrouter beincludeolva
      topics.py
      items.py
      jobs.py
      media.py
    pipeline/
      __init__.py
      timing.py             # a 03-VIDEO-SPEC §2 EGYETLEN kódbeli forrása
      comfy.py              # ComfyClient (comfyui-bridge skill)
      cutout.py             # rembg cutout + sziluett
      audio.py              # ffmpeg narráció-tisztítás + sfx-normalizálás
      segment.py            # szegmens-renderer (a mag) — ffmpeg-recipes R4
      assemble.py           # concat összefűzés — ffmpeg-recipes R5
  tests/
    conftest.py             # DATA_DIR→tmp fixture, asset-gyárak, ffmpeg-skip jelölők
    probe_phases.py         # ffprobe segéd: szegmens fázishatárok mérése
    test_slug.py
    test_storage.py
    test_timing.py
    test_jobs.py
    test_comfy.py           # mock HTTP/WS szerver ellen
    test_cutout.py          # szintetikus alfa-kép; rembg-skip ha nincs telepítve
    test_audio.py           # valódi ffmpeg, szintetikus wav
    test_segment.py         # GOLDEN: valódi ffmpeg+ffprobe, fázishosszak ±1 frame
    test_assemble.py        # valódi ffmpeg concat
    test_api.py             # FastAPI TestClient
frontend/
  package.json  vite.config.ts  tsconfig.json  tsconfig.node.json  index.html
  .eslintrc.cjs
  src/
    main.tsx  App.tsx  api.ts  types.ts  styles.css
    components/
      TopicList.tsx  TopicEditor.tsx  ItemEditor.tsx  ItemList.tsx
      NarrationRecorder.tsx  JobProgress.tsx  ImageTriptych.tsx  SfxPicker.tsx
workflows/
  item-image.json           # ComfyUI „Save (API format)" sablon (minimal SD txt2img)
  item-image.meta.json      # { "prompt_node": "...", "seed_node": "...", "save_node": "..." }
spike/
  s1_comfy.py   s2_cutout.py   s3_segment.py
  s4_record/    # minimál statikus oldal: MediaRecorder felvétel + feltöltés
README.md (frissítés), .dockerignore
```

## 2. config.py

```python
class Settings(BaseSettings):  # pydantic-settings VAGY sima os.environ olvasás
    comfyui_url: str = "http://host.docker.internal:8188"   # env COMFYUI_URL
    data_dir: str = "/data"                                  # env DATA_DIR
    tz: str = "Europe/Budapest"                              # env TZ
def get_settings() -> Settings  # cache-elt (lru_cache)
```
- `DATA_DIR`-t a tesztek tmp-re állítják env-en át; SOHA ne égess be `/data`-t
  a kódba — mindig `get_settings().data_dir`-ből indulj.
- NE hozz be `pydantic-settings`-et új függőségként, ha sima `os.environ.get`
  is elég; tartsd minimálisnak. (Ha mégis kell, vedd fel requirements-be.)

## 3. storage.py

Útvonal-helperek (mind `pathlib.Path`-t ad vissza, abszolút, a data_dir alól):
```python
def data_root() -> Path                          # get_settings().data_dir
def db_path() -> Path                            # <data>/db.sqlite3
def topic_dir(topic_slug: str) -> Path           # <data>/projects/<slug>
def item_dir(topic_slug, position: int, item_slug) -> Path  # .../items/<NN>-<slug>  (NN=zero-pad 2)
def render_dir(topic_slug) -> Path               # .../render
def sfx_dir() -> Path                            # <data>/sfx
def models_dir() -> Path                         # <data>/models
def branding_dir() -> Path                       # <data>/branding
def ensure_tree() -> None                        # létrehozza a fix mappákat (sfx, models, branding, projects)
def item_asset(item_dir: Path, name: str) -> Path  # name ∈ {generated.png, cutout.png, silhouette.png, narration_a.webm, narration_a.clean.wav, narration_b.webm, narration_b.clean.wav, segment.mp4, meta.json}
```
`slugify(text: str) -> str`:
- kisbetűsít, magyar ékezetek leképezése: á→a é→e í→i ó→o ö/ő→o ú→u ü/ű→u
  (és nagybetűs párjaik), egyéb diakritikák `unicodedata.normalize('NFKD')`
  + ascii-szűrés; nem-alfanumerikus → `-`; többszörös `-` össze; trim `-`.
- Példák (teszt-kötelező): „tűzoltóautó"→`tuzoltoauto`? NEM: a szóköz-szabály
  miatt szavanként: „tűzoltó autó"→`tuzolto-auto`; „tehén"→`tehen`;
  „Az ÉG!"→`az-eg`. (Ha a bemenet egybe van írva, marad egybe.)
- A `NN` mindig 2 jegyű, `position` 1-től.

NE írj a repo working tree-be futásidőben — csak a data_root alá (CLAUDE.md #7).

## 4. db.py

- `sqlite3`, `check_same_thread=False`, `PRAGMA journal_mode=WAL`,
  `row_factory=sqlite3.Row`.
- `def get_connection() -> sqlite3.Connection` (folyamat-szintű singleton a
  db_path()-ra; tesztben a DATA_DIR tmp miatt külön db jön létre — adj
  `reset_connection()`-t a tesztekhez).
- `def init_db() -> None` — idempotens DDL (CREATE TABLE IF NOT EXISTS):

```sql
CREATE TABLE topic(
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  background_path TEXT, settings_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL);
CREATE TABLE item(
  id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL REFERENCES topic(id) ON DELETE CASCADE,
  position INTEGER NOT NULL, slug TEXT NOT NULL, name TEXT NOT NULL,
  prompt TEXT NOT NULL DEFAULT '', seed INTEGER, sfx_path TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  UNIQUE(topic_id, position));
CREATE TABLE job(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, ref_id INTEGER,
  state TEXT NOT NULL DEFAULT 'queued', progress REAL NOT NULL DEFAULT 0,
  log TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
```
- Időbélyeg ISO-8601 UTC string (`datetime.now(timezone.utc).isoformat()`).
  FONTOS: a workflow-környezetben `datetime.now()` tiltott — DE ez RUNTIME
  kód, nem workflow-szkript; a futó appban szabad. A tesztek ne függjenek a
  pontos időtől.

## 5. models.py (pydantic v2)

Enumok (str, Enum):
```python
class TopicStatus: draft, in_progress, done
class ItemStatus:  draft, image_ok, audio_ok, segment_ok          # státuszgép (01-BLUEPRINT §3)
class JobKind:     generate_image, cutout, clean_audio, render_segment, assemble
class JobState:    queued, running, done, error
```
Pydantic modellek: `Topic`, `TopicCreate`, `TopicUpdate`, `Item`, `ItemCreate`,
`ItemUpdate`, `Job`. A `*Create/*Update` csak a kliens-küldhető mezőket
tartalmazza. A DB-Row → modell konverziót storage/api réteg végzi.

## 6. jobs.py — job-rendszer (CLAUDE.md #5, 01-BLUEPRINT §6.1)

- Perzisztens SQLite-sor + EGY asyncio worker-loop a backend-folyamatban.
- Konkurencia: egyszerre max 1 GPU-igényes (`generate_image`) ÉS 1 CPU-igényes
  (`cutout|clean_audio|render_segment|assemble`) job fut.
- Handler-registry: `register(kind: JobKind, fn)` ahol
  `fn(job_id: int, ref_id: int, set_progress: Callable[[float],None], log: Callable[[str],None]) -> None`
  (sync fn-t thread-poolban futtass, hogy ne blokkold az event-loopot).
- Publikus API:
```python
def enqueue(kind: JobKind, ref_id: int | None) -> int        # job.id
async def worker_loop() -> None                              # main.py indítja lifespan-ben
def get_job(job_id: int) -> Job
async def resume_pending() -> None                           # induláskor queued/running→queued
```
- Hibakezelés: handler-kivétel → `state=error`, a kivétel magyar üzenete a
  `log`-ba. Soha ne dőljön el a worker-loop egy job hibájától.
- Progress 0..1. A UI 2 mp-enként pollozza `GET /api/jobs/{id}`.

## 7. pipeline/timing.py — a 03-VIDEO-SPEC §2 kódbeli forrása

NINCS más helyen beégetett másodperc (CLAUDE.md #4). Minden fázishossz innen.

```python
FPS = 30
# fázis-konstansok (03-VIDEO-SPEC §2) — másodperc
ENTRY     = 0.8      # 1. belépés: sziluett fade+scale-in (0.95→1.0)
RIDDLE_PAD= 0.4      # 2. találós: len(A) + 0.4
BEAT      = 0.4      # 3. ütem-szünet
SFX_MIN   = 1.2      # 4. hangeffekt: max(len(SFX), 1.2)
REVEAL    = 0.6      # 5. reveal crossfade (sziluett→cutout)
NAMING_PAD= 0.5      # 6. megnevezés: len(B) + 0.5
HOLD      = 1.2      # 7. kitartás
XFADE     = 0.6      # elemek közti átmenet (téma-beállítás felülírhatja)
INTRO     = 4.0
OUTRO     = 4.0

@dataclass(frozen=True)
class SegmentTiming:
    entry: float; riddle: float; beat: float; sfx: float
    reveal: float; naming: float; hold: float
    @property
    def sil_section(self)  -> float  # entry+riddle+beat+sfx+reveal  (sziluett a crossfade VÉGÉIG látszik)
    @property
    def rev_section(self)  -> float  # reveal+naming+hold            (cutout a crossfade ELEJÉTŐL)
    @property
    def xfade_offset(self) -> float  # entry+riddle+beat+sfx         (crossfade kezdete)
    @property
    def total(self)        -> float  # xfade_offset + reveal + naming + hold
    # audió-offsetek (mp):
    @property
    def narr_a_at(self) -> float     # entry
    @property
    def sfx_at(self)    -> float     # entry+riddle+beat
    @property
    def narr_b_at(self) -> float     # xfade_offset + reveal   (a reveal végén indul a megnevezés)

def compute_timing(len_a: float, len_sfx: float, len_b: float) -> SegmentTiming:
    # riddle = len_a + RIDDLE_PAD ; sfx = max(len_sfx, SFX_MIN) ; naming = len_b + NAMING_PAD
def frames(seconds: float) -> int            # round(seconds*FPS)
def quantize(seconds: float) -> float        # frames(seconds)/FPS  (frame-rácsra illeszt)
```
A renderer FRAME-RÁCSRA illesztett értékekkel dolgozzon (quantize), hogy a
golden-teszt ±1 frame-en belül legyen. A golden-teszt EZT a configot használja,
nincs duplikált szám a tesztben.

## 8. pipeline/comfy.py — ComfyUI-híd (comfyui-bridge skill MÁSOLATA)

- A skill `ComfyClient` osztályát vedd át 1:1 (urllib + websocket-client).
- ÚJ függőség: `websocket-client` → requirements + ADR-7 licenc-jegyzék (MIT).
- A node-ID-ket a `workflows/item-image.meta.json`-ból olvasd (prompt/seed/save).
- Magas szintű belépő (a job-handler ezt hívja):
```python
def generate_image(*, prompt_text: str, seed: int, out_path: Path,
                   workflow_path: Path, meta_path: Path,
                   base_url: str | None = None) -> None
```
- Hibák magyar üzenettel (skill „Hibakezelés" szakasza):
  ConnectionRefused/timeout → „A ComfyUI nem érhető el — fut a Macen? (8188-as
  port; runbook: docs/04, 6. pont)". Üres images → a history `status` a logba.
- Teszt: indíts egy minimál `http.server`-alapú mock-ot (vagy monkeypatch az
  urlopen/websocket hívásokra), ami `prompt_id`-t, majd history+view PNG-t ad.
  NE függj valódi ComfyUI-tól.

## 9. pipeline/cutout.py — kivágás + sziluett (P1, 03-VIDEO-SPEC §3)

```python
def cutout(generated_path: Path, cutout_path: Path, silhouette_path: Path,
           alpha_threshold: int = 128) -> None
```
- rembg `u2net` session **singleton** (modul-szintű lazy, egyszer töltődik).
  `import rembg` CSAK a függvényen belül (lazy) — különben a teljes backend
  import elhasal a dev gépen, ahol nincs rembg.
- `cutout.png`: RGBA, háttér eltávolítva (rembg).
- `silhouette.png`: a cutout ALFA-csatornája teljesen FEKETÉVEL kitöltve
  (RGB=0,0,0; alfa = a cutout alfája, opcionálisan `alpha_threshold`-dal
  bináris). NEM sötétített kép — a textúra felismerhetetlen kell legyen.
  Ez Pillow-val (PIL) megoldható rembg nélkül is, ha már van RGBA cutout.
- `def bounding_box(cutout_path: Path) -> tuple[int,int,int,int]` — a nem-átlátszó
  pixelek bbox-a (a segment.py a skálázáshoz használja). PIL `getbbox()` az
  alfán.
- Teszt: készíts szintetikus RGBA PNG-t (PIL) ismert alfával → hívd a
  sziluett-előállítást → ellenőrizd, hogy RGB csupa 0 és az alfa egyezik.
  A rembg-hívást külön teszt fedi, `pytest.importorskip("rembg")`-gel.

## 10. pipeline/audio.py — hangtisztítás (P2, ffmpeg-recipes R2/R3, 03-spec §4)

```python
def clean_narration(raw_path: Path, clean_path: Path) -> dict   # visszaadja a loudnorm JSON-riportot
def normalize_sfx(raw_path: Path, out_path: Path) -> None        # R3
def duration_seconds(path: Path) -> float                        # ffprobe
```
- `clean_narration` az R2 láncot futtatja (48k mono → highpass → afftdn →
  silenceremove elöl/hátul → loudnorm I=-16:TP=-1.5:LRA=11), a loudnorm
  `print_format=json` riportját stderr-ből parse-olja és visszaadja + a hívó a
  job-logba írja. Idempotens (kétszer futtatva ne romoljon).
- `normalize_sfx`: R3 (loudnorm I=-18).
- ffmpeg/ffprobe a PATH-ról; subprocess, ellenőrzött returncode, hibánál
  magyar üzenet + az ffmpeg stderr utolsó sorai a logba.
- Teszt (valódi ffmpeg): generálj `anoisesrc`/`sine` wav-ot →
  `clean_narration` → a kimenet létezik, mono 48k (ffprobe), és a loudnorm
  riport `input_i`/`output_i` kulcsokat tartalmaz.

## 11. pipeline/segment.py — szegmens-renderer (a MAG, P3, ffmpeg-recipes R4)

```python
def render_segment(*, background: Path | None, silhouette: Path, cutout: Path,
                   narration_a: Path, sfx: Path | None, narration_b: Path,
                   out_path: Path, timing: SegmentTiming,
                   canvas=(1920,1080), bg_color="#EAF4FF") -> None
def segment_inputs_hash(...) -> str    # a bemenetek (fájl-hash + timing) → cache-kulcs a meta.json-höz
```
- A filtergráfot a R4 minta szerint építsd: háttér (kép loop vagy szín) +
  sziluett-szakasz (fade-in 0.8s, scale 0.95→1.0) + cutout-szakasz, a kettő
  között `xfade=transition=fade:duration=REVEAL:offset=timing.xfade_offset`.
- Sziluett és cutout AZONOS scale/overlay-koordináta (a cutout bbox-ából egyszer
  számolt méret) — különben a reveal „ugrik" (03-spec §3, §7.4).
- Skálázás: max magasság a vászon 70%-a (756px), max szélesség 60% (1152px),
  arányőrző; alapvonal a vászon ~78%-án; PÁROS méretek (`floor(/2)*2`).
- Hang: narr_a @ timing.narr_a_at, sfx @ timing.sfx_at, narr_b @ timing.narr_b_at,
  `adelay`-jel, 10ms `afade` a kattanás ellen (03-spec §7.3), `amix=normalize=0`.
  Ha nincs sfx, a 4. fázis SFX_MIN néma marad (a vizuál hossza akkor is sfx=max(0,1.2)).
- Kimenet az R1 paraméterekkel (1920×1080, 30fps, libx264 crf18, yuv420p, aac
  192k 48k stereo, +faststart).
- **GOLDEN-TESZT** (test_segment.py): fix szintetikus assetekből (PIL képek,
  rövid ismert hosszú wav-ok) renderelj → `tests/probe_phases.py` /ffprobe-bal
  mérd a teljes hosszt és a reveal-átmenet helyét → a `timing.py`-ból számolt
  értékekkel ±1 frame egyezzen. A 03-spec §7 1–4. kritériuma ellenőrzött:
  hossz, hangosság (audio-teszt fedi), kattanás-mentes határ, reveal-szinkron.

## 12. pipeline/assemble.py — összefűzés (ffmpeg-recipes R5)

```python
def assemble(*, intro: Path | None, segments: list[Path], outro: Path | None,
             out_path: Path, list_file: Path) -> None
def needs_rerender(item_dir: Path, current_hash: str) -> bool   # meta.json hash-csere (01-BLUEPRINT §6.3)
```
- concat demuxer `-c copy` (R5); ha a `-c copy` hibázik (paraméter-eltérés),
  fallback: újrakódolás R1-gyel + a logba figyelmeztetés (a helyes út az eltérő
  szegmens újrarenderelése, nem néma újrakódolás).
- A concat list.txt RELATÍV utakat a list_file helyéhez old fel — figyelj.
- Teszt: 2 db rövid, R1-paraméteres szegmens (a segment-teszt vagy egy mini
  ffmpeg-generátor) → assemble → ffprobe: a final hossza ≈ a kettő összege.

## 13. api/ — vékony route-réteg (01-BLUEPRINT §4)

`api/__init__.py`: `api_router = APIRouter(prefix="/api")`, includeolja a
topics/items/jobs alroutereket. A media külön mount (lásd main.py).
Végpontok (a hosszú műveletek JOB-ot adnak vissza `{ "job_id": int }`):
```
GET    /api/topics                          → list[Topic]
POST   /api/topics                          → Topic            (TopicCreate)
GET    /api/topics/{id}                     → Topic
PATCH  /api/topics/{id}                     → Topic            (TopicUpdate)
DELETE /api/topics/{id}                     → 204
POST   /api/topics/{id}/background          → Topic            (multipart: háttér feltöltés)
GET    /api/topics/{id}/items               → list[Item]
POST   /api/topics/{id}/items               → Item             (ItemCreate; auto position+slug+dir)
POST   /api/topics/{id}/items/reorder       → list[Item]       (body: [item_id,...] új sorrend; NN-mappa konzisztens)
POST   /api/topics/{id}/assemble            → {job_id}
GET    /api/items/{id}                       → Item
PATCH  /api/items/{id}                       → Item            (ItemUpdate)
DELETE /api/items/{id}                       → 204
POST   /api/items/{id}/generate-image       → {job_id}         (ComfyUI; új seed ha kérik)
POST   /api/items/{id}/cutout               → {job_id}
POST   /api/items/{id}/narration/{slot}     → Item             (slot ∈ a|b; multipart webm/wav → sémába)
POST   /api/items/{id}/clean-audio/{slot}   → {job_id}
POST   /api/items/{id}/render-segment       → {job_id}
GET    /api/jobs/{id}                         → Job
GET    /api/sfx                               → list (data/sfx tartalma)
```
- A route-ok NEM tartalmaznak pipeline-logikát: validálnak, storage/jobs-ot
  hívnak. A pipeline-hívás mindig job (enqueue), a route a job_id-t adja vissza.
- Az újrागenerálás/újra-cutout invalidálja a downstream asseteket (status
  visszaállítás + meta-hash), ahogy a 02-plan T5/T6 írja.

## 14. main.py

- `FastAPI(lifespan=...)`: induláskor `ensure_tree()`, `init_db()`,
  `resume_pending()`, és háttér-taskként `worker_loop()`; leálláskor a worker
  rendezett leállítása.
- `/healthz` → `{"status":"ok"}`.
- `/media` → a data_root() statikus kiszolgálása (StaticFiles), csak olvasás.
- `app.include_router(api_router)`.
- Frontend: ha létezik `frontend/dist`, azt szolgáld ki a gyökéren
  (StaticFiles html=True), különben egy „a frontend nincs buildelve" placeholder.
  A `/api` és `/media` ELŐBB legyen bekötve, mint a catch-all static.

## 15. frontend/ (React 18 + Vite + TS)

- `vite.config.ts`: dev proxy `/api` és `/media` → `http://localhost:8000`;
  build kimenet `dist/` (a backend ezt szolgálja ki).
- `api.ts`: tipizált fetch-kliens a §13 végpontokra; `types.ts` a backend
  enumok/modellek TS-tükre.
- Komponensek (UI-szöveg MAGYAR):
  - `TopicList`: témák listája + új téma.
  - `TopicEditor`: cím, háttér-feltöltés, beállítások (fps, zene, xfade), elemek.
  - `ItemList`/`ItemEditor`: elem CRUD, átrendezés (drag vagy fel/le), státusz-chip.
  - `NarrationRecorder`: MediaRecorder (`audio/webm;codecs=opus`) A/B felvétel
    (felvétel/stop/visszahallgatás/újra) + fájl-feltöltés alternatíva.
  - `ImageTriptych`: nyers/cutout/sziluett egymás mellett.
  - `SfxPicker`: data/sfx listázás + előhallgatás + hozzárendelés.
  - `JobProgress`: job_id-t pollozza 2 mp-enként (`GET /api/jobs/{id}`),
    progress-bar + magyar állapot + hibalog.
- Nincs nehéz UI-keretrendszer kötelezően; sima CSS elég. TS strict.

## 16. workflows/item-image.json

- Minimal SD txt2img „API format" graph: CheckpointLoaderSimple →
  CLIPTextEncode(pos) → CLIPTextEncode(neg) → EmptyLatentImage(768×768 v.
  512×512) → KSampler → VAEDecode → SaveImage. Node-kulcsok stringek ("3","4"…).
- `item-image.meta.json`: `{"prompt_node":"<pos CLIP id>","seed_node":"<KSampler id>","save_node":"<SaveImage id>"}`.
- A checkpoint nevét a felhasználó tölti ki Macen (ADR-7) — tegyél placeholdert
  (`"model.safetensors"`) és kommentet/README-sort, hogy ezt cserélni kell.

## 17. spike/ — F0 bizonyítékok (eldobható, de működjön)

- `s1_comfy.py "<prompt>"`: a comfy.py-t használva PNG-t ír a data alá; méri a
  generálási időt. (Macen futtatható; itt a kód helyes legyen.)
- `s2_cutout.py <png>`: cutout.py-val cutout+sziluett. (rembg kell hozzá.)
- `s3_segment.py`: szintetikus/odakészített assetekből egy `segment.mp4` a
  segment.py-val — ennek a DEV GÉPEN is le kell futnia (ffmpeg van).
- `s4_record/`: statikus index.html + kis JS: MediaRecorder felvétel és
  feltöltés a `/api/items/{id}/narration/a`-ra (a tunnelen/HTTPS-en megy élesben).

## 18. requirements.txt (futás) — minimalizmus

```
fastapi
uvicorn[standard]
python-multipart            # multipart feltöltéshez
websocket-client            # comfy.py (ADR-7: MIT)
pillow                      # sziluett/kép-műveletek
rembg                       # kivágás (NEHÉZ: onnxruntime + modell; lazy-import a kódban!)
```
requirements-dev.txt: `pytest`, `pytest-cov`, `httpx` (TestClient), `ruff`.
- A `rembg`-t a requirements-be tedd (élesben kell), de a kód lazy-importálja,
  hogy a dev gépen rembg nélkül is fusson minden NEM-cutout teszt.
- MINDEN új csomag → `docs/05-DECISIONS.md` ADR-7 licenc-jegyzék frissítése
  UGYANEBBEN a változtatásban (CLAUDE.md #8). Új sorok: python-multipart (MIT),
  websocket-client (Apache-2.0/LGPL? → ellenőrizd és írd be), httpx (BSD),
  ruff (MIT).

## 19. Tesztelési és minőségi elvárások

- `cd backend && python -m pytest -q` ZÖLDEN fusson a dev gépen MINDEN tesztre,
  KIVÉVE amik rembg-t/ComfyUI-t igényelnek (azok `importorskip`/skip-jelölővel).
- A render-tesztek VALÓDI ffmpeg-et futtatnak (van a gépen) — ne mockold.
- `frontend`: `npm install && npm run build` hibátlanul fusson (tsc + vite).
- Aranyszabályok (CLAUDE.md 1–10) BETARTVA. Kiemelt ellenőrzések a review-ban:
  nincs beégetett másodperc (csak timing.py), ffmpeg csak a recipes-mintákból,
  comfy csak a skill-mintából, futás csak /data alá, titok csak .env.
- UI magyar, kód/komment angol.
```
