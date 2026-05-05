#!/usr/bin/env python3
"""
Input manager for SwissPI launcher
Handles button and joystick input for Waveshare 1.44" LCD HAT
"""

import RPi.GPIO as GPIO
import time
from enum import Enum
from collections import deque
import threading


class InputEvent(Enum):
    KEY1      = "key1"
    KEY2      = "key2"
    KEY3      = "key3"
    JOY_UP    = "joy_up"
    JOY_DOWN  = "joy_down"
    JOY_LEFT  = "joy_left"
    JOY_RIGHT = "joy_right"
    JOY_PRESS = "joy_press"


class InputManager:
    def __init__(self):
        """Initialize GPIO for buttons and joystick"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Pin mapping confirmed via gpio_scan.py testing
        self.pins = {
            InputEvent.KEY1:      21,   # Top button
            InputEvent.KEY2:      20,   # Middle button
            InputEvent.KEY3:      16,   # Bottom button
            InputEvent.JOY_UP:     6,   # Joystick up
            InputEvent.JOY_DOWN:  19,   # Joystick down
            InputEvent.JOY_LEFT:   5,   # Joystick left
            InputEvent.JOY_RIGHT: 26,   # Joystick right
            InputEvent.JOY_PRESS: 13,   # Joystick center press
        }

        for event, pin in self.pins.items():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.event_queue   = deque(maxlen=10)
        self.last_event_time = {}
        self.debounce_time = 0.2  # 200ms debounce

        self.running = True
        self.input_thread = threading.Thread(target=self._poll_inputs, daemon=True)
        self.input_thread.start()

        print("✓ Input manager initialized")

    def _poll_inputs(self):
        """Poll inputs in background thread"""
        while self.running:
            current_time = time.time()
            for event, pin in self.pins.items():
                if GPIO.input(pin) == GPIO.LOW:
                    if event not in self.last_event_time or \
                       (current_time - self.last_event_time[event]) > self.debounce_time:
                        self.event_queue.append(event)
                        self.last_event_time[event] = current_time
            time.sleep(0.05)

    def get_event(self, timeout=None):
        """
        Get next input event.
        timeout: max seconds to wait (None = wait forever)
        Returns InputEvent or None on timeout.
        """
        start_time = time.time()
        while self.running:
            if self.event_queue:
                return self.event_queue.popleft()
            if timeout and (time.time() - start_time) > timeout:
                return None
            time.sleep(0.05)
        return None

    def cleanup(self):
        """Clean up GPIO"""
        self.running = False
        GPIO.cleanup()
