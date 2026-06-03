"""HTTP tests: start rsvp-converter on a test port, hit it with real requests."""
import os, sys, time, tempfile, subprocess, signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRV  = os.path.join(ROOT, "rsvp-converter")
PY   = sys.executable

import requests

PORT = 5571
BASE = f"http://127.0.0.1:{PORT}"


def main():
    tmpdir = tempfile.mkdtemp(prefix="rsvp-test-")
    env = os.environ.copy()
    env["BOOKS_DIR"] = tmpdir
    env["RSVP_PORT"] = str(PORT)
    env["RSVP_HOST"] = "127.0.0.1"

    proc = subprocess.Popen(
        [PY, "server.py"], cwd=SRV, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    # Poll health up to 10s.
    deadline = time.time() + 10
    healthy = False
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE}/health", timeout=1)
            if r.status_code == 200:
                healthy = True
                break
        except requests.RequestException:
            time.sleep(0.2)

    failures = []
    try:
        if not healthy:
            failures.append("server never became healthy")
            return _finish(proc, failures)

        # 1. /health
        r = requests.get(f"{BASE}/health", timeout=2)
        assert r.status_code == 200, f"health: {r.status_code}"
        assert r.json().get("ok") is True
        print("[PASS] GET /health")

        # 2. /convert with .txt
        files = {"file": ("alpha.txt",
            b"Chapter 1\n\nHello world this is fine.\nMore text here too.\n",
            "text/plain")}
        data  = {"title": "Alpha", "author": "Tester"}
        r = requests.post(f"{BASE}/convert", files=files, data=data, timeout=10)
        assert r.status_code == 200, f"convert: {r.status_code} {r.text[:200]}"
        body = r.text
        assert body.startswith("@rsvp 1"), "convert: bad header"
        assert "@title Alpha" in body
        assert "@author Tester" in body
        disp = r.headers.get("Content-Disposition", "")
        assert "alpha.rsvp" in disp, f"bad disposition: {disp}"
        print("[PASS] POST /convert (txt)")

        # 3. /library (should contain alpha.rsvp now)
        r = requests.get(f"{BASE}/library", timeout=2)
        assert r.status_code == 200
        j = r.json()
        assert isinstance(j.get("books"), list)
        names = [b["filename"] for b in j["books"]]
        assert "alpha.rsvp" in names, f"library missing alpha.rsvp: {names}"
        print("[PASS] GET /library")

        # 3b. /library/<filename> download
        r = requests.get(f"{BASE}/library/alpha.rsvp", timeout=2)
        assert r.status_code == 200
        assert r.text.startswith("@rsvp 1")
        print("[PASS] GET /library/<f>")

        # 4. DELETE nonexistent → 404
        r = requests.delete(f"{BASE}/library/does-not-exist.rsvp", timeout=2)
        assert r.status_code == 404, f"expected 404, got {r.status_code}"
        print("[PASS] DELETE /library/<nonexistent>")

        # 4b. DELETE real file → 200
        r = requests.delete(f"{BASE}/library/alpha.rsvp", timeout=2)
        assert r.status_code == 200
        assert r.json().get("deleted") == "alpha.rsvp"
        print("[PASS] DELETE /library/<f>")

        # 4c. Path traversal attempt → 404 (safe_join rejects)
        r = requests.delete(f"{BASE}/library/..%2Fescape.rsvp", timeout=2)
        assert r.status_code == 404
        print("[PASS] DELETE path traversal blocked")

        # 5. Unsupported format → 415
        files = {"file": ("x.pdf", b"%PDF-1.4 fake", "application/pdf")}
        r = requests.post(f"{BASE}/convert", files=files, timeout=5)
        assert r.status_code == 415, f"expected 415, got {r.status_code}"
        print("[PASS] POST /convert unsupported → 415")

    except AssertionError as e:
        failures.append(str(e))
    except Exception as e:
        failures.append(f"exception: {e!r}")

    return _finish(proc, failures)


def _finish(proc, failures):
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

    print(f"\n{'-'*40}")
    if failures:
        print(f"server.py: FAILED")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("server.py: all checks passed")


if __name__ == "__main__":
    main()
