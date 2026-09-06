# Implementation plan

11 tasks in 5 phases. Each has a file in [tasks/](tasks/) with its goal, the files it touches,
the interfaces it defines, and what "done" means. T10 is an owner-added enhancement (2026-09-06),
appended after the original ten shipped.

Track state in [PROGRESS.md](PROGRESS.md). Read [DESIGN.md](DESIGN.md) first.

---

## Shape of the build

- **The riskiest unknown goes first, as a throwaway spike.** T00 proves the physical device
  will fetch and show an image from our own server before any real code is built on that
  assumption. It is the owner's stated top priority ("make it display anything"), and if the
  BYOS contract or image format is wrong we learn it in an afternoon, not in task nine.
- **Everything testable automatically is built and proven before the device is in the loop
  again.** Phases 1 and 2 build the pure core, the renderer and the data adapters entirely
  against fixtures and golden images. By the end of them the whole dashboard can be produced
  and checked without the device or any live network.
- **Recovery and honesty before the always-on deploy.** Degradation (a source down → an
  "unavailable" notice, last-good image kept) is wired in T08, before T09 stands the thing up
  to run unattended, so the first unattended failure is already handled.
- **The step that needs the device and the owner's Google account comes last**, with its
  hand-verification, because only it cannot be settled by the test command.

```
Phase 0  ▸  T00                     prove the ground             throwaway
Phase 1  ▸  T01 T02 T03 T04         core, renderer, server       no live data
Phase 2  ▸  T05 T06 T07             weather, bus, calendar        against fixtures
Phase 3  ▸  T08 T09                 integrate, deploy, verify     device in the loop
Phase 4  ▸  T10                     enhancements (post-deploy)    owner-added
```

---

## Phase 0 — Prove the ground

Nothing is designed on top of an assumption not checked on the real device.

| # | Task | Depends on |
|---|---|---|
| [T00](tasks/T00-spike-display.md) | Spike: make the device display a static image from our server | — |

**T00 gates the whole build.** It confirms three load-bearing assumptions on the physical
device: that the minimal BYOS contract (`/api/setup` + `/api/display` returning `image_url` +
`refresh_rate`) works as researched; that an 800×480 1-bit BMP is accepted and rendered
correctly; and that the wifi captive portal lets us point the device at a LAN server URL. If
the image format is wrong, the renderer (T03) target changes; if the contract differs, the
server (T04) changes. Throwaway code, deleted after its findings are recorded.

## Phase 1 — Core, renderer and server (no live data)

At the end: the dashboard image can be built from hand-made data and served over the BYOS API,
all proven by tests and golden images, with no network and no device.

| # | Task | Depends on |
|---|---|---|
| [T01](tasks/T01-skeleton.md) | Project skeleton, Docker, test harness, the module boundary and its guard test | T00 |
| [T02](tasks/T02-core.md) | Pure core: view-model, `assemble`, refresh policy, degradation, time bucketing | T01 |
| [T03](tasks/T03-renderer.md) | Pillow renderer: view-model → 800×480 1-bit BMP, golden-tested | T01, T02 |
| [T04](tasks/T04-byos-server.md) | BYOS HTTP server: `/api/setup`, `/api/display`, `/api/log`, image route | T01, T02 |

## Phase 2 — Data adapters (against fixtures)

At the end: each source can be fetched and parsed into the core's input shapes, proven against
recorded responses including the empty and broken cases. No live network in tests.

| # | Task | Depends on |
|---|---|---|
| [T05](tasks/T05-weather.md) | Weather adapter (Open-Meteo) → core input | T02 |
| [T06](tasks/T06-bus.md) | Bus adapter (ckan2 departures + stop-id resolution) → core input | T02 |
| [T07](tasks/T07-calendar.md) | Google Calendar adapter (OAuth read-only) → core input | T02 |

## Phase 3 — Integrate, deploy, verify

At the end: the real dashboard runs unattended on the home box and has been seen on the device.

| # | Task | Depends on |
|---|---|---|
| [T08](tasks/T08-integrate.md) | Composition root, refresh loop, config, end-to-end degradation | T03, T04, T05, T06, T07 |
| [T09](tasks/T09-deploy-verify.md) | Deploy on the home box, run at boot, on-device hand-verification | T08 |

## Phase 4 — Enhancements (post-deploy)

Owner-added work once the dashboard was running. Each rides the same build/review alternation;
no separate plan-review (the plan was already being built when these were added).

| # | Task | Depends on |
|---|---|---|
| [T10](tasks/T10-vehicle-info.md) | Bus manufacturer + model before the fleet number, from the ZTM vehicle database (disk-cached, miss-triggered refetch) | T03, T06, T08 |

---

## Critical path

```
T00 → T01 → T02 → T03 → T08 → T09
```

T04 sits off the path (it needs only T01 and T02's refresh policy) and can slot in any time
after T02. The three adapters T05, T06, T07 are independent of each other and of T03/T04; all
they need is T02, and all three feed T08. T07 carries the Google OAuth setup, which needs the
owner's hands, so start it early in Phase 2 to leave room for that round-trip.

## Rough sizing

| Weight | Tasks |
|---|---|
| **Heavy** | T03 (laying the whole layout out in Pillow against the mock), T00 (physical unknowns, hand-verified) |
| **Medium** | T02, T04, T06, T07, T08 |
| **Light** | T01, T05, T09 |

Where it will overrun: T03, because pixel layout and 1-bit dithering are fiddly and the golden
images have to be regenerated whenever the layout genuinely changes; and T07, because Google
OAuth for a personal/unverified app has a fiddly one-time consent that depends on the owner.

## Decisions still open

- **Exact config values** — the two stop ids (resolved from stop names), the line number, the
  Gdańsk coordinates, and which calendar id(s) to read — are collected from the owner during
  T05/T06/T07 and T09. They do not block the structure of any task.
- **Web framework vs standard library for the BYOS server** — settled inside T04 by whichever
  keeps the four endpoints smallest; it changes nothing outside `server/`.
- Nothing else is open, and nothing above blocks starting T00.
