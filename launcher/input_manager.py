#!/usr/bin/env python3

import time
from enum import Enum
from collections import deque
import threading


class InputEvent(Enum):
    KEY1      = "key1"       # top button / confirm
    KEY2      = "key2"       # middle button / dashboard
    KEY3      = "key3"       # bottom button / back
    JOY_UP    = "joy_up"
    JOY_DOWN  = "joy_down"
    JOY_LEFT  = "joy_left"
    JOY_RIGHT = "joy_right"
    JOY_PRESS = "joy_press"


class InputManager:
    def __init__(self, backend=None):
        if backend is not None:
            self._backend = backend
            self._mode = "sim"
            print("✓ Input manager initialized (simulator)")
            return

        self._mode = "hardware"
        self._backend = None

        import RPi.GPIO as GPIO
        self._GPIO = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Pin mapping confirmed via gpio_scan.py — not from Waveshare docs
        self.pins = {
            InputEvent.KEY1:      21,
            InputEvent.KEY2:      20,
            InputEvent.KEY3:      16,
            InputEvent.JOY_UP:     6,
            InputEvent.JOY_DOWN:  19,
            InputEvent.JOY_LEFT:   5,
            InputEvent.JOY_RIGHT: 26,
            InputEvent.JOY_PRESS: 13,
        }

        for pin in self.pins.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.event_queue     = deque(maxlen=10)
        self.last_event_time = {}
        self.debounce_time   = 0.2
        self.running         = True

        self._thread = threading.Thread(target=self._poll_inputs, daemon=True)
        self._thread.start()
        print("✓ Input manager initialized (hardware)")

    def _poll_inputs(self):
        while self.running:
            now = time.time()
            for event, pin in self.pins.items():
                if self._GPIO.input(pin) == self._GPIO.LOW:
                    last = self.last_event_time.get(event, 0)
                    if (now - last) > self.debounce_time:
                        self.event_queue.append(event)
                        self.last_event_time[event] = now
            time.sleep(0.05)

    def get_event(self, timeout=None):
        if self._mode == "sim":
            return self._backend.get_event(timeout)

        start = time.time()
        while self.running:
            if self.event_queue:
                return self.event_queue.popleft()
            if timeout is not None and (time.time() - start) > timeout:
                return None
            time.sleep(0.05)
        return None

    def cleanup(self):
        if self._mode == "hardware":
            self.running = False
            self._GPIO.cleanup()
        elif self._mode == "sim" and hasattr(self._backend, "cleanup"):
            self._backend.cleanup()
