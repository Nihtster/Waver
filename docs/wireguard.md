# WireGuard

Self-hosted VPN server on the Pi. Clients (phone, laptop) connect from
anywhere on the internet and route traffic through the Pi — picking up
Pi-hole DNS in the process.

---

## Install

```bash
sudo apt install -y wireguard wireguard-tools iptables
```

> `iptables` is **not** a default package on current Pi OS. WireGuard's
> NAT rules need it — install it explicitly.

---

## Generate keys

```bash
cd /etc/wireguard
sudo wg genkey | sudo tee private.key | wg pubkey | sudo tee public.key
sudo chmod 600 private.key
```

`private.key` and `public.key` stay on the Pi. Never commit them, never
copy them anywhere they don't need to be.

---

## Server config

Template: [config/wg0.conf.template](../config/wg0.conf.template).

Copy to `/etc/wireguard/wg0.conf` and paste the private key:

```ini
[Interface]
PrivateKey = <contents of /etc/wireguard/private.key>
Address    = 10.0.0.1/24
ListenPort = 51820
PostUp     = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
PostDown   = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o wlan0 -j MASQUERADE

# Add peers below as needed
# [Peer]
# PublicKey  = <peer public key>
# AllowedIPs = 10.0.0.2/32
```

`wg0` is a virtual interface in the `10.0.0.0/24` subnet. The Pi takes
`.1`; each client gets a unique address (`.2`, `.3`, ...) inside that
subnet.

---

## Enable IP forwarding

```bash
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-wireguard.conf
sudo sysctl -p /etc/sysctl.d/99-wireguard.conf
```

Without this the Pi accepts packets on `wg0` but won't route them out
through `wlan0`.

---

## Start the service

```bash
sudo systemctl enable --now wg-quick@wg0
systemctl is-active wg-quick@wg0
sudo wg show
```

The `wg-quick@<name>` unit ties to the matching `<name>.conf` in
`/etc/wireguard/`. Waver's service manager maps the friendly key
`wireguard` to `wg-quick@wg0` in
[service_manager.py](../launcher/service_manager.py:21).

---

## Adding a peer

On the **client** (phone or laptop), generate a key:

```bash
wg genkey | tee peer-private.key | wg pubkey > peer-public.key
```

On the **server**, add a `[Peer]` block to `/etc/wireguard/wg0.conf`:

```ini
[Peer]
PublicKey  = <client public key>
AllowedIPs = 10.0.0.2/32
```

Reload:

```bash
sudo wg syncconf wg0 <(sudo wg-quick strip wg0)
```

(`syncconf` is a hot-reload that won't drop existing peers, unlike
`systemctl restart`.)

On the **client**, configure WireGuard with:

```ini
[Interface]
PrivateKey = <client private key>
Address    = 10.0.0.2/32
DNS        = 10.0.0.1            # use Pi-hole

[Peer]
PublicKey           = <server public key>
Endpoint            = <your-public-ip>:51820
AllowedIPs          = 0.0.0.0/0   # full tunnel
PersistentKeepalive = 25
```

The mobile WireGuard app can scan a QR-coded version of this config:

```bash
sudo apt install qrencode
qrencode -t ansiutf8 < client.conf
```

---

## Port forwarding

Your home router must forward UDP `51820` to `192.168.0.191`. The exact
path depends on the router; look for "port forwarding" or "virtual
servers". WireGuard is UDP-only — TCP forwarding does nothing.

If your ISP gives you CGNAT (no public IP), port forwarding won't work —
you'll need a tunnel service or a VPS jump host.

---

## Verify

From the client, after connecting:

```bash
curl https://ifconfig.me
# → should return your home public IP, not the client's local one
```

DNS check:

```bash
dig @10.0.0.1 doubleclick.net
# → 0.0.0.0  (Pi-hole is blocking)
```

---

## Files NOT in repo

These live on the Pi only:

- `/etc/wireguard/private.key`
- `/etc/wireguard/public.key`
- `/etc/wireguard/wg0.conf`

They contain the server's private key (and any peer public keys you don't
want to publish). Rotate the private key and regenerate peer configs if
you ever leak the file.
