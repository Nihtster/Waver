#!/usr/bin/env python3
"""
Service manager for WAVER
Handles systemd service control and status queries
"""

import subprocess
from enum import Enum


class ServiceStatus(Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    FAILED   = "failed"
    UNKNOWN  = "unknown"


class ServiceManager:
    def __init__(self):
        # Map of friendly name -> systemd service name
        self.services = {
            "pihole":       "pihole-FTL",
            "wireguard":    "wg-quick@wg0",
            "ssh":          "ssh",
            "nginx":        "nginx",
            "rsvp":         "waver-rsvp",
            "usb-storage":  "waver-usb-gadget",
            "usb-tether":   "waver-usb-tether",
        }

    def get_status(self, service_key):
        """Returns a ServiceStatus enum for the given service key"""
        if service_key not in self.services:
            return ServiceStatus.UNKNOWN

        try:
            result = subprocess.run(
                ["systemctl", "is-active", self.services[service_key]],
                capture_output=True, text=True, timeout=2
            )
            status = result.stdout.strip()
            return ServiceStatus(status) if status in [e.value for e in ServiceStatus] else ServiceStatus.UNKNOWN
        except Exception as e:
            print(f"Error checking {service_key} status: {e}")
            return ServiceStatus.UNKNOWN

    def start(self, service_key):
        """Start a service. Returns True on success."""
        if service_key not in self.services:
            return False
        try:
            subprocess.run(
                ["sudo", "systemctl", "start", self.services[service_key]],
                timeout=5, capture_output=True
            )
            return self.get_status(service_key) == ServiceStatus.ACTIVE
        except Exception as e:
            print(f"Error starting {service_key}: {e}")
            return False

    def stop(self, service_key):
        """Stop a service. Returns True on success."""
        if service_key not in self.services:
            return False
        try:
            subprocess.run(
                ["sudo", "systemctl", "stop", self.services[service_key]],
                timeout=5, capture_output=True
            )
            return self.get_status(service_key) == ServiceStatus.INACTIVE
        except Exception as e:
            print(f"Error stopping {service_key}: {e}")
            return False

    def toggle(self, service_key):
        """Toggle a service on/off. Returns True on success."""
        if self.get_status(service_key) == ServiceStatus.ACTIVE:
            return self.stop(service_key)
        else:
            return self.start(service_key)

    def get_status_string(self, service_key):
        """Returns a human-readable status string e.g. [ON] or [OFF]"""
        status = self.get_status(service_key)
        if status == ServiceStatus.ACTIVE:
            return "[ON]"
        elif status == ServiceStatus.INACTIVE:
            return "[OFF]"
        else:
            return "[?]"
