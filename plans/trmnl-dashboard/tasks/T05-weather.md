# T05 — Weather adapter (Open-Meteo)

**Phase:** 2 · **Depends on:** T02 · **Weight:** light

## Goal

Fetch Gdańsk weather from Open-Meteo and turn it into the core's weather input: current
conditions plus an hourly strip for the rest of today. Open-Meteo needs no account or key, so
there is nothing to rotate or leak on the home box. Parsing is tested against a recorded
response, not the live service, so the test suite is offline and deterministic.

## Design sections this implements

DESIGN.md §2.2 (weather content and the Open-Meteo choice), §2.6 (a fetch failure becomes a
`Failure` marker so the core can mark the region unavailable), §3.1 (adapters are the
world-facing side).

## Files

- `trmnl/adapters/weather.py` — `fetch_weather(lat, lon, now, client) -> WeatherData | Failure`.
- `tests/adapters/fixtures/open_meteo_*.json` — recorded responses.
- `tests/adapters/test_weather.py`.

## Interface

```python
def fetch_weather(lat: float, lon: float, now: datetime, client) -> WeatherData | Failure
```

Requests current weather and hourly temperature + precipitation probability for today, metric,
timezone handled by converting from the API's timestamps in the core (the adapter returns raw
tz-aware values; display formatting stays pure). A timeout is set; any network error, non-200,
or unparseable body returns `Failure`, never raises into the caller. The hourly strip is
trimmed to the remaining hours of today by the core, not here — the adapter returns the day's
hourly series and lets `assemble` cut it against `now`.

## Tests

- [ ] A recorded normal response parses into `WeatherData` with current temp, condition, wind,
      and the hourly series.
- [ ] A non-200 status returns `Failure`.
- [ ] A timeout / connection error returns `Failure` (client stubbed to raise).
- [ ] A 200 with missing or malformed fields returns `Failure`, not a half-filled object.
- [ ] Units are metric and values are the expected types (numbers, not strings).

## Done when

- [ ] `fetch_weather` returns `WeatherData` from the recorded fixture and `Failure` on every
      error path, never raising.
- [ ] Tests hit no network (fixtures only).
- [ ] The suite is green and quiet.

## Needs a person

The Gdańsk coordinates are config the owner confirms. A default (city-centre Gdańsk lat/lon) is
fine to ship; note in FINDINGS if the owner gives a specific point (e.g. their neighbourhood).
