# T04 — BYOS HTTP server

**Phase:** 1 · **Depends on:** T01, T02 · **Weight:** medium

## Goal

Speak the small HTTP protocol the TRMNL firmware expects, so the device can provision itself,
ask what to show, and fetch the image. This is the thin world-facing edge on the device side:
it serves the current image file and tells the device how long to sleep, taking the interval
from the pure refresh policy. Built against a placeholder image so it is complete and tested
before the real image pipeline (T08) is wired in.

## Design sections this implements

DESIGN.md §2.5 (`refresh_rate` in the response, from the pure policy), §2.6 (odd headers read
case/separator-insensitively; last-good image kept), §3.4 (data flow), §5.2 (LAN-only bind).

## Files

- `trmnl/server/app.py` — the endpoints and the image route.
- `tests/server/test_app.py`.

## Interface

```
GET  /api/setup    -> 200 {"api_key","friendly_id","image_url","status":200}
GET  /api/display  -> 200 {"filename","image_url","refresh_rate","reset_firmware":false,
                           "update_firmware":false}
POST /api/log      -> 204   (body logged at info; never 5xx back to the device)
GET  /<image>.bmp  -> the current image bytes, or the last-good image if a rebuild failed
```

- Request header access is case- and separator-insensitive (`ACCESS_TOKEN`, `Access-Token`,
  `access_token` all resolve); only `ID` is required.
- `refresh_rate` comes from `core/refresh.py` given the current time — the server reads the
  clock (it is on the world-facing side) and passes it in.
- `image_url` is built from the request host so it resolves on the LAN.
- The server binds to the LAN interface, not the public internet (DESIGN §5.2).
- Image fallback order, so the device is never handed a 404 or a blank: serve the current image
  if one exists; else the last-good image if a rebuild failed; else, on cold start when no image
  has ever been built, the bundled "Uruchamianie…" startup placeholder (DESIGN §2.6, §3.5). The
  placeholder is supplied to the server as a path (wired to T03's committed asset in T08), so
  T04 can be built and tested against a fixture placeholder before T03 lands.

## Tests

- [ ] `/api/display` returns valid JSON with `image_url` and an integer `refresh_rate`.
- [ ] `refresh_rate` reflects the injected clock: a service-hours time → 60, an overnight time → 1800.
- [ ] Header parsing resolves `ACCESS_TOKEN`, `Access-Token`, `access_token` to the same value.
- [ ] A request missing optional telemetry headers still succeeds (only `ID` required).
- [ ] `/api/log` returns 204 and never errors, even on a malformed body.
- [ ] The image route serves the last-good image when the current build is marked failed.
- [ ] Cold start (no image ever built) serves the startup placeholder, not a 404 or a blank.
- [ ] `image_url` host matches the request host (resolves on the LAN, not a hardcoded address).

## Done when

- [ ] All four endpoints behave as above under synthetic requests, proven by the suite.
- [ ] The clock is injected, so `refresh_rate` is tested without waiting on real time.
- [ ] The suite is green and quiet.
