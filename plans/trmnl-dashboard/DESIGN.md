# TRMNL Dashboard — Design

## 1. Purpose

A wall or desk e-ink dashboard for one person at home. A Seeed Studio TRMNL 7.5" device
(800×480 monochrome e-ink, XIAO ESP32-S3, stock firmware) shows one glanceable screen with
three things: current weather for Gdańsk, the next live bus departures for one line, and the
owner's Google Calendar for today and tomorrow. A server we run on an always-on box at home
builds the screen image; the device fetches and displays it.

The device is display-only. It wakes on a timer, asks the server for an image, draws it, and
sleeps. There is no interaction, no input, nothing to click. The whole product is the picture
the server produces.

### Success criteria

- The device shows our three-region dashboard, refreshed automatically, with no manual step
  after first setup.
- Bus times on screen are live (include real delays) and at most about two minutes stale during
  service hours.
- Weather, buses and calendar each show correct current data for Gdańsk / the owner's calendar.
- When one data source is down, its region says so and the other two keep working.
- The owner's calendar and location never leave the home network.

### Stance

- **One combined screen, all three regions at once.** Confirmed against a mock (§7). Rotating
  screens were rejected because a glance should answer all three questions without waiting.
- **The screen is built by drawing, not by a browser.** Python + Pillow renders a fixed
  800×480 1-bit image. See §3 and §7 for why this beats a headless browser here.
- **Everything the device shows is decided by a pure function of fetched data and the current
  time.** The clock is an input, never read from the system inside the core. This is what makes
  a day of behaviour testable in milliseconds.
- **Home-only and private.** The server runs on the home LAN; calendar and location data stay
  in the house. The dashboard updates only on home wifi, which for a fixed display is correct.

---

## 2. Behaviour specification

### 2.1 The screen

One 800×480 image, pure black and white (1-bit), Polish labels, 24-hour clock, Europe/Warsaw
time, metric units. Layout, top to bottom: weather top-left, buses top-right, calendar across
the bottom. The approved mock in `prototype/mock.html` is the non-binding reference for
proportion and density; the real renderer is designed fresh against it, not copied from it.

The region titles (POGODA / ODJAZDY / KALENDARZ) were dropped in a less-verbose pass (owner,
2026-09-06): each region reads clearly from its content and position, so the labels were pure
overhead. The calendar's DZIŚ / JUTRO day headers stay — they carry the date and say which
column is which. Only the dividing rules and the content remain.

There is deliberately no top bar carrying a clock, a date or a "last updated" time (§7). The
screen only redraws when the device wakes, so a clock would freeze between wakes — accurate to
the minute during the day but up to ~30 minutes behind overnight — and a wall clock that can
read wrong is worse than none. The mock's top strip is therefore not built. The accepted cost
is that nothing on screen states the time, so a server outage (device holding its last image)
looks the same as a live screen; the device still self-heals when the server returns (§6).

1-bit is not a limitation we tolerate but the physical truth of the panel: it is a
full-refresh black/white e-ink screen with no grey. Any shading is done by dithering (hatched
fills), never by a grey value, because a grey value does not exist on this hardware.

### 2.2 Weather

Current conditions and an hourly strip of the next WEATHER_HOURS hours. The strip rolls forward
across midnight into tomorrow's early hours rather than shrinking to nothing at end of day
(owner, 2026-09-06); the fetch covers two days so those hours are always present. The big current temperature and
its condition word start on the same top line; feels-like and wind sit under the condition as
one values-only line ("13° · 20 km/h"). There is no separate current-conditions icon (owner,
2026-09-06). Below that, the hourly strip: each column is a compact stack of hour / icon /
temperature / rain, packed tightly and centred vertically in the space below the current
conditions; the columns stay evenly spread across the panel width (owner, 2026-09-06). The icon
replaced an earlier bar whose height only re-encoded the temperature already printed, and it
uses the same WMO-code → icon-key mapping as the current conditions, so the fetch asks for a
per-hour weather_code. Source is Open-Meteo, chosen because it needs no account or API key and
covers Gdańsk with hourly data — a key to rotate is one more thing to break on a home box.
Location is a fixed coordinate for Gdańsk, set in config.

### 2.3 Buses

A single chronological list of the next departures for one line (default 227) from the owner's
stops, each row showing line number, destination (headsign), and time. The time format shows
the data source (owner, 2026-09-06): a GPS-tracked departure (feed `status` REALTIME) shows a
live countdown "za N min"; a schedule-only departure (SCHEDULED — no bus reporting yet) shows
its timetable clock time, e.g. "09:52". The countdown-vs-clock format is the signal, so a clock
time on the board always means "from the timetable, not yet tracked", matching the ZTM app.
This replaced an earlier rule that chose the format by distance (a `near_minutes` threshold);
`near_minutes` remains a config field but no longer affects the label. Under each time, in the
small attribution-sized font, is the vehicle's manufacturer, model and fleet number —
"`{brand} {model} · {number}`", e.g. "Solaris Urbino 12 · 2520" (T10, owner 2026-09-06). The
manufacturer and model come from the ZTM vehicle database (below); when the combined text does
not fit the column the model is trimmed (trailing words dropped, then ellipsized) while the
brand and number are always kept. A tracked vehicle whose number is not in the database shows
the number alone; a schedule-only row with no vehicle shows "—". Every row carries this line so
the rows stay a consistent height (owner, 2026-09-06). The list mixes both
directions/stops and is sorted by time, because the owner wants "what leaves next", not a
per-stop board. This simpler list replaced an earlier per-stop boxed layout at the owner's
request (§7). Rows have no separator rule between them (owner, 2026-09-06); the whitespace is
enough.

Source is the Gdańsk open-data live departures endpoint
`https://ckan2.multimediagdansk.pl/departures?stopId={stopId}`, which fuses schedule and
real-time into one per-stop response (fields: `routeShortName`, `headsign`, `estimatedTime`
in UTC, `delayInSeconds`, `status`). No API key. A stop is a physical pole with its own
`stopId`; the two directions of a street are two different poles, and there is no direction
field, so direction is fixed by choosing the pole and by the `headsign`. Stop ids are resolved
from the daily `stops.json` dataset by name and cached. Times are UTC and are converted to
Europe/Warsaw for display.

The feed is cached about 20 seconds per stop upstream, so polling faster than that gains
nothing; our ~120s refresh is well within it. The legacy `/delays` endpoint is dead (404) and
must not be used.

The manufacturer and model come from the ZTM vehicle database, a single JSON file listing every
vehicle by fleet number
(`https://files.cloudgdansk.pl/d/otwarte-dane/ztm/baza-pojazdow.json?v=2`, ~340 KB, no key;
each record carries `vehicleCode`, `brand`, `model`). It is downloaded, parsed to a
`{fleet number → brand/model}` map, and cached on disk (T10). It is re-downloaded only when a
cycle's schedule contains a fleet number absent from the cache — one download holds every
vehicle, so after the first fetch only a genuinely new bus triggers another. A vehicle still
absent after a download shows the number alone and, being a persistent cache miss, re-downloads
each cycle until it appears (owner accepted, 2026-09-06). A failed download leaves the cached
map intact and never fails the bus region — the rows just fall back to numbers.

Attribution is required: the data is CC-BY 4.0, so the screen carries a small credit to
Gdańsk open data ("Otwarte dane ZTM Gdańsk" or equivalent). This is a licence obligation, not
a style choice.

### 2.4 Calendar

The owner's Google Calendar, showing today's remaining events and tomorrow's, timed and
all-day. Access is by Google sign-in (OAuth) with a read-only scope, chosen over the secret
iCal link because OAuth reflects new events within minutes while Google's iCal link can lag by
hours. The refresh token is stored only on the home box. Which calendar(s) to read is config.

"Today" and "tomorrow" are computed in Europe/Warsaw from the current time passed into the
core, so the buckets roll over at local midnight regardless of where the code runs.

A day with no events — nothing left today, or nothing tomorrow — shows a short "Brak wydarzeń"
line in that day's column, not a blank space, so a genuinely empty day does not read as a
loading failure or a fault (§7). This is distinct from the calendar source being down, which
shows "niedostępne" (§2.6).

### 2.5 Refresh cadence

The server tells the device how long to sleep before the next wake, as `refresh_rate` seconds
in the `/api/display` response. In BYOS mode the firmware obeys whatever we return — there is
no manufacturer floor (verified in firmware source; the "5/15 minute" limits are cloud-account
limits that do not apply to our own server).

Policy: return 120 seconds during bus service hours and a long interval (e.g. 1800 s) overnight.
The reasons: the device is plugged into mains, so frequent wakes cost no battery; a full wake
cycle takes about 10.5 seconds and every wake flashes the whole screen once, so 120s keeps bus
times under two minutes stale while halving the flash rate of a once-a-minute wake (owner,
2026-09-06); overnight nobody is watching, so slowing down avoids needless flashing and
unquantified panel wear. The device is deep-sleep-only even on mains — there is no live/always-on
mode — so "as fresh as possible" means "wakes often", bounded by the ~10.5s cycle.

The refresh interval is a pure function of the current time (service-hours window in config),
so it is decided in the core and tested without a clock. The window is whole hours and does not
cross midnight, but its end may be 00:00, meaning it runs until midnight (mapped to hour 24); the
configured window is 06:00–00:00, so the slow overnight window is 00:00–06:00 (owner, 2026-09-06).

### 2.6 The unhappy paths

- **A data source is down or times out.** That region shows a short "niedostępne" (unavailable)
  notice; the other two regions render normally. Chosen over showing stale data because a wrong
  bus time is worse than an honest gap — you would miss the bus trusting it. Each adapter has a
  timeout so one slow source cannot delay the whole image.
- **The server cannot build an image at all.** The device keeps showing the last image it drew
  (e-ink persists with no power), and the server logs the failure. The next successful cycle
  replaces it. We never push a blank or error-only screen when a last-good image exists.
- **The server has never built an image yet** (first start, or just after a box reboot). Until
  the first real image exists there is no last-good image to fall back on, so the server serves
  a bundled "Uruchamianie…" (starting up) placeholder — an 800×480 1-bit BMP shipped with the
  code — so the device is never handed a 404 or a blank. Once the first real image is built the
  placeholder is never shown again (§7). This differs from the bullet above: that keeps the
  last-good image, this covers there being none.
- **The live bus feed returns empty or 404 for a stop.** Treated as "no upcoming departures"
  for that stop, not as an error; the region still renders with whatever other stop has. When
  every stop is empty — no departures at all for the line — the bus region shows a short "brak
  odjazdów" line, still available, not "niedostępne" (§7): empty is not the same as down.
- **Two refreshes overlap.** The image is written to a temporary file and atomically renamed
  over the served path, so the device never fetches a half-written image.
- **The device sends odd headers.** Header names vary by case and separator across firmware
  versions, so the server reads them case- and separator-insensitively.

---

## 3. Architecture

### 3.1 The boundary

```
core/     — pure. Takes fetched data and the current time as arguments, returns a view-model
            and the refresh interval. No clock, no network, no file I/O, no Pillow.
adapters/ — world-facing. Weather, bus and calendar HTTP clients; the system clock; config.
render/   — world-facing but deterministic. view-model → 800×480 1-bit image (Pillow).
server/   — world-facing. The BYOS HTTP API and the refresh loop that ties it together.
```

`core/` is the pure side. Everything it decides — which events are today/tomorrow, how a
departure is phrased, which regions are unavailable, what the refresh interval is, all display
formatting including UTC→Europe/Warsaw conversion — is a function of its arguments and nothing
else. A test scans `core/` for forbidden imports (no `requests`/`httpx`, no `datetime.now`, no
`PIL`, no `open`). If that test fails the fix is to move the code out of `core/`, never to
relax the test: the whole value of the boundary is that the core is checkable exhaustively in
milliseconds while everything across it can only be checked by a person or against fixtures.

`render/` touches no network or clock and its output is deterministic, so although it is not
"pure" it is tested against saved reference images (golden tests). This is the payoff of
drawing rather than screenshotting: the same input always yields the same pixels.

### 3.2 Modules

- `core/model.py` — the view-model dataclasses (weather, bus list, calendar days, per-region
  availability, "as of" timestamps) and the raw-input dataclasses adapters fill.
- `core/assemble.py` — builds the view-model from raw inputs + current time; the decision
  function (§3.3).
- `core/refresh.py` — refresh-interval policy as a pure function of current time.
- `adapters/weather.py`, `adapters/bus.py`, `adapters/calendar.py` — fetch and parse into the
  core's raw-input shapes; each with a timeout and its own failure signalling.
- `adapters/clock.py`, `adapters/config.py` — the system clock and the config file.
- `render/screen.py` — view-model → `PIL.Image` → 1-bit BMP file.
- `server/app.py` — `/api/setup`, `/api/display`, `/api/log`, and the static image route.
- `server/loop.py` — the composition root: fetch → assemble → render → publish image; owns the
  fetch cadence and degradation.

### 3.3 The decision function

`assemble(inputs, now) -> Dashboard` in `core/assemble.py` is where behaviour comes together.
`inputs` carries whatever each adapter fetched (or a marker that it failed); `now` is a
timezone-aware datetime passed in. It returns the full view-model the renderer draws, including
per-region availability. It reads nothing else — no clock, no network — so a whole day of
screens is testable by varying `now` and the inputs.

### 3.4 Data flow

The refresh loop fetches the three sources concurrently (each with a timeout), passes what came
back plus `now` to `assemble`, hands the view-model to the renderer, and atomically publishes
the resulting image file. Independently, the device polls `/api/display`; the server returns
the current image's URL and the `refresh_rate` from `core/refresh.py`. The device then fetches
the image file.

Whether the refresh loop runs on its own timer or lazily on each `/api/display` request is a
task-level decision (T08); either way the image is built by the same path.

### 3.5 Storage

Little persistent state. The generated image lives at a fixed served path, written to a temp
file and renamed over it so a fetch never sees a partial write. A bundled "Uruchamianie…"
placeholder BMP ships with the code (read-only, committed) and is served only until the first
real image exists (§2.6). The Google OAuth refresh token
is stored on the home box (file permissions restricted); it is the one secret and it never
leaves the box. Config (location, stop ids, line, calendar id, service hours) is a file on the
box. Stop-id lookups from `stops.json` are cached to avoid re-downloading daily data every
cycle; a stale cache only risks an unknown stop name, which surfaces as that stop being empty.

---

## 4. Testing

- **Core** (unit): `assemble` and `refresh` against hand-built inputs and fixed `now` values,
  including every unhappy path in §2.6. This is the bulk of the evidence.
- **Adapters** (unit against fixtures): parsing of recorded real responses (Open-Meteo JSON,
  ckan2 departures JSON, Google Calendar events, `stops.json`), including empty/404/odd-shape
  cases. Live network is not hit in tests.
- **Renderer** (golden): view-model → image compared to saved reference PNGs, so a layout
  regression is caught without a person looking.
- **Server** (unit): endpoint behaviour with synthetic requests, including header case/separator
  variance and the last-good-image fallback.

What none of these can prove: that the physical device accepts our image and shows it, that the
Google consent flow completes, and that the refresh cadence feels right in the room. Those are
§5.1.

---

## 5. Environment — read this before running anything

| | |
|---|---|
| OS (deploy) | Raspberry Pi Model B Rev 2 (original, ARMv6), Raspbian 11 (bullseye), 32-bit — confirmed at T09 by SSH. The owner's Synology DS218j NAS was ruled out (32-bit ARM, Python 3.8, no pip, no Docker, 500 MB RAM). |
| OS (dev) | macOS (Apple Silicon). |
| Language / runtime | Dev and the tests run in a local virtualenv (`.venv`, Python 3.11+; this Mac's is 3.13) — no Docker. The Pi has no Docker (ARMv6) and runs the app **natively** on its system Python 3.9: Pillow from apt (prebuilt, no compiling), the pure-Python deps via pip in a `--system-site-packages` venv, tomli standing in for tomllib. The code supports 3.9+ (requires-python `>=3.9`). |
| Toolchain | Node present but not used for the product. |
| **Deliberately absent** | No Docker (removed 2026-09-06 — dev and tests are the local venv, deploy is native on the Pi). No headless browser anywhere (deliberate, §7). ImageMagick not installed and not required — Pillow writes the BMP. |

**The test command.**

```
.venv/bin/python -m pytest -q
```

run in the Mac's local virtualenv (set up once with `python3 -m venv .venv &&
.venv/bin/pip install -e ".[test]"`). It is the only evidence a session may produce on its own.
Pytest is quiet by default (a line of dots per suite, a one-line summary), prints failures in
full with file, line and diff, and exits non-zero on failure. Add `-v` while debugging; do not
commit that.

The renderer's golden tests compare pixels exactly, so the committed goldens are tied to the
font rendering of the machine that generated them (this Mac). Regenerate on a layout change or a
new machine with `REGEN_GOLDENS=1 .venv/bin/python -m pytest tests/render`. The deploy Pi's
FreeType differs, so its 3.9 test run excludes them (`--ignore=tests/render`); run the suite
there for any change touching external parsing or newer stdlib (see FINDINGS, the
test-runtime-gap row).

**Dependencies.** Standard library first. Allowed without asking: `pytest`, `Pillow`, an HTTP
client (`httpx` or `requests`), the Google API client libraries for calendar, and
`gtfs-realtime-bindings` only if the bus adapter ever moves to GTFS-RT (not planned; the JSON
endpoint is enough — §2.3). Anything else is a decision for the product manager. No web
framework is assumed; the BYOS API is small enough that the standard library or a micro-framework
(decided in T04) suffices.

### 5.1 What the test command cannot reach

| Cannot be tested automatically | Why it needs a person |
|---|---|
| The device fetches and displays our image | Needs the physical TRMNL on home wifi, pointed at the server via its wifi captive portal. Done first as the T00 spike (static image), and again at T09 with the real dashboard. |
| The wifi captive-portal setup and server-URL entry | Only happens on the device's own setup access point, from a phone or laptop; no test can drive it. |
| Google OAuth consent and credential creation | Needs the owner's Google account and a Google Cloud project; the one-time consent is a human clicking "allow". |
| The refresh cadence feels right (flash not annoying) | Only the owner, watching the device in the room, can judge whether the once-a-minute flash is acceptable. |
| Real config values (stop ids, line, calendar id, coordinates) | Only the owner knows their stops, line, calendar and location. |

### 5.2 Seatbelts

| Flag / mechanism | Default | Effect |
|---|---|---|
| Static test image at T00 | on | The spike serves a fixed image, so the first thing pointed at the device cannot be a half-built dashboard. |
| Read-only calendar scope | on | OAuth requests only read access, so a bug can never alter or delete calendar data. |
| LAN-only server | on | The server binds to the home network and is not exposed to the internet, so calendar/location data has no public surface. |
| Overnight refresh slowdown | on | Long `refresh_rate` overnight caps needless full-screen flashes and panel wear when nobody is watching. |
| Device config is resettable | n/a | Re-running the captive portal (or `reset_firmware`) changes the server URL, so pointing the device at our server can always be undone — there is no lock-in to fear. |

The device setup is not dangerous (it is resettable), so there is no unbounded version to
avoid. The one genuine risk to bound is exposure of private data, handled by the LAN-only and
read-only seatbelts above.

---

## 6. Recovery

If the server is down or unreachable, the device keeps showing its last image and retries on
its next wake — there is nothing to recover, it self-heals when the server returns. To repoint
or reset the device, re-enter its wifi captive portal and set the server URL again. To revoke
calendar access, delete the stored refresh token on the box and remove the app's access in the
Google account settings; the calendar region then shows "unavailable" until re-authorised.

---

## 7. Decisions and rationale

- **2026-09-05 — One combined screen, all three regions at once.** Alternatives were rotating
  screens and one-main-plus-strip. Rejected because the owner wants every answer at a glance.
  Confirmed against a clickable mock the owner approved the same day (`prototype/mock.html`).
- **2026-09-05 — Bus region is a flat chronological list, not per-stop boxes.** The owner
  revised the first mock: show `line → destination time`, nearest as "za N min", rest as a
  clock time, both directions merged and sorted by time. Simpler and matches "what leaves next".
- **2026-09-05 — Python + Pillow, no headless browser.** The owner asked for Pillow and invited
  a counter-argument; there was none to make. The screen is a fixed-size, monochrome, static
  layout, which is exactly where drawing beats screenshotting: Pillow is featherlight (runs on
  any box), has no browser to crash or update, writes the exact 1-bit BMP with no conversion,
  and is deterministic so the rendered image is golden-testable. The cost is laying the layout
  out in code, paid once.
- **2026-09-05 — Google OAuth for calendar, not the secret iCal link.** OAuth reflects new
  events within minutes; the iCal link can lag hours. The cost is a fiddlier one-time setup and
  a stored token, accepted for freshness.
- **2026-09-05 — "Unavailable" notice when a source is down, not stale data.** A wrong bus time
  causes a missed bus; an honest gap does not. The owner chose this over showing last-known.
- **2026-09-05 — Home always-on box, LAN-only.** Keeps calendar and location in the house. The
  accepted consequence is that the dashboard updates only on home wifi.
- **2026-09-05 — Refresh 60s during service hours, ~1800s overnight.** No firmware floor exists
  in BYOS; mains power removes the battery cost; 60s balances freshness against the once-a-minute
  screen flash; overnight slowdown avoids needless flashing and wear. Tunable if the flash
  annoys in the room.
- **2026-09-06 — Service refresh raised 60s → 120s.** Owner judged the once-a-minute flash too
  frequent in the room; two minutes halves the flashing and still keeps bus times under two
  minutes stale. Overnight 1800s unchanged.
- **2026-09-06 — Overnight (slow) window set to 00:00–06:00.** Owner's choice; fast now runs
  06:00 until midnight. Needed the service window to end at midnight, so end=00:00 is allowed as
  a special "runs to midnight" value (mapped to hour 24), the one end that may sort before start.
- **2026-09-05 — Live departures JSON endpoint, not GTFS-RT.** For one stop and one line the
  `departures` endpoint already fuses schedule and realtime with human-readable fields; GTFS-RT
  would add protobuf and a static-GTFS join for no gain at this scope.
- **2026-09-05 (plan review) — No top bar: no on-screen clock, date or "last updated" time.**
  The mock had a top strip with all three; the owner dropped it. The screen only redraws on a
  device wake, so a clock freezes between wakes — to the minute during the day, up to ~30 min
  overnight — and a time that can read wrong is worse than none. The accepted consequence is
  that nothing on screen dates the data, so a server outage looks like a live screen; the device
  still self-heals (§6). If ever wanted, a small "akt. HH:MM" could sit in the attribution
  footer without reviving the strip.
- **2026-09-05 (plan review) — An available-but-empty region shows a short line, not a blank.**
  Calendar with no events for a day → "Brak wydarzeń"; bus list with no departures → "brak
  odjazdów". The owner chose this over leaving the space blank, because a blank region reads as
  a fault or a stuck load. It is distinct from "niedostępne", which means the source is down.
- **2026-09-05 (T03) — Region headings carry the location and line from config.** The weather
  heading is "Pogoda · {city}", the buses heading "Odjazdy · {stop label} · {line}"; the calendar
  heading stays "Kalendarz". For this deployment the values are Gdańsk / Hynka / 227. City, stop
  label and line are config, so the renderer (T03) draws the plain titles when no labels are
  passed and T08 supplies the suffixed ones from config — this keeps the core (assemble) free of
  config and T03's goldens valid. On-screen casing follows the existing uppercase tracked label
  style (e.g. "ODJAZDY · HYNKA · 227") unless the owner asks for title case.
- **2026-09-05 (plan review) — A bundled "Uruchamianie…" startup placeholder for the cold
  start.** On first start or just after a reboot no image exists yet and there is no last-good
  to fall back on. The owner chose shipping a fixed "starting up" image the server serves
  instantly over making the device wait a refresh cycle for its first picture. It is shown only
  until the first real image is built, then never again.

---

## 8. Explicitly out of scope

- **Any interaction (buttons, input, control).** The device is display-only by nature; adding a
  control surface is a different product.
- **Multiple users or calendars-as-a-feature.** One owner, one household. Config can name more
  than one calendar id, but multi-user accounts are not built.
- **A phone or web app to control the dashboard.** Nothing to control — the screen is derived
  entirely from data and time. A control app is cost with no matching need here.
- **Historical logging or analytics.** The dashboard shows now and the near future; it keeps no
  history. Storing history is a maintenance burden for a glance display.
- **Battery optimisation.** The device is mains-powered by decision, so the firmware's battery
  features are irrelevant to this build.
- **Grayscale / 2-bit / 4-bit rendering.** The OG panel is physically 1-bit; grayscale on it is
  experimental firmware territory and not a foundation to build on.
