# 03 — Videó-specifikáció („Már ezt is tudom" formátum)

> Ez a fájl a dramaturgia és az időzítés **egyetlen forrása**. A kód a
> `pipeline/timing.py`-ban lévő configból olvassa ugyanezeket az értékeket;
> változtatás CSAK itt + ott, együtt. Minden idő másodpercben.

## 1. A videó szerkezete

```
[INTRO 4,0s] → [ELEM 1] → [ELEM 2] → … → [ELEM 8-10] → [OUTRO 4,0s]
```

- **Intro**: csatorna-branding (statikus kép vagy rövid animáció) + szignál.
  MVP-ben: 1 db `intro.mp4` vagy kép+hang a `data/branding/` alól.
- **Elemek közti átmenet**: 0,5 s crossfade (xfade) VAGY vágás — téma-beállítás.
- **Outro**: branding + „Ügyes vagy!" zárás. MVP-ben statikus, v2-ben recap-rács
  (a 8-10 elem kis képei egyszerre — visszaidézés, tanulás-megerősítés).

## 2. Egy elem szegmensének idővonala

```
fázis            vizuál                       hang                hossz
───────────────  ───────────────────────────  ──────────────────  ─────────────
1. belépés       sziluett fade+scale-in       —                   0,8
                 (0,95→1,0)
2. találós       sziluett áll                 narration_a.clean   len(A) + 0,4
3. ütem-szünet   sziluett áll                 csend               0,4
4. hangeffekt    sziluett áll                 sfx                 max(len(SFX), 1,2)
5. reveal        sziluett → cutout crossfade  — (vagy SFX vége)   0,6
6. megnevezés    cutout áll                   narration_b.clean   len(B) + 0,5
7. kitartás      cutout áll                   —                   1,2
```

Szegmenshossz = a fenti összeg. Tipikus elem: ~10–14 s → egy 9 elemes videó
intróval-outróval ~2–2,5 perc. Ez a formátumnak jó alap.

## 3. Vizuális szabályok

- Vászon: **1920×1080, 30 fps**, minden szegmens és a végső videó azonos
  paraméterekkel (különben a concat nem lehet veszteségmentes).
- Háttér: témánként egy `background.png` (1920×1080) VAGY egyszínű háttér a
  téma-beállításból. Gyerekbarát, alacsony kontrasztú, hogy a sziluett üljön.
- Elem-elhelyezés: vízszintesen középre; **max. magasság a vászon 70%-a**
  (756 px), max. szélesség 60% (1152 px) — arányőrző illesztés, alsó harmadhoz
  igazított alapvonal (a tárgy „áll", nem lebeg).
- Sziluett: a `cutout.png` alfa-csatornája **teljesen feketével** kitöltve
  (nem sötétített kép! — találósnak felismerhetetlennek kell lennie a
  textúrának). Opcionális v2: enyhe fehér glow a kontúr körül.
- A reveal crossfade alatt a sziluett és a cutout **pixelre azonos pozícióban
  és méretben** van — ettől „életre kel" hatású.

## 4. Audió-szabályok

- Munkaformátum: 48 kHz; narráció mono, végső keverés sztereó.
- Narráció-tisztítás célértékei (ffmpeg `loudnorm`): **I=-16 LUFS,
  TP=-1.5 dB, LRA=11** (YouTube-barát beszédhangosság).
- SFX-ek a betöltéskor ugyanerre a hangosság-tartományra normalizálva
  (egyszeri elő-feldolgozás a könyvtárban), lejátszáskor -2 dB a narrációhoz
  képest.
- Csend-vágás: a narráció elejéről/végéről -45 dB alatti részek le, de elöl
  0,15 s, hátul 0,25 s „levegő" marad.
- Háttérzene (v2): -22 dB alapszint + sidechain-ducking a narráció alá.

## 5. Tartalmi konvenciók (a „gyár" inputjai elemenként)

| Input | Forrás | Megjegyzés |
|---|---|---|
| `name` | kézi | az elem neve (pl. „tehén") |
| `prompt` | kézi (sablonból) | a témához stílus-prefix: a téma-beállítás adja, az elem-prompt csak a tárgyat írja le |
| `seed` | auto + újragenerálható | reprodukálhatóság |
| narráció A | mikrofon | körülírás, NEM mondja ki a nevet |
| narráció B | mikrofon | „Ez a(z) … ! <egy mondat>" |
| SFX | data/sfx könyvtárból | az elemhez köthető hang |

## 6. Elnevezési szabályok

- `slug`: kisbetűs, ékezet nélkül, kötőjeles (`tehen`, `tuzolto-auto`).
- Elem-mappa: `NN-<slug>` (NN = pozíció, 01-től) — a sorrend a fájlrendszerből
  is olvasható.

## 7. Elfogadási minimum egy kész videóra

1. Minden szegmens a 2. pont idővonalát követi (±1 frame).
2. Hangosság a 4. pont szerint (loudnorm riport a job-logban).
3. Nincs hallható kattanás a szegmenshatárokon (audió fade 10 ms).
4. A reveal alatt nincs elcsúszás a sziluett és a kép között.
5. A final.mp4 QuickTimeban és Chrome-ban hibátlanul lejátszható, YouTube-ra
   feltöltve nem ír át semmit (formátum-kompatibilis).
