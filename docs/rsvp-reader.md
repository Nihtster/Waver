# RSVP Reader

Integration of [rsvpnano](https://github.com/ionutdecebal/rsvpnano) — an
ESP32-S3 e-reader that displays text one word at a time (Rapid Serial Visual
Presentation). Waver hosts the **book conversion pipeline**: a small Flask
service that turns `.epub`, `.txt`, `.md`, and `.html` files into the plain-text
`.rsvp` format the ESP32 device reads from its SD card.

The ESP32 firmware itself lives upstream — Waver doesn't run it.

---

## What it does

- Upload a book from the web dashboard (or POST to the API directly).
- Server converts it to `.rsvp` (chapter + paragraph + word-per-line).
- Converted books live in `/home/cimi/waver/rsvp-books/`.
- Dashboard lists the library; download files to copy onto the reader's SD card.

---

## Architecture

```
Browser  ─┐
          ├─► nginx (443) ──► waver-api (5000) ──► waver-rsvp (5001) ──► /home/cimi/waver/rsvp-books/
LCD menu ─┘                                                                       │
                                                                                  ▼
                                                                          SD card → ESP32-S3
```

Two systemd units involved:

| Unit              | Port | Role                                    |
|-------------------|------|-----------------------------------------|
| `waver-api`       | 5000 | Auth + proxy to converter               |
| `waver-rsvp`      | 5001 | Standalone Flask converter (this doc)   |

The Waver API authenticates the user (JWT), then forwards calls to
`waver-rsvp` over `127.0.0.1:5001`. The converter is **not** exposed
externally — only via the API.

---

## .rsvp format

```
@rsvp 1
@title The Time Machine
@author H. G. Wells
@source the-time-machine.epub
@chapter Chapter 1
@para
The
Time
Traveller
(for
so
it
will
be
convenient
to
speak
of
him)
@para
was
expounding
a
recondite
matter
to
us.
@chapter Chapter 2
@para
...
```

Directives are line-prefixed; everything else is one word per line.

---

## Setup

1. **Install dependencies** in the existing Waver venv:

   ```bash
   sudo ~/waver-env/bin/pip install -r ~/waver/rsvp-converter/requirements.txt
   sudo ~/waver-env/bin/pip install requests
   ```

2. **Create the books directory:**

   ```bash
   sudo mkdir -p /home/cimi/waver/rsvp-books
   sudo chown root:root /home/cimi/waver/rsvp-books
   ```

3. **Install + enable the systemd unit:**

   ```bash
   sudo cp ~/waver/config/systemd/waver-rsvp.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now waver-rsvp
   ```

4. **Restart the API** so the new `/api/rsvp/*` routes load:

   ```bash
   sudo systemctl restart waver-api
   ```

No nginx changes needed — the API proxies the converter internally.

---

## Endpoints

### Through Waver API (auth required)

| Method | Path                              | Body / Notes                                |
|--------|-----------------------------------|---------------------------------------------|
| POST   | `/api/rsvp/upload`                | `multipart/form-data`: `file` + optional `title`, `author` |
| GET    | `/api/rsvp/library`               | Returns `{books: [{filename, size, mtime}]}` |
| GET    | `/api/rsvp/library/<filename>`    | Download a `.rsvp` file                     |
| DELETE | `/api/rsvp/library/<filename>`    | Delete a book                               |
| GET    | `/api/rsvp/status`                | Converter service status                    |

### Direct on the converter (loopback only)

| Method | Path                          | Notes                                       |
|--------|-------------------------------|---------------------------------------------|
| GET    | `/health`                     | Health check, returns books dir             |
| POST   | `/convert`                    | Same as `/api/rsvp/upload`                  |
| GET    | `/library`                    | List books                                  |
| GET    | `/library/<filename>`         | Download                                    |
| DELETE | `/library/<filename>`         | Delete                                      |

---

## Usage

### From the dashboard

Open the **RSVP Reader** card, pick a file (`.epub`, `.txt`, `.md`, `.html`),
optionally set title/author, hit **Convert & Save**. The browser downloads the
`.rsvp` immediately and the file is also stored on the Pi for later access via
the Library list.

### From the LCD

Settings → … → RSVP Reader → **Service Status** shows whether `waver-rsvp` is
running. The full library is managed from the dashboard.

### From curl

```bash
TOKEN=$(curl -s -X POST https://waver.local/api/auth/login \
        -H "Content-Type: application/json" \
        -d '{"password":"yourpassword"}' | jq -r .token)

curl -X POST https://waver.local/api/rsvp/upload \
     -H "Authorization: Bearer $TOKEN" \
     -F "file=@./book.epub" \
     -F "title=My Book" \
     -F "author=Some Author" \
     -o book.rsvp
```

---

## Configuration

| Env var              | Default                              | Purpose                          |
|----------------------|--------------------------------------|----------------------------------|
| `BOOKS_DIR`          | `/home/cimi/waver/rsvp-books`        | Where `.rsvp` files are stored   |
| `RSVP_HOST`          | `127.0.0.1`                          | Bind host of converter           |
| `RSVP_PORT`          | `5001`                               | Bind port of converter           |
| `RSVP_CONVERTER_URL` | `http://127.0.0.1:5001`              | Used by `waver-api` to reach it  |

---

## Troubleshooting

- **`502 converter unreachable`** — `waver-rsvp` isn't running.
  `sudo systemctl status waver-rsvp` and check `journalctl -u waver-rsvp -f`.
- **`415 Unsupported file type`** — extension isn't in
  `[.epub, .txt, .md, .markdown, .html, .htm]`.
- **Empty chapters in `.rsvp`** — `.txt` chapter detection is heuristic
  (matches `Chapter N`, `Prologue`, `Part N`). If your book uses an unusual
  heading style, edit the source file first.
- **`lxml` install fails on Pi Zero 2W** — install
  `sudo apt install libxml2-dev libxslt1-dev` then retry the pip install.
