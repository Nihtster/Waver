# Simulator

A pygame-based simulator for the LCD launcher that runs on macOS, Linux,
or Windows — no Raspberry Pi or Waveshare HAT required. Source:
[simulator/](../simulator).

Use it to iterate on launcher UI without redeploying to the Pi every save.

---

## Quick start

```bash
cd ~/Documents/Projects/Waver
python3 -m venv .venv
.venv/bin/pip install pygame watchdog pillow
.venv/bin/python3 simulator/run_sim.py
```

A 144×160 pygame window pops up showing the 128×128 LCD with a key-binding
hint strip below.

---

## Key bindings

| Key             | Maps to                       |
|------------------|------------------------------|
| ↑ / ↓            | `JOY_UP` / `JOY_DOWN`        |
| ← / Esc / H / M  | `KEY3` (back)                |
| → / Enter / Space| `JOY_PRESS` (select)         |
| K                | `KEY1` (confirm)             |
| L                | `KEY2` (jump to dashboard)   |
| F2               | Force hot-reload             |
| Q                | Quit                         |

Source: [simulator/sim_input.py](../simulator/sim_input.py:31).

---

## Hot reload

Save any `.py` file in [launcher/](../launcher) and the simulator
automatically:

1. Tears down the current `Launcher` (sets the stop event).
2. Unloads the launcher modules from `sys.modules`.
3. Re-imports them fresh.
4. Constructs a new `Launcher` with the same simulator backends.
5. Flashes a brief "reload" splash so you can see it happened.

Implementation: [simulator/run_sim.py](../simulator/run_sim.py:53). Uses
`watchdog` to watch the launcher directory; flips `stop_event` on any `.py`
modification.

State that persists across hot-reloads (because it lives outside the
reloaded modules):

- The pygame window
- The mock service manager (so toggle state survives)
- The simulator's display and input backends

State that does **not** persist: the current screen and selection — every
reload starts back at HOME.

If hot reload mis-fires (e.g. you saved an unrelated edit), press F2 to
force one manually.

---

## How the simulator plugs in

`Launcher.__init__` accepts optional backends for display, input, services,
network, and updater ([launcher.py:26](../launcher/launcher.py:26)). When
present, they're used instead of the real implementations. The simulator
provides a backend for each:

| Real component     | Simulator backend                                  |
|--------------------|----------------------------------------------------|
| `ST7735Fixed`      | [`SimDisplay`](../simulator/sim_display.py)        |
| `InputManager` GPIO| [`SimInput`](../simulator/sim_input.py)            |
| `ServiceManager`   | [`MockServiceManager`](../simulator/mock_services.py) |
| `network_info`     | [`mock_get_network`](../simulator/mock_network.py) |
| `updater`          | [`mock_updater`](../simulator/mock_updater.py)     |

`SimDisplay` accepts a PIL Image just like the real ST7735 driver. It
rasterises into the pygame surface instead of pushing over SPI.

`SimInput` reads pygame keyboard events and produces the same `InputEvent`
enum values that the hardware poller produces.

`MockServiceManager` keeps service states in memory — toggles flip a bool
instead of running `systemctl`.

`mock_updater.restart_services()` returns instead of calling `sys.exit(0)`,
so a simulated OTA flow lands you back at the settings screen instead of
crashing the simulator.

---

## Window scaling

Default `SCALE = 1` matches the physical 1.44" panel size on a Retina Mac
(2× HiDPI scaling ≈ 1.3" rendered). Bump `SCALE = 2` or `3` in
[run_sim.py:30](../simulator/run_sim.py:30) for a bigger preview — useful
when iterating on text legibility.

The font fallback in
[display_manager.py:30](../launcher/display_manager.py:30) picks Menlo on
macOS, DejaVuSansMono on Linux, and Arial / Helvetica as last resorts —
which is why the same glyph metrics render slightly differently between
simulator and Pi. Don't tune sub-pixel placement in the sim; verify on
hardware.

---

## What the simulator can't tell you

- Real SPI timing (the simulator has none).
- Display offset glitches — simulator renders to a perfect 128×128 buffer.
- Real button debounce behaviour (pygame keyboard is its own beast).
- Pi temperature, real network signal, real Pi-hole stats.

Treat the simulator as a UI iteration tool. Anything hardware-shaped
(driver tweaks, GPIO ordering, throughput) needs the actual Pi.
