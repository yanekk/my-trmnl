# Progress

**Update this whenever a task changes state.** It is the handoff between sessions; a stale
tracker costs the next session more than keeping it current ever saves.

**What the build taught lives next door in [FINDINGS.md](FINDINGS.md)** — read the rows
touching the task you pick up, and append yours there.

**Sixty words to a Notes cell, counted.** Flat prose, no bold-per-clause. The cell is an index
for the next session; the account is the commit message. Whoever writes a cell also fixes the
over-budget cell they walk past.

**Plan reviewed:** not yet — run `/pir-review-plan trmnl-dashboard` before the first `/pir-work`

**Status:** Plan just written by the planning session. Requirements, a device/architecture
research pass, and an owner-approved visual mock are all done. Nothing built yet. The plan must
be read back by a fresh session before any task starts.
**Last updated:** 2026-09-05
**Next `pir-work` will:** nothing yet — it refuses to build until the plan is reviewed. After
review, the first task is T00 (the spike), which has no dependencies.

## Tasks

Legend: ⬜ not started · 🟡 in progress · 🔍 implemented, awaiting review · ✅ reviewed and
done · ⛔ blocked, needs a human.

| # | Task | Depends on | State | Notes |
|---|---|---|---|---|
| T00 | Spike: static image on the device | — | ⬜ | Throwaway. Needs the physical device + owner's hands. Gates image format and BYOS contract. |
| T01 | Skeleton, Docker, boundary guard test | T00 | ⬜ | |
| T02 | Pure core: assemble + refresh policy | T01 | ⬜ | |
| T03 | Pillow renderer → 1-bit BMP, golden-tested | T01, T02 | ⬜ | Heavy. Reference is prototype/mock.html. |
| T04 | BYOS HTTP server | T01, T02 | ⬜ | Off critical path. |
| T05 | Weather adapter (Open-Meteo) | T02 | ⬜ | |
| T06 | Bus adapter (ckan2 departures) | T02 | ⬜ | |
| T07 | Google Calendar adapter (OAuth) | T02 | ⬜ | Needs owner's Google account for one-time consent. Start early. |
| T08 | Composition root, refresh loop, config, degradation | T03,T04,T05,T06,T07 | ⬜ | |
| T09 | Deploy on home box + on-device verification | T08 | ⬜ | Hand-verified with owner. |

**Review queue:** *(empty)*

## Blocked on the user

Nothing right now. Two things will need the owner during the build, flagged so they are not a
surprise: T00 and T09 need the physical device on home wifi and the captive-portal setup; T07
needs a one-time Google sign-in and a Google Cloud project. Config values (stops, line,
coordinates, calendar id) are collected during T05/T06/T07/T09.
