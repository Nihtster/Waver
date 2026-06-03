#!/usr/bin/env python3

import threading
import math
import time
from PIL import Image, ImageDraw, ImageFont

# ── Palette ───────────────────────────────────────────────────────────────────
BLACK      = (0,   0,   0)
CYAN       = (0,   229, 255)
WHITE      = (255, 255, 255)
GREEN      = (0,   210, 80)
BLUE       = (30,  144, 255)
GRAY       = (100, 100, 110)
RED        = (255, 70,  70)
DARK_CYAN  = (0,   45,  55)
DIM_WHITE  = (170, 170, 180)
DIVIDER    = (35,  35,  45)

WIDTH          = 128
HEIGHT         = 128
ITEMS_PER_PAGE = 3


# ── Font loading ──────────────────────────────────────────────────────────────
# Prefer monospace fonts for the terminal aesthetic. Falls back gracefully
# through proportional TrueType, then Pillow's built-in default.

_FONT_CACHE: dict = {}
_SYSTEM_FONT_PATHS = [
    # Raspberry Pi OS (Bookworm)
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf",
    # macOS (simulator)
    "/System/Library/Fonts/Menlo.ttc",
    "/Library/Fonts/Courier New.ttf",
    # Generic proportional fallbacks
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]

def _font(size: int):
    if size not in _FONT_CACHE:
        for path in _SYSTEM_FONT_PATHS:
            try:
                _FONT_CACHE[size] = ImageFont.truetype(path, size)
                break
            except (IOError, OSError):
                continue
        else:
            _FONT_CACHE[size] = ImageFont.load_default(size=size)
    return _FONT_CACHE[size]


def _text(draw, xy, text, size=11, scale=1, fill=WHITE):
    """
    Crisp text: render into a greyscale buffer, threshold to binary
    (removes antialiasing haze), then paste as a solid colour.
    scale=2 gives pixel-doubled text via NEAREST resize — no blur.
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
    tmp = tmp.point(lambda p: 255 if p >= 48 else 0)

    if scale > 1:
        tmp = tmp.resize((tmp.width * scale, tmp.height * scale), Image.NEAREST)

    colored = Image.new("RGB", tmp.size, fill)
    draw._image.paste(colored, (int(xy[0]), int(xy[1])), tmp)


def _centered_text(draw, y, text, size=11, scale=1, fill=WHITE):
    text = str(text)
    font = _font(size)
    bbox = font.getbbox(text)
    if not bbox or bbox[2] <= bbox[0]:
        return
    w = (bbox[2] - bbox[0]) * scale
    x = max(0, (WIDTH - w) // 2)
    _text(draw, (x, y), text, size=size, scale=scale, fill=fill)


# ── Shared drawing primitives ─────────────────────────────────────────────────

def _status_bar(draw):
    from datetime import datetime
    t = datetime.now().strftime("%H:%M")
    draw.rectangle([(0, 0), (WIDTH - 1, 13)], fill=(8, 8, 12))
    _text(draw, (3, 2), t, size=9, fill=DIM_WHITE)
    _wifi_icon(draw, 119, 0)


def _wifi_icon(draw, cx, cy):
    """3-arc WiFi symbol. cx/cy = centre of the dot at the base."""
    bx, by = cx, cy + 9
    _dot(draw, bx, by, 1, CYAN)
    for r in (3, 5, 7):
        box = [bx - r, by - r, bx + r, by + r]
        draw.arc(box, start=215, end=325, fill=CYAN)


def _divider(draw, y):
    draw.line([(0, y), (WIDTH - 1, y)], fill=DIVIDER)


def _footer(draw, label, y=118):
    _divider(draw, y - 3)
    _text(draw, (4, y), f"> {label}", size=9, fill=CYAN)


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


def _mini_bars(draw, x, y, pct):
    """Rising 5-bar chart for percentage values (20px wide, 11px tall)."""
    heights = (3, 5, 7, 9, 11)
    bottom = y + 11
    for i, h in enumerate(heights):
        col = CYAN if pct >= (i + 1) * 20 else GRAY
        draw.rectangle([x + i * 4, bottom - h, x + i * 4 + 2, bottom], fill=col)


def _page_dots(draw, current_page, total_pages, y=110):
    """Centred row of filled/hollow dots indicating current page."""
    if total_pages <= 1:
        return
    spacing = 9
    total_w  = (total_pages - 1) * spacing
    x_start  = (WIDTH - total_w) // 2
    for i in range(total_pages):
        cx = x_start + i * spacing
        if i == current_page:
            _dot(draw, cx, y, 3, CYAN)
        else:
            draw.ellipse([(cx - 3, y - 3), (cx + 3, y + 3)], outline=GRAY)


def _list_page(items, selected_index):
    """Slice items for the current page.
    Returns (page_items, local_selected, current_page, total_pages)."""
    total = len(items)
    if total == 0:
        return [], 0, 0, 1
    page        = selected_index // ITEMS_PER_PAGE
    total_pages = math.ceil(total / ITEMS_PER_PAGE)
    start       = page * ITEMS_PER_PAGE
    return items[start:start + ITEMS_PER_PAGE], selected_index % ITEMS_PER_PAGE, page, total_pages


def _draw_list(draw, title, page_items, local_sel, page, total_pages, item_fn):
    """
    Shared scaffold for all paginated list screens.
    Layout (px):  0-13 status  14 div  15-28 header  29 div
                  30-104 items (3×25)  105-114 dots  115 div  118 footer
    item_fn(draw, y, label, is_selected) — caller draws row content.
    """
    _status_bar(draw)
    _divider(draw, 14)
    _text(draw, (4, 16), title, size=11, fill=CYAN)
    _divider(draw, 29)

    y = 30
    for i, item in enumerate(page_items):
        selected = (i == local_sel)
        if selected:
            draw.rectangle([(0, y), (WIDTH - 1, y + 24)], fill=DARK_CYAN)
        item_fn(draw, y, item, selected)
        y += 25

    _page_dots(draw, page, total_pages, y=110)


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

            _waveform(draw, x=8, y=16, w=112, h=24, phase=phase)
            _centered_text(draw, 42, "WAVER", size=10, scale=2, fill=CYAN)

            _divider(draw, 65)

            ph_color = GREEN if pihole_status == "active" else GRAY
            _dot(draw, 8, 76, 4, ph_color)
            _text(draw, (18, 67), "Pi-hole", size=11, fill=WHITE)
            _text(draw, (18, 80), "Active" if pihole_status == "active" else "Inactive", size=9, fill=ph_color)

            wg_color = BLUE if wg_status == "active" else GRAY
            _dot(draw, 8, 101, 4, wg_color)
            _text(draw, (18, 92), "WireGuard", size=11, fill=WHITE)
            _text(draw, (18, 105), "Connected" if wg_status == "active" else "Inactive", size=9, fill=wg_color)

            _footer(draw, "Tools")
            self._push(img)

    # ── TOOLS MENU ────────────────────────────────────────────────────────────

    def draw_tools_menu(self, items, selected_index=0):
        """items: list of (label, status_label, dot_color)"""
        with self.lock:
            img, draw = self._frame()
            page_items, local_sel, page, total_pages = _list_page(items, selected_index)

            def _row(draw, y, item, selected):
                label, status, color = item
                text_col = CYAN if selected else WHITE
                _dot(draw, 8, y + 12, 4, color if color else GRAY)
                if status:
                    _text(draw, (18, y + 3),  label,  size=11, fill=text_col)
                    _text(draw, (18, y + 15), status, size=9,
                          fill=(color if color else GRAY) if not selected else CYAN)
                else:
                    _text(draw, (18, y + 7),  label,  size=11, fill=text_col)
                _text(draw, (118, y + 8), ">", size=9, fill=GRAY)

            _draw_list(draw, "TOOLS", page_items, local_sel, page, total_pages, _row)
            _footer(draw, "Back")
            self._push(img)

    # ── PI-HOLE DETAIL ────────────────────────────────────────────────────────

    def draw_pihole(self, status="inactive", blocked_today=0, top_domain=""):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            ph_color = GREEN if status == "active" else GRAY
            _dot(draw, 8, 24, 4, ph_color)
            _text(draw, (18, 16), "Pi-hole", size=11, fill=CYAN)
            _text(draw, (18, 29), "Active" if status == "active" else "Inactive", size=9, fill=ph_color)

            _divider(draw, 42)

            _text(draw, (4, 44), "Blocked Today", size=9, fill=DIM_WHITE)
            _centered_text(draw, 55, f"{blocked_today:,}", size=11, scale=2, fill=WHITE)

            _divider(draw, 80)

            _text(draw, (4, 83), "Top Domain", size=9, fill=DIM_WHITE)
            _text(draw, (4, 96), (top_domain or "N/A")[:15], size=10, fill=WHITE)

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
            _dot(draw, 8, 24, 4, wg_color)
            _text(draw, (18, 16), "WireGuard", size=11, fill=CYAN)
            _text(draw, (18, 29), "Connected" if status == "active" else "Inactive", size=9, fill=wg_color)

            _divider(draw, 42)

            _text(draw, (4, 45), "Endpoint", size=9, fill=DIM_WHITE)
            _text(draw, (4, 57), endpoint or "N/A", size=10, fill=WHITE)

            _divider(draw, 72)

            _text(draw, (4, 75), "Transfer", size=9, fill=DIM_WHITE)
            _text(draw, (4, 88),  f"↓ {rx}", size=10, fill=CYAN)
            _text(draw, (4, 103), f"↑ {tx}", size=10, fill=GREEN)

            action = "Disconnect" if status == "active" else "Connect"
            _footer(draw, action)
            self._push(img)

    # ── HOTSPOT ───────────────────────────────────────────────────────────────

    def draw_hotspot(self, status="inactive", ssid="Waver", password=""):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            h_color = GREEN if status == "active" else GRAY
            _dot(draw, 8, 24, 4, h_color)
            _text(draw, (18, 16), "Hotspot", size=11, fill=CYAN)
            _text(draw, (18, 29), "Active" if status == "active" else "Inactive", size=9, fill=h_color)

            _divider(draw, 42)

            _text(draw, (4, 45), "SSID", size=9, fill=DIM_WHITE)
            _text(draw, (4, 57), (ssid or "Waver")[:17], size=11, fill=WHITE)

            _divider(draw, 72)

            _text(draw, (4, 75), "Password", size=9, fill=DIM_WHITE)
            pw_text = (password or "—")[:17] if password else "—"
            pw_color = WHITE if password else GRAY
            _text(draw, (4, 88), pw_text, size=10, fill=pw_color)

            action = "Stop" if status == "active" else "Start"
            _footer(draw, action)
            self._push(img)

    # ── WIFI SCAN ─────────────────────────────────────────────────────────────

    def draw_wifi_scan(self, networks, selected_index=0):
        with self.lock:
            img, draw = self._frame()
            page_items, local_sel, page, total_pages = _list_page(networks, selected_index)

            def _row(draw, y, item, selected):
                ssid, signal = item
                text_col = CYAN if selected else WHITE
                _text(draw, (4,  y + 7), "~",         size=11, fill=CYAN)
                _text(draw, (16, y + 7), ssid[:11],   size=11, fill=text_col)
                _text(draw, (98, y + 8), str(signal),  size=9, fill=GRAY)

            _draw_list(draw, "WiFi Scan", page_items, local_sel, page, total_pages, _row)
            _footer(draw, "Back")
            self._push(img)

    # ── WIFI TOOLKIT ──────────────────────────────────────────────────────────

    def draw_wifi_toolkit(self, items, selected_index=0):
        with self.lock:
            img, draw = self._frame()
            page_items, local_sel, page, total_pages = _list_page(items, selected_index)

            def _row(draw, y, label, selected):
                text_col = CYAN if selected else WHITE
                _text(draw, (10, y + 7),  label, size=11, fill=text_col)
                _text(draw, (118, y + 8), ">",   size=9,  fill=GRAY)

            _draw_list(draw, "WiFi Toolkit", page_items, local_sel, page, total_pages, _row)
            _footer(draw, "Select")
            self._push(img)

    # ── DASHBOARD ─────────────────────────────────────────────────────────────

    def draw_dashboard(self, cpu=0, mem=0, uptime="", clients=0):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            rows = [
                ("CPU",     f"{cpu}%",    cpu  if isinstance(cpu, int) else 0),
                ("MEM",     f"{mem}%",    mem  if isinstance(mem, int) else 0),
                ("UPTIME",  str(uptime),  None),
                ("CLIENTS", str(clients), None),
            ]

            y = 15
            for label, value, pct in rows:
                draw.rectangle([(2, y), (WIDTH - 3, y + 22)], outline=DIVIDER)
                _text(draw, (6,  y + 6), label, size=9,  fill=DIM_WHITE)
                _text(draw, (56, y + 5), value, size=11, fill=CYAN)
                if pct is not None:
                    _mini_bars(draw, 100, y + 6, int(pct))
                y += 25

            _footer(draw, "Back")
            self._push(img)

    # ── ABOUT ─────────────────────────────────────────────────────────────────

    def draw_about(self):
        with self.lock:
            img, draw = self._frame()
            phase = time.time() * 1.6

            _status_bar(draw)
            _divider(draw, 14)

            _waveform(draw, x=8, y=16, w=112, h=24, phase=phase)
            _centered_text(draw, 43, "WAVER",  size=10, scale=2, fill=CYAN)
            _centered_text(draw, 69, "v1.0.0", size=10, fill=DIM_WHITE)
            _centered_text(draw, 84, "by you", size=9,  fill=GRAY)

            _footer(draw, "Back")
            self._push(img)

    # ── SETTINGS MENU ────────────────────────────────────────────────────────

    def draw_settings(self, items, selected_index=0):
        with self.lock:
            img, draw = self._frame()
            page_items, local_sel, page, total_pages = _list_page(items, selected_index)

            def _row(draw, y, label, selected):
                text_col = CYAN if selected else WHITE
                _text(draw, (10, y + 7),  label, size=11, fill=text_col)
                _text(draw, (118, y + 8), ">",   size=9,  fill=GRAY)

            _draw_list(draw, "Settings", page_items, local_sel, page, total_pages, _row)
            _footer(draw, "Back")
            self._push(img)

    # ── UPDATE STATUS ─────────────────────────────────────────────────────────

    def draw_update_status(self, title, message="", hint=""):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            _text(draw, (4, 16), "Update", size=11, fill=CYAN)
            _divider(draw, 29)

            _text(draw, (4, 42), title, size=11, fill=WHITE)
            if message:
                _text(draw, (4, 58), message, size=9, fill=DIM_WHITE)
            if hint:
                _divider(draw, 100)
                _text(draw, (4, 104), hint, size=9, fill=CYAN)

            self._push(img)

    # ── PLACEHOLDER ───────────────────────────────────────────────────────────

    def draw_placeholder(self, title="Coming Soon"):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            _text(draw, (4, 16), title[:14], size=11, fill=CYAN)
            _divider(draw, 29)

            _text(draw, (10, 55), "Not yet",     size=11, fill=GRAY)
            _text(draw, (10, 71), "implemented", size=11, fill=GRAY)

            _footer(draw, "Back")
            self._push(img)

    # ── GENERIC STATUS ────────────────────────────────────────────────────────

    def draw_status(self, lines):
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            y = 22
            for line in lines:
                _text(draw, (5, y), str(line)[:17], size=11, fill=WHITE)
                y += 18

            self._push(img)

    # ── BOOK SELECT ───────────────────────────────────────────────────────────

    def draw_book_select(self, books, selected_index=0):
        """books: list of .rsvp filenames — strips extension for display."""
        with self.lock:
            img, draw = self._frame()
            page_items, local_sel, page, total_pages = _list_page(books, selected_index)

            def _row(draw, y, filename, selected):
                label    = filename[:-5] if filename.endswith(".rsvp") else filename
                text_col = CYAN if selected else WHITE
                _text(draw, (10,  y + 7),  label[:15], size=11, fill=text_col)
                _text(draw, (118, y + 8),  ">",        size=9,  fill=GRAY)

            _draw_list(draw, "Library", page_items, local_sel, page, total_pages, _row)
            _footer(draw, "Select")
            self._push(img)

    # ── READER ────────────────────────────────────────────────────────────────

    def draw_reader(self, word, chapter, wpm, playing, progress_pct):
        """
        Full-screen RSVP reader.
        Layout (px):
          0-13   status bar
          14     divider
          15-26  chapter name (small, dim)
          27     divider
          28-95  word — large, centered
          96     divider
          97-111 progress% | WPM | play symbol
          112    divider
          113-127 hint bar
        """
        with self.lock:
            img, draw = self._frame()
            _status_bar(draw)
            _divider(draw, 14)

            # Chapter name
            _text(draw, (4, 16), str(chapter)[:17], size=9, fill=DIM_WHITE)
            _divider(draw, 27)

            # Word — adaptive size so it always fits within ~120px width
            word = str(word)
            wlen = len(word)
            if wlen <= 3:
                size, scale = 16, 2
            elif wlen <= 5:
                size, scale = 13, 2
            elif wlen <= 8:
                size, scale = 11, 2
            elif wlen <= 13:
                size, scale = 11, 1
            else:
                size, scale = 9, 1

            # Vertically centre in the word zone (28-95 → midpoint 61)
            word_y = max(28, 61 - (size * scale) // 2)
            _centered_text(draw, word_y, word, size=size, scale=scale, fill=WHITE)

            _divider(draw, 96)

            # Bottom bar: progress | WPM | play/pause symbol
            play_sym = ">" if playing else "||"
            play_col = GREEN if playing else GRAY
            _text(draw, (4,   100), f"{progress_pct}%", size=9, fill=GRAY)
            _centered_text(draw,    100, f"{wpm}wpm",   size=9, fill=CYAN)
            _text(draw, (110, 100), play_sym,            size=9, fill=play_col)

            _divider(draw, 112)
            _text(draw, (4, 115), "< chap  play  chap >", size=8, fill=GRAY)

            self._push(img)

    def clear(self):
        with self.lock:
            self.device.clear()
