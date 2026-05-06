# Pi-hole

Pi-hole runs alongside Waver to provide network-wide DNS ad and tracker
blocking. Waver toggles it via systemd and surfaces stats on both the LCD
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

The admin UI is now at `http://192.168.0.191:8080/admin`.

---

## nginx reverse proxy

`config/nginx/waver.conf` already has the rule:

```nginx
location /pihole/ {
    proxy_pass http://127.0.0.1:8080/;
    proxy_set_header Host $host;
}
```

So the admin UI is also reachable at `http://192.168.0.191/pihole/admin`,
which is convenient if you only want one bookmark.

---

## DNS configuration

Point your router's DHCP server at `192.168.0.191` as the primary DNS to
hand out Pi-hole DNS to the whole network. Or set per-device — the Pi
itself, your phone, your laptop.

Verify:

```bash
dig @192.168.0.191 doubleclick.net
# → should return 0.0.0.0
```

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

## Stats integration — known issue

Both [api/app.py](../api/app.py:202) and
[network_info.py](../launcher/network_info.py:38) still hit the v5 endpoint:

```
http://localhost/admin/api.php?summaryRaw
```

Pi-hole v6 changed this. The new endpoint requires authentication and
returns a different shape. The current code silently catches the parse
error and returns zeros, which is why the dashboard's stats card shows
`0 / 0 / 0%` and the LCD's "Blocked Today" shows 0.

Fix path:

1. Generate an app password in the Pi-hole admin → Settings → API
2. Auth via `POST /api/auth` to get a session ID
3. Hit `GET /api/stats/summary` with `sid=<session>`
4. Map `queries.total`, `queries.blocked`, `queries.percent_blocked` to the
   existing `{queries, blocked, percent}` shape

This is on the roadmap — medium priority.

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
