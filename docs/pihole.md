# Pi-hole

Pi-hole runs alongside Waver as a portable, on-device DNS ad and tracker
blocker. Because Waver is meant to travel with you, the design is
**Pi-only** for DNS: the Pi uses its own Pi-hole as resolver, and clients
get filtering by tunnelling through Waver's WireGuard (rather than by
reconfiguring whatever LAN you happen to be on).

Waver toggles the daemon via systemd and surfaces stats on both the LCD
and the dashboard.

---

## Install

Standard Pi-hole installer:

```bash
curl -sSL https://install.pi-hole.net | bash
```

Pick `wlan0` as the upstream interface during the wizard. Set an admin
password when prompted (or skip and run `pihole -a -p` later).

---

## Move off port 80

Pi-hole v6 runs its own embedded web server. By default that grabs ports
80 / 443, which collides with nginx — so move it.

Edit `/etc/pihole/pihole.toml`:

```toml
[webserver]
port = "8080o,8443os,[::]:8080o,[::]:8443os"
```

> Both IPv4 **and** IPv6 must be on 8080. Leaving `[::]:80` enabled blocks
> nginx for IPv6 clients even if IPv4 looks fine.

Restart:

```bash
sudo systemctl restart pihole-FTL
```

The admin UI is at `http://<pi-host>:8080/admin/` — reach it directly,
not through Waver's nginx. Pi-hole's admin is hard to reverse-proxy at a
sub-path without configuring Pi-hole's `webhome` setting, and the win
isn't worth the maintenance burden. The Waver dashboard's "Open Pi-hole
Admin" button links to `:8080` directly, building the URL from
`window.location.hostname` so it works on LAN, mDNS, or over WireGuard.

---

## DNS configuration

The Pi resolves through its own Pi-hole. Set via NetworkManager (Pi OS
Bookworm uses NM, not dhcpcd):

```bash
CON=$(nmcli -t -f NAME con show --active | head -1)
sudo nmcli con mod "$CON" \
    ipv4.dns "127.0.0.1" \
    ipv4.ignore-auto-dns yes
sudo nmcli con up "$CON"
```

Verify:

```bash
dig @127.0.0.1 doubleclick.net +short
# → 0.0.0.0   (Pi-hole blocking)
dig @127.0.0.1 google.com +short
# → real IPs  (Pi-hole forwarding upstream)
```

### How clients get Pi-hole filtering

Waver is a portable device — its `wlan0` IP keeps changing as you move
networks, so configuring the LAN's DHCP server to point at it is not the
right model. Instead, clients get filtering through **WireGuard**:

1. The phone or laptop connects to Waver's WireGuard tunnel.
2. The peer config includes `DNS = 10.0.0.1` (Waver's wg0 address).
3. With `AllowedIPs = 0.0.0.0/0`, all client traffic — including DNS —
   routes through Waver, hits Pi-hole, and gets filtered.

Result: Pi-hole filtering wherever the Pi has internet, with no
LAN-side configuration needed. See [wireguard.md](wireguard.md) for the
peer flow.

> **Pi-hole listening mode for WireGuard:** when WG peers are added,
> `pihole.toml` → `dns.listeningMode` must be `ALL` (not the default
> `LOCAL`). Otherwise queries arriving on `10.0.0.0/24` from a different
> subnet than `wlan0`'s are silently dropped.

---

## systemd unit

The unit name is `pihole-FTL` (FTL = "Faster Than Light", Pi-hole's DNS
engine). Waver's service manager maps the friendly key `pihole` to this
name in [service_manager.py](../launcher/service_manager.py:21).

```bash
systemctl is-active pihole-FTL
sudo systemctl restart pihole-FTL
sudo journalctl -u pihole-FTL -f
```

---

## Stats integration (v6 API)

The dashboard and LCD pull stats through the v6 REST API, which is
session-authenticated. All of the auth dance lives in
[api/pihole_client.py](../api/pihole_client.py) and is shared by both
[api/app.py](../api/app.py) (dashboard) and
[launcher/network_info.py](../launcher/network_info.py) (LCD).

### Generating the API credential

Use a Pi-hole **application password**, not your admin password — it's
revocable independently and avoids storing the admin login in
`api/config.py`.

1. Open the admin UI: `http://192.168.0.191:8080/admin/settings/api`
2. Toggle the top-right switch from **Basic** to **Expert**
3. In *Advanced Settings*, click **Configure app password** and generate one
4. Paste the result into `PIHOLE_APP_PASSWORD` in `api/config.py`
5. Restart the API: `sudo systemctl restart waver-api`

### How the client works

```python
PiholeClient(base_url, app_password).get_stats_summary()
# → {"queries": int, "blocked": int, "percent": float}
```

Internally:

1. `POST /api/auth` with `{password}` → returns a session ID
2. `GET /api/stats/summary` with `X-FTL-SID: <sid>` header → returns
   the v6 stats blob
3. Maps `queries.total` / `queries.blocked` / `queries.percent_blocked`
   onto Waver's existing `{queries, blocked, percent}` contract

The SID is cached in-process. Default v6 session TTL is 30 min — the
client re-authenticates automatically on a 401 and retries the call once.

### Adding new endpoints

Pi-hole v6 has many more endpoints (`/api/stats/top_domains`,
`/api/stats/upstreams`, `/api/queries`, etc.). To pull from any of them,
add a method on `PiholeClient` that calls `self._get("/some/path")` and
maps the response. The auth handling is already taken care of.

---

## Toggle behaviour

Toggling Pi-hole on the LCD or dashboard runs:

```bash
sudo systemctl stop pihole-FTL    # or start
```

This is **not** the same as `pihole disable` — the latter pauses blocking
but keeps the daemon running, while ours stops the daemon entirely. For
the home-network use case this is what we want (DNS falls back to the
router when the daemon is down). If you'd rather use the soft pause, swap
the toggle to call `pihole enable` / `pihole disable`.

---

## Logs and debugging

```bash
sudo journalctl -u pihole-FTL -f          # daemon logs
tail -f /var/log/pihole/pihole.log        # query log
pihole status                             # quick status summary
pihole -t                                 # tail the query log w/ colour
```
