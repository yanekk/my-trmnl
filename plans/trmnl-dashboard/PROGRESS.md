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

**Status:** T07 reviewed clean. All three leaf adapters (weather, bus, calendar) done and
reviewed; T00 and T07-OAuth hand-verified. 135 green. T08 (composition root, refresh loop,
config, degradation) is unblocked and next. Owner decision pending for T08: multi-day all-day
events currently vanish from today/tomorrow (see FINDINGS); untitled-event wording "(bez tytułu)"
to confirm.
**Last updated:** 2026-09-05
**Next `pir-work` will:** implement T08 (composition root, refresh loop, config, degradation).

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
| T06 | Bus adapter (ckan2 departures) | T02 | ✅ | Reviewed clean, no fix commit. All 9 test items defend real behaviour; empty-vs-down and per-pole isolation genuinely tested (dead pole → others render; all-fail → Failure). Probed: Py3.12 parses `Z` (else all poles fail); a malformed 227 row drops its whole pole; serial poles 10s each. Stale-image trap hit, 111 green with mount. |
| T07 | Google Calendar adapter (OAuth) | T02 | ✅ | Reviewed clean, no fix commit. Probed: no clock read (uses `now` arg), token never in log/reason, per-calendar merge atomic (any error→region Failure), all-day→Warsaw midnight matches model. Deviations sound. OAuth consent hand-verified by owner 2026-09-05. Gap logged: multi-day all-day events vanish (core/model, T08 owner decision). |
| T08 | Composition root, refresh loop, config, degradation | T03,T04,T05,T06,T07 | ⬜ | |
| T09 | Deploy on home box + on-device verification | T08 | ⬜ | Hand-verified with owner. |

**Review queue:** (empty)

## Blocked on the user

T07 OAuth consent is done (verified 2026-09-05, FINDINGS). Read-only token minted, stored 0o600
at ~/.config/trmnl/token.json on the dev Mac. Dashboard reads one calendar:
pd0pfl6q60afma9et1o2n46f1c@group.calendar.google.com (Madziojankowy kalendarz). T08 wires this
id and the token path into config. At T09 the token file must be copied to the deploy box (it is
portable — a refresh token — so no second consent is needed).

T09 still needs the physical device for on-device verification of the real dashboard. Config
values (stops, line, coordinates, calendar id) are collected during T05/T06/T09.
