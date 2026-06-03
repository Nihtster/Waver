#!/usr/bin/env python3
"""
OTA updater — pulls latest code from the git remote and restarts services.

Setup on Pi (one-time):
  git clone https://github.com/YOU/waver.git ~/waver
  # For a private repo add a PAT token:
  # git remote set-url origin https://TOKEN@github.com/YOU/waver.git

REPO_PATH below must point to wherever the repo is cloned on the Pi.
"""

import shutil
import subprocess
import os
import sys

REPO_PATH         = "/home/cimi/waver"
SERVICES_RESTART  = ["waver", "waver-api", "waver-rsvp"]
GIT_TIMEOUT       = 30   # seconds per git command

_BASHRC       = "/home/cimi/.bashrc"
_FF_CONFIG    = "/home/cimi/.config/fastfetch/config.jsonc"
_FF_MARKER    = "# waver-fastfetch"


def _git(*args):
    return subprocess.run(
        ["git"] + list(args),
        cwd=REPO_PATH,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT,
    )


def check_updates():
    """
    Fetch remote and compare with local HEAD.
    Returns (status, message)
      status: "up_to_date" | "available" | "error"
    """
    if not os.path.isdir(os.path.join(REPO_PATH, ".git")):
        return "error", "not a git repo"

    try:
        r = _git("fetch", "--quiet")
        if r.returncode != 0:
            err = r.stderr.strip().splitlines()
            return "error", (err[0] if err else "fetch failed")[:28]

        local  = _git("rev-parse", "HEAD")
        remote = _git("rev-parse", "@{u}")

        if local.returncode != 0 or remote.returncode != 0:
            return "error", "cannot read refs"

        if local.stdout.strip() == remote.stdout.strip():
            return "up_to_date", "Already up to date"

        behind = _git("rev-list", "--count", "HEAD..@{u}")
        n = behind.stdout.strip() if behind.returncode == 0 else "?"
        return "available", f"{n} new commit(s) ready"

    except FileNotFoundError:
        return "error", "git not installed"
    except subprocess.TimeoutExpired:
        return "error", "network timeout"
    except Exception as e:
        return "error", str(e)[:28]


def do_update():
    """
    Pull latest from remote (fast-forward only — never merges).
    Returns (status, message)
      status: "success" | "error"
    """
    try:
        r = _git("pull", "--ff-only", "--quiet")
        if r.returncode == 0:
            post_update()
            # Summarise changed files
            changed = _git("diff", "--name-only", "HEAD@{1}", "HEAD")
            files = [l for l in changed.stdout.splitlines() if l.strip()]
            n = len(files)
            return "success", f"{n} file(s) updated" if n else "done"
        else:
            err = r.stderr.strip().splitlines()
            return "error", (err[0] if err else "pull failed")[:28]

    except subprocess.TimeoutExpired:
        return "error", "network timeout"
    except Exception as e:
        return "error", str(e)[:28]


def _apt_install(*packages):
    """Install apt packages. Non-fatal — logs failures to stdout (journald)."""
    for pkg in packages:
        r = subprocess.run(
            ["apt-get", "install", "-y", "-q", pkg],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            print(f"[post-update] {pkg} installed.", flush=True)
        else:
            print(f"[post-update] apt install {pkg} failed: "
                  f"{r.stderr.strip()[:80]}", flush=True)


def _patch_bashrc():
    """
    Idempotent: copy fastfetch config and append Waver aliases + login
    fastfetch call to /home/cimi/.bashrc. Guarded by _FF_MARKER so
    repeated OTAs are a no-op.
    """
    # Copy fastfetch config from repo → ~/.config/fastfetch/
    ff_src = os.path.join(REPO_PATH, "config", "fastfetch", "config.jsonc")
    if os.path.isfile(ff_src):
        os.makedirs(os.path.dirname(_FF_CONFIG), exist_ok=True)
        shutil.copy2(ff_src, _FF_CONFIG)

    # Guard: don't patch twice
    try:
        with open(_BASHRC) as f:
            if _FF_MARKER in f.read():
                return
    except FileNotFoundError:
        pass

    patch = (
        f"\n{_FF_MARKER}\n"
        f"# Waver terminal aliases\n"
        f'alias clear=\'clear && fastfetch --config "{_FF_CONFIG}"\'\n'
        f"alias stats='btop'\n"
        f"\n"
        f"# Show Waver system info on every interactive login shell\n"
        f'if [[ $- == *i* ]]; then\n'
        f'    fastfetch --config "{_FF_CONFIG}"\n'
        f"fi\n"
    )
    with open(_BASHRC, "a") as f:
        f.write(patch)
    print("[post-update] .bashrc patched with Waver aliases.", flush=True)


def post_update():
    """
    Idempotent post-pull setup. Safe to run on every update — skips steps
    that are already done. Handles new services introduced by the pull.

    Steps:
      1. Create books directory if missing.
      2. Copy any new/changed systemd units from the repo into /etc/systemd/system/.
      3. daemon-reload + enable units that aren't already enabled.
      4. Install/upgrade Python deps for the rsvp-converter.
      5. Install fastfetch + btop via apt.
      6. Copy fastfetch config + patch .bashrc with aliases.
    """
    VENV_PIP   = "/home/cimi/waver-env/bin/pip"
    UNITS_SRC  = os.path.join(REPO_PATH, "config", "systemd")
    UNITS_DST  = "/etc/systemd/system"
    BOOKS_DIR  = "/home/cimi/waver/rsvp-books"
    RSVP_REQS  = os.path.join(REPO_PATH, "rsvp-converter", "requirements.txt")

    # 1. Books directory
    os.makedirs(BOOKS_DIR, exist_ok=True)

    # 2. Sync unit files from repo → systemd
    new_units = []
    if os.path.isdir(UNITS_SRC):
        for fname in os.listdir(UNITS_SRC):
            if not fname.endswith(".service"):
                continue
            src = os.path.join(UNITS_SRC, fname)
            dst = os.path.join(UNITS_DST, fname)
            try:
                with open(src, "rb") as f:
                    src_bytes = f.read()
                dst_bytes = open(dst, "rb").read() if os.path.exists(dst) else b""
                if src_bytes != dst_bytes:
                    with open(dst, "wb") as f:
                        f.write(src_bytes)
                    new_units.append(fname)
            except OSError:
                pass  # non-fatal — unit may already be correct

    # 3. daemon-reload + enable new/updated units
    if new_units:
        subprocess.run(["systemctl", "daemon-reload"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for unit in new_units:
            subprocess.run(["systemctl", "enable", unit],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 4. Install rsvp-converter deps (pip is a no-op if already satisfied)
    if os.path.isfile(RSVP_REQS) and os.path.isfile(VENV_PIP):
        subprocess.run(
            [VENV_PIP, "install", "-q", "-r", RSVP_REQS],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    # 5. Install terminal tools directly via apt (no sudo needed — waver
    #    service runs as root or has CAP_NET_ADMIN; apt just needs root)
    _apt_install("fastfetch", "btop")

    # 6. Patch .bashrc with fastfetch config + Waver aliases
    _patch_bashrc()


def restart_services():
    """
    Restart systemd services.  Uses Popen so the call returns before
    systemd kills this process — the launcher exits cleanly on its own.
    """
    subprocess.Popen(
        ["systemctl", "restart"] + SERVICES_RESTART,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Give systemd a moment to act before we exit
    import time; time.sleep(0.5)
    sys.exit(0)
