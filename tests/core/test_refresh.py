"""refresh_seconds policy (DESIGN §2.5): 60 in service hours, 1800 outside, with
the window compared in Europe/Warsaw and the edges tested explicitly."""

from datetime import datetime, timezone

from trmnl.core.model import ServiceHours
from trmnl.core.refresh import IN_SERVICE_SECONDS, OVERNIGHT_SECONDS, refresh_seconds

SERVICE = ServiceHours(start_hour=5, end_hour=23)


def _warsaw_winter(hour: int, minute: int = 0) -> datetime:
    """A UTC instant that reads as `hour:minute` local time in winter (+1)."""
    return datetime(2026, 1, 15, hour - 1, minute, tzinfo=timezone.utc)


def test_midday_is_in_service():
    assert refresh_seconds(_warsaw_winter(12), SERVICE) == IN_SERVICE_SECONDS


def test_deep_night_is_out_of_service():
    assert refresh_seconds(_warsaw_winter(3), SERVICE) == OVERNIGHT_SECONDS


def test_start_edge_is_in_service():
    # 05:00 local exactly -> in window.
    assert refresh_seconds(_warsaw_winter(5, 0), SERVICE) == IN_SERVICE_SECONDS


def test_just_before_start_is_out():
    assert refresh_seconds(_warsaw_winter(4, 59), SERVICE) == OVERNIGHT_SECONDS


def test_end_edge_is_out_of_service():
    # 23:00 local exactly -> already slowed down (window is [start, end)).
    assert refresh_seconds(_warsaw_winter(23, 0), SERVICE) == OVERNIGHT_SECONDS


def test_just_before_end_is_in_service():
    assert refresh_seconds(_warsaw_winter(22, 59), SERVICE) == IN_SERVICE_SECONDS


def test_window_is_compared_in_warsaw_not_utc():
    # 04:30 UTC is 05:30 local (+1), which is inside the window even though the
    # UTC hour (4) is outside it. Proves the conversion happens.
    utc_0430 = datetime(2026, 1, 15, 4, 30, tzinfo=timezone.utc)
    assert refresh_seconds(utc_0430, SERVICE) == IN_SERVICE_SECONDS
