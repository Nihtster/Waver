#!/usr/bin/env python3
"""Mock updater for the simulator — simulates update states without touching git."""

import time

# Flip this to test different states in the simulator:
#   "up_to_date" | "available" | "error"
MOCK_STATE = "available"


def check_updates():
    time.sleep(0.6)   # simulate network latency
    if MOCK_STATE == "available":
        return "available", "3 new commit(s) ready"
    if MOCK_STATE == "error":
        return "error", "network timeout"
    return "up_to_date", "Already up to date"


def do_update():
    time.sleep(1.0)   # simulate pull delay
    return "success", "4 file(s) updated"


def restart_services():
    print("[mock] restart_services() called — would restart waver + waver-api")
    # In the simulator we don't actually restart; just return to home.
