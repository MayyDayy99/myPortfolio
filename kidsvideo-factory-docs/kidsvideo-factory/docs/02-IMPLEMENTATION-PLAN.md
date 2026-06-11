# 02 — Implementációs terv

> Sorrendben haladj. Minden feladatnál **Cél / Kész, ha / Függ**. A „Kész, ha"
> bizonyítandó (teszt, parancs-kimenet, vagy rövid képernyő-demó).
> A 0. fázis itt kicsi: nem elvi kérdés, hanem környezet-validálás — a
> kockázatos integrációk a TE Macedben, élesben.

## F0 — Integrációs spike (2–3 nap) — KAPU

Egy `spike/` mappa, eldobható szkriptek. Négy bizonyíték:

**S1 — Konténer → natív ComfyUI körút**
*Cél:* Docker-konténerből prompt beküldése a hoston futó ComfyUI-nak, kész PNG
visszahozása (`POST /prompt` → WS → `/history` → `/view`).
*Kész, ha:* `docker compose run app python spike/s1_comfy.py "egy piros alma"`
PNG-fájlt ír a /data alá. Mérd: generálási idő/kép a választott checkpointtal.

**S2 — Kivágás + sziluett**
*Cél:* az S1 képéből rembg-vel `cutout.png` és `silhouette.png`.
*Kész, ha:* a sziluett tiszta fekete, a kontúr a cutout-tal pixelre egyezik
(vizuális ellenőrzés + alfa-hisztogram).

**S3 — Egy szegmens ffmpeg-gel, fix assetekből**
*Cél:* kézzel odakészített assetekből (kép, 2 wav, sfx) a 03-VIDEO-SPEC 2. pont
idővonalát követő `segment.mp4` egyetlen szkripttel.
*Kész, ha:* a szegmens QuickTime-ban hibátlan; a reveal-crossfade jó; a
fázishosszak stimmelnek (±1 frame, ffprobe-bal ellenőrizve).

**S4 — Mikrofon a tunnelen át**
*Cél:* minimál oldal a backendből: felvétel MediaRecorderrel egy MÁSIK gép
böngészőjéből a Cloudflare-URL-en, feltöltés, tisztító lánc lefuttatása.
*Kész, ha:* a `narration.clean.wav` érthető, zajmentes, loudnorm-riport oké.

**GO-kritérium:** mind a négy zöld + S1 idő/kép elfogadható (irány: ≤ ~30 s/kép
a választott modellel — ha lassabb, kisebb felbontás/lépésszám vagy más
checkpoint, MIELŐTT az MVP indul).

## F1 — MVP: az első teljes videó (2–3 hét)

**T1 — Repo-váz + compose**
*Cél:* backend (FastAPI, „hello" + /healthz), frontend (Vite build a backendből
kiszolgálva), docker-compose (app + cloudflared), .env-kezelés, pytest + CI lint.
*Kész, ha:* `docker compose up --build` után a tunnel-URL-en betölt az app egy
másik gépről; `pytest -q` zöld.
*Függ:* F0

**T2 — Adatmodell + storage**
*Cél:* SQLite-séma (topic/item/job), `storage.py` a 01-BLUEPRINT fájlsémájával,
slugosítás (ékezet-kezeléssel), `/media` kiszolgálás.
*Kész, ha:* egységtesztek: topic+item létrehozás → a várt mappastruktúra
létrejön; slug-tesztek (pl. „tűzoltóautó" → `tuzolto-auto`).
*Függ:* T1

**T3 — Téma- és elem-CRUD UI**
*Cél:* témalista, téma-szerkesztő (cím, háttér-feltöltés, beállítások), elemek
hozzáadása/átrendezése/törlése, elem-státusz kijelzés.
*Kész, ha:* egy 9 elemes téma végigkattintható, az átrendezés a position-t és a
mappa-NN-t konzisztensen tartja.
*Függ:* T2

**T4 — Job-rendszer**
*Cél:* `jobs.py`: SQLite-perzisztens sor + asyncio worker; konkurencia-szabály
(1 képgen + 1 render párhuzamosan); `GET /api/jobs/{id}`; UI progress-komponens.
*Kész, ha:* teszt: 3 beküldött dummy-job sorban fut, állapotuk követhető;
backend-újraindítás után a queued jobok folytatódnak.
*Függ:* T2

**T5 — ComfyUI-híd + képgenerálás UI**
*Cél:* `pipeline/comfy.py` a comfyui-bridge skill mintájával; workflow-sablon a
`workflows/`-ból; elem-szerkesztőben „Generálás" gomb, előnézet, seed-kezelés,
„Újragenerálás" (új seed) — job-ként.
*Kész, ha:* elemhez 1 kattintással kép készül; ComfyUI leállítva → a job
értelmes magyar hibát ad; ismételt generálás felülírja a generated.png-t és
invalidálja a downstream asseteket (cutout, segment).
*Függ:* T4

**T6 — Kivágás + sziluett pipeline**
*Cél:* `pipeline/cutout.py` (rembg singleton); automatikus futás a sikeres
képgen után; UI-ban a 3 kép (nyers/cutout/sziluett) egymás mellett.
*Kész, ha:* tesztkép-készleten determinista kimenet; az alfa-küszöb és a
fekete-kitöltés a 03-spec 3. pontja szerint.
*Függ:* T5

**T7 — Narráció-felvevő**
*Cél:* elem-szerkesztőben A/B felvétel MediaRecorderrel (felvétel/megállítás/
visszahallgatás/újra), feltöltés; fájl-feltöltés alternatívaként.
*Kész, ha:* másik gépről, a tunnel-URL-en működik (HTTPS+mikrofon-engedély);
a nyers fájl a sémába kerül.
*Függ:* T3

**T8 — Hangtisztító pipeline**
*Cél:* `pipeline/audio.py` az ffmpeg-recipes lánccal (48k mono → zajszűrés →
csendvágás → loudnorm), job-ként, loudnorm-riport a logba; UI: nyers vs.
tisztított összehasonlító lejátszó.
*Kész, ha:* zajos tesztfelvételen hallhatóan tisztul; a kimenet I=-16±1 LUFS
(riportból ellenőrizve); idempotens (kétszer futtatva nem romlik).
*Függ:* T7

**T9 — SFX-könyvtár + választó**
*Cél:* `data/sfx` listázása, előhallgatás, elemhez rendelés; betöltéskori
egyszeri normalizálás (recipes szerint).
*Kész, ha:* elemhez SFX rendelhető és a szegmens-render megtalálja; licenc-
emlékeztető a UI-ban az importnál.
*Függ:* T3

**T10 — Szegmens-renderer (a mag!)**
*Cél:* `pipeline/segment.py`: a 03-spec 2–3. pontjának teljes implementációja
(timing a `timing.py`-ból), ffmpeg-recipes mintákkal; job-ként; cache-hash a
`meta.json`-ba.
*Kész, ha:* **golden-teszt**: fix bemenetekből determinista szegmens, fázis-
hosszak ffprobe-bal ±1 frame-en belül; a 03-spec 7. pontjának 1–4. kritériuma
automatikusan ellenőrzött.
*Függ:* T6, T8, T9

**T11 — Összefűzés + letöltés**
*Cél:* `pipeline/assemble.py`: intro + szegmensek + outro (concat demuxer,
azonos paraméterek), szegmens-cache (csak változott elem renderelődik újra);
„Videó elkészítése" gomb + letöltés.
*Kész, ha:* 9 elemes témából final.mp4; egy elem narrációjának cseréje után az
assemble CSAK azt az egy szegmenst rendereli újra (log bizonyítja).
*Függ:* T10

**T12 — E2E: az első éles videó**
*Cél:* egy valódi téma (8–10 elem) végigvitele a rendszeren, a 03-spec 7. pont
teljes ellenőrzőlistájával; a talált súrlódások backlogba.
*Kész, ha:* a final.mp4 feltöltve (unlisted) YouTube-ra hibátlanul megy, és te
elégedett vagy a tempóval/minőséggel.
*Függ:* T11

## F2 — Gyártósori kényelem (1–2 hét, igény szerinti sorrendben)
- Gyártósor-nézet: a téma összes eleme egy táblában státuszokkal, tömeges
  „következő lépés" gombbal.
- Háttérzene + ducking (recipes: sidechaincompress), témánkénti zeneválasztó.
- Intro/outro-szerkesztő (branding assetek cseréje UI-ból), recap-outro.
- Szegmens-előnézet az elem-szerkesztőben (csak az adott elem renderelése).
- Prompt-stílus sablonok témánként (konzisztens képi világ).

## F3 — Extrák
- **YouTube-feltöltés** (YouTube Data API, OAuth; alapértelmezetten unlisted;
  cím/leírás sablonból). Megjegyzés: „gyerekeknek készült" jelölés beállítása.
- TTS-opció a narrációra (skálázás, ha a mikrofonos út szűk keresztmetszet).
- Több felbontás/arány (Shorts 9:16 változat ugyanabból a témából).

## Backlog-fegyelem
Minden „jó lenne még" ide kerül, nem a folyó feladatba. A scope a T12-ig fix.
