#!/usr/bin/env python3
"""
OTA updater — pulls latest code from the git remote and restarts services.

Setup on Pi (one-time):
  git clone https://github.com/YOU/waver.git ~/waver
  # For a private repo add a PAT token:
  # git remote set-url origin https://TOKEN@github.com/YOU/waver.git

REPO_PATH below must point to wherever the repo is cloned on the Pi.
"""

import subprocess
import os
import sys

REPO_PATH         = os.path.expanduser("~/waver")
SERVICES_RESTART  = ["waver", "waver-api"]
GIT_TIMEOUT       = 30   # seconds per git command


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
