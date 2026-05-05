#!/usr/bin/env python3
"""
Network info module for SwissPI launcher
Pulls live data: IP, WiFi signal, uptime, CPU temp, Pi-hole stats
"""

import subprocess
import json


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
    """Get Pi-hole statistics from its local API"""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost/admin/api.php"],
            capture_output=True, text=True, timeout=3
        )
        data = json.loads(result.stdout)
        return {
            "queries": data.get("dns_queries_today", 0),
            "blocked": data.get("ads_blocked_today", 0),
            "percent": round(float(data.get("ads_percentage_today", 0)), 1)
        }
    except:
        return {"queries": 0, "blocked": 0, "percent": 0}


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
