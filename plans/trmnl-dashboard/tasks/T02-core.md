# T02 — Pure core: view-model, assemble, refresh policy

**Phase:** 1 · **Depends on:** T01 · **Weight:** medium

## Goal

Build the brain of the dashboard: the pure functions that turn whatever the adapters fetched,
plus the current time, into the exact view-model the renderer draws — and the refresh interval
the server reports. Because this is pure (no clock, no network, no drawing), a whole day of
behaviour and every failure case is testable in milliseconds. This is where the today/tomorrow
bucketing, the departure phrasing, the per-region "unavailable" logic and the refresh policy
all live.

## Design sections this implements

DESIGN.md §2.2–§2.6 (what each region shows and every unhappy path), §2.5 (refresh policy),
§3.1–§3.3 (the boundary and the `assemble` decision function).

## Files

- `trmnl/core/model.py` — dataclasses.
- `trmnl/core/assemble.py` — `assemble(inputs, now) -> Dashboard`.
- `trmnl/core/refresh.py` — `refresh_seconds(now, service) -> int`.
- `tests/core/…`.

## Interface

Shapes are illustrative but the boundary is real: every function takes its inputs and `now` as
arguments and returns data. `now` is a timezone-aware `datetime`.

```python
@dataclass(frozen=True)
class Departure:      line: str; headsign: str; when: datetime      # tz-aware, UTC in
@dataclass(frozen=True)
class HourPoint:      hour: int; temp_c: int; rain_pct: int
@dataclass(frozen=True)
class Event:          start: datetime | None; title: str; all_day: bool

# Raw inputs: each is either the parsed data or a Failure marker (source unavailable).
@dataclass(frozen=True)
class Sources:
    weather:  WeatherData | Failure
    bus:      list[Departure] | Failure
    calendar: list[Event] | Failure

# View-model the renderer consumes:
@dataclass(frozen=True)
class Region:         available: bool; as_of: datetime | None       # False -> draw "niedostępne"
@dataclass(frozen=True)
class BusRow:         line: str; headsign: str; label: str          # "za 3 min" or "08:49"
@dataclass(frozen=True)
class Dashboard:
    now_local: datetime
    weather: WeatherView;  weather_region: Region
    buses: list[BusRow];   buses_region: Region
    today: list[EventView]; tomorrow: list[EventView]; calendar_region: Region
    attribution: str                                                # e.g. "Otwarte dane ZTM Gdańsk"

def assemble(sources: Sources, now: datetime) -> Dashboard: ...
def refresh_seconds(now: datetime, service: ServiceHours) -> int:   # 60 in-window, 1800 out
```

Phrasing rule (pure): a departure within `NEAR_MINUTES` (config, default ~15) renders as
`"za N min"`; otherwise as `HH:MM` in Europe/Warsaw. Bus rows are sorted by `when` and capped
to a fixed count that fits the region. Today/tomorrow buckets are Europe/Warsaw calendar days
derived from `now`; today drops events already past.

## Tests

- [ ] Today/tomorrow bucketing rolls over at Europe/Warsaw midnight, tested across the boundary.
- [ ] An event earlier today than `now` is excluded; an all-day event today is included.
- [ ] Departure phrasing: `< NEAR_MINUTES` → "za N min"; `>=` → clock; sorted by time; capped.
- [ ] UTC departure/event times display in Europe/Warsaw (test across a DST change).
- [ ] Each source independently `Failure` → its `Region.available == False`, others unaffected.
- [ ] All three `Failure` → three unavailable regions, still a valid `Dashboard`.
- [ ] `refresh_seconds`: inside service hours → 60; outside → 1800; tested at both edges.
- [ ] Empty bus list (no departures) is not a failure — region available, list empty (the
      renderer draws "brak odjazdów"; DESIGN §2.6).
- [ ] A calendar day with no events is not a failure — region available, that day's list empty
      (the renderer draws "Brak wydarzeń"; DESIGN §2.4). Distinct from calendar `Failure`.
- [ ] `attribution` is always populated.

## Done when

- [ ] `assemble` and `refresh_seconds` are pure — the boundary guard test (T01) passes.
- [ ] Every unhappy path in DESIGN §2.6 that is a core concern has a test named for it.
- [ ] The suite is green and quiet.
