#!/usr/bin/env python3
"""
WAVER Flask API
"""

from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
from flask_socketio import SocketIO, emit, disconnect
from flask_cors import CORS
import jwt
import bcrypt
import subprocess
import json
import os
import time
import requests
from datetime import datetime, timedelta
from config import (
    PASSWORD_HASH, SECRET_KEY,
    PIHOLE_API, PIHOLE_APP_PASSWORD,
    WG_INTERFACE, NETWORK_INTERFACE,
)
from pihole_client import PiholeClient

RSVP_CONVERTER_URL = os.environ.get("RSVP_CONVERTER_URL", "http://127.0.0.1:5001")

app = Flask(__name__, static_folder='../dashboard')
app.config['SECRET_KEY'] = SECRET_KEY
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

pihole = PiholeClient(PIHOLE_API, PIHOLE_APP_PASSWORD)

# ============ HELPERS ============

def verify_token(token):
    """Verify JWT token"""
    try:
        jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return True
    except jwt.InvalidTokenError:
        return False

def get_auth_token():
    """Extract token from request header"""
    auth = request.headers.get('Authorization', '')
    return auth.replace('Bearer ', '')

def run_cmd(cmd, timeout=3):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except Exception as e:
        return None

def get_service_status(service_name):
    """Get systemd service status"""
    result = run_cmd(["systemctl", "is-active", service_name])
    return result == "active"

def toggle_service(service_name):
    """Toggle a systemd service"""
    is_active = get_service_status(service_name)
    action = "stop" if is_active else "start"
    run_cmd(["sudo", "systemctl", action, service_name], timeout=5)
    return get_service_status(service_name)

# ============ AUTH ============

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    password = data.get('password', '').encode()

    if bcrypt.checkpw(password, PASSWORD_HASH.encode()):
        token = jwt.encode(
            {
                'exp': datetime.utcnow() + timedelta(hours=24),
                'iat': datetime.utcnow(),
            },
            SECRET_KEY,
            algorithm='HS256'
        )
        return jsonify({'token': token})

    return jsonify({'error': 'Invalid password'}), 401

# ============ SYSTEM ============

@app.route('/api/system/status', methods=['GET'])
def system_status():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401

    uptime = run_cmd(["uptime", "-p"]) or "N/A"
    uptime = uptime.replace("up ", "")

    temp = run_cmd(["vcgencmd", "measure_temp"]) or "N/A"
    temp = temp.replace("temp=", "")

    ip = run_cmd(["hostname", "-I"]) or "N/A"
    ip = ip.split()[0] if ip else "N/A"

    return jsonify({
        'uptime': uptime,
        'temp': temp,
        'ip': ip,
        'pihole': get_service_status("pihole-FTL"),
        'wireguard': get_service_status("wg-quick@wg0"),
        'ssh': get_service_status("ssh"),
        'nginx': get_service_status("nginx"),
    })

# ============ NETWORK ============

@app.route('/api/network/info', methods=['GET'])
def network_info():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401

    ip = run_cmd(["hostname", "-I"]) or "N/A"
    ip = ip.split()[0] if ip else "N/A"

    signal = "N/A"
    iwconfig = run_cmd(["iwconfig", NETWORK_INTERFACE])
    if iwconfig and "Signal level" in iwconfig:
        for line in iwconfig.split('\n'):
            if "Signal level" in line:
                signal = line.split("Signal level=")[1].split(" ")[0]
                break

    return jsonify({
        'ip': ip,
        'signal': signal,
        'interface': NETWORK_INTERFACE,
    })

@app.route('/api/network/wifi/scan', methods=['GET'])
def wifi_scan():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401

    result = run_cmd(
        ["sudo", "iwlist", NETWORK_INTERFACE, "scan"], timeout=10
    )

    networks = []
    if result:
        current = {}
        for line in result.split('\n'):
            line = line.strip()
            if 'ESSID:' in line:
                ssid = line.split('ESSID:"')[1].rstrip('"')
                if ssid:
                    current['ssid'] = ssid
            if 'Signal level=' in line:
                try:
                    signal = line.split('Signal level=')[1].split(' ')[0]
                    current['signal'] = signal
                except:
                    current['signal'] = 'N/A'
            if 'ssid' in current and 'signal' in current:
                networks.append(current)
                current = {}

    # Deduplicate by SSID
    seen = set()
    unique = []
    for n in networks:
        if n['ssid'] not in seen:
            seen.add(n['ssid'])
            unique.append(n)

    return jsonify({'networks': unique})

@app.route('/api/network/wifi/connect', methods=['POST'])
def wifi_connect():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    ssid = data.get('ssid')
    password = data.get('password')

    if not ssid:
        return jsonify({'error': 'SSID required'}), 400

    try:
        if password:
            run_cmd([
                "sudo", "nmcli", "dev", "wifi", "connect",
                ssid, "password", password
            ], timeout=15)
        else:
            run_cmd([
                "sudo", "nmcli", "dev", "wifi", "connect", ssid
            ], timeout=15)

        time.sleep(2)
        new_ip = run_cmd(["hostname", "-I"])
        return jsonify({
            'success': True,
            'ip': new_ip.split()[0] if new_ip else "N/A"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ SERVICES ============

@app.route('/api/services/pihole', methods=['GET'])
def pihole_status():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401

    return jsonify({
        'active': get_service_status("pihole-FTL"),
        'stats': pihole.get_stats_summary(),
    })

@app.route('/api/services/pihole/toggle', methods=['POST'])
def pihole_toggle():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401

    is_active = toggle_service("pihole-FTL")
    socketio.emit('service_update', {'service': 'pihole', 'active': is_active})
    return jsonify({'active': is_active})

@app.route('/api/services/wireguard', methods=['GET'])
def wireguard_status():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401

    is_active = get_service_status("wg-quick@wg0")
    return jsonify({'active': is_active})

@app.route('/api/services/wireguard/toggle', methods=['POST'])
def wireguard_toggle():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401

    is_active = toggle_service("wg-quick@wg0")
    socketio.emit('service_update', {'service': 'wireguard', 'active': is_active})
    return jsonify({'active': is_active})

# ============ RSVP READER ============

@app.route('/api/rsvp/upload', methods=['POST'])
def rsvp_upload():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'missing file'}), 400

    f = request.files['file']
    files = {'file': (f.filename, f.stream, f.mimetype or 'application/octet-stream')}
    data = {
        'title':  request.form.get('title', ''),
        'author': request.form.get('author', ''),
        'save':   request.form.get('save', '1'),
    }

    try:
        r = requests.post(
            f"{RSVP_CONVERTER_URL}/convert",
            files=files, data=data, timeout=120,
        )
    except requests.RequestException as e:
        return jsonify({'error': f'converter unreachable: {e}'}), 502

    return Response(
        r.content,
        status=r.status_code,
        content_type=r.headers.get('Content-Type', 'application/octet-stream'),
        headers={
            'Content-Disposition': r.headers.get(
                'Content-Disposition', 'attachment; filename="book.rsvp"'
            ),
        },
    )

@app.route('/api/rsvp/library', methods=['GET'])
def rsvp_library():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        r = requests.get(f"{RSVP_CONVERTER_URL}/library", timeout=10)
        return jsonify(r.json()), r.status_code
    except requests.RequestException as e:
        return jsonify({'error': f'converter unreachable: {e}'}), 502

@app.route('/api/rsvp/library/<path:filename>', methods=['GET'])
def rsvp_library_download(filename):
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        r = requests.get(
            f"{RSVP_CONVERTER_URL}/library/{filename}",
            timeout=30, stream=True,
        )
    except requests.RequestException as e:
        return jsonify({'error': f'converter unreachable: {e}'}), 502

    return Response(
        r.iter_content(chunk_size=8192),
        status=r.status_code,
        content_type=r.headers.get('Content-Type', 'application/octet-stream'),
        headers={
            'Content-Disposition': r.headers.get(
                'Content-Disposition', f'attachment; filename="{filename}"'
            ),
        },
    )

@app.route('/api/rsvp/library/<path:filename>', methods=['DELETE'])
def rsvp_library_delete(filename):
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        r = requests.delete(
            f"{RSVP_CONVERTER_URL}/library/{filename}", timeout=10,
        )
        return jsonify(r.json()), r.status_code
    except requests.RequestException as e:
        return jsonify({'error': f'converter unreachable: {e}'}), 502

@app.route('/api/rsvp/status', methods=['GET'])
def rsvp_status():
    if not verify_token(get_auth_token()):
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({
        'active':   get_service_status("waver-rsvp"),
        'endpoint': RSVP_CONVERTER_URL,
    })

# ============ WEBSOCKET ============

@socketio.on('connect')
def handle_connect(auth):
    token = auth.get('token') if auth else None
    if not token or not verify_token(token):
        disconnect()
        return False
    print(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")

# ============ STATIC FILES ============

@app.route('/')
def index():
    return send_from_directory('../dashboard', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('../dashboard', path)

if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=False)
