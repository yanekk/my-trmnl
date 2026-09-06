"""`refresh_seconds(now, service) -> int` — the refresh-rate policy (DESIGN §2.5).

The server reports this to the device as how long to sleep before the next wake.
It is a pure function of the current time and the service-hours window, so the
cadence is decided on the pure side and tested without a clock.

Policy: 120 seconds (2 minutes) inside bus service hours, so on-screen bus times
stay under two minutes stale while the screen flashes half as often; a long
interval overnight, when nobody is watching, to avoid needless full-screen flashes
and panel wear. There is no firmware floor on the interval in BYOS mode (verified
at T00), so the device obeys whatever we return.
"""

from __future__ import annotations

from datetime import datetime

from .model import WARSAW, ServiceHours

# 2 minutes: bus times stay under two minutes stale, at half the flash rate of a
# once-a-minute wake (owner, 2026-09-06, DESIGN §2.5).
IN_SERVICE_SECONDS = 120
# Slow overnight: nobody is watching, so cut the flashing and wear.
OVERNIGHT_SECONDS = 1800


def refresh_seconds(now: datetime, service: ServiceHours) -> int:
    """120 during service hours, 1800 outside. `now` must be tz-aware; it is
    compared in Europe/Warsaw because the service window is local. The window is
    `[start_hour, end_hour)`: at exactly `end_hour` the device has slowed down.
    `end_hour` may be 24 (a window running until midnight); no local hour equals 24,
    so every hour of the day then falls inside the window."""
    hour = now.astimezone(WARSAW).hour
    if service.start_hour <= hour < service.end_hour:
        return IN_SERVICE_SECONDS
    return OVERNIGHT_SECONDS
