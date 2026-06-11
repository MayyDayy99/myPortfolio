# CLAUDE.md — „Már ezt is tudom" videógyár

> **FOLYTATOD A FEJLESZTÉST (másik gép / másik agent)? Olvasd el ELŐSZÖR a
> [`docs/06-STATUS.md`](docs/06-STATUS.md)-t** — jelenlegi állapot, teljes
> fájltérkép a szignatúrákkal, hátralévő munka, Mac-setup checklista. Az
> interfész-szerződés (új kódot ehhez illeszd): [`CONTRACTS.md`](CONTRACTS.md).
> Állapot (2026-06-11): a nem-Mac-specifikus MVP kód kész és verifikált
> (`pytest`: 77 passed / 1 skipped; a render-mag frame-pontos).

## Mi ez a projekt
Sablon-alapú videógenerátor („gyár") a **Már ezt is tudom** gyerekcsatornához.
Egy videó = 8–10 elem (tárgy/élőlény/fogalom), elemenként fix dramaturgia:
**sziluett → narráció (körülírás) → hangeffekt → reveal (kép) + narráció**.
Ez NEM általános videóvágó — egy kitölthető sablon plusz vékony igazító réteg.

## Architektúra (1 perc alatt)
- **app** (Docker): FastAPI backend + React/Vite frontend (build a backendből
  kiszolgálva) + ffmpeg + rembg. Minden render/hangtisztítás itt.
- **ComfyUI**: NATÍVAN fut a macOS hoston (Metal GPU), headless, `:8188`.
  A konténer a `http://host.docker.internal:8188` címen éri el.
- **cloudflared** (Docker): Cloudflare Tunnel, KIZÁRÓLAG az app-ot engedi ki.
  Előtte Cloudflare Access (csak a tulaj léphet be).
- Adat: fájlrendszer (`/data`) + SQLite (metaadat + job-sor). Nincs Postgres,
  nincs Redis — egyfelhasználós rendszer.

Részletek: `docs/01-BLUEPRINT.md`. Feladatsorrend: `docs/02-IMPLEMENTATION-PLAN.md`.

## ARANYSZABÁLYOK (ezeket soha ne sértsd meg)
1. **ComfyUI soha nem kerül a docker-compose-ba**, és **soha nem megy ki a
   tunnelen**. Dockerben a Macen nincs Metal GPU-passthrough — a ComfyUI csak
   natívan futhat. Indoklás: `docs/05-DECISIONS.md` / ADR-2.
2. **Minden ffmpeg-parancs** a `.claude/skills/ffmpeg-recipes` mintáit követi.
   Új recept születik → a skillbe kerül, nem szóródik szét a kódban.
3. **Minden ComfyUI-hívás** a `.claude/skills/comfyui-bridge` mintáit követi.
4. **Időzítés/dramaturgia egyetlen forrása**: `docs/03-VIDEO-SPEC.md` + a
   belőle származó `pipeline/timing.py` konfiguráció. Kódban nincs beégetett
   másodperc-érték.
5. **Hosszú művelet (képgen, render, hangtisztítás) mindig job** — sosem
   blokkol HTTP-kérést. Job-állapot SQLite-ban, a UI pollozza/streameli.
6. A pipeline-kód (`backend/app/pipeline/`) **tiszta, UI-független, tesztelhető**
   függvényekből áll. A FastAPI-réteg vékony.
7. Futásidőben **csak a `/data` alá írunk** (a repo working tree-be soha).
8. **Licenc-fegyelem**: új modell/könyvtár/SFX → a `docs/05-DECISIONS.md`
   licenc-jegyzéke frissül UGYANABBAN a PR-ban.
9. UI-szövegek **magyarul**, kód-azonosítók/kommentek **angolul**.
10. Titkok csak `.env`-ben (gitignore-olva); a `TUNNEL_TOKEN` soha nem kerül
    commitba.

## Könyvtárszerkezet (cél)
```
backend/app/
  main.py            # FastAPI app + statikus frontend kiszolgálás
  api/               # vékony route-réteg
  pipeline/          # a gyár magja: comfy.py, cutout.py, audio.py,
                     # segment.py, assemble.py, timing.py
  jobs.py            # SQLite-alapú job-sor + asyncio worker
  storage.py         # /data elérési utak, sémák (lásd 01-BLUEPRINT)
backend/tests/       # pytest; golden-fájl tesztek a segment-renderhez
frontend/            # React + Vite + TS
workflows/           # ComfyUI „Save (API format)" JSON sablonok
data/                # futásidejű adat (gitignore) — lásd 01-BLUEPRINT séma
```

## Parancsok
- Fejlesztés: `docker compose up --build` (app: http://localhost:8000)
- Frontend dev: `cd frontend && npm run dev` (proxy a backendre)
- Tesztek: `cd backend && pytest -q`
- ComfyUI elérés gyorsteszt a konténerből:
  `curl -s http://host.docker.internal:8188/system_stats`

## Munkamódszer Claude Code-ban
- A feladatok a `docs/02-IMPLEMENTATION-PLAN.md`-ből jönnek, **sorrendben**;
  minden feladatnak „Kész, ha" kritériuma van — a feladat zárásakor bizonyítsd
  (teszt fut / parancs kimenete).
- Nagyobb feladatnál először tervet írj (plan), utána kódolj.
- Ha a spec és a kód ütközik: a spec nyer; ha a spec hiányos: kérdezz, és a
  választ írd be a megfelelő docs fájlba.
