# T09 — Deploy on the home box, run at boot, on-device verification

**Phase:** 3 · **Depends on:** T08 · **Weight:** light (but gated on the device and the owner)

## Goal

Put the finished server on the always-on box, have it start on boot and keep running, point the
real device at it, and confirm with the owner that the real dashboard shows on the screen with
correct data. This is the task that can only be finished with the device and the owner, and it
is where the refresh cadence is judged in the room and tuned if the flash is annoying.

## Design sections this implements

DESIGN.md §5.1 (device and cadence are hand-verified), §5.2 (LAN-only, overnight slowdown),
§6 (recovery — the device self-heals when the server returns), §2.3 (attribution visible).

## Files

- `docker-compose.yml` production service (restart policy), a short deploy/run note in `README`.
- No new product code expected; if any is needed it is a finding, not a silent addition.

## Interface

Operational, not code: the box runs `docker compose up -d` (or an equivalent boot unit) with a
restart-always policy, reads the real `config.toml`, and serves on the LAN. The device's
captive portal points at the box's LAN URL.

## Tests

The test command still passes unchanged on the box (or in the same image). Beyond that, the
evidence for this task is the owner's eyes — see below.

## Done when

- [ ] The service starts on boot and restarts on failure (checked by rebooting the box once).
- [ ] The device, pointed at the box, shows the real three-region dashboard with live data.
- [ ] The data-source attribution is visible on the screen.
- [ ] The owner confirms the refresh cadence is acceptable, or names a value to set instead.

## Needs a person

This task ends with the owner, on the device. Raise it and wait; do not mark it done on the
test command alone.

```
1. On the box:  docker compose up -d   (reads config.toml; prints the LAN URL)
2. Point the TRMNL at that URL via its captive portal (as in T00 — resettable).
3. Reboot the box once and confirm the service comes back on its own.
```

Expect: the screen shows the real dashboard; after a reboot it recovers without touching the
device.
Tell me: does the real data look right (weather, your line's departures, today/tomorrow events);
is the once-a-minute flash acceptable where it sits, or should the interval change; anything on
screen that reads wrong. Record the outcome, dated, in FINDINGS as the ✅ hand-verification.
