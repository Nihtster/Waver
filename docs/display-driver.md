# Display Driver

A custom raw-SPI driver for the ST7735S controller on the Waveshare 1.44"
LCD HAT. Source: [launcher/st7735_fixed.py](../launcher/st7735_fixed.py).

---

## Why a custom driver

The ST7735S has 132×162 pixels of internal RAM, but the physical panel is
only 128×128. The visible region is offset inside that RAM, so any draw
sent to (0,0) appears at the wrong place — and the unused columns/rows
show up as garbage strips ("glitch lines") on the edges.

The fix is to apply column and row offsets when setting the draw window.

`luma.lcd` was the obvious off-the-shelf choice but it does **not** expose
the X/Y offset parameters needed for the ST7735S. `adafruit-circuitpython-st7735`
left the screen white — incompatible with this revision of the HAT.

So the driver is written directly against `spidev` and `RPi.GPIO`, modeled
on Waveshare's official Python demo code.

---

## Pin map (BCM)

```python
DC_PIN  = 25   # data/command select
RST_PIN = 27   # reset
BL_PIN  = 24   # backlight
```

SPI uses the standard CE0 channel:

| Signal | GPIO |
|--------|------|
| MOSI   | 10   |
| SCLK   | 11   |
| CS     | 8    |

> GPIO 24 (backlight) reads LOW at boot — it's pulled high by the HAT
> hardware, not by software. Don't be misled by `gpio_scan.py` showing it
> low before the driver runs.

---

## Offsets

```python
LCD_X_ADJUST = 1   # column offset
LCD_Y_ADJUST = 2   # row offset
```

These values are revision-specific. The original build used
`LCD_X_ADJUST = 2`; the current hardware needs `1`. If glitch lines reappear
after a reinstall or hardware swap, sweep `LCD_X_ADJUST` through 0–4 with
the screen filled to a single colour and pick the value with no edge
artefacts.

The offsets are applied on **every** call to `_set_window` — not just once
at init. This matters because each frame re-sets the draw window, and the
ST7735 forgets any previous window state.

```python
self._write_data((x0 & 0xFF) + LCD_X_ADJUST)
self._write_data(((x1 - 1) & 0xFF) + LCD_X_ADJUST)
```

See [st7735_fixed.py:159](../launcher/st7735_fixed.py:159).

---

## Init sequence

`_init_registers` writes the canonical Waveshare init blob:

| Register | Purpose                                        |
|----------|------------------------------------------------|
| `0xB1–B3`| Frame rate (normal / idle / partial modes)     |
| `0xB4`   | Column inversion                               |
| `0xC0–C5`| Power sequence and VCOM                        |
| `0xE0`   | Positive gamma                                 |
| `0xE1`   | Negative gamma                                 |
| `0xF0`   | Enable test command                            |
| `0xF6`   | Disable RAM power-save                         |
| `0x3A`   | Pixel format → 0x05 = RGB565                   |
| `0x36`   | Memory access (scan direction) → `0x60 \| 0x08`|
| `0x11`   | Sleep out                                      |
| `0x29`   | Display on                                     |

Don't tune these in isolation — they are coupled. If you must change them,
copy a known-good sequence from a working Waveshare example, don't compose
from scratch.

---

## Draw path

`display(image)` is the only public draw method. It:

1. Sets the window to (0, 0, 128, 128) with offsets.
2. Converts a PIL `RGB` image to RGB565 via numpy:
   - R: top 5 bits at bit 11
   - G: top 6 bits at bit 5
   - B: top 5 bits at bit 0
3. Splits each 16-bit pixel into two bytes and flushes to SPI.

Big-endian byte order, 4096-byte chunks (the `spidev` per-call max). The
SPI clock is 40 MHz, which is fast enough for ~30 fps full-screen.

---

## Hardware quirks

- **Backlight** is just a GPIO; there's no PWM dimming wired up. Drive
  `BL_PIN` HIGH to turn the panel on, LOW to turn it off.
- **Reset pulse** must be high → low → high with at least 10ms between
  edges. Skipping the pulse leaves the controller in a half-initialised
  state where colours are wrong.
- **Sleep-out latency**: after `0x11`, wait at least 120ms before sending
  `0x29` (display on), or the first frame is corrupt.

---

## Testing offsets after a reinstall

```python
from PIL import Image
from st7735_fixed import ST7735Fixed

dev = ST7735Fixed()
dev.display(Image.new("RGB", (128, 128), (255, 0, 0)))
```

If you see thin coloured strips on the left/right edges, decrement
`LCD_X_ADJUST`. Strips on the top/bottom → adjust `LCD_Y_ADJUST`.

---

## What's NOT in this driver

- No partial-update region — every frame is a full 128×128 push.
- No PIL → SPI streaming; the entire RGB565 buffer is built in RAM first.
  Fine on a Pi Zero 2W (32 KB per frame), don't do this on a microcontroller.
- No double-buffering. The DisplayManager threading lock serialises draws,
  which is enough for a 1-writer/1-reader system.
