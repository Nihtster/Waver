# Dashboard

The web dashboard is a single-page UI for controlling Waver from any device
on the LAN. Source: [dashboard/](../dashboard).

It is served as static files by Flask, and talks to the [API](api.md) over
fetch + SocketIO.

---

## Access

```
http://192.168.0.191/        # IP
http://waver.local/          # mDNS, if avahi is up
```

Login with the password whose bcrypt hash is in `api/config.py`. The JWT
returned is stored in `localStorage` and attached to every subsequent
request.

---

## Files

| File           | Role                                                 |
|----------------|------------------------------------------------------|
| `index.html`   | Login screen + dashboard markup                      |
| `style.css`    | Dark theme, single CSS file                          |
| `app.js`       | Auth, fetch wrappers, polling, toggle handlers       |

No build step. No bundler. No framework. Edit, save, refresh.

---

## Features

- Live system status: uptime, CPU temp, IP
- Service status badges for Pi-hole, WireGuard, SSH, nginx
- One-click toggle for Pi-hole and WireGuard
- WiFi scan + connect
- Pi-hole stats card (queries / blocked / block %) — see known issues

---

## Reverse proxy

nginx terminates port 80 and proxies everything to Flask on `127.0.0.1:5000`.
A second `location` block proxies `/pihole/` to the Pi-hole admin UI on
port 8080.

[config/nginx/waver.conf](../config/nginx/waver.conf):

```nginx
server {
    listen 80;
    server_name waver.local 192.168.0.191 _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 60;
        proxy_connect_timeout 60;
    }

    location /pihole/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
    }
}
```

> **No** `Upgrade` / `Connection` headers. Adding them caused SocketIO
> connections to hang during the initial handshake. Plain HTTP proxying
> works fine — gevent-websocket handles the upgrade itself.

---

## Auth flow

1. User enters password in the login form.
2. `app.js` POSTs to `/api/auth/login`, gets a JWT back.
3. Token saved to `localStorage` under a fixed key.
4. All subsequent fetches include `Authorization: Bearer <token>`.
5. SocketIO connects with `{ auth: { token } }` in the handshake.
6. Logout clears `localStorage` and reloads the page.

If a request returns 401, the client drops the token and bounces back to
the login screen.

---

## Live updates

The dashboard polls `/api/system/status` on an interval for things that
don't have a push channel (uptime, temp). Service toggles use SocketIO:
when any client toggles Pi-hole, the API emits `service_update` and every
connected dashboard updates its badge without polling.

---

## Editing the dashboard

```bash
ssh cimi@waver.local
cd ~/waver/dashboard
nano index.html        # or pull and edit locally, push, OTA update
```

No restart needed — Flask serves the files directly from disk on each
request. Hard-refresh (`Ctrl-Shift-R`) to bypass browser cache.

---

## Known issues

- Pi-hole stats card shows zeros until the v6 API integration is fixed
  (see [pihole.md](pihole.md)).
- Mobile layout works but is not a priority — buttons are tap-sized but
  some cards crowd at narrow widths.
