# Waver

A personal portable toolkit built on a Raspberry Pi Zero 2W. Inspired by devices like the Flipper Zero, Waver is a pocket-sized platform for everyday digital tasks — network monitoring, DNS filtering, VPN routing, security tooling, and more — all controllable from a physical LCD menu or a web dashboard on any device.

---

## What it does

- **LCD launcher** — a physical menu-driven interface on a 128x128 display, navigated with a joystick and three buttons
- **Pi-hole** — network-wide DNS ad and tracker blocking
- **WireGuard VPN** — self-hosted VPN server, usable from any device on the network
- **WiFi tools** — scan nearby networks, switch connections
- **RSVP Reader** — convert `.epub`/`.txt`/`.md`/`.html` books into the `.rsvp` format used by the [rsvpnano](https://github.com/ionutdecebal/rsvpnano) ESP32-S3 e-reader
- **Web dashboard** — full control panel accessible from any browser on the network
- **OTA updates** — pull the latest code and restart services from the device itself

---

## Hardware

| Component   | Details                                      |
|-------------|----------------------------------------------|
| Board       | Raspberry Pi Zero 2W (quad-core A53, 512MB)  |
| Display     | Waveshare 1.44" LCD HAT (ST7735S, 128x128)   |
| Storage     | 32GB SD card                                 |
| OS          | Raspberry Pi OS Lite 64-bit                  |

---

## Screenshots

*Coming soon.*

---

## Project Structure

```
waver/
├── launcher/
│   ├── launcher.py          # Main menu loop and input handling
│   ├── display_manager.py   # Screen rendering (menus, overlays, pagination)
│   ├── st7735_fixed.py      # Custom ST7735S raw SPI driver
│   ├── input_manager.py     # GPIO button and joystick polling (threaded)
│   ├── service_manager.py   # systemd service control
│   ├── hotspot_manager.py   # WiFi hotspot toggle (NetworkManager)
│   ├── network_info.py      # Live network data (IP, signal, temp, Pi-hole)
│   └── updater.py           # OTA git pull and service restart
├── api/
│   ├── app.py               # Flask REST API + SocketIO
│   ├── config.py            # Secrets and config (not in repo — Pi only)
│   └── config.example.py    # Template for fresh setup
├── dashboard/
│   ├── index.html           # Web dashboard UI
│   ├── style.css            # Dark theme styles
│   └── app.js               # Frontend JS (fetch API, JWT auth)
├── rsvp-converter/
│   ├── converter.py         # Book -> .rsvp conversion (epub/txt/md/html)
│   ├── server.py            # Flask service on 127.0.0.1:5001
│   └── requirements.txt     # ebooklib, beautifulsoup4, lxml, markdown
├── config/
│   ├── nginx/waver.conf           # nginx reverse proxy config
│   ├── systemd/waver.service      # LCD launcher systemd unit
│   ├── systemd/waver-api.service  # Flask API systemd unit
│   ├── systemd/waver-rsvp.service # RSVP converter systemd unit
│   ├── wg0.conf.template          # WireGuard config template
│   └── scripts/                   # One-time setup + runtime helpers
│       ├── gen-cert.sh           # Self-signed TLS cert generator
│       ├── setup-hotspot.py      # NetworkManager hotspot profile creator
│       └── hotspot.sh            # Hotspot start/stop/status
└── simulator/               # Local dev simulator (pygame, no Pi required)
```

---

## Roadmap

### Phase 1 — QoL for daily use
- [ ] HTTPS on the dashboard
- [ ] AP fallback mode
- [ ] Pi-hole, fully working
- [ ] WireGuard, on the go

### Phase 2 — WiFi Toolkit
- [ ] Scanning
- [ ] Packet capture
- [ ] Deauth

### Phase 3 — Pwnagotchi
- [ ] Passive handshake collection
- [ ] On-LCD personality / status
- [ ] Captured handshakes accessible from the dashboard

### Phase 4 — Future task bucket
- [ ] Settings overhaul
- [ ] Dashboard overhaul
- [ ] UI pass
- [ ] Battery support
- [ ] One more "fun tool"

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Setup](docs/setup.md) | Full install guide: OS, venv, cloning, static IP |
| [LCD Launcher](docs/lcd-launcher.md) | Menu system, button controls, architecture |
| [Display Driver](docs/display-driver.md) | ST7735S raw SPI driver, offsets, hardware quirks |
| [API](docs/api.md) | REST endpoints, JWT auth, gunicorn config |
| [Dashboard](docs/dashboard.md) | Web dashboard, nginx reverse proxy |
| [Pi-hole](docs/pihole.md) | Install, port config, DNS setup |
| [WireGuard](docs/wireguard.md) | Install, key generation, peer config |
| [Hotspot](docs/hotspot.md) | On-device WiFi AP — setup, toggle, troubleshooting |
| [RSVP Reader](docs/rsvp-reader.md) | Book converter for the rsvpnano ESP32-S3 reader |
| [Simulator](docs/simulator.md) | Running the local dev simulator on macOS |
