---
name: ffmpeg-recipes
description: Kanonikus ffmpeg-minták a videógyárhoz — kódolási alapparaméterek, narráció-tisztító lánc (zajszűrés, csendvágás, loudnorm), szegmensépítés (sziluett→reveal xfade), concat, SFX-normalizálás, zene-ducking és a tipikus buktatók. Használd MINDEN ffmpeg-, render-, hang-, zaj-, loudnorm-, concat- vagy szegmens-feladatnál. (ffmpeg, audio cleanup, noise reduction, render, encode, xfade, concat)
---

# ffmpeg-receptek — a render-réteg kánonja

> Szabály (CLAUDE.md #2): minden ffmpeg-hívás ezekből a mintákból indul. Új,
> bevált recept ide kerül vissza. A számszerű időzítések forrása a
> docs/03-VIDEO-SPEC + `pipeline/timing.py` — itt csak placeholder.

## R1 — Globális kódolási paraméterek (MINDEN videó-kimenetre azonos!)
```
-r 30 -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
-c:a aac -b:a 192k -ar 48000 -ac 2 -movflags +faststart
```
Miért: a szegmensek és a final azonos paraméterekkel készülnek, így a concat
veszteségmentes lehet (R5). A `yuv420p` + páros méretek nélkül sok lejátszó
elhasal. 1920×1080 fix vászon.

## R2 — Narráció-tisztító lánc (P2 pipeline)
Bemenet: nyers webm/wav → kimenet: `*.clean.wav` (48k mono, -16 LUFS).
Két lépésben (a loudnorm pontosabb két passzban, MVP-ben egy passz elég):
```
ffmpeg -y -i RAW -af "\
aformat=sample_rates=48000:channel_layouts=mono,\
highpass=f=80,\
afftdn=nr=12:nf=-30,\
silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,\
areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.25,areverse,\
loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" \
-ar 48000 CLEAN.wav
```
- A `loudnorm` JSON-riportját (stderr) a job-logba kell írni (a 03-spec 7.2
  elfogadási pontja ebből ellenőrződik).
- Zajszűrés-fokozat: ha az `afftdn` kevés, opció az `arnndn` (RNNoise) — ehhez
  modellfájl kell (`.rnnn`, a rnnoise-models repóból); a fájl útja env/config.
  Döntés esetén ADR-be.
- Hossz-lekérdezés (a timing-számításhoz):
  `ffprobe -v error -show_entries format=duration -of csv=p=0 CLEAN.wav`

## R3 — SFX egyszeri normalizálása (importkor)
```
ffmpeg -y -i SFX_RAW -af "aformat=sample_rates=48000:channel_layouts=stereo,\
loudnorm=I=-18:TP=-1.5:LRA=11" -ar 48000 data/sfx/<nev>.wav
```
(-18: a narrációnál ~2 dB-lel halkabb cél — 03-spec 4. pont.)

## R4 — Szegmensépítés (P3 magja) — a minta logikája
Egy elem szegmense két vizuális fázisból áll (sziluett-szakasz, reveal-szakasz),
amit `xfade` köt össze; a hangsáv a fázis-offsetekre `adelay`-elt keverés.
A Python (`pipeline/segment.py`) így építi a filtergráfot:

```
BEMENETEK:  background.png, silhouette.png, cutout.png,
            narr_a.clean.wav, sfx.wav, narr_b.clean.wav
IDŐK (timing.py-ból számolva): t_sil  = belépés+narrA+szünet+sfx
                               t_rev  = narrB + kitartás
                               t_total= t_sil + t_rev   (xfade átfedéssel)

VIZUÁL:
[bg loop t_total] ──┐
[silhouette skálázva, pozicionálva, fade-in 0.8s, loop t_sil] ─ overlay ─┐
[cutout UGYANAZZAL a skálával/pozícióval, loop t_rev] ───────────────────┤
        a két overlay-elt sáv:  xfade=transition=fade:duration=0.6:offset=t_sil-0.6
HANG:
[narr_a  adelay=800]  +  [sfx adelay=(belépés+narrA+szünet)*1000]
                      +  [narr_b adelay=(t_sil+0.6visszavágás)*1000]
        → amix=inputs=3:normalize=0, apad → -shortest a videóhoz
KIMENET: R1 paraméterekkel segment.mp4
```
Kötelező részletek:
- A sziluett és a cutout **azonos scale/overlay-koordinátákat** kap (a méretet
  a cutout bounding boxából egyszer számoljuk) — különben a reveal „ugrik".
- Skálázás: `scale=w=min(1152\,iw*756/ih):h=756:force_original_aspect_ratio=decrease`
  jellegű kifejezés; pozíció: vízszintes közép, alapvonal a vászon ~78%-án.
- Audió-illesztések 10 ms fade-del (`afade`) a kattanás ellen (03-spec 7.3).
- A pontos, tesztelt filtergráf a T10 feladatban véglegesedik **golden-teszttel**
  (fix bemenet → ffprobe-bal mért fázishosszak ±1 frame). A golden-teszt a
  recept változásakor is fut — ez védi a formátumot.

## R5 — Összefűzés (assemble)
Minden darab R1-gyel készült → concat demuxer, újrakódolás nélkül:
```
# list.txt:  file 'intro.mp4' / file '01-…/segment.mp4' / … / file 'outro.mp4'
ffmpeg -y -f concat -safe 0 -i list.txt -c copy render/final.mp4
```
Ha BÁRMELYIK darab paramétere eltér (pl. régi cache), a `-c copy` hibázik vagy
hibás fájlt ad → fallback: újrakódolás R1-gyel. A helyes megoldás ilyenkor az
eltérő szegmens újrarenderelése (cache-hash, 01-BLUEPRINT 6.3), nem a néma
újrakódolás.

## R6 — Háttérzene + ducking (F2)
```
[zene] volume=-22dB ─┐
[narrációk összege] ─┴ sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400
```
A zene a teljes videó alá, a duck a narráció-sávval vezérelve; intro/outro
alatt teljes szint.

## Buktató-lista (ha furcsa a kimenet, ELŐSZÖR ezt nézd)
- Páratlan képméret → libx264 hiba: minden scale-kifejezés végén biztosíts
  páros értéket (`floor(.../2)*2`).
- Hiányzó `yuv420p` → QuickTime/Safari fekete vagy nem játssza le.
- PNG alfa overlay: az inputot `format=rgba`-val vidd a filtergráfba, a végső
  kimenet előtt `format=yuv420p`.
- `amix` alapból normalizál (halkít) → `normalize=0` és kézi szintek.
- Kép-loop input: `-loop 1 -t <sec> -i kep.png` ÉS `-r 30`, különben VFR-gyanús
  kimenet lesz.
- A concat demuxer relatív utakat a list.txt helyéhez képest old fel.
- Időzítés-ellenőrzés: `ffprobe -show_frames`-szel vagy a csomagolt
  `tests/probe_phases.py`-jal — sose szemre.
