const API = '';
let token = localStorage.getItem('waver_token');
let selectedSSID = null;

window.onload = () => {
    // Pi-hole admin lives on its own port (8080) and isn't proxied — build
    // the link from whichever host the dashboard was reached from so it
    // works on LAN, mDNS, and over WireGuard alike.
    const piholeLink = document.getElementById('pihole-admin-link');
    if (piholeLink) {
        piholeLink.href = `http://${window.location.hostname}:8080/admin/`;
    }

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

    const rsvpForm = document.getElementById('rsvp-upload-form');
    if (rsvpForm) rsvpForm.addEventListener('submit', uploadRsvpBook);
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
            localStorage.setItem('waver_token', token);
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
    localStorage.removeItem('waver_token');
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
        loadNetworkInfo(),
        loadRsvpLibrary()
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

function showRsvpStatus(msg, kind) {
    const el = document.getElementById('rsvp-status');
    if (!el) return;
    el.textContent = msg;
    el.className = 'rsvp-status ' + (kind || '');
    el.classList.remove('hidden');
}

function hideRsvpStatus() {
    const el = document.getElementById('rsvp-status');
    if (el) el.classList.add('hidden');
}

async function uploadRsvpBook(e) {
    e.preventDefault();
    const fileEl = document.getElementById('rsvp-file');
    if (!fileEl.files.length) {
        showRsvpStatus('Choose a file first.', 'error');
        return;
    }
    const fd = new FormData();
    fd.append('file', fileEl.files[0]);
    const title  = document.getElementById('rsvp-title').value;
    const author = document.getElementById('rsvp-author').value;
    if (title)  fd.append('title', title);
    if (author) fd.append('author', author);

    showRsvpStatus('Converting…', '');

    try {
        const res = await fetch('/api/rsvp/upload', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token },
            body: fd
        });
        if (res.status === 401) { logout(); return; }
        if (!res.ok) {
            let msg = 'Conversion failed.';
            try { const j = await res.json(); if (j.error) msg = j.error; } catch (_) {}
            showRsvpStatus(msg, 'error');
            return;
        }
        const blob = await res.blob();
        const disp = res.headers.get('Content-Disposition') || '';
        const match = disp.match(/filename="?([^";]+)"?/i);
        const name = match ? match[1] : 'book.rsvp';

        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = name;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);

        showRsvpStatus('Saved: ' + name, 'ok');
        fileEl.value = '';
        loadRsvpLibrary();
    } catch (err) {
        showRsvpStatus('Upload error: ' + err, 'error');
    }
}

async function loadRsvpLibrary() {
    const container = document.getElementById('rsvp-books');
    if (!container) return;
    const data = await apiFetch('/api/rsvp/library');
    if (!data) return;
    if (data.error) {
        container.innerHTML = '<p class="rsvp-empty">' + data.error + '</p>';
        return;
    }
    const books = data.books || [];
    if (books.length === 0) {
        container.innerHTML = '<p class="rsvp-empty">No books yet.</p>';
        return;
    }
    container.innerHTML = books.map(function(b) {
        const kb = (b.size / 1024).toFixed(1) + ' KB';
        const safe = encodeURIComponent(b.filename);
        return '<div class="rsvp-book">'
             +   '<span class="rsvp-book-name">' + b.filename + '</span>'
             +   '<span class="rsvp-book-size">' + kb + '</span>'
             +   '<a class="rsvp-book-dl" href="/api/rsvp/library/' + safe
             +       '" onclick="return downloadRsvpBook(event, \'' + safe + '\')">Download</a>'
             +   '<button class="rsvp-book-del" onclick="deleteRsvpBook(\'' + b.filename.replace(/'/g, "\\'") + '\')">Delete</button>'
             + '</div>';
    }).join('');
}

async function downloadRsvpBook(ev, name) {
    ev.preventDefault();
    try {
        const res = await fetch('/api/rsvp/library/' + name, {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.status === 401) { logout(); return false; }
        if (!res.ok) { showRsvpStatus('Download failed.', 'error'); return false; }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = decodeURIComponent(name);
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        showRsvpStatus('Download error: ' + e, 'error');
    }
    return false;
}

async function deleteRsvpBook(name) {
    if (!confirm('Delete ' + name + '?')) return;
    const data = await apiFetch('/api/rsvp/library/' + encodeURIComponent(name), { method: 'DELETE' });
    if (!data) return;
    if (data.error) {
        showRsvpStatus(data.error, 'error');
        return;
    }
    showRsvpStatus('Deleted: ' + name, 'ok');
    loadRsvpLibrary();
}

function startAutoRefresh() {
    setInterval(loadSystemStatus, 30000);
    setInterval(loadPiholeStats, 30000);
    setInterval(loadNetworkInfo, 30000);
}
