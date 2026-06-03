#!/usr/bin/env python3
"""
rsvp-converter: tiny Flask service that turns books into .rsvp files
for the rsvpnano ESP32-S3 reader.

Listens on 127.0.0.1:5001. Reverse-proxied / called by the Waver API.
"""

import os
import re
from io import BytesIO

from flask import Flask, jsonify, request, send_file, abort

import converter


BOOKS_DIR = os.environ.get("BOOKS_DIR", "/home/cimi/waver/rsvp-books")
HOST      = os.environ.get("RSVP_HOST", "127.0.0.1")
PORT      = int(os.environ.get("RSVP_PORT", "5001"))

# Safe filename: letters, digits, underscore, dash, dot. No path separators.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

app = Flask(__name__)


def _ensure_books_dir():
    os.makedirs(BOOKS_DIR, exist_ok=True)


def _safe_join(name):
    """Return absolute path inside BOOKS_DIR or None if name is unsafe."""
    if not name or not _SAFE_NAME_RE.match(name):
        return None
    if not name.endswith(".rsvp"):
        return None
    path = os.path.abspath(os.path.join(BOOKS_DIR, name))
    if os.path.dirname(path) != os.path.abspath(BOOKS_DIR):
        return None
    return path


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "books_dir": BOOKS_DIR})


@app.route("/convert", methods=["POST"])
def convert_book():
    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "empty filename"}), 400

    title  = request.form.get("title")  or None
    author = request.form.get("author") or None
    save   = request.form.get("save", "1") not in ("0", "false", "no")

    data = f.read()
    try:
        rsvp_text, out_name = converter.convert(
            f.filename, data, title=title, author=author,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 415
    except Exception as e:
        return jsonify({"error": f"conversion failed: {e}"}), 500

    out_bytes = rsvp_text.encode("utf-8")

    if save:
        _ensure_books_dir()
        # Sanitise output name (converter already builds it from basename).
        out_name = re.sub(r"[^A-Za-z0-9._-]+", "_", out_name)
        path = os.path.join(BOOKS_DIR, out_name)
        with open(path, "wb") as fh:
            fh.write(out_bytes)

    return send_file(
        BytesIO(out_bytes),
        mimetype="text/plain",
        as_attachment=True,
        download_name=out_name,
    )


@app.route("/library", methods=["GET"])
def library():
    _ensure_books_dir()
    books = []
    for entry in sorted(os.listdir(BOOKS_DIR)):
        if not entry.endswith(".rsvp"):
            continue
        path = os.path.join(BOOKS_DIR, entry)
        if not os.path.isfile(path):
            continue
        st = os.stat(path)
        books.append({
            "filename": entry,
            "size":     st.st_size,
            "mtime":    int(st.st_mtime),
        })
    return jsonify({"books": books, "dir": BOOKS_DIR})


@app.route("/library/<path:filename>", methods=["GET"])
def library_download(filename):
    path = _safe_join(filename)
    if path is None or not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        mimetype="text/plain",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/library/<path:filename>", methods=["DELETE"])
def library_delete(filename):
    path = _safe_join(filename)
    if path is None or not os.path.isfile(path):
        abort(404)
    os.remove(path)
    return jsonify({"deleted": filename})


if __name__ == "__main__":
    _ensure_books_dir()
    app.run(host=HOST, port=PORT, debug=False)
