#!/usr/bin/env python3

import threading
import math
import time
from PIL import Image, ImageDraw, ImageFont

# ── Palette ───────────────────────────────────────────────────────────────────
BLACK      = (0,   0,   0)
CYAN       = (0,   229, 255)   # #00E5FF — primary accent
WHITE      = (255, 255, 255)
GREEN      = (0,   210, 80)    # active service
BLUE       = (30,  144, 255)   # connected / VPN
GRAY       = (100, 100, 110)   # inactive / secondary
RED        = (255, 70,  70)    # error / failed
DARK_CYAN  = (0,   45,  55)    # selected-item background
DIM_WHITE  = (170, 170, 180)   # secondary text
DIVIDER    = (35,  35,  45)    # subtle divider lines

WIDTH  = 128
HEIGHT = 128


# ── Crisp thin text ───────────────────────────────────────────────────────────
# Strategy: render with Pillow's bundled TrueType (thin strokes) into a
# greyscale buffer, then threshold to snap every pixel to fully-on or
# fully-off. This removes the anti-aliased fringe while preserving the
# lighter weight of TrueType letterforms. For larger text we render at 1×
# then scale up with NEAREST so the result stays pixel-hard at any size.

_FONT_CACHE: dict = {}

def _font(size: int):
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = ImageFont.load_default(size=size)
    return _FONT_CACHE[size]


def _text(draw, xy, text, size=8, scale=1, fill=WHITE):
    """
    Thin, crisp text: TrueType letterforms with AA fringe stripped out.
    size  — point size before any scaling
    scale — integer upscale applied after thresholding (NEAREST, no blur)
    """
    text = str(text)
    font = _font(size)

    bbox = font.getbbox(text)
    if not bbox or bbox[2] <= bbox[0]:
        return
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0

    tmp = Image.new("L", (w + 2, h + 2), 0)
    ImageDraw.Draw(tmp).text((1 - x0, 1 - y0), text, font=font, fill=255)

    # Threshold: pixels whose coverage >= 38 % stay solid, rest drop to 0.
    # Raising this value → thinner strokes; lowering → thicker.
    tmp = tmp.point(lambda p: 255 if p >= 96 else 0)

    if scale > 1:
        tmp = tmp.resize((tmp.width * scale, tmp.height * scale), Image.NEAREST)

    colored = Image.new("RGB", tmp.size, fill)
    draw._image.paste(colored, (int(xy[0]), int(xy[1])), tmp)


# ── Shared drawing primitives ─────────────────────────────────────────────────

def _status_bar(draw):
    from datetime import datetime
    t = datetime.now().strftime("%H:%M")
    draw.rectangle([(0, 0), (WIDTH - 1, 13)], fill=(8, 8, 12))
    _text(draw, (3, 3), t, size=8, fill=DIM_WHITE)
    _wifi_bars(draw, 112, 3)


def _wifi_bars(draw, x, y):
    """Three signal-strength bars — crisp pixel art, no Unicode needed."""
    for i, h in enumerate((4, 6, 8)):
        bx = x + i * 4
        by = y + (8 - h)
        col = CYAN if i < 3 else GRAY
        draw.rectangle([bx, by, bx + 2, y + 8], fill=col)


def _divider(draw, y):
    draw.line([(0, y), (WIDTH - 1, y)], fill=DIVIDER)


def _footer(draw, label, y=116):
    _divider(draw, y - 3)
    _text(draw, (4, y), f"> {label}", size=8, fill=CYAN)


def _waveform(draw, x, y, w, h, phase=0.0, color=CYAN):
    pts = []
    for i in range(w):
        t   = (i / w) * 3.0 * math.pi + phase
        env = math.sin(math.pi * i / w) ** 0.6
        amp = int(math.sin(t) * (h / 2) * env)
        pts.append((x + i, y + h // 2 - amp))
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=color, width=1)


def _dot(draw, cx, cy, r, color):
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=color)


# ── DisplayManager ────────────────────────────────────────────────────────────

class DisplayManager:
    def __init__(self, backend=None):
        if backend is None:
            from st7735_fixed import ST7735Fixed
            self.device = ST7735Fixed()
        else:
            self.device = backend

        self.width  = WIDTH
        self.height = HEIGHT
        self.lock   = threading.Lock()
        print("✓ Display manager initialized")

    def _frame(self):
        img  = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
        draw = ImageDraw.Draw(img)
        return img, draw

    def _push(self, img):
        self.device.display(img)

    # ── HOME ──────────────────────────────────────────────────────────────────

    def draw_home(self, pihole_status="inactive", wg_status="inactive"):
        with self.lock:
            img, draw = self._frame()
            phase = time.time() * 1.6

            _status_bar(draw)
            _divider(draw, 14)

            _waveform(draw, x=8, y=17, w=112, h=28, phase=phase)

            # "WAVER" brand at 2× scale — centered
            _text(draw, (34, 47), "WAVER", size=8, scale=2, fill=CYAN)

            _divider(draw, 67)

            ph_color = GREEN if pihole_status == "active" else GRAY
            _dot(draw, 9, 75, 4, ph_color)
            _text(draw, (18, 70), "Pi-hole", size=8, fill=WHITE)
            _text(draw, (18, 80), "Active" if pihole_status == "active" else "Inactive", size=7, fill=ph_color)

            wg_color = BLUE if wg_status == "active" else GRAY
            _dot(draw, 9, 95, 4, wg_color)
            _text(draw, (18, 90), "WireGuard", size=8, fill=WHITE)
            _text(draw, (18, 100), "Connected" if wg_status == "active" else "Inactive", size=7, fill=wg_color)

            _footer(draw, "Tools")
            self._push(img)

    # ── TOOLS MENU ────────────────────────────────────────────────────────────

    def draw_tools_menu(self, items, selected_index=0):
        """items: list of (label, status_label, dot_color)"""
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            _text(draw, (4, 17), "TOOLS", size=8, fill=CYAN)
            _divider(draw, 28)

            y = 31
            row_h = 13
            for i, (label, status, color) in enumerate(items):
                if i == selected_index:
                    draw.rectangle([(0, y - 1), (WIDTH - 1, y + row_h - 2)], fill=DARK_CYAN)
                    text_col = CYAN
                else:
                    text_col = WHITE

                _dot(draw, 7, y + 5, 3, color if color else GRAY)
                _text(draw, (15, y + 2), label, size=8, fill=text_col)
                _text(draw, (120, y + 2), ">", size=8, fill=GRAY)
                y += row_h

            self._push(img)

    # ── PI-HOLE DETAIL ────────────────────────────────────────────────────────

    def draw_pihole(self, status="inactive", blocked_today=0, top_domain=""):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            ph_color = GREEN if status == "active" else GRAY
            _dot(draw, 8, 22, 4, ph_color)
            _text(draw, (16, 17), "Pi-hole", size=8, fill=CYAN)
            _text(draw, (16, 27), "Active" if status == "active" else "Inactive", size=7, fill=ph_color)

            _divider(draw, 38)

            _text(draw, (4, 41), "Blocked Today", size=7, fill=DIM_WHITE)
            _text(draw, (4, 51), f"{blocked_today:,}", size=8, scale=2, fill=WHITE)

            _divider(draw, 76)

            _text(draw, (4, 79), "Top Domain", size=7, fill=DIM_WHITE)
            _text(draw, (4, 89), (top_domain or "N/A")[:18], size=8, fill=WHITE)

            action = "Disable" if status == "active" else "Enable"
            _footer(draw, action)
            self._push(img)

    # ── WIREGUARD DETAIL ──────────────────────────────────────────────────────

    def draw_wireguard(self, status="inactive", endpoint="", rx="0", tx="0"):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            wg_color = BLUE if status == "active" else GRAY
            _dot(draw, 8, 22, 4, wg_color)
            _text(draw, (16, 17), "WireGuard", size=8, fill=CYAN)
            _text(draw, (16, 27), "Connected" if status == "active" else "Inactive", size=7, fill=wg_color)

            _divider(draw, 38)

            _text(draw, (4, 42), "Endpoint", size=7, fill=DIM_WHITE)
            _text(draw, (4, 52), endpoint or "N/A", size=8, fill=WHITE)

            _divider(draw, 65)

            _text(draw, (4, 69), "Transfer", size=7, fill=DIM_WHITE)
            _text(draw, (4, 80), f"Dn {rx}", size=8, fill=CYAN)
            _text(draw, (4, 92), f"Up {tx}", size=8, fill=GREEN)

            action = "Disconnect" if status == "active" else "Connect"
            _footer(draw, action)
            self._push(img)

    # ── WIFI SCAN ─────────────────────────────────────────────────────────────

    def draw_wifi_scan(self, networks, selected_index=0):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            _text(draw, (4, 17), "WiFi Scan", size=8, fill=CYAN)
            _divider(draw, 28)

            y = 31
            row_h = 14
            for i, (ssid, signal) in enumerate(networks[:5]):
                if i == selected_index:
                    draw.rectangle([(0, y - 1), (WIDTH - 1, y + row_h - 2)], fill=DARK_CYAN)
                    text_col = CYAN
                else:
                    text_col = WHITE

                _text(draw, (3, y + 2), "~", size=8, fill=CYAN)
                _text(draw, (13, y + 2), ssid[:13], size=8, fill=text_col)
                _text(draw, (100, y + 2), str(signal), size=7, fill=GRAY)
                y += row_h

            _footer(draw, "Back")
            self._push(img)

    # ── WIFI TOOLKIT ──────────────────────────────────────────────────────────

    def draw_wifi_toolkit(self, items, selected_index=0):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            _text(draw, (4, 17), "WiFi Toolkit", size=8, fill=CYAN)
            _divider(draw, 28)

            y = 31
            row_h = 15
            for i, label in enumerate(items):
                if i == selected_index:
                    draw.rectangle([(0, y - 1), (WIDTH - 1, y + row_h - 2)], fill=DARK_CYAN)
                    text_col = CYAN
                else:
                    text_col = WHITE
                _text(draw, (8, y + 3), label, size=8, fill=text_col)
                y += row_h

            self._push(img)

    # ── DASHBOARD ─────────────────────────────────────────────────────────────

    def draw_dashboard(self, cpu=0, mem=0, uptime="", clients=0):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            rows = [
                ("CPU",     f"{cpu}%"),
                ("MEM",     f"{mem}%"),
                ("UPTIME",  str(uptime)),
                ("CLIENTS", str(clients)),
            ]

            y = 18
            for label, value in rows:
                draw.rectangle([(2, y), (WIDTH - 3, y + 19)], outline=DIVIDER)
                _text(draw, (6, y + 6), label, size=7, fill=DIM_WHITE)
                _text(draw, (68, y + 6), value, size=8, fill=CYAN)
                y += 23

            _footer(draw, "Back")
            self._push(img)

    # ── ABOUT ─────────────────────────────────────────────────────────────────

    def draw_about(self):
        with self.lock:
            img, draw = self._frame()
            phase = time.time() * 1.6

            _status_bar(draw)
            _divider(draw, 14)

            _waveform(draw, x=8, y=20, w=112, h=24, phase=phase)
            _text(draw, (34, 47), "WAVER", size=8, scale=2, fill=CYAN)
            _text(draw, (46, 67), "v1.0.0", size=7, fill=DIM_WHITE)
            _text(draw, (40, 79), "by you", size=7, fill=GRAY)

            _footer(draw, "Back")
            self._push(img)

    # ── SETTINGS MENU ────────────────────────────────────────────────────────

    def draw_settings(self, items, selected_index=0):
        """items: list of label strings"""
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            _text(draw, (4, 17), "Settings", size=8, fill=CYAN)
            _divider(draw, 28)

            y = 31
            row_h = 15
            for i, label in enumerate(items):
                if i == selected_index:
                    draw.rectangle([(0, y - 1), (WIDTH - 1, y + row_h - 2)], fill=DARK_CYAN)
                    text_col = CYAN
                else:
                    text_col = WHITE
                _text(draw, (8, y + 3), label, size=8, fill=text_col)
                _text(draw, (120, y + 3), ">", size=8, fill=GRAY)
                y += row_h

            self._push(img)

    # ── UPDATE STATUS ─────────────────────────────────────────────────────────

    def draw_update_status(self, title, message="", hint=""):
        """
        Full-screen update progress display.
        title   — primary status line (e.g. "Checking…", "Up to date")
        message — secondary detail line
        hint    — optional bottom prompt (e.g. "SELECT to install")
        """
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            _text(draw, (4, 17), "Update", size=8, fill=CYAN)
            _divider(draw, 28)

            _text(draw, (4, 40), title,   size=8, fill=WHITE)
            if message:
                _text(draw, (4, 54), message, size=7, fill=DIM_WHITE)
            if hint:
                _divider(draw, 100)
                _text(draw, (4, 103), hint, size=7, fill=CYAN)

            self._push(img)

    # ── PLACEHOLDER ───────────────────────────────────────────────────────────

    def draw_placeholder(self, title="Coming Soon"):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            _text(draw, (4, 17), title[:20], size=8, fill=CYAN)
            _divider(draw, 28)
            _text(draw, (10, 52), "Not yet", size=8, fill=GRAY)
            _text(draw, (10, 64), "implemented", size=8, fill=GRAY)

            _footer(draw, "Back")
            self._push(img)

    # ── GENERIC STATUS ────────────────────────────────────────────────────────

    def draw_status(self, lines):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            y = 18
            for line in lines:
                _text(draw, (5, y), str(line)[:21], size=8, fill=WHITE)
                y += 12

            self._push(img)

    def clear(self):
        with self.lock:
            self.device.clear()
