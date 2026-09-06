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
This session: T00–T10 all ✅ and hand-verified on the device (makers, cadence, reboot). Then
planned T11 (moon icons at night) as a Phase 4 amendment — DESIGN §2.2 + a decision, task file,
PLAN row. Probed on this machine: Open-Meteo returns a per-hour/current `is_day` flag (FINDINGS).
Phase 4 rides the normal build/review alternation with no separate plan-review (same as T10).
**Next `pir-work` will:** implement T11 (it is the only ⬜, deps T02/T03/T05 all ✅).

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
| T08 | Composition root, refresh loop, config, degradation | T03,T04,T05,T06,T07 | ✅ | Reviewed clean, no fix. Wiring signatures, Warsaw conversion, per-source timeouts, atomic `os.replace`, multi-day clip all probed; three deviations authorized. |
| T09 | Deploy on home box + on-device verification | T08 | ✅ | Deployed native on a Raspberry Pi (ARMv6, Raspbian 11, Python 3.9) via `deploy/deploy.sh`; systemd `trmnl-dashboard` active + enabled, serves `:8080`. On-device verified by owner 2026-09-06 (FINDINGS): device shows the board, cadence good (`refresh_rate=120`), reboot recovers. Docker dropped (NAS/Pi have none). |
| T10 | Bus manufacturer + model before the fleet number | T03,T06,T08 | ✅ | Reviewed clean, no fix. All `Config`/`assemble` call sites updated; vehicle line stays inside `[left,right]`, no collision; skip-empty-brand/model deviation safe. On-device visual verified by owner 2026-09-06 (FINDINGS): makers read right on real 227 rows. |
| T11 | Moon icons at night (day/night-aware weather icons) | T02,T03,T05 | ⬜ | Owner-added 2026-09-06. Open-Meteo `is_day` (fetched already, verified present) drives the icon in the pure core: sun→moon, part-cloud→moon-behind-cloud at night; every other icon unchanged. Two new line-art glyphs in the renderer, which stays day/night unaware. Only the hourly strip is drawn (big current icon removed 2026-09-06), so that is the visible change. Task file has the three owner decisions. |

**Review queue:** empty. T00–T10 are ✅ and hand-verified on the device. T11 is ⬜ (Phase 4
amendment) with all deps ✅ — the next `pir-work` implements it, then a later session reviews it.

## Blocked on the user

T07 OAuth consent is done (verified 2026-09-05, FINDINGS). Read-only token minted, stored 0o600
at ~/.config/trmnl/token.json on the dev Mac. Dashboard reads one calendar:
pd0pfl6q60afma9et1o2n46f1c@group.calendar.google.com (Madziojankowy kalendarz). T08 wires this
id and the token path into config. At T09 the token file must be copied to the deploy box (it is
portable — a refresh token — so no second consent is needed).

Nothing blocked. T09's on-device verification is done (owner, 2026-09-06, FINDINGS): the device
shows the board, cadence good, reboot recovers. Nothing on this plan now waits on the user.
