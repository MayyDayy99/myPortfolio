# „Már ezt is tudom" — videógyár dokumentációs csomag

Sablon-alapú videógenerátor a gyerekcsatornához: 8–10 elem/téma, elemenként
**sziluett → narráció → hangeffekt → reveal**. Fut: M5 MacBook Pro, Docker +
natív ComfyUI (Metal GPU), kifelé Cloudflare Tunnel + Access. A fejlesztés
Claude Code-ban történik.

> **Állapot (2026-06-11):** a nem-Mac-specifikus MVP **kód kész és verifikált**
> (backend + frontend + pipeline + tesztek; `pytest`: 77 passed / 1 skipped, a
> render-mag frame-pontos). **Folytatod a fejlesztést? → [`docs/06-STATUS.md`](docs/06-STATUS.md)**
> (állapot, fájltérkép, hátralévő munka, Mac-setup). Hátra: a Mac/host-integráció
> (rembg, ComfyUI, checkpoint, tunnel) + az éles E2E (T12).

## Mi hol van
| Fájl | Mi ez |
|---|---|
| **`docs/06-STATUS.md`** | **átadó doc: jelenlegi állapot, fájltérkép, hátralévő munka, Mac-checklista** |
| `CONTRACTS.md` | kötelező interfész-szerződés (a párhuzamos build koordinációja; új kódot ehhez illeszd) |
| `CLAUDE.md` | Claude Code projekt-memória: aranyszabályok, architektúra, parancsok |
| `docs/01-BLUEPRINT.md` | technikai blueprint (rendszer, adatmodell, pipeline-ok, biztonság) |
| `docs/02-IMPLEMENTATION-PLAN.md` | fázisolt terv: F0 spike → F1 MVP (T1–T12) → F2/F3 |
| `docs/03-VIDEO-SPEC.md` | a videóformátum egyetlen forrása (dramaturgia, időzítés, audió) |
| `docs/04-OPERATIONS.md` | runbook: Mac-beállítás, ComfyUI launchd, tunnel+Access, mentés, hibakeresés |
| `docs/05-DECISIONS.md` | ADR-ek + élő licenc-jegyzék |
| `backend/` | FastAPI backend + pipeline + tesztek (lásd `docs/06-STATUS.md` §3) |
| `frontend/` | React+Vite+TS app (a build a backendből kiszolgálva) |
| `.claude/skills/comfyui-bridge/` | skill: a headless ComfyUI hívásának kánonja |
| `.claude/skills/ffmpeg-recipes/` | skill: render- és hangtisztító receptek |
| `docker-compose.yml`, `.env.example` | indulási váz (app + cloudflared) |

## Előfeltételek a Macen
1. Docker Desktop (autostart bekapcsolva)
2. ComfyUI natívan telepítve + egy SD checkpoint (licenc: ADR-7!)
3. Cloudflare-fiók + domain a Tunnelhez (Access-szabállyal)
4. Claude Code telepítve

## Első 30 perc Claude Code-ban
```bash
cd kidsvideo-factory
cp .env.example .env        # token kitöltése
claude                      # a CLAUDE.md automatikusan betöltődik
```
Első utasításnak ezt add:
> „Olvasd el a docs/02-IMPLEMENTATION-PLAN.md-t, és kezdd az F0 spike-kal.
> Írj tervet az S1-hez, mielőtt kódolsz."

A skillek (`.claude/skills/`) maguktól aktiválódnak, amikor ComfyUI- vagy
ffmpeg-feladat jön. A dramaturgián csak a `docs/03-VIDEO-SPEC.md`-ben változtass.

## Build és futtatás

### Backend
Két út van: helyi uvicorn (gyors iteráció), vagy a teljes Docker-stack.

Helyi uvicorn (fejlesztéshez):
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
# DATA_DIR-t add meg (a futásidejű adat csak ide kerül, a repo soha):
DATA_DIR=../data COMFYUI_URL=http://127.0.0.1:8188 \
  uvicorn app.main:app --reload --port 8000
# app: http://localhost:8000  (egészség: /healthz)
```
> Megjegyzés: a `rembg` (kivágás) nehéz függőség (onnxruntime + modell).
> Lazy-importált, így a backend kivágás nélkül is elindul; helyi gépen a
> `pip install rembg` opcionális, ha csak nem-kivágós részt fejlesztesz.

Teljes stack Dockerrel (ahogy a Macen éles üzemben fut):
```bash
cp .env.example .env        # töltsd ki a TUNNEL_TOKEN-t
docker compose up --build
# app: http://localhost:8000 (csak localhost; kifelé a tunnel visz)
```
A `docker compose` az app-ot ÉS a `cloudflared`-et hozza fel. A ComfyUI NEM
ebben fut — lásd lent a Mac/host beállítást (ADR-2).

### Frontend
A frontend Reactban+Viteben készül; a build kimenetét (`frontend/dist/`) a
backend statikusan szolgálja ki.
```bash
cd frontend
npm install
npm run build        # tsc + vite → frontend/dist/
# fejlesztés közben élő reload, proxyval a backendre:
npm run dev          # http://localhost:5173, /api + /media proxy a :8000-ra
```

### Tesztek
```bash
cd backend
python -m pytest -q
```
> A render- és hangtesztek VALÓDI ffmpeg/ffprobe-ot futtatnak (legyen PATH-on).
> A `rembg`-t igénylő kivágás- és az élő ComfyUI-t igénylő tesztek automatikusan
> KIHAGYÓDNAK (skip/`importorskip`), ha ezek nincsenek telepítve — a többi
> teszt zölden fut e nélkül is.

## Mac/host beállítás (nem a compose része)

A `docs/04-OPERATIONS.md` runbookja írja le részletesen:
- **ComfyUI** natívan, a macOS hoston fut (Metal GPU), `launchd`-vel
  háttérszolgáltatásként, a `127.0.0.1:8188` porton. A konténer
  `http://host.docker.internal:8188` címen éri el. NINCS a docker-compose-ban
  és NEM megy ki a tunnelen (ADR-1/ADR-2).
- **Cloudflare Tunnel + Access** adja a kifelé menő HTTPS-t és a belépés-védelmet
  (a mikrofonos felvételhez HTTPS kell). A `TUNNEL_TOKEN` csak a `.env`-ben él.
- **Checkpoint a Macen**: a `workflows/item-image.json` ComfyUI-sablonban a
  `CheckpointLoaderSimple` `ckpt_name` mezője `model.safetensors` placeholder —
  ezt a Macen a ténylegesen telepített checkpoint nevére KELL cserélni (és a
  modell licencét az ADR-7-be bejegyezni a kereskedelmi használat előtt).
