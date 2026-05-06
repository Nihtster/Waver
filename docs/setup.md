# Setup

End-to-end install on a fresh Raspberry Pi Zero 2W with the Waveshare 1.44" LCD HAT.

---

## 1. Flash the OS

Use Raspberry Pi Imager to flash **Raspberry Pi OS Lite (64-bit)** onto a 32GB SD card.

In the imager's advanced options, set:

- Hostname: `waver`
- Username: `cimi`
- Password: *(your choice)*
- WiFi SSID + password
- SSH: enabled

Boot the Pi and SSH in:

```bash
ssh cimi@waver.local
```

---

## 2. System packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    git python3-venv python3-pip \
    nginx \
    wireguard wireguard-tools iptables \
    network-manager
```

Enable SPI for the LCD:

```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

---

## 3. Static IP

Pi OS Bookworm uses NetworkManager — do **not** edit `dhcpcd.conf`.

```bash
CON=$(nmcli -t -f NAME con show --active | head -1)
sudo nmcli con mod "$CON" \
    ipv4.addresses 192.168.0.191/24 \
    ipv4.gateway 192.168.0.1 \
    ipv4.dns "1.1.1.1" \
    ipv4.method manual
sudo nmcli con up "$CON"
```

---

## 4. Clone the repo

```bash
cd ~
git clone https://github.com/YOU/waver.git
```

For a private repo, use a personal access token in the remote URL:

```bash
git remote set-url origin https://TOKEN@github.com/YOU/waver.git
```

The OTA updater runs as root — it expects the repo at the absolute path
`/home/cimi/waver`. Allow git to operate on it as root:

```bash
sudo git config --global --add safe.directory /home/cimi/waver
```

---

## 5. Python environment

```bash
python3 -m venv ~/waver-env
~/waver-env/bin/pip install --upgrade pip
~/waver-env/bin/pip install \
    numpy pillow RPi.GPIO spidev smbus2 \
    flask flask-socketio flask-cors \
    pyjwt bcrypt \
    gunicorn gevent gevent-websocket
```

> `eventlet` is **not** compatible with Python 3.13 (the version on current
> Pi OS). Use `gevent` + `gevent-websocket` as above.

Run scripts via the venv's Python explicitly to avoid path issues:

```bash
sudo ~/waver-env/bin/python3 launcher/launcher.py
```

---

## 6. API config

The API needs a password hash and a secret key. These are kept off-repo.

```bash
cp ~/waver/api/config.example.py ~/waver/api/config.py
```

Generate a bcrypt hash for your dashboard password:

```bash
~/waver-env/bin/python3 -c \
  "import bcrypt; p=input('Password: ').encode(); \
   print(bcrypt.hashpw(p, bcrypt.gensalt()).decode())"
```

Edit `~/waver/api/config.py`:

- `PASSWORD_HASH` — paste the generated hash
- `SECRET_KEY` — random string (mash the keyboard)

`api/config.py` is in `.gitignore`. Never commit it.

---

## 7. systemd services

```bash
sudo cp ~/waver/config/systemd/waver.service     /etc/systemd/system/
sudo cp ~/waver/config/systemd/waver-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now waver waver-api
```

---

## 8. nginx

```bash
sudo cp ~/waver/config/nginx/waver.conf /etc/nginx/sites-available/waver
sudo ln -sf /etc/nginx/sites-available/waver /etc/nginx/sites-enabled/waver
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
```

The dashboard is now reachable at `http://192.168.0.191/`.

---

## 9. Optional services

- [Pi-hole](pihole.md) — moved to port 8080 so nginx can own port 80
- [WireGuard](wireguard.md) — server config + peer setup

---

## 10. Verify

```bash
systemctl is-active waver waver-api nginx
curl -s http://192.168.0.191/api/auth/login \
    -X POST -H "Content-Type: application/json" \
    -d '{"password":"yourpassword"}'
```

The LCD should now show the WAVER home screen on boot.
