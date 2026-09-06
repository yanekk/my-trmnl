# T10 — Bus manufacturer + model on each departure row

**Phase:** 4 (enhancement, post-deploy) · **Depends on:** T03, T06, T08 · **Weight:** medium

Owner-added amendment (2026-09-06), agreed after T09 stood the dashboard up. Requirements
refined with the owner in this session; the three decisions are recorded below and in DESIGN §2.3.

## Goal

Show the vehicle's manufacturer and model before its fleet number on each tracked bus row, e.g.
"Solaris Urbino 12 · 2520". The data is the ZTM vehicle database (one JSON file listing all
~509 vehicles by fleet number, each with `brand` and `model`). Download it, cache it on disk,
and re-download only when the schedule contains a fleet number not already in the cache.

## The three decisions (owner, 2026-09-06)

1. **Layout: same line, shorten if long.** The line under the departure time becomes
   "`{brand} {model} · {number}`". If it does not fit the column, trim the model (drop trailing
   words, then ellipsize) while always keeping the brand and the number. Row height is unchanged
   so the same number of departures still fit.
2. **Cache on disk, miss-triggered refetch.** The parsed list is persisted to a JSON file and
   reloaded on startup. On any cycle whose schedule carries a fleet number absent from the
   cache, re-download the whole list (it contains every vehicle) and rewrite the file.
3. **Unknown vehicle → number only, retry each cycle.** A tracked bus whose number is still
   absent after a download (a brand-new bus not yet in ZTM's list, or a download that failed)
   shows just its number. Because it stays a cache miss, the next cycle re-downloads again — the
   owner accepted hitting ZTM every refresh while an unknown is present. No suppression.

## Design sections this implements

DESIGN.md §2.3 (bus row now carries brand/model before the fleet number; the vehicle-database
source, its disk cache and miss-triggered refetch), §2.6 (a vehicle-database failure never
fails the bus region — rows still render with numbers), §3.1 (world-facing adapter; the fetch
and cache live in the composition root, the core stays pure and takes the lookup as a parameter).

## Data source

`https://files.cloudgdansk.pl/d/otwarte-dane/ztm/baza-pojazdow.json?v=2` (~340 KB, no key).
Shape: `{metadata: {sourceDate, ...}, count, results: [ {vehicleCode, brand, model,
transportationType, ...}, ... ]}`. `vehicleCode` is a string and unique across the file;
buses (`transportationType == "Autobus"`) always carry non-empty `brand` and `model`. The
departures feed's `vehicleCode` is an int stringified in T06 — match on `str(code)`.

## Files

- `trmnl/adapters/vehicles.py` — world-facing fetch + parse of the vehicle database.
- `trmnl/core/model.py` — new `VehicleInfo(brand, model)`; `BusRow` gains `maker: str | None`.
- `trmnl/core/assemble.py` — `assemble(..., vehicles=...)`; `_bus_rows` composes `maker`.
- `trmnl/server/loop.py` — a `VehicleCache` (load/persist a JSON file; `ensure(codes, client)`
  fetches on a miss, keeps the old cache on a failed fetch); `build_once` collects the bus
  codes, ensures the cache, and passes the lookup to `assemble`.
- `trmnl/adapters/config.py` — optional `vehicle_cache_path` (server section), defaulting to
  `vehicles.json` beside `image_path`.
- `trmnl/render/screen.py` — the bus row draws `maker · number`, trimming the maker to fit.
- `tests/adapters/fixtures/ztm_vehicles_sample.json`, `tests/adapters/test_vehicles.py`,
  additions to `tests/core/test_assemble.py`, `tests/server/test_loop.py`, `tests/render/`.

## Interface

```python
# adapters/vehicles.py — world-facing only; no clock, no disk.
def fetch_vehicles(client: httpx.Client, url: str = _VEHICLES_URL) -> dict[str, VehicleInfo] | Failure

# core/model.py
@dataclass(frozen=True)
class VehicleInfo:
    brand: str
    model: str

# core/assemble.py
def assemble(sources, now, *, near_minutes=..., vehicles: Mapping[str, VehicleInfo] = {}) -> Dashboard
```

- `fetch_vehicles` returns `{vehicleCode: VehicleInfo}` on a clean 200, or `Failure` on any
  network error, non-200, or unparseable/wrong-shaped body — never raising (DESIGN §2.6).
- `assemble` sets each `BusRow.maker` to `"{brand} {model}"` when the departure's code is in
  `vehicles`, else `None`; the fleet-number logic (`vehicle`, "—") is unchanged. Empty
  `vehicles` (the failure/cold path) yields all-`None` makers, i.e. number-only rows.
- The disk cache and the miss-triggered fetch are the composition root's job, not the core's or
  the adapter's. A fetch failure leaves the on-disk cache intact.
- The vehicle fetch is bounded by its own httpx timeout and is isolated so it never delays or
  fails the other regions.

## Tests

- [ ] `fetch_vehicles` parses the sample into `{code: VehicleInfo}`; a known bus code maps to
      the right brand/model; the code key is a string.
- [ ] `fetch_vehicles` returns `Failure` (not raises) on network error, non-200, non-JSON, and a
      body missing `results`.
- [ ] `assemble`: a departure whose code is in `vehicles` gets `maker == "Brand Model"`; a code
      absent from `vehicles` gets `maker is None` (number still shown); a schedule-only row (no
      code) keeps `vehicle == "—"` and `maker is None`.
- [ ] `VehicleCache.ensure`: fetches when a code is missing; does **not** fetch when every code
      is already cached; a failed fetch keeps the previous cache and returns it.
- [ ] The cache round-trips through its file: written on update, reloaded on a fresh instance.
- [ ] Renderer: a row with a long maker ("Solaris Urbino 12 Electric") trims the maker but keeps
      "· number"; a row with no maker draws the number alone; "—" unchanged. Goldens regenerated.
- [ ] No test hits the network.

## Done when

- [ ] Tracked bus rows show "Brand Model · number"; unknown-code rows show the number alone;
      schedule-only rows show "—" — all from fixtures and goldens.
- [ ] The vehicle list is downloaded only when the schedule holds a code not already cached, the
      cache persists on disk across a restart, and a download failure leaves the bus region
      rendering numbers (never "niedostępne" for a vehicle-database problem).
- [ ] The suite is green and quiet on the Mac; and on the Pi 3.9 (`--ignore=tests/render`),
      because this parses external data (see CLAUDE.md deploy note).

## Needs a person

The parsing and layout are fully testable here. What only the device shows: that the brand/model
read correctly for real tracked buses on the board. Fold this into the next on-device pass
(with T09) — point the device, watch a few realtime 227 rows, confirm the makers look right —
and record it dated in FINDINGS.
