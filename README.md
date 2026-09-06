# trmnl-dashboard

An e-ink dashboard for a Seeed Studio TRMNL 7.5" device. A server we run on an
always-on home box builds one 800×480 monochrome screen — weather for Gdańsk,
live bus departures, and today/tomorrow from Google Calendar — and the device
fetches and displays it. The full design is in
[`plans/trmnl-dashboard/DESIGN.md`](plans/trmnl-dashboard/DESIGN.md).

## Running the tests

Set up a virtualenv once (Python 3.11+), then run the suite:

```
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest -q
```

It exits non-zero on failure and prints failures in full. To see per-test detail
while debugging, add `-v`.

The renderer's golden-image tests compare pixels exactly, so the committed goldens
are tied to the font rendering of the machine that made them (this dev Mac). If you
change the layout — or run the tests on another machine — regenerate them there:

```
REGEN_GOLDENS=1 .venv/bin/python -m pytest tests/render
```

The deploy Pi runs Python 3.9; for changes that parse external data or touch newer
stdlib, also run the suite on the Pi, skipping the machine-specific render goldens:
`.venv/bin/python -m pytest --ignore=tests/render`.

## Deploying to the box

The always-on box is a Raspberry Pi on the same LAN as the device (never exposed to
the internet — DESIGN §5.2). The Pi has no Docker, so the server runs **natively**
as a systemd service. One command from a dev machine deploys or updates it.

First, in the repo root (both git-ignored, so they never get committed):

- `config.toml` — copied from [`config.example.toml`](config.example.toml) and
  filled in with the household's coordinates, stops, line and calendar id. Leave the
  paths using `~` (they resolve to the deploy user's home on the box):

  ```toml
  [calendar]
  token_path = "~/.config/trmnl/token.json"

  [server]
  image_path = "~/trmnl-dashboard/screen.bmp"
  ```

- `token.json` — the OAuth refresh token from the one-time consent on the dev Mac
  (DESIGN §3.5). It is portable, so no second consent is needed.

Then:

```
deploy/deploy.sh pi@<box-ip>        # e.g. deploy/deploy.sh pi@192.168.0.185
```

This rsyncs the code, copies the two secrets over the same SSH key, then runs
`deploy/install.sh` on the box: it installs the system Pillow and a venv from `apt`,
the pure-Python deps with `pip`, and a `trmnl-dashboard` systemd service. The
service is `Restart=always` and enabled at boot, so it comes back on failure and
after a reboot; the device keeps its last screen while the server is down and
self-heals when it returns (DESIGN §6). Re-run `deploy/deploy.sh` any time to
update — it is idempotent.

Point the TRMNL at `http://<box-ip>:8080` via its wifi captive portal (as in the
T00 spike — resettable, DESIGN §6). Check the service on the box with
`systemctl status trmnl-dashboard` and `journalctl -u trmnl-dashboard -f`.

## Layout

The package is split along the one architectural boundary the design rests on
(DESIGN §3.1):

- `trmnl/core/` — pure: fetched data + the current time in, a view-model and the
  refresh interval out. No clock, no network, no file I/O, no Pillow.
- `trmnl/adapters/` — world-facing: the weather, bus and calendar HTTP clients,
  the system clock, and config.
- `trmnl/render/` — deterministic drawing: view-model → 800×480 1-bit BMP.
- `trmnl/server/` — the BYOS HTTP API and the refresh loop.

`tests/test_boundary.py` guards the core's purity with a static scan. If it
fails, move the offending code out of `core/` — never relax the test.
