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

**Status:** T04 implemented, awaiting review. BYOS server speaks the four firmware endpoints on
stdlib `http.server` (no framework dep); request logic is a socket-independent `App.handle` so
it is tested with synthetic requests, plus one real-socket integration test. `refresh_rate`
comes from the pure policy given an injected clock. Cold start serves the placeholder, never a
404. Suite green (69 tests). T00 still the only hand-verified task.
**Last updated:** 2026-09-05
**Next `pir-work` will:** review T04.

## Tasks

Legend: ⬜ not started · 🟡 in progress · 🔍 implemented, awaiting review · ✅ reviewed and
done · ⛔ blocked, needs a human.

| # | Task | Depends on | State | Notes |
|---|---|---|---|---|
| T00 | Spike: static image on the device | — | ✅ | Hand-verified with owner 2026-09-05: real TRMNL (FW 1.5.12) displayed our 800×480 1-bit BMP3 from the LAN server. spike/ deleted; contract corrections in FINDINGS. |
| T01 | Skeleton, Docker, boundary guard test | T00 | ✅ | Reviewed; guard now also catches `datetime.utcnow()`. Residual aliased-datetime / pathlib-I/O gaps in FINDINGS, left by design. |
| T02 | Pure core: assemble + refresh policy | T01 | ✅ | Reviewed clean. Both deviations (tz-aware `Event.start`, `HourPoint.time`) pull UTC→Warsaw into the core, correct per §3.1. Suite green. |
| T03 | Pillow renderer → 1-bit BMP, golden-tested | T01, T02 | ✅ | Reviewed. Five goldens eyeballed correct (populated, weather-down, empty-bus, empty-cal, startup); empty distinct from niedostępne; weekday map verified (2026-09-05=sb). Fixed: documented regen command lacked the `-v "$PWD":/app` mount, silently discarding regen (6492dfd). Plain titles owner-approved (§7); T08 adds a labels hook to `render()`. 53 green. |
| T04 | BYOS HTTP server | T01, T02 | 🔍 | stdlib `http.server`, no framework dep (DESIGN §5 left the choice here). `App.handle(method,path,headers,body)→Response` is socket-free and synthetic-tested; `_Handler`+`make_server` add the socket. Headers read case/separator-insensitively; `/api/setup/` trailing slash handled. `image_url` from request Host. Filename is a content hash (skips redundant flashes — unverified on device, see FINDINGS). Cold start → placeholder, never 404. Review it. |
| T05 | Weather adapter (Open-Meteo) | T02 | ⬜ | |
| T06 | Bus adapter (ckan2 departures) | T02 | ⬜ | |
| T07 | Google Calendar adapter (OAuth) | T02 | ⬜ | Needs owner's Google account for one-time consent. Start early. |
| T08 | Composition root, refresh loop, config, degradation | T03,T04,T05,T06,T07 | ⬜ | |
| T09 | Deploy on home box + on-device verification | T08 | ⬜ | Hand-verified with owner. |

**Review queue:** T04

## Blocked on the user

Nothing right now. T00 is done (device verified on home wifi). Two things still need the owner
later: T09 needs the physical device again for on-device verification of the real dashboard; T07
needs a one-time Google sign-in and a Google Cloud project. Config values (stops, line,
coordinates, calendar id) are collected during T05/T06/T07/T09.
