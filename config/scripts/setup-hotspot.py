#!/usr/bin/env python3
"""
One-time setup for Waver's WiFi hotspot.

Reads HOTSPOT_SSID and HOTSPOT_PASSWORD from api/config.py and creates a
NetworkManager connection profile named "waver-hotspot". Re-run to recreate
(deletes the existing profile first — idempotent).

Run on the Pi:
    sudo ~/waver-env/bin/python3 ~/waver/config/scripts/setup-hotspot.py

The profile is autoconnect=no — it never comes up on its own. The launcher
toggles it via Settings -> Hotspot, or you can do it manually:
    sudo nmcli connection up   waver-hotspot
    sudo nmcli connection down waver-hotspot

Note: hotspot mode is mutually exclusive with WiFi-client mode on a single
radio. Activating the hotspot disconnects whatever WiFi the Pi is on.
"""

import os
import pathlib
import subprocess
import sys

PROFILE_NAME = "waver-hotspot"

# NetworkManager spawns its own dnsmasq for DHCP+DNS when a connection uses
# `ipv4.method shared`. We want DHCP only — DNS is Pi-hole's job, and
# pi-hole already owns port 53 on the interface, so NM's dnsmasq can't bind
# and the hotspot dies after ~30s with "ip-config-unavailable".
# Dropping `port=0` into NM's shared-dnsmasq.d disables NM's DNS without
# breaking DHCP. Clients still get told "DNS = gateway", and pi-hole
# answers them.
DNSMASQ_DROPIN = "/etc/NetworkManager/dnsmasq-shared.d/00-waver-no-dns.conf"
DNSMASQ_DROPIN_BODY = "# Created by Waver setup-hotspot.py\nport=0\n"

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

try:
    from config import HOTSPOT_SSID, HOTSPOT_PASSWORD
except ImportError as e:
    sys.exit(
        f"error: cannot read config: {e}\n"
        f"       ensure api/config.py exists and defines\n"
        f"       HOTSPOT_SSID and HOTSPOT_PASSWORD"
    )

if not HOTSPOT_PASSWORD or "REPLACE" in HOTSPOT_PASSWORD:
    sys.exit(
        "error: set HOTSPOT_PASSWORD in api/config.py to a real value first"
    )

if len(HOTSPOT_PASSWORD) < 8:
    sys.exit("error: HOTSPOT_PASSWORD must be at least 8 characters (WPA2 minimum)")

if os.geteuid() != 0:
    sys.exit("error: must run as root (use sudo)")


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


# Remove existing profile if present — idempotent re-runs
subprocess.run(
    ["nmcli", "connection", "delete", PROFILE_NAME],
    capture_output=True,
)

# Create the connection profile
run([
    "nmcli", "connection", "add",
    "type",          "wifi",
    "ifname",        "wlan0",
    "con-name",      PROFILE_NAME,
    "autoconnect",   "no",
    "ssid",          HOTSPOT_SSID,
])

# Configure as a WPA2 hotspot with NAT'd shared internet
run([
    "nmcli", "connection", "modify", PROFILE_NAME,
    "802-11-wireless.mode",  "ap",
    "802-11-wireless.band",  "bg",
    "ipv4.method",           "shared",
    "wifi-sec.key-mgmt",     "wpa-psk",
    "wifi-sec.psk",          HOTSPOT_PASSWORD,
])

# Drop in dnsmasq config: DHCP-only for shared connections (Pi-hole owns DNS)
dropin_path = pathlib.Path(DNSMASQ_DROPIN)
dropin_path.parent.mkdir(parents=True, exist_ok=True)
dropin_path.write_text(DNSMASQ_DROPIN_BODY)
dropin_path.chmod(0o644)

print(f"✓ Hotspot profile created: {PROFILE_NAME}")
print(f"  SSID:    {HOTSPOT_SSID}")
print(f"  Subnet:  10.42.0.1/24  (NetworkManager 'shared' default)")
print(f"✓ NM dnsmasq drop-in: {DNSMASQ_DROPIN} (port=0 — DHCP-only)")
print()
print("Toggle from the LCD:  Settings -> Hotspot")
print("Or manually:")
print(f"  sudo nmcli connection up   {PROFILE_NAME}")
print(f"  sudo nmcli connection down {PROFILE_NAME}")
