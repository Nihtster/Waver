#!/bin/bash
# usb-sync.sh — triggered by udev when the host PC unplugs the USB drive.
#
# Flow:
#   1. Unload g_mass_storage (release the image from USB gadget).
#   2. Mount the FAT32 image onto rsvp-books/ so the Pi can read it.
#   3. Copy any new source files (.epub/.txt/.md/.html) into rsvp-books/.
#   4. Restart waver-rsvp — startup scan auto-converts new files.
#   5. Wait for waver-rsvp to finish, then unmount and reload the gadget.
#
# Called via systemd-run by the udev rule — runs as root, outside udev context.

set -euo pipefail

IMAGE=/home/cimi/waver/rsvp-books.img
BOOKS_DIR=/home/cimi/waver/rsvp-books
MOUNT_DIR=/mnt/waver-usb
SOURCE_EXTS=("*.epub" "*.txt" "*.md" "*.markdown" "*.html" "*.htm")
LOG_TAG="waver-usb-sync"

log() { echo "[$LOG_TAG] $*" | tee -a /var/log/waver-usb-sync.log; }

# ── Guard: image must exist ───────────────────────────────────────────────────
if [[ ! -f "$IMAGE" ]]; then
    log "ERROR: image $IMAGE not found — aborting"
    exit 1
fi

log "USB disconnect detected — starting sync"

# ── 1. Stop the gadget (frees the image file) ────────────────────────────────
log "Stopping waver-usb-gadget..."
systemctl stop waver-usb-gadget.service || true

# ── 2. Mount image on the Pi ─────────────────────────────────────────────────
mkdir -p "$MOUNT_DIR"
if mountpoint -q "$MOUNT_DIR"; then
    umount "$MOUNT_DIR"
fi
mount -o loop,rw "$IMAGE" "$MOUNT_DIR"
log "Mounted $IMAGE at $MOUNT_DIR"

# ── 3. Copy new source files into BOOKS_DIR ──────────────────────────────────
mkdir -p "$BOOKS_DIR"
copied=0
for pattern in "${SOURCE_EXTS[@]}"; do
    for src in "$MOUNT_DIR"/$pattern; do
        [[ -f "$src" ]] || continue
        fname=$(basename "$src")
        dest="$BOOKS_DIR/$fname"
        if [[ ! -f "$dest" ]]; then
            cp "$src" "$dest"
            log "Copied: $fname"
            (( copied++ )) || true
        fi
    done
done
log "$copied new file(s) copied to $BOOKS_DIR"

# ── 4. Unmount image ─────────────────────────────────────────────────────────
umount "$MOUNT_DIR"
log "Unmounted $MOUNT_DIR"

# ── 5. Restart waver-rsvp — auto-convert runs on startup ─────────────────────
if (( copied > 0 )); then
    log "Restarting waver-rsvp for auto-convert..."
    systemctl restart waver-rsvp.service
    # Give it up to 60s to convert (large EPUBs can take a few seconds each)
    timeout 60 bash -c '
        until systemctl is-active --quiet waver-rsvp.service; do sleep 1; done
    ' || log "WARNING: waver-rsvp did not become active within 60s"
    log "waver-rsvp is up — conversion done"
else
    log "No new files — skipping waver-rsvp restart"
fi

# ── 6. Hand image back to the USB gadget ─────────────────────────────────────
log "Reloading USB gadget..."
systemctl start waver-usb-gadget.service
log "USB gadget ready — plug in to mount on host PC"
