"""`refresh_seconds(now, service) -> int` — the refresh-rate policy (DESIGN §2.5).

The server reports this to the device as how long to sleep before the next wake.
It is a pure function of the current time and the service-hours window, so the
cadence is decided on the pure side and tested without a clock.

Policy: 60 seconds inside bus service hours, so on-screen bus times stay under a
minute stale; a long interval overnight, when nobody is watching, to avoid
needless full-screen flashes and panel wear. There is no firmware floor on the
interval in BYOS mode (verified at T00), so the device obeys whatever we return.
"""

from __future__ import annotations

from datetime import datetime

from .model import WARSAW, ServiceHours

# Fast enough that bus times never drift a minute stale (DESIGN §2.5).
IN_SERVICE_SECONDS = 60
# Slow overnight: nobody is watching, so cut the flashing and wear.
OVERNIGHT_SECONDS = 1800


def refresh_seconds(now: datetime, service: ServiceHours) -> int:
    """60 during service hours, 1800 outside. `now` must be tz-aware; it is
    compared in Europe/Warsaw because the service window is local. The window is
    `[start_hour, end_hour)`: at exactly `end_hour` the device has slowed down."""
    hour = now.astimezone(WARSAW).hour
    if service.start_hour <= hour < service.end_hour:
        return IN_SERVICE_SECONDS
    return OVERNIGHT_SECONDS
