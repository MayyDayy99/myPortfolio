# Tartalomposztoló bekötése

A blog úgy épül fel, hogy a `blog/_posts/` mappába kerülő JSON fájlokból a
GitHub Actions legenerálja a `/blog/` oldalt. A posztolónak tehát csak annyi a
dolga, hogy egy poszt eljusson ebbe a mappába. Erre két út van.

---

## 1. út — közvetlenül a GitHubra (ez az egyszerűbb)

Akkor jó, ha a posztolóba be tudod állítani a kérés törzsét is, nem csak a
végpontot és a kulcsot.

**Végpont**

```
https://api.github.com/repos/MayyDayy99/myPortfolio/dispatches
```

**Fejlécek**

```
Authorization: Bearer <a GitHub tokened>
Accept: application/vnd.github+json
Content-Type: application/json
```

**Törzs**

```json
{
  "event_type": "new-post",
  "client_payload": {
    "title": "A poszt címe",
    "content": "Markdown vagy HTML szöveg.",
    "excerpt": "Egy mondatos ajánló. Elhagyható.",
    "tags": ["lokális AI", "automatizálás"],
    "date": "2026-08-25"
  }
}
```

A `title` és a `content` kötelező, a többi elhagyható. A `slug` és a `date`
magától kitöltődik, ha nem küldöd. Ha `"status": "draft"` van a posztban, a
fájl bekerül a repóba, de nem jelenik meg az oldalon.

**A token**

GitHub → Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token.

- Repository access: csak a `myPortfolio` repó
- Permissions → Repository permissions → **Contents: Read and write**
  (a `metadata: read` magától bejön)

Ez a token megy a posztoló „App-password / kulcs” mezőjébe. Ne a GitHub
jelszavad add meg, és ne is másold be sehova máshova.

**Teszt**

```bash
curl -X POST https://api.github.com/repos/MayyDayy99/myPortfolio/dispatches \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -d '{"event_type":"new-post","client_payload":{"title":"Teszt poszt","content":"Ez egy teszt. Ha látod a blogon, működik."}}'
```

Sikeres kérésre a GitHub `204`-et ad, üres törzzsel. Utána a repó **Actions**
fülén megjelenik a „Blog építése” futás, és pár perc múlva ott a poszt.

---

## 2. út — a híd (ha a posztoló csak WordPress-alakot tud küldeni)

Ha a posztolóban csak egy végpont és egy jelszó adható meg, és a törzset ő maga
állítja össze WordPress-alakban (`{"title": ..., "content": ..., "status": ...}`),
akkor a GitHub végpontja nem jó neki: a GitHub `event_type` mezőt vár. Ilyenkor
a `worker.js` fájl a megoldás — WordPress-alakot fogad, és átfordítja.

**Telepítés (telefonról is megy, pár perc)**

1. [dash.cloudflare.com](https://dash.cloudflare.com) → Workers & Pages →
   Create → Start with Hello World → Deploy
2. Edit code → töröld a mintát, másold be a `worker.js` tartalmát → Deploy
3. Settings → Variables and Secrets:

   | Név | Típus | Érték |
   |---|---|---|
   | `REPO` | Text | `MayyDayy99/myPortfolio` |
   | `BRIDGE_KEY` | Secret | egy általad kitalált hosszú jelszó |
   | `GH_TOKEN` | Secret | a fenti fine-grained GitHub token |

**A posztolóba ez kerül**

```
A honlap API-végpontja:  https://<a-workered>.workers.dev/wp-json/wp/v2/posts
App-password / kulcs:    a BRIDGE_KEY értéke
```

A híd `Basic` és `Bearer` fejlécet is elfogad, JSON és form törzset is, és
WordPress-szerű választ ad vissza, hogy a posztoló sikeresnek lássa a küldést.
A GitHub token csak a Workerben van, a posztoló soha nem látja.

**Teszt**

```bash
curl -X POST https://<a-workered>.workers.dev/wp-json/wp/v2/posts \
  -H "Authorization: Bearer $BRIDGE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title":"Teszt a hídon át","content":"Ha ez megjelenik, a híd is jó."}'
```

---

## Amire figyelj

- **A workflow-nak a `main` ágon kell lennie.** A `repository_dispatch` mindig
  az alapértelmezett ág workflow-ját futtatja. Amíg a blog csak a fejlesztői
  ágon van, a webhook nem indít semmit — a `main`-be olvasztás után indul.
- **Kézi teszt token nélkül:** repó → Actions → „Blog építése” → Run workflow.
  Ez újraépíti a blogot a már meglévő fájlokból.
- **Fájllal is lehet posztolni:** tegyél egy `blog/_posts/2026-08-25-cim.json`
  fájlt a repóba, a workflow ugyanúgy lefut.
