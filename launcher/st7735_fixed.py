#!/usr/bin/env python3
"""
ST7735S display driver based directly on Waveshare's official code.
Bypasses luma's display method entirely.

Key offsets for Waveshare 1.44" LCD HAT (128x128):
  LCD_X_ADJUST = 1  (column offset)
  LCD_Y_ADJUST = 2  (row offset)

These are applied on every draw call to account for the ST7735S
controller's internal 132x162 memory vs the physical 128x128 display.
"""

import spidev
import RPi.GPIO as GPIO
import numpy as np
from PIL import Image
import time

# Pin definitions (BCM)
DC_PIN  = 25
RST_PIN = 27
BL_PIN  = 24

# Waveshare 1.44" offsets (discovered through testing)
LCD_X_ADJUST = 1
LCD_Y_ADJUST = 2
LCD_WIDTH    = 128
LCD_HEIGHT   = 128


class ST7735Fixed:
    def __init__(self):
        # GPIO already initialized by InputManager
        GPIO.setup(DC_PIN,  GPIO.OUT)
        GPIO.setup(RST_PIN, GPIO.OUT)
        GPIO.setup(BL_PIN,  GPIO.OUT)

        # SPI
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 40000000
        self.spi.mode = 0

        self.width  = LCD_WIDTH
        self.height = LCD_HEIGHT

        # Turn on backlight
        GPIO.output(BL_PIN, GPIO.HIGH)

        # Initialize display
        self._reset()
        self._init_registers()
        self._set_scan_direction()
        time.sleep(0.2)

        # Sleep out
        self._write_reg(0x11)
        time.sleep(0.12)

        # Display on
        self._write_reg(0x29)

        print("✓ ST7735Fixed initialized")

    def _write_reg(self, reg):
        GPIO.output(DC_PIN, GPIO.LOW)
        self.spi.writebytes([reg])

    def _write_data(self, data):
        GPIO.output(DC_PIN, GPIO.HIGH)
        if isinstance(data, int):
            self.spi.writebytes([data])
        else:
            for i in range(0, len(data), 4096):
                self.spi.writebytes(list(data[i:i+4096]))

    def _reset(self):
        GPIO.output(RST_PIN, GPIO.HIGH)
        time.sleep(0.01)
        GPIO.output(RST_PIN, GPIO.LOW)
        time.sleep(0.01)
        GPIO.output(RST_PIN, GPIO.HIGH)
        time.sleep(0.01)

    def _init_registers(self):
        # Frame rate
        self._write_reg(0xB1)
        self._write_data(0x01)
        self._write_data(0x2C)
        self._write_data(0x2D)

        self._write_reg(0xB2)
        self._write_data(0x01)
        self._write_data(0x2C)
        self._write_data(0x2D)

        self._write_reg(0xB3)
        self._write_data(0x01)
        self._write_data(0x2C)
        self._write_data(0x2D)
        self._write_data(0x01)
        self._write_data(0x2C)
        self._write_data(0x2D)

        # Column inversion
        self._write_reg(0xB4)
        self._write_data(0x07)

        # Power sequence
        self._write_reg(0xC0)
        self._write_data(0xA2)
        self._write_data(0x02)
        self._write_data(0x84)
        self._write_reg(0xC1)
        self._write_data(0xC5)
        self._write_reg(0xC2)
        self._write_data(0x0A)
        self._write_data(0x00)
        self._write_reg(0xC3)
        self._write_data(0x8A)
        self._write_data(0x2A)
        self._write_reg(0xC4)
        self._write_data(0x8A)
        self._write_data(0xEE)

        # VCOM
        self._write_reg(0xC5)
        self._write_data(0x0E)

        # Gamma
        self._write_reg(0xe0)
        for val in [0x0f, 0x1a, 0x0f, 0x18, 0x2f, 0x28, 0x20, 0x22,
                    0x1f, 0x1b, 0x23, 0x37, 0x00, 0x07, 0x02, 0x10]:
            self._write_data(val)

        self._write_reg(0xe1)
        for val in [0x0f, 0x1b, 0x0f, 0x17, 0x33, 0x2c, 0x29, 0x2e,
                    0x30, 0x30, 0x39, 0x3f, 0x00, 0x07, 0x03, 0x10]:
            self._write_data(val)

        # Enable test command
        self._write_reg(0xF0)
        self._write_data(0x01)

        # Disable ram power save mode
        self._write_reg(0xF6)
        self._write_data(0x00)

        # 65k mode (RGB565)
        self._write_reg(0x3A)
        self._write_data(0x05)

    def _set_scan_direction(self):
        # U2D_R2L scan direction (matches Waveshare default)
        self._write_reg(0x36)
        self._write_data(0x60 | 0x08)  # 0x08 = RGB color filter

    def _set_window(self, x0, y0, x1, y1):
        """Set display window with Waveshare offsets applied"""
        # Column address set
        self._write_reg(0x2A)
        self._write_data(0x00)
        self._write_data((x0 & 0xFF) + LCD_X_ADJUST)
        self._write_data(0x00)
        self._write_data(((x1 - 1) & 0xFF) + LCD_X_ADJUST)

        # Row address set
        self._write_reg(0x2B)
        self._write_data(0x00)
        self._write_data((y0 & 0xFF) + LCD_Y_ADJUST)
        self._write_data(0x00)
        self._write_data(((y1 - 1) & 0xFF) + LCD_Y_ADJUST)

        # Memory write
        self._write_reg(0x2C)

    def display(self, image):
        """Display a PIL Image on the screen"""
        self._set_window(0, 0, self.width, self.height)

        img = image.convert("RGB")
        img_array = np.asarray(img)

        r = (img_array[:, :, 0] & 0xF8).astype(np.uint16) << 8
        g = (img_array[:, :, 1] & 0xFC).astype(np.uint16) << 3
        b = (img_array[:, :, 2] >> 3).astype(np.uint16)

        rgb565 = (r | g | b).flatten()

        byte_data = np.zeros(len(rgb565) * 2, dtype=np.uint8)
        byte_data[0::2] = (rgb565 >> 8) & 0xFF
        byte_data[1::2] = rgb565 & 0xFF

        self._write_data(byte_data.tolist())

    def clear(self, color=(0, 0, 0)):
        """Clear display to a solid color"""
        img = Image.new("RGB", (self.width, self.height), color)
        self.display(img)

    def cleanup(self):
        """Clean up SPI"""
        self.spi.close()
