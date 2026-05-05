# SwissPI — Session Log
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
- **Hostname:** swisspi / cimi@cimi
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
display is 128x128. This causes glitch lines on the right and bottom edges.

### Solution
The luma.lcd library does NOT support offset parameters for ST7735. We wrote a
custom raw SPI driver based on Waveshare's official Python demo code.

### Key offsets (discovered through testing)
```python
LCD_X_ADJUST = 2   # Column offset
LCD_Y_ADJUST = 2   # Row offset
```

These MUST be applied on every draw call (not just at initialization).
The luma library resets the window on every frame, which is why one-time
offset commands don't work.

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
~/swisspi-env (Python virtualenv)

### Key packages
```
numpy==2.4.4
pillow==12.2.0
RPi.GPIO==0.7.1
spidev==3.8
smbus2==0.6.1
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
sudo ~/swisspi-env/bin/python3 script.py
```

### WSGI server
Using gunicorn with gevent-websocket worker.
eventlet is NOT compatible with Python 3.13 (our version).

---

## Project File Structure

```
~/swisspi/
├── launcher/
│   ├── launcher.py          # Main menu loop + input handling
│   ├── display_manager.py   # Wrapper around ST7735Fixed
│   ├── st7735_fixed.py      # Custom ST7735S driver (raw SPI)
│   ├── input_manager.py     # GPIO button/joystick polling (threaded)
│   ├── service_manager.py   # systemd service control via subprocess
│   └── network_info.py      # Live network data (IP, signal, temp, pihole)
├── api/
│   ├── app.py               # Flask REST API + SocketIO
│   └── config.py            # Passwords, secrets, config (NOT in git)
└── dashboard/
    ├── index.html           # Web dashboard UI
    ├── style.css            # Dark theme styles
    └── app.js               # Frontend JS (fetch API, JWT auth)
```

---

## Launcher Architecture

### Menu system
- Menus defined as dicts in launcher.py
- Each menu has: title, items list, type (services/regular)
- Navigation: joystick UP/DOWN cycles items, PRESS/KEY1 selects
- KEY2 shows system status overlay
- KEY3 goes back to main menu

### Input handling
- InputManager polls GPIO in a background thread
- Events queued in collections.deque (maxlen=10)
- 200ms debounce per button
- get_event(timeout) blocks until event or timeout

### Display rendering
- DisplayManager wraps ST7735Fixed
- Threading lock prevents concurrent SPI writes
- draw_menu() renders title + item list with selected item in green
- draw_status() renders a simple text list
- All rendering creates a PIL Image then calls device.display()

### Service integration
- ServiceManager wraps systemctl via subprocess
- get_status() → ServiceStatus enum (ACTIVE/INACTIVE/FAILED/UNKNOWN)
- toggle() checks status then calls start() or stop()
- Service names map: pihole→pihole-FTL, wireguard→wg-quick@wg0

### GPIO initialization order (CRITICAL)
InputManager MUST be initialized before DisplayManager.
InputManager calls GPIO.setmode(BCM) which ST7735Fixed depends on.
If DisplayManager initializes first, luma tries to set GPIO mode and conflicts.

---

## Services Running

### pihole-FTL (Pi-hole v6.4.2)
- Runs on port 8080 (moved from 80 to free it for nginx)
- Config: /etc/pihole/pihole.toml
- Port changed in toml: `port = "8080o,8443os,[::]:8080o,[::]:8443os"`
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
- Config: /etc/nginx/sites-available/swisspi
- server_name: swisspi.local 192.168.0.191 _
- Removed WebSocket upgrade headers (caused hanging) — plain proxy works fine

### swisspi-api (Flask + gunicorn)
- Port: 5000 (internal, proxied by nginx)
- Worker: geventwebsocket.gunicorn.workers.GeventWebSocketWorker
- 1 worker process
- systemd: swisspi-api

### swisspi (LCD Launcher)
- Autostart on boot
- WorkingDirectory: /home/cimi/swisspi/launcher
- Runs as root (required for GPIO/SPI access)
- systemd: swisspi

---

## Web Dashboard

### Authentication
- bcrypt password hash stored in api/config.py
- Login returns JWT token (24hr expiry, HS256)
- Token stored in browser localStorage
- All API endpoints require Authorization: Bearer <token> header
- WebSocket auth via auth dict on connect

### API Endpoints
```
POST /api/auth/login          — Login, returns JWT token
GET  /api/system/status       — Uptime, temp, IP, all service statuses
GET  /api/network/info        — IP, WiFi signal strength
GET  /api/network/wifi/scan   — Scan nearby WiFi networks (iwlist)
POST /api/network/wifi/connect — Connect to WiFi network (nmcli)
GET  /api/services/pihole     — Pi-hole status + stats
POST /api/services/pihole/toggle    — Toggle Pi-hole on/off
GET  /api/services/wireguard  — WireGuard status
POST /api/services/wireguard/toggle — Toggle WireGuard on/off
```

### Known Issues / Gotchas
- Pi-hole v6 API format may differ from v5 (stats endpoint changed)
- WiFi scan requires sudo iwlist — works because gunicorn runs as root
- WebSocket upgrade headers in nginx caused connection hanging — removed
- gunicorn eventlet worker incompatible with Python 3.13 — use gevent instead

---

## Network Configuration

### Static IP
Set via NetworkManager (nmcli), NOT dhcpcd.
Pi OS Bookworm uses NetworkManager by default.
dhcpcd.conf changes have no effect.

```bash
sudo nmcli con mod "$(nmcli -t -f NAME con show --active | head -1)" \
    ipv4.addresses 192.168.0.191/24 \
    ipv4.gateway 192.168.0.1 \
    ipv4.dns "127.0.0.1,1.1.1.1" \
    ipv4.method manual
```

DNS points to 127.0.0.1 (Pi-hole) with 1.1.1.1 as fallback.

---

## Known Issues & Decisions Made

1. **luma.lcd abandoned** — No offset support for ST7735S glitch fix.
   Custom raw SPI driver written instead.

2. **eventlet abandoned** — Incompatible with Python 3.13.
   Using gevent + gevent-websocket instead.

3. **WebSocket headers removed from nginx** — Caused connection hanging.
   Plain HTTP proxy works fine for current use case.

4. **Pi-hole on port 8080** — Pi-hole v6 runs its own web server.
   Moved to 8080 so nginx can own port 80.

5. **GPIO initialization order** — InputManager must init before DisplayManager.
   Both share GPIO but InputManager sets the mode.

6. **sudo required for launcher** — GPIO/SPI access requires root.
   Systemd service runs as root.

7. **Virtual environment** — Pi OS Bookworm enforces externally-managed-environment.
   All Python packages must be installed in ~/swisspi-env.

---

## TODO / Planned Features

### High Priority
- [ ] HTTPS with self-signed certificate (openssl + nginx SSL config)
- [ ] Pi-hole proper DNS setup (configure router to use Pi as DNS)
- [ ] WireGuard peer configuration (add phone/laptop as peers)
- [ ] Hotspot/AP fallback mode (hostapd — broadcast own WiFi if no network)

### Medium Priority
- [ ] TOTP authenticator (oathtool or pyotp — store secrets locally)
- [ ] Network scanner (nmap wrapper with results on LCD/dashboard)
- [ ] WiFi scanner display on LCD (nearby networks + signal strength)
- [ ] Dashboard UI improvements (better layout, mobile support)
- [ ] Pi-hole stats on dashboard (fix API — v6 format changed)

### Low Priority / Future
- [ ] USB HID gadget mode (Rubber Ducky payloads via USB)
- [ ] Wardriving logger (requires GPS module)
- [ ] Tailscale as alternative to WireGuard
- [ ] Packet sniffer (tcpdump wrapper)
- [ ] E-ink display integration (secondary display for idle/status)
- [ ] HTTPS for web dashboard

---

## Useful Commands

```bash
# Start launcher manually
cd ~/swisspi/launcher && sudo ~/swisspi-env/bin/python3 launcher.py

# Check all service statuses
systemctl is-active pihole-FTL wg-quick@wg0 nginx swisspi swisspi-api

# View API logs
sudo journalctl -u swisspi-api -f

# View launcher logs
sudo journalctl -u swisspi -f

# Restart all SwissPI services
sudo systemctl restart swisspi swisspi-api nginx pihole-FTL

# Test API
curl http://192.168.0.191/api/auth/login \
  -X POST -H "Content-Type: application/json" \
  -d '{"password": "yourpassword"}'

# Check what's on port 80/8080
sudo ss -tlnp | grep -E ':80|:8080'

# Check Pi-hole version
pihole -v

# Check Pi temperature
vcgencmd measure_temp

# Check WiFi signal
iwconfig wlan0 | grep "Signal level"
```

---

## Files NOT in Repo (stay on Pi only)

- `api/config.py` — contains PASSWORD_HASH and SECRET_KEY
- `/etc/wireguard/private.key` — WireGuard private key
- `/etc/wireguard/public.key` — WireGuard public key
- `/etc/wireguard/wg0.conf` — WireGuard config with private key
