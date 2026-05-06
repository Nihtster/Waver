#!/usr/bin/env python3
"""
Pi-hole v6 API client with session caching.

The v6 API requires:
  1. POST /api/auth with {password} -> get a session ID (sid)
  2. Pass sid in the X-FTL-SID header on every subsequent call
  3. Sessions expire (default 30min) -> re-auth on 401

This client caches the SID in-process and re-authenticates on demand.
Used by both api/app.py (dashboard) and launcher/network_info.py (LCD).
"""

import json
import threading
import urllib.error
import urllib.request


class PiholeClient:
    def __init__(self, base_url, app_password, timeout=3):
        self.base_url = base_url.rstrip("/")
        self.password = app_password
        self.timeout  = timeout
        self._sid     = None
        self._lock    = threading.Lock()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _authenticate(self):
        """Fetch a fresh SID. Returns True on success."""
        try:
            body = json.dumps({"password": self.password}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/auth",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())

            session = data.get("session", {})
            if session.get("valid") and session.get("sid"):
                self._sid = session["sid"]
                return True
            self._sid = None
            return False
        except (urllib.error.URLError, json.JSONDecodeError, OSError):
            self._sid = None
            return False

    # ── Generic GET with re-auth on 401 ───────────────────────────────────────

    def _get(self, path):
        """GET path with current SID. Re-auth + retry once on 401."""
        with self._lock:
            if self._sid is None and not self._authenticate():
                return None

            data = self._raw_get(path)
            if data is None:
                # Could be a stale SID — try re-auth once and retry
                if self._authenticate():
                    data = self._raw_get(path)
            return data

    def _raw_get(self, path):
        try:
            req = urllib.request.Request(
                f"{self.base_url}{path}",
                headers={"X-FTL-SID": self._sid or ""},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                if r.status != 200:
                    return None
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._sid = None
            return None
        except (urllib.error.URLError, json.JSONDecodeError, OSError):
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    def get_stats_summary(self):
        """
        Map v6 /api/stats/summary onto our existing dashboard contract:
            {queries, blocked, percent}
        Returns zeros on any failure so callers can render safely.
        """
        data = self._get("/stats/summary")
        if not data:
            return {"queries": 0, "blocked": 0, "percent": 0}

        q = data.get("queries", {}) or {}
        return {
            "queries": q.get("total", 0),
            "blocked": q.get("blocked", 0),
            "percent": round(float(q.get("percent_blocked", 0.0)), 1),
        }
