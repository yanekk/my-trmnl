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
| 2026-09-05 | ✅ | T00 spike verified by hand with owner: real TRMNL (FW 1.5.12, model `xiao_epaper_display`, MAC `E0:72:A1:FA:0D:F8`) fetched and displayed our 800×480 1-bit BMP3 from the LAN server. Biggest risk retired. |
| 2026-09-05 | 📌 | FW 1.5.12 GETs `/api/setup/` with a trailing slash. Spike matched only `/api/setup` → device got 404 (it logged "Code - 404"), then continued to `/api/display` and displayed anyway. T04 must serve `/api/setup/` returning `api_key`; a setup miss is non-fatal but noisy. |
| 2026-09-05 | 📌 | Real firmware headers: `ID`=MAC; `Access-Token` (hyphen, empty until setup succeeds); `FW-Version`; and on `/api/display` also `Model`,`Width`(800),`Height`(480),`RSSI`,`Battery-Voltage`,`Refresh-Rate`. Plan's `ACCESS_TOKEN` spelling is wrong; case/separator-insensitive header read is required and sufficient. |
| 2026-09-05 | 📌 | Device POSTs telemetry/errors to `/api/log` as JSON `{"logs":[{message,source_path,wifi_status,battery_voltage,wake_reason,...}]}`. The earlier reboots the owner saw were `wifi_status:no_shield` "connection to the new WiFi failed" — transient association failures, not a server fault. |
| 2026-09-05 | 📌 | Bus live feed is `https://ckan2.multimediagdansk.pl/departures?stopId={id}` (no key, CC-BY, ~20s cache). Legacy `/delays` is dead (404). Times UTC. `stopId` is per pole; direction has no field, fix it by pole + `headsign`. |
| 2026-09-05 | 📌 | BYOS: firmware GETs `/api/display` with `ID`(MAC) header, expects JSON `{filename,image_url,refresh_rate}`, then GETs the image separately. Image contract: 800×480 1-bit BMP3. Read request headers case/separator-insensitively. |
| 2026-09-05 | 📌 | No firmware floor on `refresh_rate` in BYOS (verified in firmware source); the 5/15-min limits are cloud-account only. Wake cycle ~10.5s, deep-sleep only even on mains (no live mode), whole-screen flash every wake. |
| 2026-09-05 | 📌 | Seeed OG DIY kit ships pre-flashed (FW 1.5.12+); server URL is set in the wifi captive portal, no reflash. Silicon is ESP32-S3, not the retail OG's C3 — only matters if firmware is ever rebuilt. |
| 2026-09-05 | 🔄 | Owner revised bus region from per-stop boxes to a flat chronological list (`line → dest time`, nearest as "za N min"). Recorded in DESIGN §7; mock updated. |
