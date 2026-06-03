# rsvpnano × Waver — Integration Research & Plan

> **Prepared for:** Christian  
> **Date:** 2026-06-02  
> **Status:** Complete. Both repos fully investigated. The core integration is already done — this document captures what was built, how it works, and what remains.

---

## TL;DR

**The rsvpnano integration into Waver is already implemented.** The `rsvp-converter/` service, its systemd unit, the API proxy routes, and the dashboard UI were all built in the session logged under `SESSION_LOG.md → Session: RSVP Reader integration (2026-06-01)`.

This document is a full architectural record plus a prioritised list of what still needs doing.

---

## 1. What rsvpnano Is

**rsvpnano** (`github.com/ionutdecebal/rsvpnano`) is open-source MIT firmware for the **Waveshare ESP32-S3-Touch-LCD-3.49** — a physical e-reader device. It is not a server or web app. It runs on a chip, reads books off an SD card, and displays them one word at a time using RSVP (Rapid Serial Visual Presentation).

**Key facts:**
- Language: C++ (96.8%) + Python tools, Arduino/PlatformIO build system
- No HTTP server, no REST API, no database — pure embedded firmware
- Books are stored as `.rsvp` files on the SD card (plain text, custom header format)
- The **desktop/server-side concern** is only: converting EPUB/TXT/MD/HTML → `.rsvp`
- The project is growing fast: 863 stars, 96 forks, active PRs for WiFi OTA, companion apps (Kotlin Multiplatform for Android/iOS), internet radio, and more

**Waver's role:** Waver hosts the conversion pipeline. The ESP32 firmware itself stays upstream; Waver doesn't run it or flash it.

---

## 2. What Waver Is

Waver is a **Raspberry Pi Zero 2W portable toolkit** — a pocket-sized "digital swiss army knife" running on bare Pi OS with systemd services. It has:

- **LCD launcher** — physical 128×128 display menu (ST7735S, custom SPI driver) with joystick + 3 buttons
- **Flask REST API** (`waver-api`, port 5000) — JWT-authed, SocketIO, gunicorn/gevent, handles all backend logic
- **Web dashboard** — dark-theme single-page app served by the Flask API, accessible from any browser on the LAN
- **Nginx reverse proxy** — HTTPS on 443, proxies to Flask on 5000
- **Pi-hole** — DNS ad/tracker blocking (port 8080)
- **WireGuard VPN** — self-hosted VPN (port 51820)
- **RSVP Converter** (`waver-rsvp`, port 5001) — the rsvpnano integration

**Runtime:** systemd-only. No Docker, no containers. Services communicate over loopback (`127.0.0.1`). The Pi is a single-user appliance.

---

## 3. Current Architecture (as-built)

```
Internet / LAN
      │
      ▼
  nginx :443 (HTTPS, self-signed)
      │
      ▼
  waver-api :5000 (Flask + gunicorn/gevent)
  ├── GET  /api/system/status
  ├── GET  /api/network/info
  ├── GET  /api/network/wifi/scan
  ├── POST /api/network/wifi/connect
  ├── GET  /api/services/pihole
  ├── POST /api/services/pihole/toggle
  ├── GET  /api/services/wireguard
  ├── POST /api/services/wireguard/toggle
  ├── POST /api/rsvp/upload          ─┐
  ├── GET  /api/rsvp/library          │  proxies to waver-rsvp
  ├── GET  /api/rsvp/library/<f>      │
  ├── DELETE /api/rsvp/library/<f>    │
  └── GET  /api/rsvp/status           ┘
            │
            ▼
  waver-rsvp :5001 (Flask, loopback-only)
  ├── POST /convert
  ├── GET  /library
  ├── GET  /library/<filename>
  ├── DELETE /library/<filename>
  └── GET  /health
            │
            ▼
  /home/cimi/waver/rsvp-books/*.rsvp
            │
            ▼   (manual SD card copy)
  ESP32-S3 rsvpnano device
```

**Service inventory:**

| systemd unit | Port | Process | Role |
|---|---|---|---|
| `waver` | — | Python (GPIO/SPI) | LCD launcher |
| `waver-api` | 5000 | gunicorn/gevent | Flask API + dashboard |
| `waver-rsvp` | 5001 | python3 (bare Flask) | RSVP book converter |
| `nginx` | 80, 443 | nginx | TLS + reverse proxy |
| `pihole-FTL` | 8080 | Pi-hole | DNS filtering |
| `wg-quick@wg0` | 51820 | WireGuard | VPN |

---

## 4. The rsvp-converter Service — Implementation Details

### `rsvp-converter/converter.py`

The core conversion engine. A clean, well-structured Python module with no hardware dependencies. Supports:

| Input format | Parser | Chapter detection |
|---|---|---|
| `.epub` | ebooklib (lazily imported) | First `<h1>/<h2>/<h3>` per EPUB document item, fallback to filename |
| `.txt` | Custom regex | `Chapter N`, `Prologue`, `Epilogue`, `Part N` patterns |
| `.md` | markdown → HTML → BeautifulSoup | `<h1>/<h2>/<h3>` headings |
| `.html`/`.htm` | BeautifulSoup + lxml | `<h1>/<h2>/<h3>` headings |

Public API:
```python
rsvp_text, output_filename = converter.convert(filename, data_bytes, title=None, author=None)
```

### `rsvp-converter/server.py`

Flask service on `127.0.0.1:5001`. Endpoints:

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Returns `{ok: true, books_dir: ...}` |
| `POST` | `/convert` | `multipart/form-data`: `file` + optional `title`, `author`, `save` (default 1) |
| `GET` | `/library` | Lists `*.rsvp` files with size + mtime |
| `GET` | `/library/<filename>` | Download a book (path-traversal-safe) |
| `DELETE` | `/library/<filename>` | Delete a book |

### `rsvp-converter/requirements.txt`

```
flask>=3.0
ebooklib>=0.18
beautifulsoup4>=4.12
lxml>=5.0
markdown>=3.5
```

### `config/systemd/waver-rsvp.service`

```ini
[Service]
User=root
WorkingDirectory=/home/cimi/waver/rsvp-converter
Environment=BOOKS_DIR=/home/cimi/waver/rsvp-books
ExecStart=/home/cimi/waver-env/bin/python3 server.py
Restart=on-failure
RestartSec=5
```

**Design decisions:**
- Bare `python3` (no gunicorn) — single-user, low-traffic, conversions take seconds
- Loopback-only binding — no nginx changes, no new attack surface
- Separate service from `waver-api` — keeps ebooklib/lxml startup time out of the main API worker

### Test coverage

`tests/test_converter.py` has 5 synthetic unit tests covering all formats + unsupported-type rejection. **4/5 pass in isolation** (epub test requires ebooklib installed). Tests are self-contained — no Pi hardware needed.

---

## 5. What the API Proxy Does

`api/app.py` was extended with 5 RSVP routes (all JWT-authed):

```python
RSVP_CONVERTER_URL = os.environ.get("RSVP_CONVERTER_URL", "http://127.0.0.1:5001")
```

The API receives the authenticated request, strips auth, and forwards to the converter using `requests`. File uploads are streamed through. Responses (including the `.rsvp` download) are proxied back with correct `Content-Disposition` headers.

The `RSVP_CONVERTER_URL` env var makes it easy to point at a different host/port in testing without code changes.

---

## 6. What's NOT Done Yet (Ordered by Priority)

### 6.1 Setup on the Pi (HIGH — nothing works until this is done)

The code is in the repo but the Pi doesn't have it running yet. Steps:

```bash
# 1. Pull latest code
cd /home/cimi/waver && git pull

# 2. Install converter deps into the existing venv
sudo ~/waver-env/bin/pip install -r rsvp-converter/requirements.txt
sudo ~/waver-env/bin/pip install requests  # for api/app.py

# 3. Create the books directory
sudo mkdir -p /home/cimi/waver/rsvp-books
sudo chown root:root /home/cimi/waver/rsvp-books

# 4. Install and start the systemd unit
sudo cp config/systemd/waver-rsvp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now waver-rsvp

# 5. Restart the API to load the new /api/rsvp/* routes
sudo systemctl restart waver-api

# 6. Verify
curl http://127.0.0.1:5001/health
systemctl is-active waver-rsvp waver-api
```

### 6.2 Dashboard UI for RSVP (HIGH — wired in but needs verification)

The session log says the dashboard was updated. Verify the "RSVP Reader" card is visible and functional at `https://waver.local`. If the card is missing, check `dashboard/index.html` and `dashboard/app.js` for the RSVP sections.

### 6.3 LCD Launcher RSVP screen (MEDIUM)

The session log says a `RSVP_READER` screen was added to `launcher/launcher.py` with `Library` and `Service Status` sub-items. Currently it shows service status only — no full library browsing on-device (that's dashboard-only). This is acceptable for now.

### 6.4 lxml install may fail on Pi Zero 2W (MEDIUM — known issue)

If `pip install lxml` fails:
```bash
sudo apt install libxml2-dev libxslt1-dev
sudo ~/waver-env/bin/pip install lxml
```

The Pi Zero 2W runs 64-bit ARM and compiles lxml from source. It's slow but works.

### 6.5 Pi-hole stats are broken (MEDIUM — pre-existing, unrelated to rsvpnano)

Pi-hole v6 changed its API. The `pihole_status` handler in `app.py` hits the v5 path and returns zeros. Tracked in `docs/api.md`. Fix separately.

### 6.6 Web flasher for ESP32-S3 OTA (LOW — explicitly deferred)

The rsvpnano web flasher (`web/` folder in the rsvpnano repo) could optionally be served from Waver so users can flash devices from the local network. Not in scope yet. When the time comes:

```bash
# Simple approach: clone rsvpnano into a known path, run fetch_release_firmware.py,
# then add an nginx location block to serve it:
# location /flash/ { root /home/cimi/rsvpnano/web; }
```

Requires HTTPS (already set up on Waver) and Chrome/Edge (Web Serial API).

### 6.7 LCD library browser (LOW)

Full book library navigation on the 128×128 screen. Pagination would work fine — the display manager already handles paginated lists. The converter returns `{books: [{filename, size, mtime}]}` which is everything needed. Would require an SSH command to trigger download to connected SD card, which is out of scope.

---

## 7. Development Plan

### Branch name
```
feature/rsvpnano-integration
```
(This branch should already contain the work from the June 1 session. If it was committed to `main`, no new branch is needed — just deploy to the Pi.)

### Immediate next session checklist

- [ ] `git pull` on the Pi and confirm `rsvp-converter/` folder is present
- [ ] Run setup steps from §6.1 above
- [ ] Test end-to-end: upload an `.epub` via `curl` or the dashboard → confirm `.rsvp` downloads
- [ ] Check `systemctl is-active waver-rsvp` shows `active`
- [ ] Verify the RSVP card is visible on the web dashboard
- [ ] Run `python3 tests/test_converter.py` on the Pi (with deps installed) — all 5 should pass

### Short-term polish (1–2 sessions)

- [ ] Fix Pi-hole v6 API stats (see `docs/api.md → Known issues`)
- [ ] Add RSVP library count to system status endpoint (so dashboard header shows "3 books")
- [ ] Verify lxml installs cleanly; document the `apt` workaround in `docs/rsvp-reader.md` ← already documented

### Medium-term (Phase 2 of Roadmap)

- [ ] Add HTTPS cert auto-renewal (currently manual `gen-cert.sh`)
- [ ] Mobile layout pass for the dashboard
- [ ] WiFi toolkit (scanning, packet capture)

---

## 8. Environment Variables Reference

| Variable | Default | Set in | Purpose |
|---|---|---|---|
| `RSVP_CONVERTER_URL` | `http://127.0.0.1:5001` | `api/app.py` env | Where the API finds the converter |
| `BOOKS_DIR` | `/home/cimi/waver/rsvp-books` | `waver-rsvp.service` | Where `.rsvp` files are stored |
| `RSVP_HOST` | `127.0.0.1` | `rsvp-converter/server.py` | Converter bind address |
| `RSVP_PORT` | `5001` | `rsvp-converter/server.py` | Converter bind port |

---

## 9. Key File Map

```
Waver/
├── rsvp-converter/
│   ├── converter.py          ← Core conversion engine (all formats)
│   ├── server.py             ← Flask service (loopback :5001)
│   └── requirements.txt      ← flask, ebooklib, beautifulsoup4, lxml, markdown
├── api/
│   └── app.py                ← RSVP_CONVERTER_URL + /api/rsvp/* routes (lines 249–337)
├── config/systemd/
│   └── waver-rsvp.service    ← systemd unit for the converter
├── dashboard/
│   ├── index.html            ← RSVP Reader card
│   ├── style.css             ← RSVP styles (/* RSVP Reader */ block)
│   └── app.js                ← Upload form, library list, delete
├── tests/
│   ├── test_converter.py     ← Unit tests for converter.py (5 tests)
│   ├── test_server.py        ← Flask endpoint tests
│   └── test_integration.py   ← Full upload→library integration test
└── docs/
    └── rsvp-reader.md        ← Setup guide + endpoint reference + .rsvp format
```

---

## 10. Notable Gotchas

**ebooklib is a lazy import.** `converter.py` imports `ebooklib` inside `convert_epub()` so the service starts fast even if ebooklib isn't installed — it only fails at the moment an `.epub` is uploaded. This is intentional but means a missing-package error surfaces at request time, not startup.

**gevent, not eventlet.** The `waver-api` gunicorn worker uses `geventwebsocket.gunicorn.workers.GeventWebSocketWorker`. eventlet is incompatible with Python 3.13 (current Pi OS). Don't swap them.

**Both services run as root.** Required for systemctl/GPIO/SPI/iwlist access. Acceptable for a single-user home appliance. Don't expose either service publicly.

**CORS is wide open** (`cors_allowed_origins="*"`). Fine for LAN-only. If Waver ever gets a public domain, tighten this.

**The converter is not behind auth.** It binds `127.0.0.1` so only `waver-api` (which is JWT-authed) can reach it. Don't change the bind address without adding auth to the converter.

**rsvpnano is evolving fast.** The upstream project is gaining WiFi OTA, a KMP companion app, and internet radio. As those features land, Waver could expand its role (OTA hosting, book sync over WiFi). Worth watching the upstream PRs.

---

*Generated by Claude · 2026-06-02 · Based on direct inspection of both repos*
