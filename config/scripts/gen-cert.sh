#!/usr/bin/env bash
#
# Generate a self-signed TLS certificate for Waver's nginx.
#
# Output:
#   /etc/ssl/waver/waver.crt    (cert,  644)
#   /etc/ssl/waver/waver.key    (key,   600)
#
# Subject Alt Names cover:
#   - DNS:  waver, waver.local, localhost
#   - IP:   127.0.0.1, 192.168.0.191 (LAN), 10.0.0.1 (WireGuard)
#
# 10-year validity — re-issuing self-signed certs annually is just paperwork.
# If you change networks and need a different LAN IP in the cert, edit
# the SAN list below and re-run with --force.
#
# Usage:
#   sudo ./gen-cert.sh             # generate (refuses to overwrite)
#   sudo ./gen-cert.sh --force     # regenerate, replacing existing
#
# After running, restart nginx:
#   sudo systemctl restart nginx
#
set -euo pipefail

CERT_DIR="/etc/ssl/waver"
CERT_FILE="$CERT_DIR/waver.crt"
KEY_FILE="$CERT_DIR/waver.key"
DAYS="3650"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
    FORCE=1
fi

if [[ "$EUID" -ne 0 ]]; then
    echo "error: must run as root (use sudo)" >&2
    exit 1
fi

if [[ ( -f "$CERT_FILE" || -f "$KEY_FILE" ) && "$FORCE" -ne 1 ]]; then
    echo "error: cert/key already exist at $CERT_DIR" >&2
    echo "       re-run with --force to regenerate" >&2
    exit 1
fi

mkdir -p "$CERT_DIR"

OPENSSL_CONFIG="$(mktemp)"
trap 'rm -f "$OPENSSL_CONFIG"' EXIT

cat > "$OPENSSL_CONFIG" <<'EOF'
[req]
default_bits        = 2048
prompt              = no
default_md          = sha256
distinguished_name  = dn
x509_extensions     = v3_ext

[dn]
CN = waver

[v3_ext]
subjectAltName    = @alt_names
keyUsage          = digitalSignature, keyEncipherment
extendedKeyUsage  = serverAuth
basicConstraints  = CA:FALSE

[alt_names]
DNS.1 = waver
DNS.2 = waver.local
DNS.3 = localhost
IP.1  = 127.0.0.1
IP.2  = 192.168.0.191
IP.3  = 10.0.0.1
EOF

openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$KEY_FILE" \
    -out    "$CERT_FILE" \
    -days   "$DAYS" \
    -config "$OPENSSL_CONFIG"

chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"
chown root:root "$KEY_FILE" "$CERT_FILE"

echo
echo "✓ cert: $CERT_FILE"
echo "✓ key:  $KEY_FILE"
echo
echo "Restart nginx to pick up the new cert:"
echo "  sudo systemctl restart nginx"
