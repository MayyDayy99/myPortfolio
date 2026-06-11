# „Már ezt is tudom" — videógyár dokumentációs csomag

Sablon-alapú videógenerátor a gyerekcsatornához: 8–10 elem/téma, elemenként
**sziluett → narráció → hangeffekt → reveal**. Fut: M5 MacBook Pro, Docker +
natív ComfyUI (Metal GPU), kifelé Cloudflare Tunnel + Access. A fejlesztés
Claude Code-ban történik.

> **Állapot (2026-06-11):** a nem-Mac-specifikus MVP **kód kész és verifikált**
> (backend + frontend + pipeline + tesztek; `pytest`: 77 passed / 1 skipped). A
> projekt a `kidsvideo-factory-docs/kidsvideo-factory/` mappában él. **Folytatod
> a fejlesztést? Olvasd el a `docs/06-STATUS.md`-t** (állapot, fájltérkép,
> hátralévő munka, Mac-setup checklista) és a `CONTRACTS.md`-t (interfész-szerződés).

## Mi hol van
| Fájl | Mi ez |
|---|---|
| **`docs/06-STATUS.md`** | **átadó doc: jelenlegi állapot, fájltérkép, hátralévő munka, Mac-checklista** |
| `CONTRACTS.md` | kötelező interfész-szerződés (új kódot ehhez illeszd) |
| `CLAUDE.md` | Claude Code projekt-memória: aranyszabályok, architektúra, parancsok |
| `docs/01-BLUEPRINT.md` | technikai blueprint (rendszer, adatmodell, pipeline-ok, biztonság) |
| `docs/02-IMPLEMENTATION-PLAN.md` | fázisolt terv: F0 spike → F1 MVP (T1–T12) → F2/F3 |
| `docs/03-VIDEO-SPEC.md` | a videóformátum egyetlen forrása (dramaturgia, időzítés, audió) |
| `docs/04-OPERATIONS.md` | runbook: Mac-beállítás, ComfyUI launchd, tunnel+Access, mentés, hibakeresés |
| `docs/05-DECISIONS.md` | ADR-ek + élő licenc-jegyzék |
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
