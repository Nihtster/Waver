#!/usr/bin/env python3
"""
Mock service manager for the WAVER simulator.
Mirrors the ServiceManager interface but stores state in memory.
Toggle state persists across hot-reloads because the instance lives
in run_sim.py (which is never reloaded).
"""


class MockServiceManager:
    def __init__(self):
        self._states = {
            "pihole":     "active",
            "wireguard":  "active",
            "pwnagotchi": "inactive",
            "nginx":      "active",
            "ssh":        "active",
        }

    def get_status(self, service_key):
        """Return lowercase status string: active | inactive | unknown"""
        return self._states.get(service_key, "unknown")

    def get_status_string(self, service_key):
        """Human-readable bracket string for legacy callers."""
        s = self.get_status(service_key)
        return "[ON]" if s == "active" else "[OFF]"

    def toggle(self, service_key):
        if service_key not in self._states:
            return False
        current = self._states[service_key]
        self._states[service_key] = "inactive" if current == "active" else "active"
        print(f"[mock] {service_key}: {current} → {self._states[service_key]}")
        return True

    def start(self, service_key):
        if service_key in self._states:
            self._states[service_key] = "active"
            return True
        return False

    def stop(self, service_key):
        if service_key in self._states:
            self._states[service_key] = "inactive"
            return True
        return False
