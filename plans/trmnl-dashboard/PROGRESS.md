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

**Status:** T06 reviewed clean, no fix commit. Bus adapter (resolve_stop_ids + fetch_departures
+ fetch_stops) confirmed: per-pole isolation and the empty-vs-down distinction are genuinely
tested, Py3.12 parses the feed's `Z` times, boundary intact. All of Phase 2's leaf adapters
(T05 weather, T06 bus) are now done; only T07 (calendar, needs owner's Google account) remains
before T08 integration. T00 still the only hand-verified task. 111 green.
**Last updated:** 2026-09-05
**Next `pir-work` will:** implement T07 (Google Calendar adapter) — needs owner's Google account
for one-time OAuth consent; see "Blocked on the user".

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
| T05 | Weather adapter (Open-Meteo) | T02 | ✅ | Reviewed. Code clean. Probed the tz contract: `.replace(tzinfo=utc)` is safe only because the request pins `timezone=GMT`; core keeps hourly points where `time>now` and Warsaw-date==today, so null-precip→0% far-horizon hours never leak in; `forecast_days=2` genuinely needed at the UTC-day boundary. Fix: request test asserted units but not `timezone`/`forecast_days` — a silent-mislabel gap; added those assertions (5a31177). 83 green. |
| T06 | Bus adapter (ckan2 departures) | T02 | ✅ | Reviewed clean, no fix commit. All 9 test items defend real behaviour; empty-vs-down and per-pole isolation genuinely tested (dead pole → others render; all-fail → Failure). Probed: Py3.12 parses `Z` (else all poles fail); a malformed 227 row drops its whole pole; serial poles 10s each. Stale-image trap hit, 111 green with mount. |
| T07 | Google Calendar adapter (OAuth) | T02 | ⬜ | Needs owner's Google account for one-time consent. Start early. |
| T08 | Composition root, refresh loop, config, degradation | T03,T04,T05,T06,T07 | ⬜ | |
| T09 | Deploy on home box + on-device verification | T08 | ⬜ | Hand-verified with owner. |

**Review queue:** empty

## Blocked on the user

Nothing right now. T00 is done (device verified on home wifi). Two things still need the owner
later: T09 needs the physical device again for on-device verification of the real dashboard; T07
needs a one-time Google sign-in and a Google Cloud project. Config values (stops, line,
coordinates, calendar id) are collected during T05/T06/T07/T09.
