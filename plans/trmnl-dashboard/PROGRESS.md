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

**Status:** T09 deployed on the Pi and running. `deploy/deploy.sh pi@<ip>` sets up a native
systemd service (no Docker on ARMv6); it serves `:8080` with all three sources live, verified
over HTTP. Owner render changes this session (diacritics, hourly icons, less-verbose layout,
realtime/scheduled bus labels, vehicle numbers) and 3.9-compat fixes for the Pi (tomli,
zip(strict), fromisoformat "Z"). Docker removed — tests run in the Mac's local `.venv`
(`.venv/bin/python -m pytest -q`): 175 green on 3.13, 161 on the Pi 3.9.
**Last updated:** 2026-09-06
This session (owner, on device): hourly weather strip now rolls the next 6 hours across midnight;
service refresh 60s→120s; overnight slow window set to 00:00–06:00 (fast 06:00→midnight, via
config `end="00:00"`→hour 24). All deployed live (181 green Mac, 167 Pi, `refresh_rate=120`).
Then owner added T10 (bus manufacturer+model); requirements refined and the task written, not
yet built. See FINDINGS.
**Next `pir-work` will:** implement T10 — the owner asked for it next, out of order, while T09's
on-device check stays with them. T09 stays 🟡 (implementation done, human verification pending);
do not treat it as having implementation work left.

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
| T09 | Deploy on home box + on-device verification | T08 | 🟡 | Deployed native on a Raspberry Pi (ARMv6, Raspbian 11, Python 3.9) via `deploy/deploy.sh`; systemd `trmnl-dashboard` active + enabled, serves `:8080`, all three sources verified live over HTTP. Docker deploy dropped (NAS/Pi have none). Outstanding, owner on the device: point the TRMNL at the Pi, judge cadence, confirm reboot recovery. Implementation complete; only the human device check remains. |
| T10 | Bus manufacturer + model before the fleet number | T03,T06,T08 | ⬜ | Owner-added 2026-09-06; requirements refined with the owner this session. ZTM vehicle DB (one JSON, all vehicles by fleet number → brand/model), disk-cached, re-downloaded only on a cache miss; unknown vehicle shows number only and retries each cycle; a DB failure never breaks the bus region. Task file has the three owner decisions. |

**Review queue:** empty. T09 is 🟡 — deployed and serving on the Pi; its implementation is
done and only the owner's on-device check (point the device, reboot check) remains, held open
at the owner's request. T10 is ⬜ with all deps ✅; the owner asked for it to be built next,
out of order, while T09's device check stays with them.

## Blocked on the user

T07 OAuth consent is done (verified 2026-09-05, FINDINGS). Read-only token minted, stored 0o600
at ~/.config/trmnl/token.json on the dev Mac. Dashboard reads one calendar:
pd0pfl6q60afma9et1o2n46f1c@group.calendar.google.com (Madziojankowy kalendarz). T08 wires this
id and the token path into config. At T09 the token file must be copied to the deploy box (it is
portable — a refresh token — so no second consent is needed).

T09 still needs the physical device for on-device verification of the real dashboard. Config
values (stops, line, coordinates, calendar id) are collected during T05/T06/T09.
