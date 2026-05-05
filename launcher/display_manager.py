#!/usr/bin/env python3
"""
Display manager for SwissPI launcher
Uses custom ST7735Fixed driver based on Waveshare official code
"""

from st7735_fixed import ST7735Fixed
from PIL import Image, ImageDraw
import threading

class DisplayManager:
    def __init__(self):
        try:
            self.device = ST7735Fixed()
            print("✓ Display manager initialized")
        except Exception as e:
            print(f"✗ Display init failed: {e}")
            raise

        self.width  = 128
        self.height = 128
        self.lock   = threading.Lock()

    def clear(self):
        with self.lock:
            self.device.clear()

    def draw_menu(self, title, items, selected_index=0, status_dict=None):
        with self.lock:
            img  = Image.new("RGB", (self.width, self.height), color="black")
            draw = ImageDraw.Draw(img)

            # Title
            draw.text((5, 5), title, fill="cyan")
            draw.line([(0, 18), (127, 18)], fill="white")

            # Items
            y_pos = 25
            for i, item in enumerate(items):
                color  = "green" if i == selected_index else "white"
                prefix = "> " if i == selected_index else "  "

                status_text = ""
                if status_dict and item in status_dict:
                    status_text = f" {status_dict[item]}"

                display_text = f"{prefix}{item}{status_text}"[:20]
                draw.text((5, y_pos), display_text, fill=color)
                y_pos += 20

            self.device.display(img)

    def draw_status(self, lines):
        with self.lock:
            img  = Image.new("RGB", (self.width, self.height), color="black")
            draw = ImageDraw.Draw(img)

            y_pos = 5
            for line in lines:
                draw.text((5, y_pos), line, fill="white")
                y_pos += 15

            self.device.display(img)

    def draw_text(self, text, x=10, y=10, color="white"):
        with self.lock:
            img  = Image.new("RGB", (self.width, self.height), color="black")
            draw = ImageDraw.Draw(img)
            draw.text((x, y), text, fill=color)
            self.device.display(img)
