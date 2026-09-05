# T08 — Composition root, refresh loop, config, end-to-end degradation

**Phase:** 3 · **Depends on:** T03, T04, T05, T06, T07 · **Weight:** medium

## Goal

Wire the pieces into a running whole: fetch the three sources, hand what came back plus the
current time to the core, render the image, and publish it for the server to serve — repeating
on a cadence. This is where the config file is read, where a slow or failed source is turned
into an "unavailable" region rather than a crash, and where the last-good image is preserved
when a rebuild fails. After this task the real dashboard exists end to end; only running it on
the box unattended and seeing it on the device remain.

## Design sections this implements

DESIGN.md §2.6 (degradation, timeouts, last-good image, atomic publish), §3.4 (data flow),
§3.5 (storage, config), §2.5 (the loop respects the refresh policy the server reports).

## Files

- `trmnl/server/loop.py` — the composition root and refresh loop.
- `trmnl/adapters/config.py` — load and validate the config file.
- `config.example.toml` — documented example config.
- `tests/server/test_loop.py`.

## Interface

```python
@dataclass(frozen=True)
class Config:
    lat: float; lon: float
    stops: list[str]; line: str; near_minutes: int
    calendar_ids: list[str]
    service_start: time; service_end: time      # Europe/Warsaw, drive refresh policy
    image_path: str

def build_once(config, now, clients) -> BuildResult   # fetch → assemble → render → publish
def run_loop(config, clock, clients) -> None          # build_once on a cadence
```

- Each source is fetched with its own timeout; a source that fails or times out becomes a
  `Failure` in `Sources`, and the region degrades — one bad source never fails the build.
- `build_once` renders and publishes via the renderer's temp+rename, so the served image is
  always whole. If rendering itself fails, the last-good image is kept and the failure logged.
- The loop's cadence is independent of the device; the device gets its own `refresh_rate` from
  the server. Fetch frequency here is at least as often as the fastest device refresh.
- The server is wired to T03's committed startup placeholder so that, before `build_once` first
  succeeds (cold start / just after a reboot), the device is served the "Uruchamianie…"
  placeholder rather than a 404 (DESIGN §2.6). `build_once`'s first success replaces it.
- Config is validated on load with clear errors (missing calendar id, bad coordinate).

## Tests

- [ ] `build_once` with all sources healthy publishes a whole image (temp+rename observed).
- [ ] One source failing (e.g. bus timeout) still publishes; that region is marked unavailable.
- [ ] All three sources failing still publishes a valid image with three unavailable regions.
- [ ] A rendering failure keeps the previous image (last-good) and logs, does not crash the loop.
- [ ] Before the first successful `build_once`, the served image is the startup placeholder.
- [ ] Config load rejects a missing/invalid field with a clear message.
- [ ] The loop calls `build_once` repeatedly using the injected clock (no real sleep in tests).

## Done when

- [ ] End to end, from config + stubbed clients + a fixed clock, a correct image is published.
- [ ] Every degradation path in DESIGN §2.6 is exercised by a test and none crashes the loop.
- [ ] The suite is green and quiet; `config.example.toml` documents every field.
