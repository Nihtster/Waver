const API = '';
let token = localStorage.getItem('swisspi_token');
let selectedSSID = null;

window.onload = () => {
    if (token) {
        showDashboard();
        loadAll();
        startAutoRefresh();
    } else {
        showLogin();
    }
    document.getElementById('password').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') login();
    });
};

async function login() {
    const password = document.getElementById('password').value;
    const error = document.getElementById('login-error');
    error.classList.add('hidden');
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        const data = await res.json();
        if (data.token) {
            token = data.token;
            localStorage.setItem('swisspi_token', token);
            showDashboard();
            loadAll();
            startAutoRefresh();
        } else {
            error.classList.remove('hidden');
        }
    } catch (e) {
        error.textContent = 'Connection error';
        error.classList.remove('hidden');
    }
}

function logout() {
    localStorage.removeItem('swisspi_token');
    token = null;
    showLogin();
}

function showLogin() {
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('dashboard').classList.add('hidden');
}

function showDashboard() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('dashboard').classList.remove('hidden');
}

async function apiFetch(path, options = {}) {
    const res = await fetch(path, {
        ...options,
        headers: {
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json',
            ...options.headers
        }
    });
    if (res.status === 401) {
        logout();
        return null;
    }
    return res.json();
}

async function loadAll() {
    await Promise.all([
        loadSystemStatus(),
        loadPiholeStats(),
        loadNetworkInfo()
    ]);
}

async function loadSystemStatus() {
    const data = await apiFetch('/api/system/status');
    if (!data) return;
    document.getElementById('uptime').textContent = '⏱ ' + data.uptime;
    document.getElementById('temp').textContent = '🌡 ' + data.temp;
    document.getElementById('ip').textContent = '🌐 ' + data.ip;
    updateService('pihole', data.pihole);
    updateService('wireguard', data.wireguard);
    updateService('ssh', data.ssh);
    updateService('nginx', data.nginx);
}

async function loadPiholeStats() {
    const data = await apiFetch('/api/services/pihole');
    if (!data) return;
    document.getElementById('pihole-queries').textContent = data.stats.queries.toLocaleString();
    document.getElementById('pihole-blocked').textContent = data.stats.blocked.toLocaleString();
    document.getElementById('pihole-percent').textContent = data.stats.percent + '%';
}

async function loadNetworkInfo() {
    const data = await apiFetch('/api/network/info');
    if (!data) return;
    document.getElementById('net-ip').textContent = data.ip;
    document.getElementById('net-signal').textContent = data.signal + ' dBm';
}

function updateService(name, isActive) {
    const el = document.getElementById('svc-' + name);
    if (!el) return;
    const status = el.querySelector('.service-status');
    status.textContent = isActive ? 'ON' : 'OFF';
    status.className = 'service-status ' + (isActive ? 'status-on' : 'status-off');
}

async function toggleService(name) {
    const data = await apiFetch('/api/services/' + name + '/toggle', { method: 'POST' });
    if (!data) return;
    updateService(name, data.active);
}

async function scanWifi() {
    const container = document.getElementById('wifi-networks');
    container.innerHTML = '<p style="color:#718096;padding:8px">Scanning...</p>';
    const data = await apiFetch('/api/network/wifi/scan');
    if (!data) return;
    if (data.networks.length === 0) {
        container.innerHTML = '<p style="color:#718096;padding:8px">No networks found</p>';
        return;
    }
    container.innerHTML = data.networks.map(function(n) {
        return '<div class="wifi-network"><span>' + n.ssid + ' (' + n.signal + ' dBm)</span><button onclick="startConnect(\'' + n.ssid + '\')">Connect</button></div>';
    }).join('');
}

function startConnect(ssid) {
    selectedSSID = ssid;
    document.getElementById('connecting-ssid').textContent = 'Connect to: ' + ssid;
    document.getElementById('wifi-connect-form').classList.remove('hidden');
    document.getElementById('wifi-password').focus();
}

function cancelConnect() {
    selectedSSID = null;
    document.getElementById('wifi-connect-form').classList.add('hidden');
    document.getElementById('wifi-password').value = '';
}

async function connectWifi() {
    const password = document.getElementById('wifi-password').value;
    const data = await apiFetch('/api/network/wifi/connect', {
        method: 'POST',
        body: JSON.stringify({ ssid: selectedSSID, password: password })
    });
    if (data && data.success) {
        alert('Connected to ' + selectedSSID + '! New IP: ' + data.ip);
        cancelConnect();
        loadNetworkInfo();
    } else {
        alert('Connection failed. Check password and try again.');
    }
}

function startAutoRefresh() {
    setInterval(loadSystemStatus, 30000);
    setInterval(loadPiholeStats, 30000);
    setInterval(loadNetworkInfo, 30000);
}
