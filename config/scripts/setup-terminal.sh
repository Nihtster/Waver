#!/usr/bin/env bash
# setup-terminal.sh — install fastfetch + btop + Waver terminal branding
# Idempotent: safe to run on every OTA update.
set -e

REPO_DIR="${REPO_DIR:-/home/cimi/waver}"
BASHRC="${HOME}/.bashrc"
FF_CONFIG_DIR="${HOME}/.config/fastfetch"
FF_MARKER="# waver-fastfetch"

echo "[setup-terminal] Installing fastfetch..."

# Install fastfetch if not present
if ! command -v fastfetch &>/dev/null; then
    # Raspberry Pi OS (Debian bookworm) ships fastfetch in backports;
    # fall back to the GitHub release binary if apt can't find it.
    if apt-cache show fastfetch &>/dev/null 2>&1; then
        sudo apt-get install -y -q fastfetch
    else
        ARCH="$(dpkg --print-architecture)"   # armhf or arm64
        TAG="$(curl -fsSL https://api.github.com/repos/fastfetch-cli/fastfetch/releases/latest \
               | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')"
        DEB="fastfetch-linux-${ARCH}.deb"
        TMP="$(mktemp -d)"
        curl -fsSL -o "${TMP}/${DEB}" \
            "https://github.com/fastfetch-cli/fastfetch/releases/download/${TAG}/${DEB}"
        sudo dpkg -i "${TMP}/${DEB}"
        rm -rf "${TMP}"
    fi
    echo "[setup-terminal] fastfetch installed."
else
    echo "[setup-terminal] fastfetch already installed — skipping."
fi

# Install btop if not present
if ! command -v btop &>/dev/null; then
    sudo apt-get install -y -q btop
    echo "[setup-terminal] btop installed."
else
    echo "[setup-terminal] btop already installed — skipping."
fi

# Copy Waver fastfetch config
mkdir -p "${FF_CONFIG_DIR}"
cp "${REPO_DIR}/config/fastfetch/config.jsonc" "${FF_CONFIG_DIR}/config.jsonc"
echo "[setup-terminal] Fastfetch config written to ${FF_CONFIG_DIR}/config.jsonc"

# Append aliases + fastfetch call to .bashrc (idempotent — check for marker)
if ! grep -qF "${FF_MARKER}" "${BASHRC}" 2>/dev/null; then
    cat >> "${BASHRC}" <<EOF

${FF_MARKER}
# Waver terminal aliases
alias clear='clear && fastfetch --config "${FF_CONFIG_DIR}/config.jsonc"'
alias stats='btop'

# Show Waver system info on every interactive login shell
if [[ \$- == *i* ]]; then
    fastfetch --config "${FF_CONFIG_DIR}/config.jsonc"
fi
EOF
    echo "[setup-terminal] Appended aliases + fastfetch call to ${BASHRC}"
else
    echo "[setup-terminal] .bashrc already patched — skipping."
fi

echo "[setup-terminal] Done. Re-login or run: fastfetch --config ${FF_CONFIG_DIR}/config.jsonc"
