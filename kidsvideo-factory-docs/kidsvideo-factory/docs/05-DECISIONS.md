# 05 — Döntési jegyzőkönyv (ADR) és licenc-jegyzék

Rövid, számozott döntések. Új jelentős döntés → új ADR, a régit nem írjuk át
(legfeljebb „felülírta: ADR-N" megjegyzést kap).

## ADR-1 — Szerveroldali ffmpeg-pipeline, nem böngészős WebCodecs
**Döntés:** minden render a szerveren (konténerben) fut ffmpeg-gel.
**Indoklás:** a korábbi (elvetett) terv böngészős kódolásra épült, aminek fő
kockázatai (alpha-kódolás megbízhatatlansága, iOS-memóriakorlátok, böngésző-
mátrix) itt nem léteznek; a végtermék amúgy is kész MP4, nem alpha-klip. Az
ffmpeg ráadásul a hangtisztítást is adja.
**Ár:** a kliens vékony — minden terhelés a Macen.

## ADR-2 — ComfyUI natívan a macOS hoston, nem Dockerben
**Döntés:** a ComfyUI külön natív folyamat (launchd), a konténer API-n hívja
(`host.docker.internal:8188`).
**Indoklás:** macOS-en a konténerek Linux VM-ben futnak, és nincs Metal
GPU-passthrough — Dockerben az SD csak CPU-n menne (használhatatlanul lassú).
Natívan az M5 GPU-ja teljes sebességgel dolgozik.
**Ár:** egy compose-on kívüli komponens, amit a runbook (04) kezel.

## ADR-3 — FastAPI (Python) backend + React/Vite frontend
**Döntés:** Python backend.
**Indoklás:** a rembg natív Python; a ComfyUI-kliensminták Pythonosak; az
ffmpeg-orchesztráció subprocess-szel triviális; egy nyelvben marad a teljes
pipeline. Frontend: React+Vite, a build a backendből statikusan kiszolgálva
(egyetlen exponált szolgáltatás).
**Alternatíva volt:** TS-monorepo (Node backend) — elvetve a rembg/ML miatt.

## ADR-4 — SQLite + fájlrendszer; nincs Redis/Postgres/Celery
**Döntés:** metaadat és job-sor SQLite-ban, assetek fájlrendszeren, worker az
app-folyamat asyncio-loopjában.
**Indoklás:** egyfelhasználós „gyár"; a legkisebb mozgó alkatrész nyer. A
job-sor perzisztens (újraindítás-álló), ennyi elég.
**Felülvizsgálat:** ha valaha többfelhasználós lesz — most nem cél.

## ADR-5 — ComfyUI-kimenet a /history + /view úton (nem websocket-streamelt kép)
**Döntés:** beküldés `POST /prompt`-tal, készre-várás websocketen, a kép
letöltése `/history/{prompt_id}` + `/view`-val (SaveImage node-dal).
**Indoklás:** ez a hivatalos példa mintája; újraindítás/megszakadás után is
visszakereshető a kész kép (a websocket-only út törékenyebb, és custom node-ot
igényelne RGBA-hoz). A kivágást úgyis mi végezzük rembg-vel.

## ADR-6 — Kifelé csak az app, Cloudflare Access-szel
**Döntés:** a tunnel egyetlen public hostname-je az app; előtte Access-policy
(csak a tulaj e-mailje). A ComfyUI és a backend-port LAN felé sem publikált.
**Indoklás:** a ComfyUI-nak nincs hitelesítése — kiengedése azonnali kockázat;
az Access nulla extra kóddal ad belépés-védelmet és HTTPS-t (mikrofonhoz kell).

## ADR-7 — Licenc-jegyzék (élő lista — minden új függőségnél frissítendő)

| Összetevő | Licenc | Állapot / teendő |
|---|---|---|
| FastAPI / uvicorn / pydantic | MIT/BSD | ✔ |
| React / Vite / TS | MIT/Apache | ✔ |
| rembg | MIT | ✔ |
| onnxruntime (rembg húzza be) | MIT | ✔ runtime-függőség a rembg inferenciához |
| u2net / u2netp modell | Apache-2.0 | ✔ (a letöltött fájl hash-ét rögzítsd) |
| python-multipart | MIT | ✔ multipart feltöltés (FastAPI form/file) |
| websocket-client | Apache-2.0 | ✔ comfy.py WS-várakozás (a csomag az 1.0 óta Apache-2.0; a régi LGPL csak <1.0) |
| httpx | BSD-3-Clause | ✔ csak dev/teszt (FastAPI TestClient) |
| pillow (PIL) | HPND/PIL (SPDX: MIT-CMU) | ✔ kép-/sziluett-műveletek |
| ruff | MIT | ✔ csak dev (lint/format) |
| ffmpeg build (libx264-gyel) | GPL | ✔ belső futtatás, nem terjesztjük; ha valaha terjesztenénk az appot, újraértékelendő |
| ComfyUI | GPL-3.0 | ✔ külön folyamat, API-n át |
| SD checkpoint (választott) | OpenRAIL-jellegű / egyedi | ⚠ A KONKRÉT modell licencét le kell ellenőrizni kereskedelmi (monetizált YouTube) használatra, MIELŐTT éles videóba kerül. A döntést ide jegyezd be (modellnév + licenc + dátum). |
| SFX-fájlok | egyedi | ⚠ Csak redistribution/sync jogú hang kerülhet a data/sfx-be; forrás+licenc fájlonként a data/sfx/LICENSES.md-ben |
| Betűtípus (branding) | OFL ajánlott | ⚠ rögzítendő, ha intro/outro szöveget kap |

## ADR-8 — Tartalmi irányelv (platformkockázat)
**Döntés:** a gyár MINŐSÉGI, oktató jellegű gyerektartalmat gyorsít (igényes
narráció, tiszta hang, átgondolt képi világ) — nem tömeg-spam eszköz. A
YouTube „made for kids" szabályait a feltöltési folyamat (F3) kötelezően
kezeli (jelölés, megfelelő metaadat).
**Indoklás:** a gyerektartalom-piac szabályozási/monetizációs nyomás alatt áll;
a hosszú távú csatorna-érték a minőségből jön.
