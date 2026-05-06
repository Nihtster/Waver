#!/usr/bin/env python3
"""
WiFi hotspot control for the WAVER launcher.

Wraps config/scripts/hotspot.sh — that script in turn wraps `nmcli` calls
against the "waver-hotspot" NetworkManager profile created by setup-hotspot.py.

The launcher uses this to toggle AP mode from Settings -> Hotspot. Reads
SSID + password from api/config.py for display on the LCD when the user
needs to connect a phone or laptop to the hotspot.
"""

import os
import pathlib
import subprocess
import sys
from enum import Enum


# ── Config (SSID + password for LCD display) ──────────────────────────────────
# Reads from api/config.py via path tweak — same pattern as network_info.py.

_API_DIR = pathlib.Path(__file__).resolve().parent.parent / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

try:
    from config import HOTSPOT_SSID, HOTSPOT_PASSWORD
except (ImportError, AttributeError):
    HOTSPOT_SSID = "Waver"
    HOTSPOT_PASSWORD = ""


# ── Script paths ──────────────────────────────────────────────────────────────

_SCRIPT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "config" / "scripts" / "hotspot.sh"
)


class HotspotStatus(Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    UNKNOWN  = "unknown"


class HotspotManager:
    """
    Real implementation — shells out to hotspot.sh, which calls nmcli.
    Both the launcher and the script run as root in production, so no
    sudo prefix is needed.
    """

    def __init__(self, script_path=_SCRIPT):
        self.script = str(script_path)
        self.ssid     = HOTSPOT_SSID
        self.password = HOTSPOT_PASSWORD

    def get_status(self):
        try:
            result = subprocess.run(
                ["bash", self.script, "status"],
                capture_output=True, text=True, timeout=4,
            )
            out = result.stdout.strip()
            if out == "active":
                return HotspotStatus.ACTIVE
            if out == "inactive":
                return HotspotStatus.INACTIVE
            return HotspotStatus.UNKNOWN
        except Exception:
            return HotspotStatus.UNKNOWN

    def start(self):
        return self._run("start")

    def stop(self):
        return self._run("stop")

    def toggle(self):
        return self.stop() if self.get_status() == HotspotStatus.ACTIVE else self.start()

    def _run(self, action):
        try:
            subprocess.run(
                ["bash", self.script, action],
                capture_output=True, text=True, timeout=10, check=False,
            )
            return self.get_status()
        except Exception:
            return HotspotStatus.UNKNOWN
