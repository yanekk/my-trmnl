# trmnl-dashboard

An e-ink dashboard for a Seeed Studio TRMNL 7.5" device. A server we run on an
always-on home box builds one 800×480 monochrome screen — weather for Gdańsk,
live bus departures, and today/tomorrow from Google Calendar — and the device
fetches and displays it. The full design is in
[`plans/trmnl-dashboard/DESIGN.md`](plans/trmnl-dashboard/DESIGN.md).

## Running the tests

```
docker compose run --rm test
```

This runs `python -m pytest -q --color=no` inside the Python 3.12 image and is
the one canonical test command. It exits non-zero on failure and prints failures
in full. To see per-test detail while debugging, add `-v`; don't commit that.

Running the suite in a local Python 3.12 virtualenv with the pinned deps works
too and gives the same result:

```
pip install -e ".[test]"
python -m pytest -q --color=no
```

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
