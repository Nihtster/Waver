#!/usr/bin/env python3
"""
SwissPI API Configuration

SETUP INSTRUCTIONS:
1. Generate a bcrypt password hash:
   source ~/swisspi-env/bin/activate
   python3 -c "import bcrypt; p=input('Password: ').encode(); print(bcrypt.hashpw(p, bcrypt.gensalt()).decode())"

2. Paste the hash into PASSWORD_HASH below

3. Change SECRET_KEY to a random string (mash your keyboard)
"""

# Your bcrypt password hash
PASSWORD_HASH = "REPLACE_WITH_YOUR_BCRYPT_HASH"

# JWT secret key - make this random and keep it secret
SECRET_KEY = "REPLACE_WITH_RANDOM_SECRET"

# Pi-hole settings (v6 runs on port 8080)
PIHOLE_API = "http://localhost:8080/admin/api.php"

# WireGuard interface name
WG_INTERFACE = "wg0"

# Network interface
NETWORK_INTERFACE = "wlan0"

# Static IP address
STATIC_IP = "192.168.0.191"
