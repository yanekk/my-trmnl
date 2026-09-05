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
| 2026-09-05 | 📌 | Bus live feed is `https://ckan2.multimediagdansk.pl/departures?stopId={id}` (no key, CC-BY, ~20s cache). Legacy `/delays` is dead (404). Times UTC. `stopId` is per pole; direction has no field, fix it by pole + `headsign`. |
| 2026-09-05 | 📌 | BYOS: firmware GETs `/api/display` with `ID`(MAC) header, expects JSON `{filename,image_url,refresh_rate}`, then GETs the image separately. Image contract: 800×480 1-bit BMP3. Read request headers case/separator-insensitively. |
| 2026-09-05 | 📌 | No firmware floor on `refresh_rate` in BYOS (verified in firmware source); the 5/15-min limits are cloud-account only. Wake cycle ~10.5s, deep-sleep only even on mains (no live mode), whole-screen flash every wake. |
| 2026-09-05 | 📌 | Seeed OG DIY kit ships pre-flashed (FW 1.5.12+); server URL is set in the wifi captive portal, no reflash. Silicon is ESP32-S3, not the retail OG's C3 — only matters if firmware is ever rebuilt. |
| 2026-09-05 | 🔄 | Owner revised bus region from per-stop boxes to a flat chronological list (`line → dest time`, nearest as "za N min"). Recorded in DESIGN §7; mock updated. |
