# 04 — Üzemeltetési runbook (a Mac mint csendes szerver)

## 1. Egyszeri Mac-beállítás

**1.1 Alapok**
- Docker Desktop telepítve, „Start Docker Desktop when you sign in" bekapcsolva.
- Automatikus bejelentkezés a felhasználóra (Rendszerbeállítások → Felhasználók),
  hogy áramszünet utáni újraindulásnál minden magától felálljon. FileVault
  esetén az automatikus login korlátozott — tudatos döntés kell (biztonság vs.
  kényelem).

**1.2 ComfyUI natívan (Metal GPU)**
- Telepítés a hivatalos repo szerint külön venv-be (pl. `~/comfy/ComfyUI`),
  modellek a `~/comfy/ComfyUI/models/checkpoints` alá.
- Indítás kézzel (teszthez): `python main.py --listen 127.0.0.1 --port 8188`
  — a `127.0.0.1` fontos: így a LAN felől sem elérhető, csak a gépen belülről.
- Fontos: a Docker Desktop alapból átengedi a konténerből a
  `host.docker.internal` hívást a host 8188-ra — ellenőrzés:
  `docker compose run app curl -s http://host.docker.internal:8188/system_stats`

**1.3 ComfyUI mint háttérszolgáltatás (launchd)**
`~/Library/LaunchAgents/com.kidsvideo.comfyui.plist` (sablon — az utakat írd át):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.kidsvideo.comfyui</string>
  <key>ProgramArguments</key><array>
    <string>/Users/TE/comfy/venv/bin/python</string>
    <string>/Users/TE/comfy/ComfyUI/main.py</string>
    <string>--listen</string><string>127.0.0.1</string>
    <string>--port</string><string>8188</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/TE/comfy/ComfyUI</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/comfyui.log</string>
  <key>StandardErrorPath</key><string>/tmp/comfyui.err</string>
</dict></plist>
```
Aktiválás: `launchctl load ~/Library/LaunchAgents/com.kidsvideo.comfyui.plist`

**1.4 Alvás-beállítások (a „csendben dolgozik" kulcsa)**
- Tápon tartva: `sudo pmset -c sleep 0` (rendszer nem alszik el hálózaton),
  a kijelző alhat: `sudo pmset -c displaysleep 10`.
- **Csukott fedél**: hivatalosan csak clamshell módban marad ébren (táp +
  külső kijelző csatlakoztatva). Külső kijelző nélkül csukva tartáshoz
  harmadik féltől származó eszköz kell (pl. Amphetamine closed-display) — ez
  nem támogatott út, és **csukva romlik a hűtés**: tartós SD-generálásnál
  throttle-olhat. **Ajánlott üzemmód:** fedél NYITVA, kijelző sötét, tápon —
  ugyanolyan csendes, jobb hűtés.

## 2. Cloudflare Tunnel + Access

1. Cloudflare Zero Trust → Tunnels → új tunnel → a kapott **tokent** a `.env`
   `TUNNEL_TOKEN` változójába (a cloudflared konténer ezt használja).
2. Public hostname: `gyar.sajatdomain.hu` → service: `http://app:8000`
   (a compose-hálózaton belüli név).
3. **Access-szabály** ugyanerre a hostnévre: Zero Trust → Access → Application
   → policy: csak a saját e-mail címed (One-time PIN vagy Google login).
4. **Tilos**: bármilyen public hostname a 8188-ra. A ComfyUI sosem megy ki.
5. Teszt másik gépről: a hostnév betölt → Access-login → app látszik;
   `https://gyar.sajatdomain.hu` alatt a mikrofon-engedély kérhető (HTTPS ✔).

## 3. Indítás / leállítás

```
# indítás (a repo gyökerében)
docker compose up -d --build
# állapot
docker compose ps && curl -s localhost:8000/healthz
# leállítás
docker compose down
```
A ComfyUI a launchd miatt magától fut; kézi újraindítás:
`launchctl kickstart -k gui/$(id -u)/com.kidsvideo.comfyui`

## 4. Mentés

- **Mit**: a teljes `data/` (projektek, hangok, db.sqlite3) + a `workflows/`
  + a `.env` (titok! — külön, titkosítva).
- **Hogyan**: a legegyszerűbb a Time Machine (a repo + data a gépen van), plusz
  heti `tar` a data/-ról külső tárhelyre. A modellek (`data/models`,
  ComfyUI checkpointok) újra letölthetők — mentésük opcionális.
- Visszaállítás-teszt félévente: data/ visszamásolás üres gépre → compose up →
  a témák látszanak.

## 5. Frissítés

- App: `git pull && docker compose up -d --build`.
- ComfyUI: `git pull` a ComfyUI mappában + venv-frissítés → **előbb** kézi
  teszt egy generálással, csak utána launchd-újraindítás. A workflow-JSON-ok
  verzióérzékenyek lehetnek — frissítés után az S1 spike-szkripttel füstteszt.

## 6. Hibakeresés (tünet → teendő)

| Tünet | Valószínű ok / teendő |
|---|---|
| App: „ComfyUI nem érhető el" | natív folyamat áll → `tail -f /tmp/comfyui.err`; launchd kickstart; port-teszt a hostról: `curl 127.0.0.1:8188/system_stats` |
| Képgen elindul, sosem ér véget | ComfyUI-oldali hiba (modell hiányzik?) → comfyui.log; a job-log mutassa a ComfyUI üzenetét |
| Tunnel-URL nem tölt be | `docker compose logs cloudflared`; token érvényes? Cloudflare-oldalon a tunnel „healthy"? |
| Mikrofon nem kérhető | csak HTTPS-en megy → a tunnel-URL-t használd, ne IP-t; böngésző-engedélyek |
| Render lassú / gép forró | csukott fedél? → nyisd ki / clamshell külső kijelzővel; egyszerre futó jobok száma (T4 konkurencia) |
| Éjjel megáll minden | pmset-beállítás visszaállt? `pmset -g` ellenőrzés; Docker Desktop fut? |
| `data/` betelik | régi `render/final.mp4`-ek és nyers narrációk archiválása; a generated.png-k újraállíthatók seedből |
