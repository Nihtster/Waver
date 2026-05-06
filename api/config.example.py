#!/usr/bin/env python3
"""
WAVER API Configuration

SETUP INSTRUCTIONS:
1. Generate a bcrypt password hash:
   ~/waver-env/bin/python3 -c "import bcrypt; p=input('Password: ').encode(); print(bcrypt.hashpw(p, bcrypt.gensalt()).decode())"

2. Paste the hash into PASSWORD_HASH below

3. Change SECRET_KEY to a random string (mash your keyboard)
"""

# Your bcrypt password hash
PASSWORD_HASH = "REPLACE_WITH_YOUR_BCRYPT_HASH"

# JWT secret key - make this random and keep it secret
SECRET_KEY = "REPLACE_WITH_RANDOM_SECRET"

# Pi-hole v6 API
# Base URL of the Pi-hole API (no trailing slash)
PIHOLE_API = "http://localhost:8080/api"

# Application password for Pi-hole API access
# Generate at: http://<pi-ip>:8080/admin/settings/api -> Expert mode
#              -> Advanced Settings -> Configure app password
PIHOLE_APP_PASSWORD = "REPLACE_WITH_PIHOLE_APP_PASSWORD"

# WireGuard interface name
WG_INTERFACE = "wg0"

# Network interface
NETWORK_INTERFACE = "wlan0"

# Static IP address
STATIC_IP = "192.168.0.191"
