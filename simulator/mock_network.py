#!/usr/bin/env python3
"""
Mock network / system data for the WAVER simulator.
Returns a static snapshot that matches the concept-art values.
Edit these values to test different UI states.
"""

import random
import time


# Optionally add a tiny drift to CPU/mem so the dashboard looks "live"
_start = time.time()


def mock_get_network():
    elapsed = time.time() - _start
    cpu = int(23 + 8 * abs(((elapsed * 0.3) % 2) - 1))   # oscillates 15–31 %
    mem = 38   # stable

    return {
        "ip":      "192.168.0.191",
        "signal":  "-42 dBm",
        "uptime":  "2h 14m",
        "temp":    "45.2°C",
        "cpu":     cpu,
        "mem":     mem,
        "clients": 5,

        "wifi_scan": [
            ("WaverLab",    -42),
            ("CoffeeShop",  -67),
            ("HomeNetwork", -71),
            ("Guest_Net",   -80),
        ],

        "pihole": {
            "queries":    12453,
            "blocked":    2351,
            "percent":    18.9,
            "top_domain": "google.com",
        },

        "wireguard": {
            "endpoint": "10.6.0.2",
            "rx":       "1.2 MB",
            "tx":       "657 KB",
        },
    }
