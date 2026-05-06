#!/usr/bin/env python3
"""
Network info module for WAVER launcher
Pulls live data: IP, WiFi signal, uptime, CPU temp, Pi-hole stats
"""

import os
import sys
import subprocess
import json

# Reach into ../api so launcher and dashboard share one Pi-hole client +
# one credential source. If the api dir or config.py isn't there
# (e.g. fresh checkout that hasn't run setup), fall back to zeros.
_API_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api")
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

try:
    from pihole_client import PiholeClient
    from config import PIHOLE_API, PIHOLE_APP_PASSWORD
    _pihole = PiholeClient(PIHOLE_API, PIHOLE_APP_PASSWORD)
except (ImportError, AttributeError):
    _pihole = None


def get_ip():
    """Get current IP address"""
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True, text=True, timeout=2
        )
        return result.stdout.strip().split()[0]
    except:
        return "N/A"


def get_wifi_signal():
    """Get WiFi signal strength in dBm"""
    try:
        result = subprocess.run(
            ["iwconfig", "wlan0"],
            capture_output=True, text=True, timeout=2
        )
        for line in result.stdout.split('\n'):
            if "Signal level" in line:
                return line.split("Signal level=")[1].split(" ")[0]
        return "N/A"
    except:
        return "N/A"


def get_pihole_stats():
    """Get Pi-hole statistics via the shared v6 API client."""
    if _pihole is None:
        return {"queries": 0, "blocked": 0, "percent": 0}
    return _pihole.get_stats_summary()


def get_uptime():
    """Get system uptime in a short format"""
    try:
        result = subprocess.run(
            ["uptime", "-p"],
            capture_output=True, text=True, timeout=2
        )
        uptime = result.stdout.strip()
        uptime = uptime.replace("up ", "")
        uptime = uptime.replace(" hours", "h")
        uptime = uptime.replace(" hour", "h")
        uptime = uptime.replace(" minutes", "m")
        uptime = uptime.replace(" minute", "m")
        uptime = uptime.replace(", ", " ")
        return uptime
    except:
        return "N/A"


def get_cpu_temp():
    """Get CPU temperature"""
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True, text=True, timeout=2
        )
        return result.stdout.strip().replace("temp=", "")
    except:
        return "N/A"


def get_network_summary():
    """Get all network info as a dict"""
    return {
        "ip":     get_ip(),
        "signal": get_wifi_signal(),
        "uptime": get_uptime(),
        "temp":   get_cpu_temp(),
        "pihole": get_pihole_stats()
    }
