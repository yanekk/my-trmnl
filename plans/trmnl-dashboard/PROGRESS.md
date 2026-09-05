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

**Status:** T02 implemented, awaiting review. Pure core (model, assemble, refresh) in; suite
green (39 tests) via `docker compose run --rm --build test`. T00 still the only hand-verified
task.
**Last updated:** 2026-09-05
**Next `pir-work` will:** review T02.

## Tasks

Legend: ⬜ not started · 🟡 in progress · 🔍 implemented, awaiting review · ✅ reviewed and
done · ⛔ blocked, needs a human.

| # | Task | Depends on | State | Notes |
|---|---|---|---|---|
| T00 | Spike: static image on the device | — | ✅ | Hand-verified with owner 2026-09-05: real TRMNL (FW 1.5.12) displayed our 800×480 1-bit BMP3 from the LAN server. spike/ deleted; contract corrections in FINDINGS. |
| T01 | Skeleton, Docker, boundary guard test | T00 | ✅ | Reviewed; guard now also catches `datetime.utcnow()`. Residual aliased-datetime / pathlib-I/O gaps in FINDINGS, left by design. |
| T02 | Pure core: assemble + refresh policy | T01 | 🔍 | model/assemble/refresh + 24 tests (39 total). Two deviations from task interface, kept in commit msg: `Event.start` is a required tz-aware datetime not `datetime\|None` (all-day needs a date to bucket; local-midnight, `all_day` only gates the label); `HourPoint` carries tz-aware `time` not `hour:int` so all UTC→Warsaw conversion stays in core. |
| T03 | Pillow renderer → 1-bit BMP, golden-tested | T01, T02 | ⬜ | Heavy. Reference is prototype/mock.html. No top bar. Empty regions draw "brak odjazdów"/"Brak wydarzeń"; also renders the startup placeholder. |
| T04 | BYOS HTTP server | T01, T02 | ⬜ | Off critical path. Cold start serves the bundled placeholder (no image yet), never 404. |
| T05 | Weather adapter (Open-Meteo) | T02 | ⬜ | |
| T06 | Bus adapter (ckan2 departures) | T02 | ⬜ | |
| T07 | Google Calendar adapter (OAuth) | T02 | ⬜ | Needs owner's Google account for one-time consent. Start early. |
| T08 | Composition root, refresh loop, config, degradation | T03,T04,T05,T06,T07 | ⬜ | |
| T09 | Deploy on home box + on-device verification | T08 | ⬜ | Hand-verified with owner. |

**Review queue:** T02

## Blocked on the user

Nothing right now. T00 is done (device verified on home wifi). Two things still need the owner
later: T09 needs the physical device again for on-device verification of the real dashboard; T07
needs a one-time Google sign-in and a Google Cloud project. Config values (stops, line,
coordinates, calendar id) are collected during T05/T06/T07/T09.
