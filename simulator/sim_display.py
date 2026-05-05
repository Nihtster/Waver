#!/usr/bin/env python3
"""
Pygame display backend for the WAVER simulator.
Renders the 128×128 LCD scaled up in a desktop window.
"""

import time
import pygame
from PIL import Image

BEZEL_BG     = (12, 12, 18)
BEZEL_BORDER = (38, 38, 50)
HINT_COLOR   = (70, 70, 85)

HINTS = [
    ("↑ ↓",   "Navigate"),
    ("→ / Enter", "Select"),
    ("← / Esc",   "Back"),
    ("F2",    "Hot-reload"),
    ("Q",     "Quit"),
]


class SimDisplay:
    """
    Drop-in display backend for DisplayManager.
    Implements .display(pil_image) and .clear().
    """

    def __init__(self, surface, scale: int = 4, bezel: int = 24):
        self.surface = surface
        self.scale   = scale
        self.bezel   = bezel
        self.lcd_x   = bezel
        self.lcd_y   = bezel
        self.width   = 128
        self.height  = 128
        self._hints_surf = self._build_hints_surface()

        # Draw blank bezel on startup
        self.surface.fill(BEZEL_BG)
        pygame.display.flip()

    # ── Public API (matches ST7735Fixed interface) ────────────────────────────

    def display(self, pil_image):
        """Blit a PIL Image to the simulator window."""
        img    = pil_image.convert("RGB")
        scaled = img.resize(
            (self.width * self.scale, self.height * self.scale),
            Image.NEAREST,
        )
        pg_surf = pygame.image.fromstring(scaled.tobytes(), scaled.size, "RGB")

        self.surface.fill(BEZEL_BG)
        self._draw_hints()
        self.surface.blit(pg_surf, (self.lcd_x, self.lcd_y))
        self._draw_border()
        pygame.display.flip()

    def clear(self, color=(0, 0, 0)):
        blank = Image.new("RGB", (128, 128), color)
        self.display(blank)

    # ── Visual extras ─────────────────────────────────────────────────────────

    def show_reload_flash(self):
        """Brief "Reloading…" overlay between hot-reloads."""
        from PIL import ImageDraw, ImageFont
        img  = Image.new("RGB", (128, 128), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default(size=9)
        draw.text((14, 55), "Hot reloading...", font=font, fill=(0, 229, 255))
        self.display(img)
        time.sleep(0.25)

    # ── Internal drawing ──────────────────────────────────────────────────────

    def _draw_border(self):
        rect = pygame.Rect(
            self.lcd_x - 1,
            self.lcd_y - 1,
            self.width  * self.scale + 2,
            self.height * self.scale + 2,
        )
        pygame.draw.rect(self.surface, BEZEL_BORDER, rect, 1)

    def _build_hints_surface(self):
        """Render key hints as a compact PIL image — avoids pygame.font (Python 3.14 compat)."""
        from PIL import Image as PILImage, ImageDraw, ImageFont
        w = self.width * self.scale + self.bezel * 2
        h = 20
        img  = PILImage.new("RGB", (w, h), (12, 12, 18))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default(size=8)
        line = "↑↓ nav  → select  ←/Esc back  F2 reload  Q quit"
        draw.text((0, 5), line, font=font, fill=(65, 65, 80))
        return pygame.image.fromstring(img.tobytes(), img.size, "RGB")

    def _draw_hints(self):
        hints_y = self.lcd_y + self.height * self.scale + 4
        self.surface.blit(self._hints_surf, (self.lcd_x, hints_y))
