# LCD Launcher

The launcher is the on-device menu that runs on the 128×128 LCD. It owns
input polling, screen rendering, and service toggles. Source lives in
[launcher/](../launcher).

---

## Hardware controls

Three pushbuttons and a five-way joystick, all wired to GPIO with internal
pull-ups (active low).

| Input        | GPIO | Default action              |
|--------------|------|-----------------------------|
| KEY1 (top)    | 21  | Confirm / select            |
| KEY2 (middle) | 20  | Jump to dashboard screen    |
| KEY3 (bottom) | 16  | Back                        |
| Joystick UP    | 6  | Move selection up           |
| Joystick DOWN  | 19 | Move selection down         |
| Joystick LEFT  | 5  | Back                        |
| Joystick RIGHT | 26 | Confirm / select            |
| Joystick PRESS | 13 | Confirm / select            |

> Pin map was discovered via `gpio_scan.py`. The Waveshare HAT documentation
> had the wrong pins for this revision — trust the code, not the datasheet.

---

## Screens

| Screen        | Purpose                                                |
|---------------|--------------------------------------------------------|
| `HOME`        | WAVER logo, live Pi-hole / WireGuard status            |
| `TOOLS`       | Top-level menu — entry point for everything            |
| `PIHOLE`      | Pi-hole status, blocked-today count, top domain        |
| `HOTSPOT`     | AP toggle screen — SSID, password, status              |
| `WIREGUARD`   | WireGuard status, endpoint, RX/TX counters             |
| `WIFI_KIT`    | WiFi sub-menu (Scan, Deauth, Capture, Evil Twin)       |
| `WIFI_SCAN`   | Live list of nearby WiFi networks                      |
| `DASHBOARD`   | CPU / memory / uptime / client count                   |
| `SETTINGS`    | Hotspot, WiFi, Display, Check Update, About            |
| `UPDATE`      | OTA update flow (blocking)                             |
| `ABOUT`       | Version and credits                                    |
| `PLACEHOLDER` | Stub for unimplemented features                        |

Navigation rules live in [launcher.py](../launcher/launcher.py:225)
(`_back`) and the `destinations` map in `_select`.

---

## Architecture

```
┌─────────────┐
│  Launcher   │  main loop: render → input → state
└──────┬──────┘
       │
   ┌───┴────┬─────────────┬──────────────┬──────────────┐
   ▼        ▼             ▼              ▼              ▼
Display  Input       Service        Network        Updater
Manager  Manager     Manager        Info           (OTA)
   │        │             │              │              │
   ▼        ▼             ▼              ▼              ▼
ST7735   RPi.GPIO    systemctl      iwconfig /     git +
(SPI)    polling     subprocess     vcgencmd /     systemctl
                                    pihole API
```

### Main loop

[launcher.py:69](../launcher/launcher.py:69) — `Launcher.run()` is a tight
loop: render the current screen, block on the input queue with a per-screen
timeout, dispatch the event. Animated screens (HOME, ABOUT) use a 100ms
timeout so the waveform animates; static screens use 400ms to save power.

### Input handling

[input_manager.py](../launcher/input_manager.py) polls all GPIO pins in a
background thread every 50ms with a 200ms per-key debounce. Events go onto
a `deque(maxlen=10)`. `get_event(timeout)` is the only blocking call the
main loop makes.

Constructor takes an optional `backend` — when present, hardware GPIO is
skipped and the backend's `get_event` / `cleanup` are used. The simulator
plugs in here.

### Display rendering

[display_manager.py](../launcher/display_manager.py) wraps the ST7735
driver. Every `draw_*` method:

1. Acquires `self.lock` (one writer at a time over SPI).
2. Builds a fresh `PIL.Image` 128×128 RGB.
3. Composes the screen via shared primitives (`_status_bar`, `_divider`,
   `_footer`, `_page_dots`, `_waveform`, `_text`).
4. Pushes the finished image to the device with `device.display(img)`.

Text uses a custom renderer (`_text` at
[display_manager.py:58](../launcher/display_manager.py:58)) that draws into
a greyscale buffer, thresholds at 48 to kill antialias haze, and pastes as
a solid colour. `scale=2` does NEAREST pixel-doubling for headlines. The
result is crisp on a 128×128 panel where 11px text would otherwise smear.

Fonts are searched from a hard-coded list in
[display_manager.py:30](../launcher/display_manager.py:30) — DejaVuSansMono
on the Pi, Menlo on macOS for the simulator, then proportional fallbacks.

### Pagination

List screens (TOOLS, SETTINGS, WIFI_KIT, WIFI_SCAN) show 3 items per page.
`selected_index` is **global** across all items;
`_list_page` ([display_manager.py:162](../launcher/display_manager.py:162))
slices into the current page and converts the index to a local one.
Page-indicator dots render at y=110.

### Service control

[service_manager.py](../launcher/service_manager.py) wraps `systemctl` via
subprocess. Friendly names map to systemd unit names:

| Key         | systemd unit    |
|-------------|-----------------|
| `pihole`    | `pihole-FTL`    |
| `wireguard` | `wg-quick@wg0`  |
| `ssh`       | `ssh`           |
| `nginx`     | `nginx`         |

`get_status()` returns a `ServiceStatus` enum
(`ACTIVE` / `INACTIVE` / `FAILED` / `UNKNOWN`). `toggle()` checks status
and dispatches `start()` or `stop()`. All start/stop calls require sudo —
the launcher runs as root.

### OTA updates

[updater.py](../launcher/updater.py) implements a three-step flow:

1. `check_updates()` — `git fetch`, compare local HEAD to `@{u}`, return
   `up_to_date` / `available` / `error`.
2. `do_update()` — `git pull --ff-only`. Never merges.
3. `restart_services()` — `systemctl restart waver waver-api` via Popen,
   then `sys.exit(0)`. systemd brings the launcher back up on the new code.

`REPO_PATH` is the absolute path `/home/cimi/waver`. The service runs as
root, so `~` would expand to `/root` and break.

The blocking flow lives in `_run_update` at
[launcher.py:241](../launcher/launcher.py:241) — it pre-empts the normal
render loop and drives the LCD imperatively while waiting on user input
between steps.

---

## GPIO initialisation order — critical

`InputManager` **must** be initialised before `DisplayManager`.
`InputManager.__init__` calls `GPIO.setmode(BCM)`, which the ST7735 driver
relies on for its DC/RST/BL pins. The order is enforced in
[launcher.py:38](../launcher/launcher.py:38).

---

## Adding a new screen

1. Add a screen-id constant near the top of
   [launcher.py](../launcher/launcher.py:9).
2. Add a `draw_<name>(...)` method on `DisplayManager`. Reuse `_status_bar`,
   `_divider`, `_footer`, `_page_dots` for visual consistency.
3. Add an `elif self.screen == FOO:` branch in `Launcher._render`.
4. Wire navigation: add an entry in the `destinations` map in `_select`,
   and (if needed) a custom rule in `_back`.
5. If the screen is a list, call `_list_page` + `_draw_list` so pagination
   and the dot indicator work for free.

---

## Running standalone

For development on the Pi without systemd in the way:

```bash
sudo systemctl stop waver
sudo ~/waver-env/bin/python3 ~/waver/launcher/launcher.py
```

Logs go to stdout. `Ctrl-C` to exit cleanly (the `KeyboardInterrupt` handler
calls `_cleanup` → `input.cleanup()` → `GPIO.cleanup()`).

For development without a Pi, use the [simulator](simulator.md).
