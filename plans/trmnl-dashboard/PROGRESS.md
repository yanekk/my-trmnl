# Progress

**Update this whenever a task changes state.** It is the handoff between sessions; a stale
tracker costs the next session more than keeping it current ever saves.

**What the build taught lives next door in [FINDINGS.md](FINDINGS.md)** — read the rows
touching the task you pick up, and append yours there.

**Sixty words to a Notes cell, counted.** Flat prose, no bold-per-clause. The cell is an index
for the next session; the account is the commit message. Whoever writes a cell also fixes the
over-budget cell they walk past.

**Plan reviewed:** 2026-09-05 — clean of mechanical defects; 3 decisions taken with the owner
(no on-screen clock/top bar; empty regions show a short line; cold-start "Uruchamianie…" placeholder).

**Status:** T09 build half done: production `dashboard` compose service (`restart: always`) +
README deploy note. Several owner-directed render changes on 2026-09-06: diacritics fixed
(`_tracked` baseline), hourly weather icons, then a less-verbose pass (region titles removed
except DZIŚ/JUTRO, no main icon, one-line "13° · 20 km/h", compact centred hourly stack, no bus
separators), then bus labels driven by the feed's realtime/scheduled status (GPS → "za N min",
schedule-only → clock), and the vehicle fleet number under each time ("—" when none; DESIGN §2.3).
Design iterated on a local venv server (see FINDINGS); goldens regenerated, 171 green.
T09 deploy target chosen: a Raspberry Pi (ARMv6, Raspbian 11, Python 3.9), native (no Docker on
the box); NAS ruled out. Code made 3.9-compatible (tomli fallback, requires-python >=3.9).
Next: install deps on the Pi, run as a systemd service, then on-device verification with the owner.
**Last updated:** 2026-09-06
**Next `pir-work` will:** review T09's deploy artifacts once the owner has confirmed on device.

## Tasks

Legend: ⬜ not started · 🟡 in progress · 🔍 implemented, awaiting review · ✅ reviewed and
done · ⛔ blocked, needs a human.

| # | Task | Depends on | State | Notes |
|---|---|---|---|---|
| T00 | Spike: static image on the device | — | ✅ | Hand-verified with owner 2026-09-05: real TRMNL (FW 1.5.12) displayed our 800×480 1-bit BMP3 from the LAN server. spike/ deleted; contract corrections in FINDINGS. |
| T01 | Skeleton, Docker, boundary guard test | T00 | ✅ | Reviewed; guard now also catches `datetime.utcnow()`. Residual aliased-datetime / pathlib-I/O gaps in FINDINGS, left by design. |
| T02 | Pure core: assemble + refresh policy | T01 | ✅ | Reviewed clean; both deviations pull UTC→Warsaw into the core, correct per §3.1. |
| T03 | Pillow renderer → 1-bit BMP, golden-tested | T01, T02 | ✅ | Reviewed clean. Five goldens eyeballed; empty distinct from niedostępne. Golden regen must mount `-v "$PWD":/app` (see FINDINGS). T08 adds a labels hook to `render()`. |
| T04 | BYOS HTTP server | T01, T02 | ✅ | Reviewed clean. Stateless `App`, content-hash filename, cold-start placeholder, 204 on bad body, `.bmp` route ignores path. Flash-skip unverified on device (T09). |
| T05 | Weather adapter (Open-Meteo) | T02 | ✅ | Reviewed clean; fix 5a31177 added `timezone`/`forecast_days` request assertions. tz contract probed (safe only because request pins `timezone=GMT`). |
| T06 | Bus adapter (ckan2 departures) | T02 | ✅ | Reviewed clean. Per-pole isolation tested (dead pole → others render; all-fail → Failure). A malformed 227 row drops its whole pole; poles fetched serially, 10s each. |
| T07 | Google Calendar adapter (OAuth) | T02 | ✅ | Reviewed clean. OAuth consent hand-verified by owner 2026-09-05 (FINDINGS). Multi-day all-day gap handed to T08. |
| T08 | Composition root, refresh loop, config, degradation | T03,T04,T05,T06,T07 | ✅ | Reviewed clean, no fix commit. 168 green. Probed past the doc: every wiring signature (adapters, App, make_server) matches the real callee, not just the loop stubs; UTC `_clock` is converted to Warsaw in `refresh_seconds`; each source bounded by its httpx timeout; `os.replace` keeps the image atomic; multi-day span clips exclusive `[d0,d_end)` to today/tomorrow. Three deviations authorized. |
| T09 | Deploy on home box + on-device verification | T08 | 🟡 | Build half done: `dashboard` service in docker-compose.yml (`restart: always`, port 8080, `/config` + `trmnl-data` mounts), README deploy note, 168 green. Outstanding half needs the owner on the device: cadence, live data, attribution, reboot recovery. Handover raised; awaiting owner. |

**Review queue:** empty. T09 is 🟡 — its deploy artifacts are built; the on-device
verification with the owner is outstanding before it can be reviewed and closed.

## Blocked on the user

T07 OAuth consent is done (verified 2026-09-05, FINDINGS). Read-only token minted, stored 0o600
at ~/.config/trmnl/token.json on the dev Mac. Dashboard reads one calendar:
pd0pfl6q60afma9et1o2n46f1c@group.calendar.google.com (Madziojankowy kalendarz). T08 wires this
id and the token path into config. At T09 the token file must be copied to the deploy box (it is
portable — a refresh token — so no second consent is needed).

T09 still needs the physical device for on-device verification of the real dashboard. Config
values (stops, line, coordinates, calendar id) are collected during T05/T06/T09.
