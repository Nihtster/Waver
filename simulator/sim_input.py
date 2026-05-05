#!/usr/bin/env python3
"""
Keyboard input backend for the WAVER simulator.
Processes pygame key events and maps them to InputEvent values.

Key bindings:
  ↑ / ↓         → JOY_UP / JOY_DOWN
  → / Enter      → JOY_PRESS (select)
  ← / Escape     → KEY3 (back)
  K              → KEY1 (confirm)
  L              → KEY2 (dashboard shortcut)
  F2             → force hot-reload
  Q              → quit
"""

import time
import pygame
from collections import deque

# InputEvent imported at call time to support hot-reload without circular refs
_EVENTS = None

def _get_events():
    global _EVENTS
    if _EVENTS is None:
        from input_manager import InputEvent
        _EVENTS = InputEvent
    return _EVENTS


def _build_key_map():
    IE = _get_events()
    return {
        pygame.K_UP:     IE.JOY_UP,
        pygame.K_DOWN:   IE.JOY_DOWN,
        pygame.K_LEFT:   IE.JOY_LEFT,
        pygame.K_RIGHT:  IE.JOY_RIGHT,
        pygame.K_RETURN: IE.JOY_PRESS,
        pygame.K_SPACE:  IE.JOY_PRESS,
        pygame.K_k:      IE.KEY1,
        pygame.K_l:      IE.KEY2,
        pygame.K_h:      IE.KEY3,      # back (shortcut to HOME with repeated presses)
        pygame.K_m:      IE.KEY3,
        pygame.K_ESCAPE: IE.KEY3,
    }


class SimInput:
    """
    Drop-in input backend for InputManager.
    Implements .get_event(timeout) and .cleanup().
    """

    def __init__(self, stop_event):
        self.stop_event     = stop_event
        self.event_queue    = deque(maxlen=20)
        self.quit_requested = False
        self._key_map       = None   # built lazily after pygame init

    def get_event(self, timeout=None):
        """
        Block until an InputEvent is available, stop_event fires, or timeout.
        Processes pygame events inline (must be called from the main thread).
        """
        if self._key_map is None:
            self._key_map = _build_key_map()

        start = time.time()

        while not self.stop_event.is_set():
            for pg_event in pygame.event.get():
                self._handle_pg_event(pg_event)

            if self.event_queue:
                return self.event_queue.popleft()

            if timeout is not None and (time.time() - start) >= timeout:
                return None

            time.sleep(0.016)   # ~60 fps polling cadence

        return None

    def cleanup(self):
        pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _handle_pg_event(self, pg_event):
        if pg_event.type == pygame.QUIT:
            self.quit_requested = True
            self.stop_event.set()
            return

        if pg_event.type != pygame.KEYDOWN:
            return

        key = pg_event.key

        if key == pygame.K_q:
            self.quit_requested = True
            self.stop_event.set()
            return

        if key == pygame.K_F2:
            # Force hot-reload without quitting
            self.stop_event.set()
            return

        mapped = self._key_map.get(key)
        if mapped is not None:
            self.event_queue.append(mapped)
