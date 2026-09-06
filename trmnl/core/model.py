"""The data shapes on both sides of the pure core (DESIGN §3.1, §3.2).

Two families live here:

* **Raw inputs** the adapters fill (`WeatherData`, `Departure`, `HourPoint`,
  `Event`, wrapped in `Sources`). Times in these are tz-aware and generally UTC
  as fetched; the core converts them to Europe/Warsaw. A source that failed to
  fetch is a `Failure` marker in its slot, never an exception and never stale
  data.
* **The view-model** the renderer draws (`Dashboard` and the `*View`/`Region`
  pieces). Everything the screen shows is already decided here: the Polish
  condition word, the "za N min" phrasing, which regions are unavailable, the
  local-time labels. The renderer only lays these out; it makes no decisions.

Nothing here reads the clock or the network — `now` is always an argument. That
is the rule the boundary guard (tests/test_boundary.py) enforces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

# Every local time on the screen is Europe/Warsaw (DESIGN §2.1). Constructing a
# ZoneInfo is not a clock read, so the core is free to hold this.
WARSAW = ZoneInfo("Europe/Warsaw")

# CC-BY 4.0 obligation for the Gdańsk open-data bus feed (DESIGN §2.3): the
# screen must credit the source whenever it uses it. Kept constant and always
# rendered so the credit can never silently drop off.
ATTRIBUTION = "Otwarte dane ZTM Gdańsk"

# A departure closer than this many minutes reads as "za N min"; further off, as
# a clock time (DESIGN §2.3). Config may override the default at T08.
NEAR_MINUTES = 15

# How many rows/columns each region can hold before it overflows its box. These
# are display capacities the renderer (T03) draws to; kept here because the core
# does the capping so the renderer never has to.
BUS_ROWS = 5
WEATHER_HOURS = 6


# --- failure marker ---------------------------------------------------------


@dataclass(frozen=True)
class Failure:
    """A source that could not be fetched or parsed this cycle. Its region draws
    "niedostępne" (DESIGN §2.6). `reason` is for the server log, never the screen."""

    reason: str = ""


# --- raw inputs the adapters fill -------------------------------------------


@dataclass(frozen=True)
class HourPoint:
    """One hour of the forecast. `time` is tz-aware (UTC as fetched); the core
    localizes it and keeps only the rest of today (DESIGN §2.2). `code` is that
    hour's Open-Meteo WMO weather code; the core maps it to an icon key for the
    hourly strip, the same mapping the current conditions use."""

    time: datetime
    temp_c: int
    rain_pct: int
    code: int


@dataclass(frozen=True)
class WeatherData:
    """Current conditions plus the hourly forecast. `condition_code` is an
    Open-Meteo WMO weather code; the core maps it to a Polish word and an icon
    key so the mapping is testable and lives on the pure side."""

    temp_c: int
    condition_code: int
    feels_like_c: int
    wind_kmh: int
    hourly: list[HourPoint] = field(default_factory=list)


@dataclass(frozen=True)
class Departure:
    """One upcoming bus. `when` is tz-aware (UTC as fetched from ckan2). There is
    no direction field in the feed; direction is implied by `headsign` and the
    stop the adapter chose (DESIGN §2.3).

    `realtime` is the feed's `status`: True for a GPS-tracked bus (REALTIME, `when`
    is the live estimate), False for a schedule-only run (SCHEDULED, `when` is the
    timetable time, no bus reporting yet). The board shows the two differently — a
    live countdown vs a clock time (DESIGN §2.3)."""

    line: str
    headsign: str
    when: datetime
    realtime: bool


@dataclass(frozen=True)
class Event:
    """One calendar event. `start` is always a tz-aware datetime, even for
    all-day events (local midnight of the event's day) — the core needs a date to
    bucket the event into today/tomorrow. `all_day` controls only whether a time
    label is shown, not whether `start` is present."""

    start: datetime
    title: str
    all_day: bool = False


@dataclass(frozen=True)
class Sources:
    """What the three adapters fetched this cycle, each either the parsed data or
    a `Failure` marker. Passed to `assemble` together with `now`."""

    weather: WeatherData | Failure
    bus: list[Departure] | Failure
    calendar: list[Event] | Failure


@dataclass(frozen=True)
class ServiceHours:
    """The daily window, in local (Europe/Warsaw) hours, during which buses run
    and the screen refreshes fast. `start_hour <= hour < end_hour` is in-window.
    Does not cross midnight (start < end); the real values come from config at T08."""

    start_hour: int
    end_hour: int


# --- the view-model the renderer draws --------------------------------------


@dataclass(frozen=True)
class Region:
    """Per-region availability. `available` False means the renderer draws
    "niedostępne" and ignores the region's content (DESIGN §2.6). `as_of` is the
    time the screen was built for an available region — not shown today (the top
    bar was dropped, DESIGN §2.1), kept for the possible "akt. HH:MM" footer (§7)."""

    available: bool
    as_of: datetime | None


@dataclass(frozen=True)
class HourView:
    """One column of the hourly strip, already localized. `label` is the local
    hour, e.g. "09"; `icon` is the renderer's icon key for that hour's expected
    weather (same vocabulary as `WeatherView.icon`)."""

    label: str
    temp_c: int
    rain_pct: int
    icon: str


@dataclass(frozen=True)
class WeatherView:
    """Current weather ready to draw. `condition` is the Polish word, `icon` a
    key the renderer maps to a glyph (e.g. "sun", "cloud", "rain")."""

    temp_c: int
    condition: str
    icon: str
    feels_like_c: int
    wind_kmh: int
    hours: list[HourView] = field(default_factory=list)


@dataclass(frozen=True)
class BusRow:
    """One departure ready to draw. `label` is the finished phrasing — "za 3 min"
    or "08:49" — so the renderer makes no time decisions."""

    line: str
    headsign: str
    label: str


@dataclass(frozen=True)
class EventView:
    """One calendar event ready to draw. `label` is the local start time
    ("09:30") for a timed event, or empty for an all-day one (the renderer draws
    an all-day badge instead)."""

    label: str
    title: str
    all_day: bool


@dataclass(frozen=True)
class Dashboard:
    """The whole screen as data. The renderer turns this into 800×480 pixels and
    decides nothing on its own. An unavailable region carries empty content and
    an `available=False` Region; an available-but-empty region (no departures, a
    day with no events) carries an empty list and `available=True`, so the
    renderer can tell "niedostępne" from "brak odjazdów"/"Brak wydarzeń"
    (DESIGN §2.6)."""

    now_local: datetime
    weather: WeatherView | None
    weather_region: Region
    buses: list[BusRow]
    buses_region: Region
    today: list[EventView]
    tomorrow: list[EventView]
    calendar_region: Region
    attribution: str
