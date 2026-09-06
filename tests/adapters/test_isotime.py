"""Tests for the 3.9-safe ISO parser (DESIGN §5). The whole point of this helper
is the trailing "Z" that stdlib fromisoformat rejects before Python 3.11, so that
is the case that matters most — it is what silently emptied the bus board on the
deploy Pi while the 3.12 test runtime stayed green."""

from datetime import datetime, timezone

import pytest

from trmnl.adapters.isotime import from_iso


def test_z_suffix_parses_as_utc():
    dt = from_iso("2026-09-05T19:10:00Z")
    assert dt == datetime(2026, 9, 5, 19, 10, tzinfo=timezone.utc)
    assert dt.utcoffset() == timezone.utc.utcoffset(None)


def test_numeric_offset_is_preserved():
    dt = from_iso("2026-09-06T09:00:00+02:00")
    assert dt.utcoffset().total_seconds() == 2 * 3600


def test_naive_string_passes_through_unchanged():
    dt = from_iso("2026-09-05T19:10:00")
    assert dt.tzinfo is None
    assert dt == datetime(2026, 9, 5, 19, 10)


def test_malformed_raises_valueerror():
    # Same failure mode as datetime.fromisoformat, so the adapters' existing
    # try/except (which drops the row/region) keeps working.
    with pytest.raises(ValueError):
        from_iso("not a timestamp")
