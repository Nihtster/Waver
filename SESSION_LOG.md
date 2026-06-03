# WAVER — Session Log
# For use with Claude Code to continue development

## Project Overview
Building a portable "digital swiss army knife" on a Raspberry Pi Zero 2W with a
Waveshare 1.44" LCD HAT. The device runs a physical LCD menu launcher and a web
dashboard accessible from any device on the network.

---

## Hardware

- **Board:** Raspberry Pi Zero 2W (quad-core ARM Cortex-A53, 512MB RAM)
- **Display:** Waveshare 1.44" LCD HAT (ST7735S controller, 128x128 pixels)
- **Storage:** 32GB SD card
- **OS:** Raspberry Pi OS Lite 64-bit
- **Static IP:** 192.168.0.191
- **Hostname:** waver
- **Username:** cimi

---

## Hardware Pin Mapping (BCM numbering)
Discovered via gpio_scan.py — not from documentation (Waveshare docs had wrong pins)

### Display
| Function | GPIO |
|---|---|
| DC (Data/Command) | 25 |
| RST (Reset) | 27 |
| BL (Backlight) | 24 |
| MOSI | 10 |
| SCLK | 11 |
| CS (CE0) | 8 |

### Buttons & Joystick
| Function | GPIO |
|---|---|
| KEY1 (top button) | 21 |
| KEY2 (middle button) | 20 |
| KEY3 (bottom button) | 16 |
| Joystick UP | 6 |
| Joystick DOWN | 19 |
| Joystick LEFT | 5 |
| Joystick RIGHT | 26 |
| Joystick PRESS (center) | 13 |

Note: GPIO 24 is always LOW at startup (backlight pin, pulled high by hardware)

---

## Display Driver — Critical Notes

### Problem
The ST7735S controller has internal memory of 132x162 pixels, but the physical
display is 128x128. This causes glitch lines on the edges.

### Solution
The luma.lcd library does NOT support offset parameters for ST7735. We wrote a
custom raw SPI driver based on Waveshare's official Python demo code.

### Key offsets (discovered through testing on current hardware)
```python
LCD_X_ADJUST = 1   # Column offset — NOTE: was 2 on original setup, 1 on reinstall
LCD_Y_ADJUST = 2   # Row offset
```

These MUST be applied on every draw call (not just at initialization).
The luma library resets the window on every frame, which is why one-time
offset commands don't work. If glitch lines reappear after a reinstall,
re-test LCD_X_ADJUST values 0–4 until clean.

### Driver file: launcher/st7735_fixed.py
- Bypasses luma entirely
- Uses spidev directly
- Implements full ST7735S initialization sequence from Waveshare source
- Applies X/Y offsets in _set_window() which is called by display()
- Converts PIL Images to RGB565 format for the display

### Libraries used
- spidev — raw SPI communication
- RPi.GPIO — GPIO control
- numpy — efficient RGB565 pixel conversion
- pillow (PIL) — image/text rendering

### Libraries NOT used (tried and abandoned)
- luma.lcd — no offset support, caused glitch lines
- adafruit-circuitpython-st7735 — screen stayed white, incompatible

---

## Python Environment

### Location
~/waver-env (Python virtualenv)

### Key packages
```
numpy
pillow
RPi.GPIO
spidev
smbus2
flask
flask-socketio
flask-cors
pyjwt
bcrypt
gunicorn
gevent
gevent-websocket
```

### Running scripts
Always use full path to avoid venv issues:
```bash
sudo ~/waver-env/bin/python3 script.py
```

### WSGI server
Using gunicorn with gevent-websocket worker.
eventlet is NOT compatible with Python 3.13 (our version).

---

## Project File Structure

```
~/waver/
├── launcher/
│   ├── launcher.py          # Main menu loop + input handling
│   ├── display_manager.py   # All screen rendering (monospace font, paginated menus)
│   ├── st7735_fixed.py      # Custom ST7735S driver (raw SPI)
│   ├── input_manager.py     # GPIO button/joystick polling (threaded)
│   ├── service_manager.py   # systemd service control via subprocess
│   ├── network_info.py      # Live network data (IP, signal, temp, pihole)
│   └── updater.py           # OTA git pull + service restart
├── api/
│   ├── app.py               # Flask REST API + SocketIO
│   ├── config.py            # Passwords, secrets, config (NOT in git — Pi only)
│   └── config.example.py   # Template for fresh setup
├── dashboard/
│   ├── index.html           # Web dashboard UI
│   ├── style.css            # Dark theme styles
│   └── app.js               # Frontend JS (fetch API, JWT auth)
├── config/
│   ├── nginx/waver.conf     # nginx reverse proxy config
│   ├── systemd/waver.service      # LCD launcher systemd unit
│   ├── systemd/waver-api.service  # Flask API systemd unit
│   └── wg0.conf.template    # WireGuard config template
└── simulator/               # Local dev simulator (pygame, hot-reload)
```

---

## Launcher Architecture

### Menu system
- Screens: HOME, TOOLS, PIHOLE, WIREGUARD, WIFI_SCAN, WIFI_KIT,
  DASHBOARD, SETTINGS, UPDATE, ABOUT, PLACEHOLDER
- Navigation: joystick UP/DOWN cycles items, PRESS/KEY1/JOY_RIGHT selects
- KEY2 goes to dashboard, KEY3/JOY_LEFT goes back

### Pagination
- All list screens show 3 items per page
- Page indicator dots shown at bottom
- selected_index is global across all items; display_manager slices per page

### Input handling
- InputManager polls GPIO in a background thread
- Events queued in collections.deque (maxlen=10)
- 200ms debounce per button
- get_event(timeout) blocks until event or timeout

### Display rendering
- DisplayManager wraps ST7735Fixed
- Monospace font (DejaVuSansMono on Pi, Menlo on macOS simulator)
- Threading lock prevents concurrent SPI writes
- All rendering creates a PIL Image then calls device.display()
- Font binarisation threshold=48 for bold crisp strokes

### Service integration
- ServiceManager wraps systemctl via subprocess
- get_status() → ServiceStatus enum (ACTIVE/INACTIVE/FAILED/UNKNOWN)
- toggle() checks status then calls start() or stop()
- Service names map: pihole→pihole-FTL, wireguard→wg-quick@wg0

### GPIO initialization order (CRITICAL)
InputManager MUST be initialized before DisplayManager.
InputManager calls GPIO.setmode(BCM) which ST7735Fixed depends on.

### OTA Updater
- REPO_PATH = "/home/cimi/waver" (absolute path — service runs as root, ~ = /root)
- git safe.directory must be set: `sudo git config --global --add safe.directory /home/cimi/waver`
- Checks git fetch, compares HEAD to @{u}, pulls with --ff-only

---

## Services Running

### pihole-FTL (Pi-hole v6)
- Runs on port 8080 (moved from 80 to free it for nginx)
- Config: /etc/pihole/pihole.toml
- Port setting: `port = "8080o,8443os,[::]:8080o,[::]:8443os"`
- Web admin: http://192.168.0.191:8080/admin
- systemd: pihole-FTL

### wg-quick@wg0 (WireGuard)
- Config: /etc/wireguard/wg0.conf
- Interface: wg0, Address: 10.0.0.1/24, Port: 51820
- IP forwarding enabled: net.ipv4.ip_forward=1
- Required iptables (installed separately — not included by default on Pi OS)
- systemd: wg-quick@wg0

### nginx
- Owns port 80
- Reverse proxies to Flask API on port 5000
- Config: /etc/nginx/sites-available/waver
- Proxies /pihole/ to port 8080
- No WebSocket upgrade headers (caused connection hanging)

### waver-api (Flask + gunicorn)
- Port: 5000 (internal, proxied by nginx)
- Worker: geventwebsocket.gunicorn.workers.GeventWebSocketWorker
- 1 worker process
- systemd: waver-api

### waver (LCD Launcher)
- Autostart on boot
- WorkingDirectory: /home/cimi/waver/launcher
- Runs as root (required for GPIO/SPI access)
- systemd: waver

---

## Web Dashboard

### Authentication
- bcrypt password hash stored in api/config.py (off-repo)
- Login returns JWT token (24hr expiry, HS256)
- Token stored in browser localStorage
- All API endpoints require Authorization: Bearer <token> header

### API Endpoints
```
POST /api/auth/login                — Login, returns JWT token
GET  /api/system/status             — Uptime, temp, IP, all service statuses
GET  /api/network/info              — IP, WiFi signal strength
GET  /api/network/wifi/scan         — Scan nearby WiFi networks (iwlist)
POST /api/network/wifi/connect      — Connect to WiFi network (nmcli)
GET  /api/services/pihole           — Pi-hole status + stats
POST /api/services/pihole/toggle    — Toggle Pi-hole on/off
GET  /api/services/wireguard        — WireGuard status
POST /api/services/wireguard/toggle — Toggle WireGuard on/off
```

### Known Issues / Gotchas
- Pi-hole v6 API format changed from v5 — stats endpoint needs fixing
- WiFi scan requires sudo iwlist — works because gunicorn runs as root
- WebSocket upgrade headers in nginx caused connection hanging — removed
- gunicorn eventlet worker incompatible with Python 3.13 — use gevent instead

---

## Network Configuration

### Static IP
Set via NetworkManager (nmcli), NOT dhcpcd.
Pi OS Bookworm uses NetworkManager by default.

```bash
sudo nmcli con mod "$(nmcli -t -f NAME con show --active | head -1)" \
    ipv4.addresses 192.168.0.191/24 \
    ipv4.gateway 192.168.0.1 \
    ipv4.dns "1.1.1.1" \
    ipv4.method manual
sudo nmcli con up "$(nmcli -t -f NAME con show --active | head -1)"
```

---

## Known Issues & Decisions Made

1. **luma.lcd abandoned** — No offset support for ST7735S glitch fix.
   Custom raw SPI driver written instead.

2. **eventlet abandoned** — Incompatible with Python 3.13.
   Using gevent + gevent-websocket instead.

3. **WebSocket headers removed from nginx** — Caused connection hanging.
   Plain HTTP proxy works fine for current use case.

4. **Pi-hole on port 8080** — Pi-hole v6 runs its own web server.
   Moved to 8080 so nginx can own port 80. Pi-hole must be set for BOTH
   IPv4 and IPv6 on 8080 — leaving [::]:80 active blocks nginx for IPv6 clients.

5. **GPIO initialization order** — InputManager must init before DisplayManager.
   Both share GPIO but InputManager sets the mode.

6. **sudo required for launcher** — GPIO/SPI access requires root.
   Systemd service runs as root, so ~/waver in updater.py expands to /root/waver.
   REPO_PATH must be an absolute path: /home/cimi/waver.

7. **git safe.directory** — Running git as root on a repo owned by cimi requires:
   `sudo git config --global --add safe.directory /home/cimi/waver`

8. **api/config.py off-repo** — Contains PASSWORD_HASH and SECRET_KEY.
   Listed in .gitignore and untracked. Template at api/config.example.py.
   On fresh Pi setup: copy example, fill in hash + secret, never commit.

9. **LCD_X_ADJUST = 1** — On current hardware revision the column offset is 1,
   not 2 as on the original build. If glitch lines reappear after reinstall,
   test values 0–4.

---

## TODO / Planned Features

### High Priority
- [ ] WireGuard peer configuration (add phone/laptop as peers)
- [ ] HTTPS with self-signed certificate (openssl + nginx SSL config)
- [ ] Hotspot/AP fallback mode (hostapd — broadcast own WiFi if no network)

### Medium Priority
- [ ] Pi-hole stats on dashboard (fix API — v6 format changed)
- [ ] TOTP authenticator (pyotp — store secrets locally, generate codes on LCD)
- [ ] Network scanner (nmap wrapper with results on LCD + dashboard)
- [ ] Dashboard UI improvements (mobile layout)

### Low Priority / Future
- [ ] Terminal screen on LCD (shown in design mockup)
- [ ] USB HID gadget mode (Rubber Ducky payloads via USB)
- [ ] Packet sniffer (tcpdump wrapper)
- [ ] Tailscale as alternative to WireGuard
- [ ] Wardriving logger (requires GPS module)

---

## Useful Commands

```bash
# Check all service statuses
systemctl is-active pihole-FTL wg-quick@wg0 nginx waver waver-api

# View API logs
sudo journalctl -u waver-api -f

# View launcher logs
sudo journalctl -u waver -f

# Restart all WAVER services
sudo systemctl restart waver waver-api nginx pihole-FTL

# Test API login
curl http://192.168.0.191/api/auth/login \
  -X POST -H "Content-Type: application/json" \
  -d '{"password": "yourpassword"}'

# Check port bindings
sudo ss -tlnp | grep -E ':80|:5000|:8080'

# Check Pi temperature
vcgencmd measure_temp

# Check WiFi signal
iwconfig wlan0 | grep "Signal level"

# Run simulator (Mac)
cd ~/Documents/Waver && .venv/bin/python3 simulator/run_sim.py
```

---

## Session: RSVP Reader integration (2026-06-01)

### Goal
Wire [rsvpnano](https://github.com/ionutdecebal/rsvpnano) — an ESP32-S3 RSVP
e-reader — into Waver as a first-class feature. Waver hosts the book
conversion pipeline; the firmware itself stays upstream and runs on the
ESP32. No Docker (Waver is systemd-only).

### What was added
- **`rsvp-converter/`** — new top-level service.
  - `converter.py` ports the `.rsvp` text format (header → `@title` →
    `@author` → `@chapter` → `@para` → one word per line). Supports
    `.epub` (ebooklib), `.txt` (heuristic chapter regex), `.md`
    (markdown → html → parse), `.html`/`.htm` (BeautifulSoup + lxml).
  - `server.py` — Flask app on `127.0.0.1:5001`. Endpoints:
    `POST /convert`, `GET /library`, `GET /library/<f>`,
    `DELETE /library/<f>`, `GET /health`.
  - `requirements.txt` — flask, ebooklib, beautifulsoup4, lxml, markdown.
  - Books directory configurable via `BOOKS_DIR`; default
    `/home/cimi/waver/rsvp-books`.
- **`config/systemd/waver-rsvp.service`** — mirrors `waver-api.service`
  style. Runs as root, `Restart=on-failure`, bare `python3 server.py`
  (no gunicorn — single-user, low-traffic).
- **`api/app.py`** — added `/api/rsvp/{upload,library,library/<f> (GET+DELETE),status}`.
  All JWT-authed. Uses `requests` to proxy to converter. Configurable
  via `RSVP_CONVERTER_URL` (default `http://127.0.0.1:5001`).
- **`dashboard/`** — new "RSVP Reader" card on `index.html`.
  Upload form (file + optional title/author), library list with download
  + delete, status banner. Matched existing dark theme; added rules under
  `/* RSVP Reader */` block in `style.css`.
- **`launcher/launcher.py`** — new `RSVP_READER` screen with sub-items
  `Library` and `Service Status`. Reachable from TOOLS menu. Reuses
  `draw_wifi_toolkit` rendering (generic menu list).
- **`launcher/service_manager.py`** — registered `rsvp → waver-rsvp`.
- **`docs/rsvp-reader.md`** — setup + architecture + endpoints + .rsvp
  format reference + troubleshooting.

### Key decisions
1. **Two services, not one.** The converter is its own Flask app on
   :5001 — separation of concerns, and avoids dragging ebooklib /
   lxml startup time into the main API worker.
2. **Loopback only.** Converter binds `127.0.0.1`; only the Waver API
   talks to it. No new nginx rules, no new attack surface.
3. **Synchronous Flask, not gunicorn.** Conversions take seconds and
   the service is single-user. Bare `python3 server.py` keeps the unit
   simple and matches the "small Pi appliance" philosophy.
4. **`requests` dependency added to API.** Used to proxy to the
   converter. Needs `pip install requests` in `waver-env`.
5. **No web flasher.** Future task — out of scope per spec.

### Setup steps on the Pi
```bash
sudo ~/waver-env/bin/pip install -r ~/waver/rsvp-converter/requirements.txt
sudo ~/waver-env/bin/pip install requests
sudo mkdir -p /home/cimi/waver/rsvp-books
sudo cp ~/waver/config/systemd/waver-rsvp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now waver-rsvp
sudo systemctl restart waver-api waver
```

### TODO follow-ups
- Web flasher for ESP32-S3 firmware OTA (deferred).
- LCD library browser (currently just shows service status; full
  library navigation lives on the dashboard).
- Cover-image extraction from EPUB (rsvpnano doesn't render images yet).

---

## Files NOT in Repo (stay on Pi only)

- `api/config.py` — contains PASSWORD_HASH and SECRET_KEY
- `/etc/wireguard/private.key` — WireGuard private key
- `/etc/wireguard/public.key` — WireGuard public key
- `/etc/wireguard/wg0.conf` — WireGuard config with private key
