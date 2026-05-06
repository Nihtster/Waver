# Hotspot

Waver can broadcast its own WiFi access point so you can connect a
phone or laptop directly to it — useful when there's no other WiFi
around, or when you want to use Waver's services (Pi-hole, WireGuard,
etc.) on a network you fully control.

The Pi has one radio, so **AP mode and WiFi-client mode are mutually
exclusive on `wlan0`**: activating the hotspot disconnects whatever
WiFi the Pi is on. SSH sessions running over that WiFi will die. Worth
remembering before you toggle.

---

## How it works

NetworkManager's built-in `shared` mode does everything we need: AP
broadcast, DHCP for clients, NAT'd internet sharing (when the Pi has
upstream connectivity via Ethernet, USB-tether, or another route). We
don't run `hostapd` separately because NM and `hostapd` fight over
ownership of `wlan0`.

A connection profile named `waver-hotspot` is created during setup and
toggled by the launcher (or manually with `nmcli`). It is
`autoconnect=no` — never comes up on its own.

---

## One-time setup

After cloning the repo and editing `api/config.py` to set
`HOTSPOT_SSID` and `HOTSPOT_PASSWORD`:

```bash
sudo ~/waver-env/bin/python3 ~/waver/config/scripts/setup-hotspot.py
```

The script:

1. Reads SSID + password from `api/config.py`
2. Deletes any existing profile named `waver-hotspot` (idempotent)
3. Creates a fresh profile with WPA2, AP mode, and `ipv4.method shared`

The hotspot subnet is `10.42.0.0/24` (NetworkManager's default for
`shared` mode). The Pi is `10.42.0.1`; clients get `.2` and up via DHCP.

---

## Toggling the hotspot

### From the LCD

`Settings → Hotspot` → press select to start/stop. The screen shows the
SSID, password (in the clear), and current status.

### From a shell

```bash
sudo nmcli connection up   waver-hotspot     # start
sudo nmcli connection down waver-hotspot     # stop

# Or via the wrapper script the launcher uses:
sudo bash ~/waver/config/scripts/hotspot.sh start
sudo bash ~/waver/config/scripts/hotspot.sh stop
sudo bash ~/waver/config/scripts/hotspot.sh status
```

---

## Connecting a device

1. Toggle the hotspot on from the LCD
2. On your phone/laptop, connect to the SSID shown on the LCD with the
   password shown on the LCD
3. You'll get an IP in `10.42.0.0/24`
4. The Pi is at `10.42.0.1` — the dashboard, Pi-hole admin, and any
   other Waver services are reachable from there

> **About showing the password on screen:** the hotspot detail screen
> displays the password in plain text. This is intentional — you're
> looking at the screen because you want to type the password into a
> connecting device. If the device sits unattended in public, treat
> the password as visible to anyone in line of sight and pick something
> you'd rotate occasionally.

---

## Pi-hole + the hotspot

When the hotspot is up, `wlan0` has IP `10.42.0.1`. Hotspot clients are
in the same `10.42.0.0/24` subnet, so Pi-hole's default
`listeningMode = LOCAL` accepts their queries.

NetworkManager's `shared` mode hands out the Pi as DNS via DHCP, so
clients automatically use Pi-hole — no extra configuration needed on
the connecting device.

> **Stacking with WireGuard:** if you also bring up WG while the hotspot
> is active, WG clients (`10.0.0.0/24`) are on a *different* subnet from
> `wlan0`. For Pi-hole to answer their DNS queries, set
> `dns.listeningMode = ALL` in `pihole.toml`. See
> [pihole.md](pihole.md#dns-configuration) for the same caveat in the
> WireGuard context.

---

## Troubleshooting

```bash
# Profile actually exists?
nmcli connection show | grep waver-hotspot

# What state is wlan0 in right now?
nmcli device status

# Why didn't the hotspot come up?
sudo journalctl -u NetworkManager -n 40 --no-pager

# DHCP / dnsmasq logs (NM runs an internal dnsmasq for shared mode)
sudo journalctl -u NetworkManager | grep -i dnsmasq | tail -20
```

If clients connect to the SSID but fail to get an IP, NM's internal
DHCP probably isn't running (port 53 / 67 conflict, or NM was unhappy
with the profile). Check the journal.

If the LCD button does nothing visible, the launcher service may not
have access to the script. Confirm:

```bash
ls -la ~/waver/config/scripts/hotspot.sh
sudo bash ~/waver/config/scripts/hotspot.sh status
```

---

## Files NOT in repo

- `api/config.py` — contains `HOTSPOT_PASSWORD` (off-repo, gitignored)
