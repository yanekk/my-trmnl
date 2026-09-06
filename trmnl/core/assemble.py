"""`assemble(sources, now) -> Dashboard` — the decision function (DESIGN §3.3).

Everything the screen shows is decided here from what the adapters fetched plus
`now`, and nothing else: no clock, no network, no drawing. Vary `now` and the
sources and you can test a whole day of behaviour, and every unhappy path in
DESIGN §2.6, in milliseconds. That is the entire point of the boundary.

The shape of the work per region:

* A `Failure` in a source's slot → that region is unavailable; the other two are
  untouched (DESIGN §2.6). Content for a failed region is left empty.
* An available source with no data (no departures, a day with no events) is NOT
  a failure: the region stays available with an empty list, and the renderer
  draws the short "brak odjazdów" / "Brak wydarzeń" line, not "niedostępne".
* All UTC→Europe/Warsaw conversion and all display phrasing happen here, so the
  renderer only lays out finished strings.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .model import (
    ATTRIBUTION,
    BUS_ROWS,
    NEAR_MINUTES,
    WARSAW,
    WEATHER_HOURS,
    BusRow,
    Dashboard,
    Departure,
    Event,
    EventView,
    Failure,
    HourPoint,
    HourView,
    Region,
    Sources,
    WeatherData,
    WeatherView,
)

# Open-Meteo WMO weather codes → (Polish condition word, renderer icon key). The
# codes are grouped exactly as Open-Meteo documents them; the icon key is a small
# fixed vocabulary the renderer (T03) will map to glyphs. An unknown code falls
# back to a neutral cloud rather than crashing the screen.
_WEATHER: dict[int, tuple[str, str]] = {
    0: ("Bezchmurnie", "sun"),
    1: ("Przeważnie słonecznie", "part-cloud"),
    2: ("Częściowe zachmurzenie", "part-cloud"),
    3: ("Pochmurno", "cloud"),
    45: ("Mgła", "fog"),
    48: ("Mgła osadzająca szron", "fog"),
    51: ("Mżawka", "drizzle"),
    53: ("Mżawka", "drizzle"),
    55: ("Mżawka", "drizzle"),
    56: ("Marznąca mżawka", "drizzle"),
    57: ("Marznąca mżawka", "drizzle"),
    61: ("Deszcz", "rain"),
    63: ("Deszcz", "rain"),
    65: ("Silny deszcz", "rain"),
    66: ("Marznący deszcz", "rain"),
    67: ("Marznący deszcz", "rain"),
    71: ("Śnieg", "snow"),
    73: ("Śnieg", "snow"),
    75: ("Silny śnieg", "snow"),
    77: ("Ziarna śniegu", "snow"),
    80: ("Przelotny deszcz", "rain"),
    81: ("Przelotny deszcz", "rain"),
    82: ("Ulewny deszcz", "rain"),
    85: ("Przelotny śnieg", "snow"),
    86: ("Przelotny śnieg", "snow"),
    95: ("Burza", "storm"),
    96: ("Burza z gradem", "storm"),
    99: ("Burza z gradem", "storm"),
}
_WEATHER_FALLBACK = ("—", "cloud")


def _icon_for(code: int) -> str:
    """The renderer icon key for a WMO weather code, or the fallback cloud for an
    unknown code. Used for both the current conditions and each hourly point, so
    the strip's icons match the big current-weather icon."""
    return _WEATHER.get(code, _WEATHER_FALLBACK)[1]


def assemble(
    sources: Sources, now: datetime, *, near_minutes: int = NEAR_MINUTES
) -> Dashboard:
    """Build the full view-model from fetched sources and the current time.

    `now` must be timezone-aware. Every source is handled independently so one
    failure never affects another (DESIGN §2.6). `near_minutes` is retained for
    interface and config compatibility (the composition root still passes it) but
    no longer affects the board: the departure label is now driven by the feed's
    realtime/scheduled status, not by distance (DESIGN §2.3, owner 2026-09-06)."""
    now_local = now.astimezone(WARSAW)

    if isinstance(sources.weather, Failure):
        weather_view: WeatherView | None = None
        weather_region = Region(available=False, as_of=None)
    else:
        weather_view = _weather_view(sources.weather, now)
        weather_region = Region(available=True, as_of=now)

    if isinstance(sources.bus, Failure):
        buses: list[BusRow] = []
        buses_region = Region(available=False, as_of=None)
    else:
        buses = _bus_rows(sources.bus, now)
        buses_region = Region(available=True, as_of=now)

    if isinstance(sources.calendar, Failure):
        today: list[EventView] = []
        tomorrow: list[EventView] = []
        calendar_region = Region(available=False, as_of=None)
    else:
        today, tomorrow = _calendar_buckets(sources.calendar, now)
        calendar_region = Region(available=True, as_of=now)

    return Dashboard(
        now_local=now_local,
        weather=weather_view,
        weather_region=weather_region,
        buses=buses,
        buses_region=buses_region,
        today=today,
        tomorrow=tomorrow,
        calendar_region=calendar_region,
        attribution=ATTRIBUTION,
    )


# --- weather ----------------------------------------------------------------


def _weather_view(w: WeatherData, now: datetime) -> WeatherView:
    condition = _WEATHER.get(w.condition_code, _WEATHER_FALLBACK)[0]
    icon = _icon_for(w.condition_code)
    return WeatherView(
        temp_c=w.temp_c,
        condition=condition,
        icon=icon,
        feels_like_c=w.feels_like_c,
        wind_kmh=w.wind_kmh,
        hours=_weather_hours(w.hourly, now),
    )


def _weather_hours(hourly: list[HourPoint], now: datetime) -> list[HourView]:
    """The rest of today's hours, localized and capped (DESIGN §2.2). Keeps the
    points strictly after `now` that still fall on today's local calendar day,
    sorted, up to WEATHER_HOURS. Near midnight this can be empty, which the
    renderer handles as an empty strip."""
    now_local = now.astimezone(WARSAW)
    rows: list[HourView] = []
    for pt in sorted(hourly, key=lambda p: p.time):
        local = pt.time.astimezone(WARSAW)
        if pt.time > now and local.date() == now_local.date():
            rows.append(
                HourView(
                    label=local.strftime("%H"),
                    temp_c=pt.temp_c,
                    rain_pct=pt.rain_pct,
                    icon=_icon_for(pt.code),
                )
            )
    return rows[:WEATHER_HOURS]


# --- buses ------------------------------------------------------------------


def _bus_rows(departures: list[Departure], now: datetime) -> list[BusRow]:
    """Upcoming departures, sorted by time and capped (DESIGN §2.3). Departures
    already gone (`when < now`) are dropped so the list never shows a negative
    "za N min". An empty result is a valid available region ("brak odjazdów")."""
    upcoming = sorted((d for d in departures if d.when >= now), key=lambda d: d.when)
    return [
        BusRow(line=d.line, headsign=d.headsign, label=_bus_label(d.when, now, d.realtime))
        for d in upcoming[:BUS_ROWS]
    ]


def _bus_label(when: datetime, now: datetime, realtime: bool) -> str:
    """A GPS-tracked departure shows a live countdown ("za N min"); a schedule-only
    one shows its timetable clock time. The format itself signals the source, so a
    clock time on the board always means "from the timetable, not yet tracked"
    (DESIGN §2.3, owner 2026-09-06). This replaced an earlier near/far rule keyed on
    `near_minutes`, which is why that config value no longer drives the label."""
    if realtime:
        delta_min = (when - now).total_seconds() / 60
        return f"za {max(0, round(delta_min))} min"
    return when.astimezone(WARSAW).strftime("%H:%M")


# --- calendar ---------------------------------------------------------------


def _calendar_buckets(
    events: list[Event], now: datetime
) -> tuple[list[EventView], list[EventView]]:
    """Split events into today's and tomorrow's columns by Europe/Warsaw calendar
    day (DESIGN §2.4). Today drops timed events already past `now`; all-day events
    are always kept for their day. Each column is sorted by start, so an all-day
    event (local midnight) sorts to the top of its column, matching the mock."""
    now_local = now.astimezone(WARSAW)
    today_date = now_local.date()
    tomorrow_date = today_date + timedelta(days=1)

    today: list[EventView] = []
    tomorrow: list[EventView] = []
    for ev in sorted(events, key=lambda e: e.start):
        local = ev.start.astimezone(WARSAW)
        day = local.date()
        if day == today_date:
            if ev.all_day or ev.start >= now:
                today.append(_event_view(ev, local))
        elif day == tomorrow_date:
            tomorrow.append(_event_view(ev, local))
    return today, tomorrow


def _event_view(ev: Event, local: datetime) -> EventView:
    label = "" if ev.all_day else local.strftime("%H:%M")
    return EventView(label=label, title=ev.title, all_day=ev.all_day)
