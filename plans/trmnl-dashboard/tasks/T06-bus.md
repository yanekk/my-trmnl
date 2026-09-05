# T06 — Bus adapter (ckan2 live departures)

**Phase:** 2 · **Depends on:** T02 · **Weight:** medium

## Goal

Fetch live next-departures for the owner's line from their stops, using Gdańsk's open-data
departures endpoint, and turn them into the core's list of `Departure`s. This includes
resolving stop names to the numeric `stopId` the endpoint needs, from the daily stops dataset,
and caching that so we do not re-download it every cycle. Parsing and resolution are tested
against recorded responses, including the empty and broken shapes the feed really produces.

## Design sections this implements

DESIGN.md §2.3 (the endpoint, the per-pole `stopId`, direction via headsign, UTC times,
attribution, the dead `/delays` endpoint), §2.6 (empty/404 for a stop is "no departures", a
network failure is `Failure`), §3.1 (world-facing adapter).

## Files

- `trmnl/adapters/bus.py` — stop resolution + departures fetch.
- `tests/adapters/fixtures/ckan_departures_*.json`, `ckan_stops_sample.json`.
- `tests/adapters/test_bus.py`.

## Interface

```python
def resolve_stop_ids(stop_names: list[str], stops_json: dict) -> dict[str, int]
def fetch_departures(stop_ids: list[int], line: str, now, client) -> list[Departure] | Failure
```

- `resolve_stop_ids` matches `stopName` (optionally `zoneName == "Gdańsk"`) in the dataset;
  a name may map to more than one pole (directions) and all are kept.
- `fetch_departures` calls `https://ckan2.multimediagdansk.pl/departures?stopId={id}` per stop,
  keeps rows where `routeShortName == line`, reads `estimatedTime` (UTC) as the departure time,
  and returns the merged list for the core to sort and phrase.
- An empty `departures` array or a 404 for one stop contributes no rows and is not a failure.
- A network error or unparseable body across the board returns `Failure`.
- The stops dataset is fetched once and cached; a URL that has moved (the download path carries
  a dataset UUID that can change) is re-resolved from the resource page or falls back to cache.

## Tests

- [ ] `resolve_stop_ids` finds the pole(s) for a stop name and returns all matching `stopId`s.
- [ ] A stop name with two direction poles resolves to both ids.
- [ ] `fetch_departures` parses a recorded response into `Departure`s filtered to the line.
- [ ] Rows for other lines at the same stop are excluded.
- [ ] An empty `departures: []` yields no rows and is not `Failure`.
- [ ] A 404 for one stop of several still returns the others' rows.
- [ ] A total network error returns `Failure`.
- [ ] `estimatedTime` is read as UTC and carried through tz-aware.
- [ ] The legacy `/delays` path is not used anywhere (grep-level check acceptable).

## Done when

- [ ] Stop names resolve to ids and live departures parse into the core's list, from fixtures.
- [ ] Every empty/partial/broken case behaves per DESIGN §2.3/§2.6, none of them raising.
- [ ] Tests hit no network; the suite is green and quiet.

## Needs a person

The two stop names (or ids) and the line are config only the owner knows; the mock used line
227 with Jelitkowo / Chełm Cienista, which are real. Confirm the exact stops and direction with
the owner during this task, record them in FINDINGS, and put them in config.
