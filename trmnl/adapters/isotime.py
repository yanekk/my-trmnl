"""Parse ISO-8601 timestamps from the feeds into datetimes on Python 3.9+.

`datetime.fromisoformat` only learned to accept a trailing "Z" (and other full
ISO-8601 forms) in Python 3.11. The deploy box runs 3.9 (DESIGN §5), where a "Z"
raises `ValueError` — which the adapters catch and turn into a dropped row or a
degraded region, so a bus feed that stamps its times "…Z" silently produced an
empty board on the Pi while passing every test on the 3.12 dev/Docker runtime.

Normalising a trailing "Z" to "+00:00" here fixes it for 3.9 and is a no-op on
3.11+. Numeric offsets ("+02:00") and naive strings are already handled by
`fromisoformat` on 3.9, so they pass through unchanged.
"""

from __future__ import annotations

from datetime import datetime


def from_iso(s: str) -> datetime:
    """Parse an ISO-8601 timestamp to a datetime, accepting a trailing "Z" on
    Python 3.9. Raises `ValueError` on a malformed string, same as
    `datetime.fromisoformat`, so callers' existing error handling is unchanged."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)
