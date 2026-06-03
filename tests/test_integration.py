"""Static + wiring checks: api routes, dashboard HTML/JS alignment, launcher, systemd."""
import os, sys, re, ast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

results = []
def check(label, cond, detail=""):
    results.append((label, cond, detail))
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {label}" + (f" — {detail}" if detail and not cond else ""))


# ── 3. api/app.py — route registration via AST ───────────────────────────────
def check_api():
    print("\n=== api/app.py ===")
    path = os.path.join(ROOT, "api", "app.py")
    src = open(path, encoding="utf-8").read()

    expected_routes = {
        ("/api/rsvp/upload",            ("POST",)),
        ("/api/rsvp/library",           ("GET",)),
        ("/api/rsvp/library/<path:filename>", ("GET",)),
        ("/api/rsvp/library/<path:filename>", ("DELETE",)),
        ("/api/rsvp/status",            ("GET",)),
    }

    tree = ast.parse(src)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            # @app.route(path, methods=[...])
            if not (isinstance(dec.func, ast.Attribute) and dec.func.attr == "route"):
                continue
            if not dec.args:
                continue
            path_arg = dec.args[0]
            if not isinstance(path_arg, ast.Constant):
                continue
            route_path = path_arg.value
            methods = ("GET",)
            for kw in dec.keywords:
                if kw.arg == "methods" and isinstance(kw.value, ast.List):
                    methods = tuple(e.value for e in kw.value.elts if isinstance(e, ast.Constant))
            found.add((route_path, methods))

    for route in expected_routes:
        check(f"route {route[1][0]} {route[0]}", route in found)

    check("auth check on /api/rsvp/*", src.count("verify_token(get_auth_token())") >= 5)
    check("RSVP_CONVERTER_URL configurable", "RSVP_CONVERTER_URL" in src and "os.environ.get" in src)
    check("uses requests for proxy", "import requests" in src and "requests.post" in src)
    check("forwards multipart correctly", "files=files" in src and "data=data" in src)
    check("forwards to /convert endpoint", "/convert" in src)
    check("forwards to /library endpoint", "/library" in src)


# ── 4. Dashboard HTML/JS alignment ───────────────────────────────────────────
def check_dashboard():
    print("\n=== dashboard ===")
    html = open(os.path.join(ROOT, "dashboard", "index.html"), encoding="utf-8").read()
    js   = open(os.path.join(ROOT, "dashboard", "app.js"),     encoding="utf-8").read()
    css  = open(os.path.join(ROOT, "dashboard", "style.css"),  encoding="utf-8").read()

    # 1. RSVP panel exists
    check("HTML has rsvp-card", 'id="rsvp-card"' in html)
    check("HTML has RSVP Reader heading", "RSVP Reader" in html)

    # 2. Required IDs
    required_ids = [
        "rsvp-upload-form", "rsvp-file", "rsvp-title",
        "rsvp-author", "rsvp-status", "rsvp-books",
    ]
    for rid in required_ids:
        check(f"HTML id={rid}", f'id="{rid}"' in html)

    # 3. file input accepts correct types
    accept_match = re.search(r'id="rsvp-file"[^>]*accept="([^"]+)"', html)
    if accept_match:
        accept = accept_match.group(1)
        for ext in [".epub", ".txt", ".md", ".html"]:
            check(f"file input accepts {ext}", ext in accept)
    else:
        check("file input has accept=", False, "missing accept attr")

    # 4. JS → HTML ID cross-check
    id_refs = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", js))
    rsvp_refs = {r for r in id_refs if r.startswith("rsvp-")}
    for rid in rsvp_refs:
        check(f"JS ref id={rid} exists in HTML", f'id="{rid}"' in html)

    # 5. JS handlers exist
    for fn in ["uploadRsvpBook", "loadRsvpLibrary", "downloadRsvpBook", "deleteRsvpBook"]:
        check(f"JS function {fn}() defined", re.search(rf"function\s+{fn}\b|{fn}\s*=", js) is not None)

    # 6. Form is wired
    check("rsvp-upload-form has submit listener",
          "rsvp-upload-form" in js and "addEventListener('submit'" in js)
    check("loadRsvpLibrary called on init",
          "loadRsvpLibrary()" in js and "loadAll" in js)

    # 7. fetch() targets correct routes + uses Bearer
    check("JS POSTs /api/rsvp/upload", "'/api/rsvp/upload'" in js)
    check("JS GETs /api/rsvp/library", "'/api/rsvp/library'" in js)
    check("JS DELETE /api/rsvp/library/", "/api/rsvp/library/" in js and "method: 'DELETE'" in js)
    check("upload uses Bearer token", "'Authorization': 'Bearer ' + token" in js)

    # 8. CSS theme consistency — uses existing palette colors, no inline <style> hacks
    check("CSS has rsvp-card rule", "#rsvp-card" in css)
    check("CSS uses theme dark bg (#0f1117 or #1a1d2e)", "#0f1117" in css and ".rsvp-" in css)
    check("CSS uses theme accent #63b3ed/#3182ce", "#3182ce" in css or "#63b3ed" in css)
    check("HTML uses existing 'card' class for rsvp section",
          re.search(r'class="card"\s+id="rsvp-card"', html) is not None)
    check("No inline style= on rsvp- elements",
          not re.search(r'<[^>]*id="rsvp-[^"]+"[^>]*style=', html))

    # 9. Tag balance — minimal sanity
    check("section opens & closes", html.count("<section") == html.count("</section>"))
    check("div opens & closes",     html.count("<div ") + html.count("<div>") <= html.count("</div>") + 5)  # loose


# ── 5. launcher.py wiring ────────────────────────────────────────────────────
def check_launcher():
    print("\n=== launcher ===")
    launcher = open(os.path.join(ROOT, "launcher", "launcher.py"), encoding="utf-8").read()
    svcmgr   = open(os.path.join(ROOT, "launcher", "service_manager.py"), encoding="utf-8").read()

    check("RSVP_READER screen const", "RSVP_READER" in launcher and 'RSVP_READER = "rsvp_reader"' in launcher)
    check("RSVP Reader in tools menu", '"RSVP Reader"' in launcher)
    check("RSVP Reader -> RSVP_READER destination", '"RSVP Reader":  RSVP_READER' in launcher)
    check("RSVP_READER sub-items defined", "_rsvp_items" in launcher and "Library" in launcher and "Service Status" in launcher)
    check("RSVP_READER renders menu", "elif self.screen == RSVP_READER" in launcher)
    check("Service Status reads rsvp service", 'self._svc("rsvp")' in launcher)
    check("back nav handles RSVP_READER", "RSVP_READER, ABOUT" in launcher or "RSVP_READER," in launcher)
    check("service_manager maps rsvp -> waver-rsvp", '"rsvp":' in svcmgr and '"waver-rsvp"' in svcmgr)


# ── 6. systemd unit ──────────────────────────────────────────────────────────
def check_systemd():
    print("\n=== systemd unit ===")
    path = os.path.join(ROOT, "config", "systemd", "waver-rsvp.service")
    src = open(path, encoding="utf-8").read()

    check("has [Unit]",    "[Unit]"    in src)
    check("has [Service]", "[Service]" in src)
    check("has [Install]", "[Install]" in src)
    check("ExecStart present", re.search(r"^ExecStart=", src, re.M) is not None)
    check("WorkingDirectory present", re.search(r"^WorkingDirectory=", src, re.M) is not None)
    check("Restart= present", re.search(r"^Restart=", src, re.M) is not None)
    check("User=root", "User=root" in src)
    check("WantedBy=multi-user.target", "WantedBy=multi-user.target" in src)
    check("ExecStart points at waver-env python", "/home/cimi/waver-env/bin/python3" in src)
    check("ExecStart runs server.py", "server.py" in src)
    check("BOOKS_DIR env set", "BOOKS_DIR=" in src)


if __name__ == "__main__":
    check_api()
    check_dashboard()
    check_launcher()
    check_systemd()

    total = len(results)
    failed = [r for r in results if not r[1]]
    print(f"\n{'='*50}")
    print(f"Total: {total}  |  Passed: {total - len(failed)}  |  Failed: {len(failed)}")
    if failed:
        print("\nFailures:")
        for label, _, detail in failed:
            print(f"  - {label}" + (f" ({detail})" if detail else ""))
        sys.exit(1)
    print("ALL CHECKS PASSED")
