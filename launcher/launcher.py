#!/usr/bin/env python3

import time
import threading
import json
import os

from display_manager import DisplayManager, GREEN, BLUE, CYAN, GRAY
from input_manager import InputManager, InputEvent

BOOKS_DIR     = os.environ.get("BOOKS_DIR", "/home/cimi/waver/rsvp-books")
PROGRESS_FILE = os.path.join(BOOKS_DIR, ".rsvp-progress.json")

# ── Screen identifiers ────────────────────────────────────────────────────────
HOME        = "home"
TOOLS       = "tools"
PIHOLE      = "pihole"
WIREGUARD   = "wireguard"
HOTSPOT     = "hotspot"
WIFI_SCAN   = "wifi_scan"
WIFI_KIT    = "wifi_toolkit"
RSVP_READER = "rsvp_reader"
USB_MODE    = "usb_mode"
BOOK_SELECT = "book_select"
READER      = "reader"
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
        self._usb_items         = ["Storage Mode", "Tether Mode"]
        self._placeholder_title = "Coming Soon"

        # ── Reader state ──────────────────────────────────────────────────────
        self._reader_books    = []    # .rsvp filenames in BOOKS_DIR
        self._reader_book     = None  # currently loaded filename
        self._reader_title    = ""
        self._reader_words    = []    # flat word list from parsed .rsvp
        self._reader_chapters = []    # [(chapter_title, start_word_index)]
        self._reader_pos      = 0     # current word index
        self._reader_wpm      = 250
        self._reader_playing  = False
        self._reader_last_adv = 0.0   # time.time() of last word advance

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

        elif self.screen == BOOK_SELECT:
            self.display.draw_book_select(self._reader_books, self.selected)

        elif self.screen == READER:
            # Advance word if playing and enough time has elapsed
            if self._reader_playing and self._reader_words:
                interval = 60.0 / self._reader_wpm
                now = time.time()
                if now - self._reader_last_adv >= interval:
                    self._reader_pos += 1
                    self._reader_last_adv = now
                    if self._reader_pos >= len(self._reader_words):
                        self._reader_pos = len(self._reader_words) - 1
                        self._reader_playing = False  # finished
            word = self._reader_words[self._reader_pos] if self._reader_words else ""
            pct  = int(100 * self._reader_pos / max(1, len(self._reader_words) - 1))
            self.display.draw_reader(
                word=word,
                chapter=self._current_chapter_title(),
                wpm=self._reader_wpm,
                playing=self._reader_playing,
                progress_pct=pct,
            )

        elif self.screen == USB_MODE:
            storage_active = self._svc("usb-storage") == "active"
            tether_active  = self._svc("usb-tether")  == "active"
            items = [
                "Storage Mode" + (" [ON]"  if storage_active else ""),
                "Tether Mode"  + (" [ON]"  if tether_active  else ""),
            ]
            self.display.draw_wifi_toolkit(items, self.selected)

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
        if self.screen == READER and self._reader_playing:
            # Wake up just in time for the next word advance
            remaining = max(0.02, (60.0 / self._reader_wpm) - (time.time() - self._reader_last_adv))
            timeout = remaining
        elif self.screen in (HOME, ABOUT):
            timeout = 0.1
        else:
            timeout = 0.4

        event = self.input.get_event(timeout=timeout)

        if self.stop_event.is_set() or event is None:
            return

        # Reader consumes all input so joystick axes aren't hijacked
        if self.screen == READER:
            self._handle_reader_input(event)
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
        if self.screen == USB_MODE:
            return len(self._usb_items)
        if self.screen == BOOK_SELECT:
            return len(self._reader_books)
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
                "USB Mode":     USB_MODE,
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
            if label == "Library":
                self._reader_books = self._load_books()
                if not self._reader_books:
                    self.display.draw_status(["No books", "Add .rsvp files"])
                    self.input.get_event(timeout=2)
                else:
                    self._goto(BOOK_SELECT)
            elif label == "Service Status":
                status = self._svc("rsvp")
                line = "Active" if status == "active" else "Off"
                self.display.draw_status(["RSVP Reader", line])
                self.input.get_event(timeout=2)
            else:
                self._placeholder_title = label
                self._goto(PLACEHOLDER)

        elif self.screen == BOOK_SELECT:
            filename = self._reader_books[self.selected]
            self.display.draw_status(["Loading...", filename[:14]])
            try:
                title, words, chapters = self._load_book(filename)
                self._reader_book     = filename
                self._reader_title    = title
                self._reader_words    = words
                self._reader_chapters = chapters
                prog = self._load_progress()
                saved = prog.get(filename, 0)
                self._reader_pos     = min(saved, max(0, len(words) - 1))
                self._reader_playing  = False
                self._reader_last_adv = time.time()
                self._goto(READER)
            except Exception as e:
                self.display.draw_status(["Load failed", str(e)[:14]])
                self.input.get_event(timeout=2)

        elif self.screen == USB_MODE:
            label = self._usb_items[self.selected]
            svc   = "usb-storage" if label == "Storage Mode" else "usb-tether"
            self.display.draw_status(["Switching...", label])
            self.services.start(svc)   # Conflicts= stops the other automatically
            time.sleep(1.5)
            status = self._svc(svc)
            line   = "Active" if status == "active" else "Failed"
            self.display.draw_status([label, line])
            self.input.get_event(timeout=2)

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
        elif self.screen == BOOK_SELECT:
            self._goto(RSVP_READER)
        elif self.screen in (PIHOLE, WIREGUARD, WIFI_KIT, RSVP_READER, USB_MODE, ABOUT, DASHBOARD, PLACEHOLDER, SETTINGS):
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
            ("USB Mode",     "Tether" if self._svc("usb-tether") == "active" else "Storage", CYAN),
            ("Dashboard",    "",      CYAN),
            ("Settings",     "",      CYAN),
            ("About",        "",      CYAN),
        ]

    # ── Reader helpers ────────────────────────────────────────────────────────

    def _load_books(self):
        try:
            if not os.path.isdir(BOOKS_DIR):
                return []
            return sorted(f for f in os.listdir(BOOKS_DIR) if f.endswith(".rsvp"))
        except OSError:
            return []

    def _load_book(self, filename):
        """Parse a .rsvp file into (title, flat_word_list, chapter_index).
        chapter_index = [(chapter_title, start_word_index)]."""
        path = os.path.join(BOOKS_DIR, filename)
        with open(path, encoding="utf-8") as f:
            text = f.read()

        words    = []
        chapters = []
        title    = filename[:-5] if filename.endswith(".rsvp") else filename

        for line in text.splitlines():
            line = line.strip()
            if line.startswith("@title "):
                title = line[7:]
            elif line.startswith("@chapter "):
                chapters.append((line[9:], len(words)))
            elif line.startswith("@"):
                continue  # @rsvp, @author, @source, @para — skip
            elif line:
                words.append(line)

        if not chapters:
            chapters = [("Book", 0)]

        return title, words, chapters

    def _load_progress(self):
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_progress(self):
        if not self._reader_book:
            return
        try:
            prog = self._load_progress()
            prog[self._reader_book] = self._reader_pos
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(prog, f)
        except OSError:
            pass

    def _current_chapter_index(self):
        for i in range(len(self._reader_chapters) - 1, -1, -1):
            if self._reader_pos >= self._reader_chapters[i][1]:
                return i
        return 0

    def _current_chapter_title(self):
        if not self._reader_chapters:
            return ""
        return self._reader_chapters[self._current_chapter_index()][0]

    def _next_chapter(self):
        ci = self._current_chapter_index()
        if ci + 1 < len(self._reader_chapters):
            self._reader_pos      = self._reader_chapters[ci + 1][1]
            self._reader_last_adv = time.time()

    def _prev_chapter(self):
        ci = self._current_chapter_index()
        if ci > 0:
            self._reader_pos = self._reader_chapters[ci - 1][1]
        else:
            self._reader_pos = 0
        self._reader_last_adv = time.time()

    def _handle_reader_input(self, event):
        if event in (InputEvent.JOY_PRESS, InputEvent.KEY1):
            self._reader_playing  = not self._reader_playing
            self._reader_last_adv = time.time()
        elif event == InputEvent.JOY_UP:
            self._reader_wpm = min(self._reader_wpm + 25, 1000)
        elif event == InputEvent.JOY_DOWN:
            self._reader_wpm = max(self._reader_wpm - 25, 50)
        elif event == InputEvent.JOY_RIGHT:
            self._next_chapter()
        elif event == InputEvent.JOY_LEFT:
            self._prev_chapter()
        elif event == InputEvent.KEY3:
            self._reader_playing = False
            self._save_progress()
            self._goto(BOOK_SELECT)

    def _cleanup(self):
        try:
            self.input.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    launcher = Launcher()
    launcher.run()
