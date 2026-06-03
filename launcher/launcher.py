#!/usr/bin/env python3

import time
import threading

from display_manager import DisplayManager, GREEN, BLUE, CYAN, GRAY
from input_manager import InputManager, InputEvent

# ── Screen identifiers ────────────────────────────────────────────────────────
HOME        = "home"
TOOLS       = "tools"
PIHOLE      = "pihole"
WIREGUARD   = "wireguard"
HOTSPOT     = "hotspot"
WIFI_SCAN   = "wifi_scan"
WIFI_KIT    = "wifi_toolkit"
RSVP_READER = "rsvp_reader"
DASHBOARD   = "dashboard"
SETTINGS    = "settings"
UPDATE      = "update"
ABOUT       = "about"
PLACEHOLDER = "placeholder"

_SETTINGS_ITEMS = ["Hotspot", "WiFi", "Display", "Check Update", "About"]


class Launcher:
    def __init__(
        self,
        display_backend=None,
        input_backend=None,
        service_backend=None,
        hotspot_backend=None,
        network_fn=None,
        updater=None,
        stop_event=None,
    ):
        self.stop_event = stop_event or threading.Event()

        print("Initializing WAVER...")
        self.input   = InputManager(backend=input_backend)
        self.display = DisplayManager(backend=display_backend)

        if service_backend is not None:
            self.services = service_backend
        else:
            from service_manager import ServiceManager
            self.services = ServiceManager()

        if hotspot_backend is not None:
            self.hotspot = hotspot_backend
        else:
            from hotspot_manager import HotspotManager
            self.hotspot = HotspotManager()

        if network_fn is not None:
            self.get_network = network_fn
        else:
            from network_info import get_network_summary
            self.get_network = get_network_summary

        if updater is not None:
            self.updater = updater
        else:
            import updater as _upd
            self.updater = _upd

        self.screen   = HOME
        self.selected = 0
        self.running  = True

        self._tools_items       = self._build_tools_items()
        self._wifi_kit          = ["Scan", "Deauth", "Capture", "Evil Twin"]
        self._rsvp_items        = ["Library", "Service Status"]
        self._placeholder_title = "Coming Soon"

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        print("WAVER running")
        try:
            while self.running and not self.stop_event.is_set():
                self._render()
                self._handle_input()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self._cleanup()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self):
        if self.screen == HOME:
            self.display.draw_home(
                pihole_status=self._svc("pihole"),
                wg_status=self._svc("wireguard"),
            )

        elif self.screen == TOOLS:
            self._tools_items = self._build_tools_items()
            self.display.draw_tools_menu(self._tools_items, self.selected)

        elif self.screen == PIHOLE:
            net = self.get_network()
            ph  = net.get("pihole", {})
            self.display.draw_pihole(
                status=self._svc("pihole"),
                blocked_today=ph.get("blocked", 0),
                top_domain=ph.get("top_domain", ""),
            )

        elif self.screen == WIREGUARD:
            net = self.get_network()
            wg  = net.get("wireguard", {})
            self.display.draw_wireguard(
                status=self._svc("wireguard"),
                endpoint=wg.get("endpoint", ""),
                rx=wg.get("rx", "0"),
                tx=wg.get("tx", "0"),
            )

        elif self.screen == HOTSPOT:
            self.display.draw_hotspot(
                status=self._hotspot_status(),
                ssid=self.hotspot.ssid,
                password=self.hotspot.password,
            )

        elif self.screen == WIFI_SCAN:
            networks = self.get_network().get("wifi_scan", [])
            self.display.draw_wifi_scan(networks, self.selected)

        elif self.screen == WIFI_KIT:
            self.display.draw_wifi_toolkit(self._wifi_kit, self.selected)

        elif self.screen == RSVP_READER:
            self.display.draw_wifi_toolkit(self._rsvp_items, self.selected)

        elif self.screen == DASHBOARD:
            net = self.get_network()
            self.display.draw_dashboard(
                cpu=net.get("cpu", 0),
                mem=net.get("mem", 0),
                uptime=net.get("uptime", ""),
                clients=net.get("clients", 0),
            )

        elif self.screen == SETTINGS:
            self.display.draw_settings(_SETTINGS_ITEMS, self.selected)

        elif self.screen == UPDATE:
            # UPDATE is handled imperatively in _run_update(); render is a no-op
            pass

        elif self.screen == ABOUT:
            self.display.draw_about()

        elif self.screen == PLACEHOLDER:
            self.display.draw_placeholder(self._placeholder_title)

    # ── Input handling ────────────────────────────────────────────────────────

    def _handle_input(self):
        timeout = 0.1 if self.screen in (HOME, ABOUT) else 0.4
        event = self.input.get_event(timeout=timeout)

        if self.stop_event.is_set() or event is None:
            return

        if event == InputEvent.JOY_UP:
            self._nav(-1)
        elif event == InputEvent.JOY_DOWN:
            self._nav(+1)
        elif event in (InputEvent.JOY_PRESS, InputEvent.KEY1, InputEvent.JOY_RIGHT):
            self._select()
        elif event in (InputEvent.KEY3, InputEvent.JOY_LEFT):
            self._back()
        elif event == InputEvent.KEY2:
            self._goto(DASHBOARD)

    def _nav(self, direction):
        count = self._nav_count()
        if count:
            self.selected = (self.selected + direction) % count

    def _nav_count(self):
        if self.screen == TOOLS:
            return len(self._tools_items)
        if self.screen == WIFI_KIT:
            return len(self._wifi_kit)
        if self.screen == RSVP_READER:
            return len(self._rsvp_items)
        if self.screen == WIFI_SCAN:
            return len(self.get_network().get("wifi_scan", []))
        if self.screen == SETTINGS:
            return len(_SETTINGS_ITEMS)
        return 0

    def _select(self):
        if self.screen == HOME:
            self._goto(TOOLS)

        elif self.screen == TOOLS:
            label = self._tools_items[self.selected][0]
            destinations = {
                "Pi-hole":      PIHOLE,
                "WireGuard":    WIREGUARD,
                "WiFi Toolkit": WIFI_KIT,
                "RSVP Reader":  RSVP_READER,
                "Dashboard":    DASHBOARD,
                "About":        ABOUT,
                "Settings":     SETTINGS,
            }
            if label in destinations:
                self._goto(destinations[label])
            else:
                self._placeholder_title = label
                self._goto(PLACEHOLDER)

        elif self.screen == WIFI_KIT:
            label = self._wifi_kit[self.selected]
            if label == "Scan":
                self._goto(WIFI_SCAN)
            else:
                self._placeholder_title = label
                self._goto(PLACEHOLDER)

        elif self.screen == RSVP_READER:
            label = self._rsvp_items[self.selected]
            if label == "Service Status":
                status = self._svc("rsvp")
                line = "Active" if status == "active" else "Off"
                self.display.draw_status(["RSVP Reader", line])
                self.input.get_event(timeout=2)
            else:
                self._placeholder_title = label
                self._goto(PLACEHOLDER)

        elif self.screen == SETTINGS:
            label = _SETTINGS_ITEMS[self.selected]
            if label == "Check Update":
                self._run_update()
            elif label == "About":
                self._goto(ABOUT)
            elif label == "Hotspot":
                self._goto(HOTSPOT)
            else:
                self._placeholder_title = label
                self._goto(PLACEHOLDER)

        elif self.screen == PIHOLE:
            self.display.draw_status(["Toggling...", "Pi-hole"])
            self.services.toggle("pihole")
            time.sleep(0.5)

        elif self.screen == WIREGUARD:
            self.display.draw_status(["Toggling...", "WireGuard"])
            self.services.toggle("wireguard")
            time.sleep(0.5)

        elif self.screen == HOTSPOT:
            self.display.draw_status(["Toggling...", "Hotspot"])
            self.hotspot.toggle()
            time.sleep(0.5)

    def _back(self):
        if self.screen == HOME:
            return
        if self.screen == HOTSPOT:
            self._goto(SETTINGS)
        elif self.screen in (PIHOLE, WIREGUARD, WIFI_KIT, RSVP_READER, ABOUT, DASHBOARD, PLACEHOLDER, SETTINGS):
            self._goto(TOOLS)
        elif self.screen == WIFI_SCAN:
            self._goto(WIFI_KIT)
        else:
            self._goto(HOME)

    def _goto(self, screen):
        self.screen   = screen
        self.selected = 0

    # ── OTA update flow ───────────────────────────────────────────────────────

    def _run_update(self):
        """
        Blocking update flow — runs entirely within the main loop iteration.
        Displays progress on the LCD and waits for user confirmation.
        """
        # 1. Check
        self.display.draw_update_status("Checking...", "Connecting to remote")
        status, msg = self.updater.check_updates()

        if status == "error":
            self.display.draw_update_status("Check failed", msg)
            self.input.get_event(timeout=3)
            self._goto(SETTINGS)
            return

        if status == "up_to_date":
            self.display.draw_update_status("Up to date", msg)
            self.input.get_event(timeout=3)
            self._goto(SETTINGS)
            return

        # 2. Updates available — ask user to confirm
        self.display.draw_update_status(
            "Update available",
            msg,
            hint="SELECT to install",
        )
        event = self.input.get_event(timeout=15)
        if event not in (InputEvent.JOY_PRESS, InputEvent.KEY1, InputEvent.JOY_RIGHT):
            self._goto(SETTINGS)
            return

        # 3. Pull
        self.display.draw_update_status("Updating...", "Please wait")
        status, msg = self.updater.do_update()

        if status == "error":
            self.display.draw_update_status("Update failed", msg)
            self.input.get_event(timeout=3)
            self._goto(SETTINGS)
            return

        # 4. Success — restart services (kills this process on real hardware)
        self.display.draw_update_status("Done!", msg, hint="Restarting...")
        time.sleep(1.5)
        self.updater.restart_services()

        # On simulator restart_services() returns instead of exiting,
        # so we land back at the settings screen.
        self._goto(SETTINGS)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _svc(self, key):
        status = self.services.get_status(key)
        return status.value if hasattr(status, "value") else str(status).lower()

    def _hotspot_status(self):
        status = self.hotspot.get_status()
        return status.value if hasattr(status, "value") else str(status).lower()

    def _build_tools_items(self):
        ph = self._svc("pihole")
        wg = self._svc("wireguard")
        return [
            ("Pi-hole",      "Active" if ph == "active" else "Off", GREEN if ph == "active" else GRAY),
            ("WireGuard",    "On"     if wg == "active" else "Off", BLUE  if wg == "active" else GRAY),
            ("Pwnagotchi",   "Off",   GRAY),
            ("WiFi Toolkit", "",      CYAN),
            ("RF Tools",     "",      CYAN),
            ("RSVP Reader",  "Active" if self._svc("rsvp") == "active" else "Off", CYAN),
            ("Dashboard",    "",      CYAN),
            ("Settings",     "",      CYAN),
            ("About",        "",      CYAN),
        ]

    def _cleanup(self):
        try:
            self.input.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    launcher = Launcher()
    launcher.run()
