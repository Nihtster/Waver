# SwissPI — Raspberry Pi Zero 2W Swiss Army Knife

A portable network security and utility device built on a Raspberry Pi Zero 2W
with a Waveshare 1.44" LCD HAT. Features a physical menu launcher, Pi-hole DNS
filtering, WireGuard VPN, a live network dashboard on the LCD, and a web
dashboard accessible from any device on the network.

---

## Hardware

| Component | Model |
|---|---|
| Board | Raspberry Pi Zero 2W |
| Display HAT | Waveshare 1.44" LCD HAT (ST7735S, 128x128) |
| Storage | 32GB+ SD card (Class 10) |

### LCD HAT Pin Reference (BCM numbering)

| Function       | GPIO |
|----------------|------|
| DC             | 25   |
| RST            | 27   |
| Backlight (BL) | 24   |
| KEY1 (top)     | 21   |
| KEY2 (middle)  | 20   |
| KEY3 (bottom)  | 16   |
| Joystick UP    | 6    |
| Joystick DOWN  | 19   |
| Joystick LEFT  | 5    |
| Joystick RIGHT | 26   |
| Joystick PRESS | 13   |

---

## Project Structure

```
swisspi/
├── launcher/
│   ├── launcher.py          # Main menu loop
│   ├── display_manager.py   # Display rendering
│   ├── st7735_fixed.py      # ST7735S driver (Waveshare-based)
│   ├── input_manager.py     # Button/joystick input
│   ├── service_manager.py   # systemd service control
│   └── network_info.py      # Live network data
├── api/
│   ├── app.py               # Flask REST API + WebSocket
│   └── config.py            # API configuration (passwords, secrets)
├── dashboard/
│   ├── index.html           # Web dashboard
│   ├── style.css            # Dashboard styles
│   └── app.js               # Dashboard JavaScript
└── config/
    ├── nginx/swisspi.conf   # nginx reverse proxy config
    ├── systemd/
    │   ├── swisspi.service      # LCD launcher autostart
    │   └── swisspi-api.service  # Flask API autostart
    └── wg0.conf.template        # WireGuard config template
```

---

## Phase 1 — OS Setup

### 1. Flash OS

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Select:
   - Device: **Raspberry Pi Zero 2 W**
   - OS: **Raspberry Pi OS Lite (64-bit)**
   - Storage: Your SD card
3. Click **Edit Settings**:
   - Hostname: `swisspi`
   - Username: `cimi`
   - Password: (choose a strong password)
   - WiFi SSID and password
   - Timezone: your local timezone
   - Enable SSH
4. Flash and insert SD card into Pi

### 2. First Boot & SSH

```bash
ssh cimi@swisspi.local
```

### 3. Update System

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl wget python3-pip python3-venv
```

### 4. Enable SPI and I2C

```bash
sudo raspi-config
# Interface Options -> SPI -> Enable
# Interface Options -> I2C -> Enable
sudo reboot
```

---

## Phase 2 — Python Environment

```bash
python3 -m venv ~/swisspi-env
source ~/swisspi-env/bin/activate
pip install numpy pillow RPi.GPIO spidev smbus2
pip install flask flask-socketio flask-cors pyjwt bcrypt
pip install gunicorn gevent gevent-websocket
```

---

## Phase 3 — Copy Project Files

Copy all files from this repo to the Pi:

```bash
mkdir -p ~/swisspi/{launcher,api,dashboard,config}
# SCP or manually create each file on the Pi
```

---

## Phase 4 — LCD Display Setup

The display uses a custom ST7735S driver based on Waveshare's official code.
Key offsets discovered through testing (applied in `st7735_fixed.py`):

```python
LCD_X_ADJUST = 2   # Column offset
LCD_Y_ADJUST = 2   # Row offset
```

**Note:** The `luma.lcd` library does not support these offsets natively.
We use a raw SPI driver instead.

---

## Phase 5 — Launcher

### Button Controls

| Button/Input     | Action                        |
|------------------|-------------------------------|
| Joystick UP/DOWN | Navigate menu items           |
| Joystick PRESS   | Select item / toggle service  |
| KEY1 (top)       | Select item / toggle service  |
| KEY2 (middle)    | Show system status overlay    |
| KEY3 (bottom)    | Go back to main menu          |

### Autostart

```bash
sudo cp config/systemd/swisspi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable swisspi
sudo systemctl start swisspi
```

---

## Phase 6 — Pi-hole

### Install

```bash
curl -sSL https://install.pi-hole.net | bash
```

Installer options:
- Upstream DNS: **Cloudflare (1.1.1.1)**
- Install web interface: **Yes**
- Install lighttpd: **Yes**
- Log queries: **Yes**
- Note the admin password shown at the end

### Move Pi-hole to port 8080 (for nginx to own port 80)

```bash
sudo nano /etc/pihole/pihole.toml
```

Find the port line and change it to:
```toml
port = "8080o,8443os,[::]:8080o,[::]:8443os"
```

```bash
sudo systemctl restart pihole-FTL
```

### Web Admin

Access at: `http://192.168.0.191:8080/admin`

---

## Phase 7 — WireGuard

### Install

```bash
sudo apt install -y wireguard wireguard-tools iptables
```

### Generate Keys

```bash
wg genkey | sudo tee /etc/wireguard/private.key
sudo chmod go= /etc/wireguard/private.key
sudo cat /etc/wireguard/private.key | wg pubkey | sudo tee /etc/wireguard/public.key
```

### Configure

```bash
sudo nano /etc/wireguard/wg0.conf
```

Use `config/wg0.conf.template`, replacing the PrivateKey placeholder with:
```bash
sudo cat /etc/wireguard/private.key
```

### Enable

```bash
sudo chmod 600 /etc/wireguard/wg0.conf
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0
```

---

## Phase 8 — Static IP

```bash
sudo nmcli con mod "$(nmcli -t -f NAME con show --active | head -1)" \
    ipv4.addresses 192.168.0.191/24 \
    ipv4.gateway 192.168.0.1 \
    ipv4.dns "127.0.0.1,1.1.1.1" \
    ipv4.method manual

sudo nmcli con up "$(nmcli -t -f NAME con show --active | head -1)"
sudo reboot
```

---

## Phase 9 — Web Dashboard (nginx + Flask)

### Install nginx

```bash
sudo apt install -y nginx
sudo systemctl enable nginx
```

### Configure nginx

```bash
sudo cp config/nginx/swisspi.conf /etc/nginx/sites-available/swisspi
sudo ln -s /etc/nginx/sites-available/swisspi /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### Configure Flask API

Edit `api/config.py`:

1. Generate password hash:
```bash
source ~/swisspi-env/bin/activate
python3 -c "import bcrypt; p=input('Password: ').encode(); print(bcrypt.hashpw(p, bcrypt.gensalt()).decode())"
```

2. Paste hash into `PASSWORD_HASH`
3. Set a random `SECRET_KEY`

### Start Flask API

```bash
sudo cp config/systemd/swisspi-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable swisspi-api
sudo systemctl start swisspi-api
```

### Access Dashboard

Open in browser: `http://192.168.0.191`

---

## Static IP Reference

| Setting  | Value               |
|----------|---------------------|
| IP       | 192.168.0.191       |
| Gateway  | 192.168.0.1         |
| Subnet   | /24                 |
| DNS (1)  | 127.0.0.1 (Pi-hole) |
| DNS (2)  | 1.1.1.1 (Cloudflare)|

---

## Python Dependencies

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

---

## Planned Features (TODO)

- [ ] HTTPS with self-signed certificate
- [ ] Pi-hole proper DNS configuration for network devices
- [ ] WireGuard peer configuration
- [ ] Hotspot/AP fallback mode (broadcast own WiFi if no network)
- [ ] TOTP authenticator app
- [ ] Network scanner (nmap wrapper)
- [ ] WiFi scanner (nearby networks + signal)
- [ ] USB HID gadget mode (Rubber Ducky payloads)
- [ ] Wardriving logger (requires GPS module)
