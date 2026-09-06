# Findings log

**What the build taught.** Read the rows touching the task you pick up; read it whole before
anything only a person can verify — a ✅ row is the entire record that something was seen
working for real.

**Newest first. Forty words a row, counted.** The long version is in the commit message that
carried the fix. This is the index, not the account.

## Keeping it short

**Whoever appends, compacts.** Before adding a row, if this file is over 60 rows or 15 KB,
spend two minutes shrinking it. Merge rows that are one lesson twice; drop a row whose lesson
is now enforced by code, a test or a rule in DESIGN.md, naming where it went. Never drop a ✅
row or its date, or anything someone would grep for (a flag, an error string, a path).

Legend: 🐞 defect found · ✅ verified by hand with the user · 📌 worth knowing ·
🔄 a decision the user changed.

| Date | | Finding |
|---|---|---|
| 2026-09-06 | 🔄 | Owner decided: a multi-day all-day event shows on every day it covers within the today/tomorrow window. Today `Event` has no `end` and buckets by one day, so a running vacation vanishes. T08 fixes it — adapter emits one Event per covered day, or model gains `end`. |
| 2026-09-05 | ✅ | T07 OAuth consent done by owner: read-only credential minted, loads, valid, reads live events end to end. Token 0o600 at ~/.config/trmnl/token.json (dev Mac, outside repo; copy to box at T09). Dashboard calendar id: pd0pfl6q60afma9et1o2n46f1c@group.calendar.google.com (Madziojankowy kalendarz). |
| 2026-09-05 | 📌 | T07 calendar adapter fetches Google Calendar REST over httpx (Bearer token), not the discovery client. New deps google-auth 2.35.0 + google-auth-oauthlib 1.2.1 — rebuild the image. Calendar is one source: any calendar error → whole-region Failure (no per-pole-style isolation). |
| 2026-09-05 | 📌 | T07: all-day events placed at Warsaw local midnight (core buckets by day). Untitled event → "(bez tytułu)" placeholder — owner confirmed the wording 2026-09-06. OAuth token stored 0o600, never logged (both asserted). Consent flow itself is owner-run, unverified. |
| 2026-09-05 | 📌 | T06 review clean. `_parse_pole` reads `estimatedTime`; a 227 row lacking it (scheduled-only, no realtime) or otherwise malformed drops that whole pole, not just the row. Live feed 2026-09-05 always had it; watch on device at T09. |
| 2026-09-05 | 📌 | T06 config resolved: line 227, Hynka poles stopId 1767 (→Chełm Cienista) and 1768 (→Jelitkowo), zone Gdańsk. Live feed 2026-09-05 confirms both serve 227. Owner already fixed Hynka/227 in DESIGN §7; config values land at T08. |
| 2026-09-05 | 📌 | T06 bus adapter reads `estimatedTime` (ISO `Z`, UTC, realtime incl delay) as departure time. `resolve_stop_ids` returns `dict[str,list[int]]` (a name has two direction poles). Per-pole: 404/empty/unparseable pole skipped; `Failure` only when every pole fails. |
| 2026-09-05 | 📌 | T05 weather adapter is coordinate-agnostic (lat/lon are args); Gdańsk city-centre default is fine, owner confirms the exact point at T08 config. Requests `timezone=GMT` (times UTC, core localizes) and pins metric units. Null hourly precip→0%; null temp→`Failure`. |
| 2026-09-05 | 📌 | `docker compose run --rm test` reuses a stale baked image (Dockerfile `COPY`s source at build). New source/test files need `docker compose build test` first, or the `-v "$PWD":/app` mount. Suite read 69 until rebuild, then 83. |
| 2026-09-05 | 📌 | T04 returns `filename` as a content hash of the served BMP, so an unchanged screen keeps its name and the firmware can skip a redundant full-screen flash. The name is ours (device fetches our `image_url`; `.bmp` route serves the one image). Flash-skip unverified on hardware — check at T09. |
| 2026-09-05 | 📌 | T03 renderer goldens are generated and compared inside Docker: `docker compose run --rm -v "$PWD":/app -e REGEN_GOLDENS=1 test`. FreeType hinting makes pixels exact only within the same Pillow/FreeType build, so regen in the env tests run in. Bundled IBM Plex OFL fonts live in trmnl/render/fonts/. |
| 2026-09-05 | 📌 | T01 boundary guard is a name-based static AST scan. Review added `utcnow` to the clock check. Residual gaps by design: aliased `from datetime import datetime as dt; dt.now()`, and file I/O via `pathlib`/`os` (only `open()` builtin caught). Catches accidental reaches, not adversarial. |
| 2026-09-05 | ✅ | T00 spike verified by hand with owner: real TRMNL (FW 1.5.12, model `xiao_epaper_display`, MAC `E0:72:A1:FA:0D:F8`) fetched and displayed our 800×480 1-bit BMP3 from the LAN server. Biggest risk retired. |
| 2026-09-05 | 📌 | FW 1.5.12 GETs `/api/setup/` with a trailing slash. Spike matched only `/api/setup` → device got 404 (it logged "Code - 404"), then continued to `/api/display` and displayed anyway. T04 must serve `/api/setup/` returning `api_key`; a setup miss is non-fatal but noisy. |
| 2026-09-05 | 📌 | Real firmware headers: `ID`=MAC; `Access-Token` (hyphen, empty until setup succeeds); `FW-Version`; and on `/api/display` also `Model`,`Width`(800),`Height`(480),`RSSI`,`Battery-Voltage`,`Refresh-Rate`. Plan's `ACCESS_TOKEN` spelling is wrong; case/separator-insensitive header read is required and sufficient. |
| 2026-09-05 | 📌 | Device POSTs telemetry/errors to `/api/log` as JSON `{"logs":[{message,source_path,wifi_status,battery_voltage,wake_reason,...}]}`. The earlier reboots the owner saw were `wifi_status:no_shield` "connection to the new WiFi failed" — transient association failures, not a server fault. |
| 2026-09-05 | 📌 | Bus live feed is `https://ckan2.multimediagdansk.pl/departures?stopId={id}` (no key, CC-BY, ~20s cache). Legacy `/delays` is dead (404). Times UTC. `stopId` is per pole; direction has no field, fix it by pole + `headsign`. |
| 2026-09-05 | 📌 | BYOS: firmware GETs `/api/display` with `ID`(MAC) header, expects JSON `{filename,image_url,refresh_rate}`, then GETs the image separately. Image contract: 800×480 1-bit BMP3. Read request headers case/separator-insensitively. |
| 2026-09-05 | 📌 | No firmware floor on `refresh_rate` in BYOS (verified in firmware source); the 5/15-min limits are cloud-account only. Wake cycle ~10.5s, deep-sleep only even on mains (no live mode), whole-screen flash every wake. |
| 2026-09-05 | 📌 | Seeed OG DIY kit ships pre-flashed (FW 1.5.12+); server URL is set in the wifi captive portal, no reflash. Silicon is ESP32-S3, not the retail OG's C3 — only matters if firmware is ever rebuilt. |
| 2026-09-05 | 🔄 | Owner revised bus region from per-stop boxes to a flat chronological list (`line → dest time`, nearest as "za N min"). Recorded in DESIGN §7; mock updated. |
