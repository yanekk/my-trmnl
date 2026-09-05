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

**Status:** Plan written, then read back by a fresh session. Documents agree, the machine and the
three live data sources match the plan, and nothing is being rebuilt (empty repo). Nothing built
yet. Ready for the first `/pir-work`.
**Last updated:** 2026-09-05
**Next `pir-work` will:** implement T00 (the spike) — no dependencies. It needs the physical
device and the owner's hands; raise the handover and wait.

## Tasks

Legend: ⬜ not started · 🟡 in progress · 🔍 implemented, awaiting review · ✅ reviewed and
done · ⛔ blocked, needs a human.

| # | Task | Depends on | State | Notes |
|---|---|---|---|---|
| T00 | Spike: static image on the device | — | ⬜ | Throwaway. Needs the physical device + owner's hands. Gates image format and BYOS contract. |
| T01 | Skeleton, Docker, boundary guard test | T00 | ⬜ | |
| T02 | Pure core: assemble + refresh policy | T01 | ⬜ | |
| T03 | Pillow renderer → 1-bit BMP, golden-tested | T01, T02 | ⬜ | Heavy. Reference is prototype/mock.html. No top bar. Empty regions draw "brak odjazdów"/"Brak wydarzeń"; also renders the startup placeholder. |
| T04 | BYOS HTTP server | T01, T02 | ⬜ | Off critical path. Cold start serves the bundled placeholder (no image yet), never 404. |
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
