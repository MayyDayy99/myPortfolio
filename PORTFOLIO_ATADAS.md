# Portfólió — átadási dokumentum (handoff)

> Cél: ebből a fájlból egy új Claude Code (vagy fejlesztő) a beszélgetés ismerete
> nélkül is fel tudja venni a fonalat. A kész oldal jelenleg **egyetlen fájl**:
> `portfolio.html`. Deploynál nevezd át `index.html`-re.

---

## 1. Mi ez a projekt?

Egy **egyoldalas (one-page) portfólió-weboldal** egy AI-fejlesztő egyéni
vállalkozónak. A tulajdonos **diplomás AI-alkalmazó** és **diplomás
műszaki/projektmenedzser**, aki **magánszemélyeknek és kisvállalkozásoknak**
készít AI-megoldásokat, és **oktatást** is vállal.

- **Fő cél:** ügyfélszerzés (lead generation).
- **Nyelv:** magyar.
- **Technológia:** statikus HTML + CSS + JS egy fájlban, build-lépés nélkül,
  külső függőség nélkül (csak Google Fonts CDN).
- **Hosting terv:** GitHub Pages (külön repó), később saját domain.

---

## 2. VEZÉRELVEK — ezeket ne rontsd el

Ezek tudatos döntések, több iteráció eredményei. Módosításnál tartsd meg őket:

1. **„Show, don't tell".** A munka győzzön meg, ne az önfényezés. Nincs hangzatos
   szlogen, nincs „miért engem" reklámszöveg, nincsenek kitalált vélemények.
   A hangnem tárgyilagos, csendesen magabiztos.
2. **Rejtett komplexitás.** NINCS kiírva „Szint 01/02/03", „alapok/haladó", vagy
   „az egyszerűtől az összetettig". A sorrend (weboldal → webalkalmazás →
   lokális AI) és az, hogy a Lokális AI külön, részletesebb, sötét blokkot kap,
   **magától sugallja** a mélységet. Ne tegyél vissza explicit szint-címkéket.
3. **A lokális / privát AI a fő megkülönböztető.** Weboldalt ma bárki összerak
   olcsón; a „bármilyen nyílt modellt privátban, a te gépeden/felhődben" az, amit
   kevés versenytárs kínál. Az arculat efelé hajlik, és ez az érv a legerősebb.
4. **Minimális, szándékos dizájn.** Egy meleg akcentusszín (borostyán), sok
   levegő, visszafogott tipográfia. Ne legyen sablonos vagy túldíszített.
5. **Diszkrét, de megtalálható UI.** A típusválasztó pl. szegmens-vezérlő
   kerettel lett kiemelve — látszik, hogy vezérlő, de nem harsány.

---

## 3. Oldalszerkezet (fentről lefelé)

| # | Szekció | Azonosító | Tartalom |
|---|---|---|---|
| 1 | Fejléc | `.header` | Ragadós navigáció, mobil hamburger |
| 2 | Masthead | `.mast` | Rövid, tárgyilagos bevezető (nincs szlogen) |
| 3 | Munkák | `#munkak` | **Típusválasztó + lapozható kártyák** (lásd 4. pont) |
| 4 | Lokális AI | `#lokalis-ai` | **Kiemelt, sötét blokk:** architektúra-ábra (inline SVG) + futtatható modelltípusok + hol futtatható + „proof-shot" képhely |
| 5 | Eszköztár | `#amivel` | Technológia-címkék (gyors áttekintés) |
| 6 | Oktatás | `#oktatas` | 3 képzési forma |
| 7 | Rólam | `#rolam` | Rövid, tárgyilagos (2 mondat + diplomák) |
| 8 | Kapcsolat | `#kapcsolat` | E-mail + GitHub + LinkedIn |
| 9 | Lábléc | `.footer` | Név + linkek |

---

## 4. A lapozó (carousel) működése — fontos a kódhoz

A „Munkák" szekcióban **típus szerint böngészhető, lapozható kártyák** vannak.

- **Típusgombok:** `<button class="cat" data-cat="web|app|local">`. Szegmens-
  vezérlő keretben, „Mutasd" felirattal és **automatikus darabszámmal** (a JS
  számolja gombonként).
- **Kártyák:** `<article class="proj" data-cat="web|app|local">` a
  `<div class="track" id="track">` konténeren belül.
- **Viselkedés (JS):** a kiválasztott típushoz nem tartozó kártyák `hidden`-re
  állítódnak; a track `scroll-snap` alapú vízszintes lapozó; asztali gépen a ◀ ▶
  gombok (`.cnav`), mobilon ujjal húzás; alul pöttyök (`.dots`) jelzik a pozíciót.
- **Új projekt hozzáadása:** másolj egy meglévő `<article class="proj" ...>`
  blokkot a `#track`-be, és állítsd a `data-cat`-et. Semmi mást nem kell — a
  szűrés, a lapozás és a darabszám automatikus.

### Kártya-sablon
```html
<article class="proj" data-cat="app">
  <div class="proj-img"><img src="images/valami.png" alt="Leírás"></div>
  <div class="proj-body">
    <div class="meta"><span>Típus</span><span>Fő technológia</span></div>
    <h3>Projekt címe</h3>
    <p>Egy-két mondat: mit csinál, mi a haszna.</p>
    <div class="tags"><span>React</span><span>API</span></div>
    <div class="plinks">
      <a href="https://github.com/OWNER/REPO">GitHub ↗</a>
      <a href="https://ELO-URL/">Élő oldal ↗</a>
    </div>
  </div>
</article>
```
Privát/megbízói munkánál link helyett: `<span class="priv">megbízói projekt — kód-link nélkül</span>`.

---

## 5. Technikai részletek

- **Egy fájl, nincs build.** Minden CSS a `<style>`-ban, minden JS az egy
  `<script>`-ban a `</body>` előtt.
- **Fontok (Google Fonts):** `Bricolage Grotesque` (címsorok), `Hanken Grotesk`
  (törzsszöveg), `Space Mono` (címkék, meta, mono elemek).
- **Színek (CSS változók a `:root`-ban):**
  ```
  --ink:#12231f   --ink-soft:#1b302a   --ink-line:#2a443c   --ink-deep:#0f1c18
  --paper:#eff1ec --paper-2:#e6e9e2    --paper-3:#d6dcd3    --paper-dim:#c3cbc2
  --text:#12231f  --muted:#566760      --amber:#c9822a  (AKCENT – takarékosan!)
  --maxw:1080px   --r:14px
  ```
- **Placeholder képek:** amelyik `<img>`-nek `data-ph` attribútuma van, annak a
  JS betölt egy beépített SVG helykitöltőt. **Valódi képhez:** töröld a `data-ph`-t
  és adj `src`-t (`images/...`).
- **Beágyazott élő demó mechanizmus (jelenleg nincs aktív kártya):** a kód
  támogat egy `.demo-frame` iframe-et:
  - `data-load="sample"` → beépített, működő minta-chatbot (a `DEMO_SAMPLE`
    JS-változóból, `srcdoc`-kal). Ez most **nincs** az oldalon (kivettük, amikor
    bejöttek a valódi repók), de a mechanizmus és a `DEMO_SAMPLE` a JS-ben marad.
  - `data-src="https://..."` → egy hosztolt appot ágyaz be (lazy, csak a fül/
    kategória megnyitásakor tölt). Beágyazható hosztok: Streamlit (`?embed=true`),
    Hugging Face Spaces, Vercel/Netlify/GitHub Pages, StackBlitz/CodeSandbox.
  - **Buktató:** `X-Frame-Options`/`CSP frame-ancestors` egyes oldalakon tiltja a
    beágyazást; a saját hosztolt demók működnek.
- **Reveal-on-scroll:** `[data-reveal]` + IntersectionObserver; JS nélkül és
  `prefers-reduced-motion` esetén minden látható marad (nem tűnik el tartalom).
- **Akadálymentesség:** skip-link, `aria` a füleken/gombokon, `:focus-visible`
  kontúr, reduced-motion tisztelet.
- **TILOS:** `localStorage`/`sessionStorage` (nincs használatban, ne is legyen —
  statikus oldalnál felesleges).

---

## 6. A valós projektek (jelenlegi állapot)

A kártyák a megadott repók README-jei alapján készültek. Kategóriák:
**web** = Weboldalak, **app** = Webalkalmazások, **local** = Lokális AI.

| Repó | Kártyacím | data-cat | Élő URL | Borítókép | Megjegyzés |
|---|---|---|---|---|---|
| MayyDayy99/**AI_workstation** | EDTI Studio — videófeldolgozó AI | `local` | `mayydayy99.github.io/AI_workstation/` ⚠️*konstruált* | placeholder | **A fő AI-bizonyíték.** Whisper→NLLB→XTTS-v2→Demucs pipeline, FastAPI+GPU. Statikus demó. Emeld ki a Lokális AI szekcióba. |
| MayyDayy99/**ago_socihalo** | Nexus — szociálisháló-térkép | `app` | `mayydayy99.github.io/ago_socihalo/` ⚠️*konstruált* | placeholder | React/TS/Vite/Tailwind/D3/Supabase. A license „private". |
| MayyDayy99/**Trollhunting** | Mohás Roham — 3D íjászjáték | `app` | `mayydayy99.github.io/GameDev/` ✅*dokumentált* | placeholder | Three.js FPS, 1 HTML fájl, 2–4 fős co-op. Jó embed-jelölt. |
| MayyDayy99/**cinepair** | CinePair — filmválasztó pároknak | `app` | — *ismeretlen* | ✅ valós (`public/icon-512.png`) | PWA, swipe&match, push. Élő URL pótlandó. |
| LoricatusGroup/**monopoly** | Monopoly — böngészős társas | `app` | `loricatusgroup.github.io/monopoly/` ⚠️*konstruált* | placeholder | README = Vite-sablon; a leírás a névből/stackből készült, **bővítendő**. |
| LoricatusGroup/**museum_2** | Pixel Art Múzeum — 3D kiállítótér | `app` | `loricatusgroup.github.io/museum_2/` ⚠️*konstruált* | ✅ valós (`assets/og-image.png`) | Three.js 3D múzeum, háromnyelvű (HU/EN/IT). Embed-jelölt. |
| MayyDayy99/**obs-stream-overlay-m** | OBS stream-vezérlő — Óbudai Egyetem | `app` | — *OBS-ben fut* | placeholder | OBS overlay-menedzser, controller felület. |
| LoricatusGroup/**loricatus_honlap** | Loricatus — céges weboldal | `web` | `loricatusgroup.github.io/loricatus_honlap/` ⚠️*konstruált* | ✅ valós (`DJI-Zenmuse-L1-scaled.webp`) | Statikus céges honlap (HTML/CSS/JS). |
| MayyDayy99/**balaton** | — | — | — | — | ⚠️ **404 – nem található.** Elgépelés vagy privát repó. Tisztázni. |

**Jelmagyarázat:**
`✅ dokumentált` = a README-ben szerepel, megbízható.
`⚠️ konstruált` = a szokásos `OWNER.github.io/REPO/` minta alapján készült, **NEM ellenőrzött** (a build-környezet IP-jét a Pages CDN tiltotta) — kattintással ellenőrizni kell, hogy tényleg él-e.

### Jelenleg hotlinkelt képek (raw GitHub) — érdemes `images/`-be tenni
```
museum_2:          https://raw.githubusercontent.com/LoricatusGroup/museum_2/HEAD/assets/og-image.png
cinepair:          https://raw.githubusercontent.com/MayyDayy99/cinepair/HEAD/public/icon-512.png
loricatus_honlap:  https://raw.githubusercontent.com/LoricatusGroup/loricatus_honlap/HEAD/DJI-Zenmuse-L1-scaled.webp
```

---

## 7. Kitöltendő placeholderek

Keress rá a `[ ]` jelekre a `portfolio.html`-ben, és cseréld le:

- `[NEVED]` — a teljes név (fejléc, masthead „Rólam", lábléc, `<title>`, meta)
- `[TE.EMAIL@PELDA.HU]` — e-mail cím (Kapcsolat, `mailto:`)
- `[github-felhasznalo]` — a fő GitHub felhasználónév (az „összes projekt" gomb, Kapcsolat)
- `[linkedin-profil]` — LinkedIn URL-részlet (Kapcsolat)

---

## 8. Nyitott feladatok (TODO)

1. **`balaton` 404** — tisztázni: elgépelés, átnevezés vagy privát repó? Javítani vagy elhagyni.
2. **Élő URL-ek ellenőrzése** — a ⚠️ jelölt (konstruált) linkeket végigkattintani; ahol nem él, a valódi URL-re cserélni (vagy elhagyni).
3. **Képek:** 5 kártyán placeholder van (EDTI Studio, Nexus, Mohás Roham, OBS, Monopoly) — képernyőkép kell. A 3 hotlinkelt képet is érdemes `images/`-be letölteni és a `src`-t átírni.
4. **Kategória-egyensúly:** a `app` tele (6), a `web` és `local` 1-1. Vagy több weboldal/lokális projekt, vagy a kategóriák átcsoportosítása/átnevezése (pl. a játékok/3D külön).
5. **`monopoly`** leírása bővítendő (a repó README-je csak a Vite-sablon).
6. **Leírások lektorálása** — a kártyaszövegeket az AI fogalmazta a README-k alapján; érdemes átolvasni pontosságért.
7. **EDTI Studio kiemelése** — a legerősebb AI-bizonyíték; tedd be a „Lokális AI" szekció bizonyíték-részébe (nem csak kártyaként). A generikus modell-listát is lehet a valós pipeline-ra hangolni (ASR→fordítás→hangklónozás→stem-szeparáció).
8. **Valódi beágyazott demó** visszatétele (opcionális) — az EDTI Studio statikus demója vagy a Mohás Roham a legjobb jelölt, ha az élő URL-jük megbízhatóan működik.

---

## 9. Deploy (GitHub Pages)

1. Új, publikus repó (pl. `portfolio`).
2. A `portfolio.html` → nevezd át **`index.html`**-re, tedd a repó gyökerébe.
3. Képek az `images/` mappába (a hotlinkek helyett), a `src`-eket átírni.
4. Repó → **Settings → Pages → Branch: `main`** (gyökér). Pár perc múlva él.
5. **Saját domain (ajánlott):** egy `nev.hu` aránytalanul sokat dob a szakmai
   megjelenésen ügyfélszemmel. Pages → Custom domain + DNS.

---

## 10. Stratégiai javaslatok (opcionális, de érdemes)

- **A lokális/privát AI-val nyiss** — ez a megkülönböztető. A weboldal-készítés
  árversenyes piac; a privát AI nem az.
- **Csökkentsd a kapcsolatfelvétel súrlódását** — az „írj e-mailt" a legmagasabb
  küszöb. Egy „foglalj 20 perces hívást" (pl. Calendly) vagy egy egyszerű űrlap
  többet konvertál. Egy árjelzés („ingyenes felmérés" / „…-tól") is old a
  bizonytalanságon.
- **A legerősebb bizonyíték egy valódi felvétel** — 20–30 mp-es képernyővideó a
  futó saját lokális AI-ról (pl. Open WebUI), ideálisan egy anonim ügyféleset
  konkrét számmal („heti X óra megspórolva").
- **Valódi képernyőképek mindenek felett** — a „show, don't tell" irányban egy
  igazi kép többet ér minden szövegnél.

---

## 11. Rövid kontextus a Code-nak (bemásolható)

> Egy magyar nyelvű, egyfájlos (`index.html`) portfólió-weboldalon dolgozom egy
> AI-fejlesztő egyéni vállalkozónak. Vezérelvek: „show, don't tell" (a munka
> győzzön meg, ne az önfényezés); a projektkomplexitást csak **sugallni** akarjuk,
> NEM kiírni (nincs „Szint 1/2/3"); a **lokális/privát AI** a fő megkülönböztető.
> A „Munkák" szekció egy típus szerint lapozható carousel: a kártyák
> `<article class="proj" data-cat="web|app|local">` a `#track`-ben, a szűrés/
> lapozás/darabszám automatikus. Statikus HTML+CSS+JS, nincs build, nincs külső
> függőség (csak Google Fonts). Ne vezess be `localStorage`-t. A részletes állapot,
> a valós projektek, a nyitott feladatok és a színek/fontok ebben az átadási
> dokumentumban vannak.
