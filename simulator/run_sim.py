#!/usr/bin/env python3
"""
WAVER Simulator — local dev with hot reload
Usage: python simulator/run_sim.py

Every time you save a file in launcher/, the simulator automatically
reloads the launcher modules and restarts the UI. The pygame window
stays open throughout.

Dependencies (install once):
    pip install pygame watchdog pillow
"""

import os
import sys
import threading
import importlib

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER_DIR = os.path.join(ROOT, "launcher")
SIM_DIR      = os.path.join(ROOT, "simulator")

sys.path.insert(0, LAUNCHER_DIR)
sys.path.insert(0, SIM_DIR)

# ── Window geometry ───────────────────────────────────────────────────────────
# SCALE=1 matches the physical 1.44" size on a Retina Mac (2× physical pixels
# per logical pixel ≈ 1.3–1.4" rendered size). Increase to 2 or 3 if needed.
SCALE    = 1
BEZEL    = 8          # tight bezel around the LCD area
HINTS_H  = 24         # space below LCD for key-binding hints
WIN_W    = 128 * SCALE + BEZEL * 2
WIN_H    = 128 * SCALE + BEZEL * 2 + HINTS_H

# ── Launcher module names to unload on each hot-reload ───────────────────────
_LAUNCHER_MODS = [
    "launcher",
    "display_manager",
    "input_manager",
    "service_manager",
    "network_info",
]


def _unload_launcher_modules():
    for mod in _LAUNCHER_MODS:
        sys.modules.pop(mod, None)


# ── Watchdog file-change observer ─────────────────────────────────────────────

def _start_watcher(watch_path, stop_event):
    """Watch launcher/ for .py changes; fires stop_event on any save."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("[sim] watchdog not installed — hot reload disabled")
        print("[sim]   pip install watchdog")
        return None

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if not event.is_directory and event.src_path.endswith(".py"):
                fname = os.path.basename(event.src_path)
                print(f"[sim] changed: {fname} — reloading")
                stop_event.set()

    observer = Observer()
    observer.schedule(_Handler(), watch_path, recursive=False)
    observer.start()
    return observer


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import pygame

    pygame.init()
    pygame.display.set_caption("WAVER Simulator  •  1.44\" 128×128")
    window = pygame.display.set_mode((WIN_W, WIN_H))

    # Load simulator backends (never unloaded / reloaded)
    from sim_display   import SimDisplay
    from sim_input     import SimInput
    from mock_services import MockServiceManager
    from mock_network  import mock_get_network
    import mock_updater

    sim_display = SimDisplay(window, scale=SCALE, bezel=BEZEL)
    mock_svc    = MockServiceManager()   # persists state across hot-reloads

    print(f"[sim] WAVER simulator starting  (window {WIN_W}×{WIN_H})")
    print(f"[sim] watching: {LAUNCHER_DIR}")
    print()

    while True:
        stop_event = threading.Event()
        sim_input  = SimInput(stop_event)

        # Start file watcher for this iteration
        observer = _start_watcher(LAUNCHER_DIR, stop_event)

        # Fresh import of launcher modules
        _unload_launcher_modules()
        from launcher import Launcher  # noqa: PLC0415

        sim_display.show_reload_flash()

        app = Launcher(
            display_backend=sim_display,
            input_backend=sim_input,
            service_backend=mock_svc,
            network_fn=mock_get_network,
            updater=mock_updater,
            stop_event=stop_event,
        )

        try:
            app.run()
        except SystemExit:
            sim_input.quit_requested = True
        finally:
            if observer:
                observer.stop()
                observer.join(timeout=1)

        if sim_input.quit_requested:
            print("[sim] quit")
            break

        # Brief pause so watchdog doesn't fire again immediately after a save
        import time
        time.sleep(0.15)

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
