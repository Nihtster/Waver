#!/usr/bin/env bash
#
# Runtime helper for Waver's WiFi hotspot.
#
# Usage:
#   hotspot.sh start    # bring the AP up (knocks out wifi-client mode)
#   hotspot.sh stop     # tear the AP down (rejoin client wifi if available)
#   hotspot.sh status   # echo "active" or "inactive"
#
# Profile must already exist — created once via setup-hotspot.py.
#
set -euo pipefail

PROFILE_NAME="waver-hotspot"

profile_exists() {
    nmcli -t -f NAME connection show | grep -qx "$PROFILE_NAME"
}

is_active() {
    nmcli -t -f NAME connection show --active | grep -qx "$PROFILE_NAME"
}

case "${1:-}" in
    start)
        if ! profile_exists; then
            echo "error: profile '$PROFILE_NAME' not found — run setup-hotspot.py first" >&2
            exit 1
        fi
        nmcli connection up "$PROFILE_NAME" >/dev/null
        echo "active"
        ;;
    stop)
        if is_active; then
            nmcli connection down "$PROFILE_NAME" >/dev/null
        fi
        echo "inactive"
        ;;
    status)
        if is_active; then
            echo "active"
        else
            echo "inactive"
        fi
        ;;
    *)
        echo "usage: $0 start|stop|status" >&2
        exit 2
        ;;
esac
