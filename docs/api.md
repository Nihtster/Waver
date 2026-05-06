# API

Flask + SocketIO REST API that powers the web dashboard. Source:
[api/app.py](../api/app.py).

Runs as the `waver-api` systemd service on internal port 5000, fronted by
nginx on port 80.

---

## Authentication

All endpoints except `POST /api/auth/login` require a JWT in the
`Authorization: Bearer <token>` header.

- Password is verified against a `bcrypt` hash stored in
  [api/config.py](../api/config.example.py) (off-repo).
- Tokens are HS256-signed with `SECRET_KEY` and expire after 24 hours.
- Tokens are stateless — the server keeps no session table. Logout is
  client-side (drop the token).

```bash
curl -X POST http://192.168.0.191/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"password":"yourpassword"}'
# → {"token": "eyJhbGciOi..."}
```

---

## Endpoints

### Auth

| Method | Path                | Body              | Response                  |
|--------|---------------------|-------------------|---------------------------|
| POST   | `/api/auth/login`   | `{password}`      | `{token}` or 401          |

### System

| Method | Path                  | Returns                                                      |
|--------|-----------------------|--------------------------------------------------------------|
| GET    | `/api/system/status`  | `{uptime, temp, ip, pihole, wireguard, ssh, nginx}` (booleans for service fields) |

### Network

| Method | Path                          | Body          | Returns / Notes                          |
|--------|-------------------------------|---------------|------------------------------------------|
| GET    | `/api/network/info`           | —             | `{ip, signal, interface}`                |
| GET    | `/api/network/wifi/scan`      | —             | `{networks: [{ssid, signal}]}` (deduped) |
| POST   | `/api/network/wifi/connect`   | `{ssid, password?}` | `{success, ip}` after `nmcli` connect |

### Services

| Method | Path                              | Returns                              |
|--------|-----------------------------------|--------------------------------------|
| GET    | `/api/services/pihole`            | `{active, stats: {queries, blocked, percent}}` |
| POST   | `/api/services/pihole/toggle`     | `{active}` — emits SocketIO event    |
| GET    | `/api/services/wireguard`         | `{active}`                           |
| POST   | `/api/services/wireguard/toggle`  | `{active}` — emits SocketIO event    |

---

## SocketIO

Toggle endpoints emit a `service_update` event so the dashboard can update
without a poll round-trip:

```js
socket.emit('service_update', { service: 'pihole', active: true })
```

The connect handler verifies the JWT in the auth payload:

```js
io({ auth: { token: localStorage.getItem('token') } })
```

A missing or invalid token disconnects immediately
([api/app.py:255](../api/app.py:255)).

---

## Running as a service

`waver-api.service` ([config/systemd/waver-api.service](../config/systemd/waver-api.service)):

```ini
ExecStart=/home/cimi/waver-env/bin/gunicorn \
    --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
    --workers 1 \
    --bind 127.0.0.1:5000 \
    app:app
```

Single worker. SocketIO needs sticky connections, and one worker is fine
for a single-user dashboard.

---

## Why gevent and not eventlet

`eventlet` has not been compatible with Python 3.13 (which ships on current
Pi OS). Symptoms: `ImportError: cannot import name 'ALREADY_HANDLED'` or a
hang on first request. `gevent` + `gevent-websocket` works correctly.

---

## Why running as root

Several endpoints shell out to commands that require root:

- `iwlist scan` (WiFi scan)
- `nmcli dev wifi connect` (WiFi switch)
- `systemctl start/stop` (service toggles)

The systemd unit runs as `User=root`. Don't shave off this privilege without
moving the privileged ops behind a separate helper or polkit rules.

---

## Known issues

- **Pi-hole stats endpoint stale** — Pi-hole v6 changed its API surface.
  The current `pihole_status` handler ([api/app.py:202](../api/app.py:202))
  still hits the v5 path and returns zeros. See [pihole.md](pihole.md).
- **No rate limiting on login** — bcrypt verification is slow but a
  determined attacker on the LAN could still brute-force. Add `Flask-Limiter`
  if exposing this beyond the home network.
- **CORS is wide open** (`cors_allowed_origins="*"`) — fine for LAN-only,
  not fine if you put this behind a public domain.

---

## Adding an endpoint

1. Add a handler in [api/app.py](../api/app.py).
2. Start with `if not verify_token(get_auth_token()): return 401`.
3. For privileged ops use `run_cmd([...])` — it captures stdout, sets a
   timeout, and swallows exceptions to a None return.
4. For service toggles, also `socketio.emit('service_update', ...)` so the
   dashboard updates live.
5. Restart the service: `sudo systemctl restart waver-api`.
