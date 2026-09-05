"""assemble() — the pure decision function (DESIGN §3.3). Every unhappy path in
§2.6 that is a core concern has a test named for it here, alongside the bucketing,
phrasing and timezone rules from §2.2–§2.4.

All times are built in UTC (as the adapters fetch them) so the tests also prove
the UTC->Europe/Warsaw conversion the core is responsible for.
"""

from datetime import datetime, timezone

from trmnl.core.assemble import assemble
from trmnl.core.model import (
    ATTRIBUTION,
    BUS_ROWS,
    Departure,
    Event,
    Failure,
    HourPoint,
    Sources,
    WeatherData,
)


def utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def weather_ok():
    return WeatherData(temp_c=12, condition_code=3, feels_like_c=10, wind_kmh=15, hourly=[])


def sources(weather=None, bus=None, calendar=None):
    """A Sources with each slot defaulting to an available-but-empty value, so a
    test overrides only the slot it cares about."""
    return Sources(
        weather=weather_ok() if weather is None else weather,
        bus=[] if bus is None else bus,
        calendar=[] if calendar is None else calendar,
    )


# --- failure handling (DESIGN §2.6) -----------------------------------------


def test_weather_failure_only_affects_weather():
    d = assemble(sources(weather=Failure("timeout")), utc(2026, 1, 15, 12))
    assert d.weather_region.available is False
    assert d.weather is None
    assert d.buses_region.available is True
    assert d.calendar_region.available is True


def test_bus_failure_only_affects_buses():
    d = assemble(sources(bus=Failure()), utc(2026, 1, 15, 12))
    assert d.buses_region.available is False
    assert d.buses == []
    assert d.weather_region.available is True
    assert d.calendar_region.available is True


def test_calendar_failure_only_affects_calendar():
    d = assemble(sources(calendar=Failure()), utc(2026, 1, 15, 12))
    assert d.calendar_region.available is False
    assert d.today == [] and d.tomorrow == []
    assert d.weather_region.available is True
    assert d.buses_region.available is True


def test_all_three_failed_still_a_valid_dashboard():
    d = assemble(
        Sources(weather=Failure(), bus=Failure(), calendar=Failure()),
        utc(2026, 1, 15, 12),
    )
    assert d.weather_region.available is False
    assert d.buses_region.available is False
    assert d.calendar_region.available is False
    # Still a fully-formed screen: attribution and now_local are present.
    assert d.attribution == ATTRIBUTION
    assert d.now_local is not None


# --- available-but-empty is NOT a failure (DESIGN §2.6, §2.4) ---------------


def test_empty_bus_list_is_available_not_failed():
    d = assemble(sources(bus=[]), utc(2026, 1, 15, 12))
    assert d.buses_region.available is True  # renderer draws "brak odjazdów"
    assert d.buses == []


def test_calendar_day_with_no_events_is_available_not_failed():
    # An event tomorrow, nothing today: today is empty but the region is available.
    ev_tomorrow = Event(start=utc(2026, 1, 16, 9), title="Przegląd auta")
    d = assemble(sources(calendar=[ev_tomorrow]), utc(2026, 1, 15, 12))
    assert d.calendar_region.available is True  # renderer draws "Brak wydarzeń"
    assert d.today == []
    assert [e.title for e in d.tomorrow] == ["Przegląd auta"]


# --- today/tomorrow bucketing (DESIGN §2.4) ---------------------------------


def test_bucketing_rolls_over_at_warsaw_midnight():
    # Event at 08:00 local on 16 Jan (winter, +1) = 07:00 UTC.
    ev = Event(start=utc(2026, 1, 16, 7), title="Rano")

    # now = 23:30 local 15 Jan (= 22:30 UTC): the event is tomorrow.
    before = assemble(sources(calendar=[ev]), utc(2026, 1, 15, 22, 30))
    assert [e.title for e in before.tomorrow] == ["Rano"]
    assert before.today == []

    # now = 00:30 local 16 Jan (= 23:30 UTC): same event is now today.
    after = assemble(sources(calendar=[ev]), utc(2026, 1, 15, 23, 30))
    assert [e.title for e in after.today] == ["Rano"]
    assert after.tomorrow == []


def test_past_timed_event_today_is_dropped_allday_kept():
    now = utc(2026, 1, 15, 12)  # 13:00 local
    past = Event(start=utc(2026, 1, 15, 8), title="Standup")  # 09:00 local, past
    later = Event(start=utc(2026, 1, 15, 15), title="Dentysta")  # 16:00 local
    allday = Event(start=utc(2026, 1, 15, 0), title="Urlop", all_day=True)
    d = assemble(sources(calendar=[past, later, allday]), now)
    titles = [e.title for e in d.today]
    assert "Standup" not in titles
    assert "Dentysta" in titles
    assert "Urlop" in titles


def test_allday_event_has_empty_label_and_sorts_first():
    now = utc(2026, 1, 16, 6)  # tomorrow view is 17 Jan
    allday = Event(start=utc(2026, 1, 17, 0), title="Urodziny", all_day=True)
    timed = Event(start=utc(2026, 1, 17, 9), title="Kino")
    d = assemble(sources(calendar=[timed, allday]), now)
    assert [e.title for e in d.tomorrow] == ["Urodziny", "Kino"]
    assert d.tomorrow[0].all_day is True
    assert d.tomorrow[0].label == ""
    assert d.tomorrow[1].label == "10:00"  # 09:00 UTC -> 10:00 local (+1)


# --- departure phrasing (DESIGN §2.3) ---------------------------------------


def test_departures_phrasing_sorting_and_cap():
    now = utc(2026, 1, 15, 12, 0)
    deps = [
        Departure("227", "Jelitkowo", now.replace(minute=40)),  # +40 -> clock
        Departure("227", "Chełm", now.replace(minute=3)),  # +3 -> za 3 min
        Departure("227", "Jelitkowo", now.replace(minute=20)),  # +20 -> clock
        Departure("227", "Chełm", now.replace(minute=10)),  # +10 -> za 10 min
        Departure("227", "Jelitkowo", now.replace(minute=50)),  # +50 -> clock
        Departure("227", "Chełm", now.replace(minute=55)),  # +55 -> clock (6th)
        Departure("227", "Gone", utc(2026, 1, 15, 11, 30)),  # past -> dropped
    ]
    d = assemble(sources(bus=deps), now)
    labels = [r.label for r in d.buses]
    # Past one dropped, sorted by time, capped to BUS_ROWS.
    assert len(d.buses) == BUS_ROWS
    assert "Gone" not in [r.headsign for r in d.buses]
    assert labels[0] == "za 3 min"
    assert labels[1] == "za 10 min"
    # 13:20 local (12:20 UTC +1) etc. — the far ones are clock times.
    assert labels[2] == "13:20"
    assert labels[3] == "13:40"
    assert labels[4] == "13:50"


def test_near_minutes_boundary_is_exclusive():
    now = utc(2026, 1, 15, 12, 0)
    just_inside = Departure("227", "A", now.replace(minute=14))  # 14 < 15 -> phrase
    on_boundary = Departure("227", "B", now.replace(minute=15))  # 15 -> clock
    d = assemble(sources(bus=[just_inside, on_boundary]), now)
    assert d.buses[0].label == "za 14 min"
    assert d.buses[1].label == "13:15"  # 12:15 UTC -> 13:15 local


# --- timezone conversion across a DST change (DESIGN §2.1, §2.3) ------------


def test_departure_clock_label_respects_dst():
    # Summer: Warsaw is +2. 06:30 UTC -> 08:30 local.
    summer_now = utc(2026, 7, 1, 5, 0)
    summer_dep = Departure("227", "Jelitkowo", utc(2026, 7, 1, 6, 30))
    d_summer = assemble(sources(bus=[summer_dep]), summer_now)
    assert d_summer.buses[0].label == "08:30"

    # Winter: Warsaw is +1. 06:30 UTC -> 07:30 local. Same UTC clock, one hour
    # earlier locally — this is the DST difference the core must get right.
    winter_now = utc(2026, 1, 15, 5, 0)
    winter_dep = Departure("227", "Jelitkowo", utc(2026, 1, 15, 6, 30))
    d_winter = assemble(sources(bus=[winter_dep]), winter_now)
    assert d_winter.buses[0].label == "07:30"


def test_event_label_respects_dst():
    summer = assemble(
        sources(calendar=[Event(start=utc(2026, 7, 1, 12), title="Lunch")]),
        utc(2026, 7, 1, 6),
    )
    assert summer.today[0].label == "14:00"  # +2
    winter = assemble(
        sources(calendar=[Event(start=utc(2026, 1, 15, 12), title="Lunch")]),
        utc(2026, 1, 15, 6),
    )
    assert winter.today[0].label == "13:00"  # +1


# --- weather (DESIGN §2.2) --------------------------------------------------


def test_weather_condition_word_and_icon_from_code():
    d = assemble(sources(weather=weather_ok()), utc(2026, 1, 15, 12))
    assert d.weather.condition == "Pochmurno"  # code 3
    assert d.weather.icon == "cloud"
    assert d.weather.temp_c == 12
    assert d.weather.feels_like_c == 10
    assert d.weather.wind_kmh == 15


def test_unknown_weather_code_falls_back_not_crashes():
    w = WeatherData(temp_c=5, condition_code=1234, feels_like_c=3, wind_kmh=8, hourly=[])
    d = assemble(sources(weather=w), utc(2026, 1, 15, 12))
    assert d.weather.condition == "—"
    assert d.weather.icon == "cloud"


def test_weather_hours_are_rest_of_today_localized_and_capped():
    now = utc(2026, 1, 15, 7, 30)  # 08:30 local (+1)
    # Points at 07,08,...,23 UTC today plus one yesterday and one tomorrow.
    hourly = [HourPoint(time=utc(2026, 1, 15, h), temp_c=h, rain_pct=h) for h in range(7, 24)]
    hourly.append(HourPoint(time=utc(2026, 1, 14, 23), temp_c=-1, rain_pct=0))
    hourly.append(HourPoint(time=utc(2026, 1, 16, 6), temp_c=99, rain_pct=99))
    w = WeatherData(temp_c=8, condition_code=0, feels_like_c=6, wind_kmh=10, hourly=hourly)
    d = assemble(sources(weather=w), now)
    hours = d.weather.hours
    # Only future same-local-day points, capped at 6. 08:00 UTC (09:00 local) is
    # the first strictly after now; labels are local hours.
    assert len(hours) == 6
    assert hours[0].label == "09"  # 08:00 UTC -> 09:00 local
    assert hours[-1].label == "14"
    assert all(h.temp_c < 99 for h in hours)  # tomorrow's point excluded


# --- attribution (DESIGN §2.3) ----------------------------------------------


def test_attribution_always_populated_even_when_all_down():
    d = assemble(Sources(weather=Failure(), bus=Failure(), calendar=Failure()), utc(2026, 1, 15, 12))
    assert d.attribution == ATTRIBUTION
    assert d.attribution
