#!/bin/bash
# setup-usb-gadget.sh — one-time USB mass storage gadget setup for Waver.
#
# Configures the Pi Zero 2W's OTG USB port to present a FAT32 image as a
# USB drive to a host PC. Users drag-and-drop source books (.epub/.txt/etc.)
# onto the drive; on unplug the Pi auto-converts them via waver-rsvp.
#
# Run on the Pi (once):
#   sudo bash ~/waver/config/scripts/setup-usb-gadget.sh
#
# A reboot is required after running this script.

set -euo pipefail

IMAGE=/home/cimi/waver/rsvp-books.img
IMAGE_SIZE=2048  # MB — adjust to taste (must fit on your SD card)
BOOKS_DIR=/home/cimi/waver/rsvp-books
# Detect which config.txt the bootloader is actually reading
if [[ -f /boot/config.txt && $(stat -c%s /boot/config.txt) -gt 0 ]]; then
    BOOT_CONFIG=/boot/config.txt        # Bullseye / legacy boot partition
else
    BOOT_CONFIG=/boot/firmware/config.txt  # Bookworm
fi
MODULES_FILE=/etc/modules
SYNC_SCRIPT=/home/cimi/waver/config/scripts/usb-sync.sh
UDEV_RULE=/etc/udev/rules.d/99-waver-usb.rules
SYSTEMD_UNIT=/etc/systemd/system/waver-usb-gadget.service
UNIT_SRC=/home/cimi/waver/config/systemd/waver-usb-gadget.service

# ── 0. Must be root ───────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run as root (sudo)."
    exit 1
fi

echo "[1/7] Enabling dwc2 USB gadget overlay (peripheral mode)..."
if grep -q "dtoverlay=dwc2" "$BOOT_CONFIG"; then
    # Replace any existing dwc2 entry — could be host or missing dr_mode
    sed -i 's/dtoverlay=dwc2.*/dtoverlay=dwc2,dr_mode=peripheral/' "$BOOT_CONFIG"
    echo "      updated existing entry to dr_mode=peripheral"
else
    echo "dtoverlay=dwc2,dr_mode=peripheral" >> "$BOOT_CONFIG"
    echo "      added dtoverlay=dwc2,dr_mode=peripheral to $BOOT_CONFIG"
fi

echo "[2/7] Adding dwc2 module to /etc/modules-load.d/waver-dwc2.conf..."
if [[ ! -f /etc/modules-load.d/waver-dwc2.conf ]]; then
    echo "dwc2" > /etc/modules-load.d/waver-dwc2.conf
    echo "      created /etc/modules-load.d/waver-dwc2.conf"
else
    echo "      already present — skipped"
fi

echo "[3/7] Creating books directory..."
mkdir -p "$BOOKS_DIR"

echo "[4/7] Creating FAT32 image (${IMAGE_SIZE} MB)..."
if [[ -f "$IMAGE" ]]; then
    echo "      $IMAGE already exists — skipped (delete it to recreate)"
else
    dd if=/dev/zero of="$IMAGE" bs=1M count="$IMAGE_SIZE" status=progress
    mkdosfs -F 32 -n RSVP-BOOKS "$IMAGE"
    echo "      created $IMAGE"
fi

echo "[5/7] Installing waver-usb-gadget systemd unit..."
if [[ -f "$UNIT_SRC" ]]; then
    cp "$UNIT_SRC" "$SYSTEMD_UNIT"
    systemctl daemon-reload
    systemctl enable waver-usb-gadget.service
    echo "      unit installed and enabled"
else
    echo "      WARNING: $UNIT_SRC not found — unit not installed"
fi

echo "[6/7] Installing udev rule..."
cat > "$UDEV_RULE" << 'EOF'
# Waver USB gadget — trigger sync when host PC unplugs / releases drive.
# dwc2 UDC transitions to "not attached" when the USB cable is disconnected.
SUBSYSTEM=="udc", ACTION=="change", ATTR{state}=="not attached", \
    RUN+="/bin/systemd-run --no-block /home/cimi/waver/config/scripts/usb-sync.sh"
EOF
udevadm control --reload-rules
echo "      installed $UDEV_RULE"

echo "[7/7] Making sync script executable..."
chmod +x "$SYNC_SCRIPT"

echo ""
echo "================================================================"
echo " Setup complete. REBOOT REQUIRED for dwc2 overlay to take effect."
echo " After reboot, plug the Pi into a PC via the USB OTG port (not"
echo " the power port) and it will appear as a USB drive named"
echo " RSVP-BOOKS."
echo ""
echo " Drop .epub/.txt/.md/.html files onto the drive, safely eject"
echo " in your OS, then unplug. The Pi will auto-convert them to .rsvp."
echo "================================================================"
