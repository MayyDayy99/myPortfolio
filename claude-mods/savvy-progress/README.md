# Savvy Progress

Claude Code mod: látod, mit csinál minden segéd-Claude (subagent), és nagyjából mennyibe kerül, élőben.

- **Sáv a prompt felett:** `Agents 1/3 ████░░░░ ≈$0.34 · 196k tok · 0:19`, alatta pixel rákok sétálnak, amíg dolgoznak a subagentek.
- **`/agents-info` panel** (megnyitja / bezárja): a feladat címe, összköltség / tokenek / idő, aztán **Running** és (összecsukható) **Finished** csoport. Minden subagentnél: leírás, típus, modell, effort, kontextus-telítettség sávja, `ctx % · tokenek · ≈$ · idő`.

A költség becslés a token-számokból és egy beépített ártáblából (`hooks/pricing.ts`), nem a tényleges számla.

## Telepítés

Claude Code terminálban (2.1.287+), miután ez a mappa a repó alapértelmezett ágán van:

```
/plugin install savvy-progress --marketplace MayyDayy99/myPortfolio
```

Erre `y` (marketplace hozzáadása), majd Enter a user scope-ra. Utána indíts új sessiont, vagy futtasd: `/reload-plugins`.

Csak kipróbálni, egy sessionre, a repó egy klónjából:

```
claude --plugin-dir ./claude-mods/savvy-progress
```

## Kipróbálás

Adj Claude-nak egy feladatot, ami több subagentre bontható, aztán írd be: `/agents-info`.

## Fejlesztés

```
claude plugin validate ./claude-mods/savvy-progress
claude plugin test ./claude-mods/savvy-progress
```
