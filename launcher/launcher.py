#!/usr/bin/env python3
"""
SwissPI Launcher - Main menu system with service integration
"""

from display_manager import DisplayManager
from input_manager import InputManager, InputEvent
from service_manager import ServiceManager
from network_info import get_network_summary
import time
import subprocess

class Launcher:
    def __init__(self):
        print("Initializing components...")
        self.input = InputManager()
        time.sleep(0.5)

        self.display = DisplayManager()
        time.sleep(0.5)

        self.services = ServiceManager()
        self.running = True
        self.current_menu = "main"
        self.selected_index = 0

        # Menu structure
        self.menus = {
            "main": {
                "title": "SwissPI",
                "items": ["Pi-hole", "WireGuard", "Network", "Tools", "Settings"],
                "type": "services"
            },
            "tools": {
                "title": "Tools",
                "items": ["Scanner", "TOTP", "Dashboard", "Back"],
                "type": "regular"
            }
        }

        # Service keys for main menu
        self.service_keys = {
            "Pi-hole": "pihole",
            "WireGuard": "wireguard"
        }

    def run(self):
        """Main launcher loop"""
        print("Starting SwissPI launcher...")
        time.sleep(0.5)

        try:
            while self.running:
                self.render_current_menu()
                self.handle_input()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.cleanup()

    def render_current_menu(self):
        """Render current menu on display"""
        menu_data = self.menus.get(self.current_menu)
        if not menu_data:
            return

        status_dict = None
        if menu_data.get("type") == "services":
            status_dict = {}
            for item in menu_data["items"]:
                if item in self.service_keys:
                    service_key = self.service_keys[item]
                    status_dict[item] = self.services.get_status_string(service_key)

        self.display.draw_menu(
            menu_data["title"],
            menu_data["items"],
            self.selected_index,
            status_dict
        )

    def handle_input(self):
        """Handle input events"""
        event = self.input.get_event(timeout=0.5)

        if not event:
            return

        menu_data = self.menus[self.current_menu]
        num_items = len(menu_data["items"])

        if event == InputEvent.JOY_UP:
            self.selected_index = (self.selected_index - 1) % num_items
        elif event == InputEvent.JOY_DOWN:
            self.selected_index = (self.selected_index + 1) % num_items
        elif event == InputEvent.JOY_PRESS or event == InputEvent.KEY1:
            self.handle_selection()
        elif event == InputEvent.KEY2:
            self.show_status()
        elif event == InputEvent.KEY3:
            if self.current_menu != "main":
                self.current_menu = "main"
                self.selected_index = 0

    def handle_selection(self):
        """Handle menu selection"""
        menu_data = self.menus[self.current_menu]
        selected_item = menu_data["items"][self.selected_index]

        if selected_item in self.service_keys:
            service_key = self.service_keys[selected_item]
            self.display.draw_status([
                "Please wait...",
                f"Toggling {selected_item}"
            ])
            success = self.services.toggle(service_key)
            status = "ON" if self.services.get_status(service_key).value == "active" else "OFF"
            self.display.draw_status([
                f"{selected_item}",
                f"Now: {status}"
            ])
            time.sleep(1)

        elif selected_item == "Tools":
            self.current_menu = "tools"
            self.selected_index = 0
        elif selected_item == "Network":
            self.show_network_info()
        elif selected_item == "Settings":
            self.show_settings()
        elif selected_item == "Back":
            self.current_menu = "main"
            self.selected_index = 0

    def show_network_info(self):
        """Show network information screen"""
        self.display.draw_status([
            "Network Info",
            "Loading..."
        ])

        info = get_network_summary()
        pihole = info["pihole"]

        lines = [
            "Network Info",
            f"IP: {info['ip']}",
            f"WiFi: {info['signal']}",
            f"Up: {info['uptime']}",
            f"Temp: {info['temp']}",
            f"Q: {pihole['queries']}",
            f"Blk: {pihole['blocked']}({pihole['percent']}%)"
        ]

        self.display.draw_status(lines)
        self.input.get_event(timeout=5)

    def show_settings(self):
        """Show settings screen"""
        lines = [
            "Settings",
            "WiFi: Connected",
            "IP: 192.168.0.191",
            "Press any key..."
        ]
        self.display.draw_status(lines)
        self.input.get_event(timeout=3)

    def show_status(self):
        """Show quick status overlay"""
        try:
            uptime_result = subprocess.run(
                ["uptime", "-p"],
                capture_output=True,
                text=True,
                timeout=2
            )
            uptime = uptime_result.stdout.strip()
            uptime = uptime.replace("up ", "")
            uptime = uptime.replace(" hours", "h")
            uptime = uptime.replace(" hour", "h")
            uptime = uptime.replace(" minutes", "m")
            uptime = uptime.replace(" minute", "m")
            uptime = uptime.replace(", ", " ")
        except:
            uptime = "N/A"

        pihole_status = self.services.get_status_string("pihole")
        wg_status = self.services.get_status_string("wireguard")

        lines = [
            "System Status",
            f"Up: {uptime}",
            f"Pi-hole: {pihole_status}",
            f"WireGuard: {wg_status}",
            "Press any key..."
        ]
        self.display.draw_status(lines)
        self.input.get_event(timeout=3)

    def cleanup(self):
        """Clean up resources"""
        try:
            self.input.cleanup()
        except:
            pass

if __name__ == "__main__":
    launcher = Launcher()
    launcher.run()
