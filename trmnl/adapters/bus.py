"""Bus adapter — Gdańsk ckan2 live departures → the core's `Departure` list
(DESIGN §2.3, §2.6, §3.1).

The live feed fuses schedule and realtime into one per-pole response and needs no
API key (DESIGN §2.3). This module is the world-facing side: it resolves stop
*names* to the numeric pole ids the endpoint wants, fetches each pole's
departures, and parses the rows for one line into the core's plain `Departure`
shape. It reads no clock and makes no display decisions — `estimatedTime` comes
back tz-aware in UTC and the core (`assemble._bus_rows`) sorts, drops past
departures, phrases "za N min" and localizes to Europe/Warsaw.

Three shapes of failure, none of them an exception into the caller (DESIGN §2.6):

* One pole returns empty (`departures: []`) or 404 → that pole contributes no
  rows and is *not* a failure; the other poles still render (DESIGN §2.6). An
  all-empty result is a valid available region ("brak odjazdów").
* Every pole fails to fetch (network error / non-200 / unparseable body across
  the board) → `Failure`, so `assemble` marks the region "niedostępne".
* A `Failure` is returned rather than raised, so the refresh loop never catches.

The legacy `/delays` endpoint is dead (404) and is deliberately not used
anywhere here (DESIGN §2.3); the live path is `/departures`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from trmnl.adapters.isotime import from_iso
from trmnl.core.model import Departure, Failure

# The live per-pole departures feed. No key, no account (DESIGN §2.3). One HTTP
# GET per pole with a `stopId` query.
_DEPARTURES_URL = "https://ckan2.multimediagdansk.pl/departures"

# The daily stops dataset, keyed by date, each date carrying a `stops` array of
# poles. The download path embeds a dataset UUID that can change when ZTM
# republishes the resource; T08 owns fetching this once, caching it, and
# re-resolving the URL if it has moved (DESIGN §2.3, §3.5). It is a parameter of
# `fetch_stops` so that re-resolution stays the composition root's concern.
_STOPS_URL = (
    "https://ckan.multimediagdansk.pl/dataset/"
    "c24aa637-3619-4dc2-a171-a23eec8f2172/resource/"
    "4c4025f0-01bf-41f7-a39f-d156d201b82b/download/stops.json"
)

# The zone the poles must sit in. Two cities in the tri-city share stop names, so
# without this a name like "Hynka" could match a Gdynia pole too (DESIGN §2.3).
_DEFAULT_ZONE = "Gdańsk"

# One slow source must not delay the whole image (DESIGN §2.6), so every fetch is
# bounded. Set on the call so the guarantee holds whatever client is injected.
_TIMEOUT_S = 10.0

# The stops dataset is ~9 MB, so it gets a longer bound than a per-pole fetch.
# It is downloaded rarely (once, then cached — DESIGN §3.5), never per cycle.
_STOPS_TIMEOUT_S = 30.0


def resolve_stop_ids(
    stop_names: list[str], stops_json: dict, zone: str | None = _DEFAULT_ZONE
) -> dict[str, list[int]]:
    """Map each requested stop name to the pole ids that serve it.

    A physical stop is one pole with its own `stopId`; the two directions of a
    street are two different poles sharing a `stopName`, and the feed carries no
    direction field, so every matching pole is kept and direction is fixed later
    by the pole plus the `headsign` (DESIGN §2.3). The return is therefore a list
    of ids per name, not a single id — the task's `dict[str, int]` signature
    predates that clarification; its own prose ("a name may map to more than one
    pole … and all are kept") is the binding requirement.

    `zone` (default "Gdańsk") excludes same-named poles in the neighbouring cities
    (DESIGN §2.3); pass `None` to match on name alone. `stops_json` may be the raw
    date-keyed dataset (`{date: {stops: [...]}}`) or an already-unwrapped
    `{stops: [...]}` — both are accepted, and poles repeated across date buckets
    are de-duplicated by id. Every requested name appears in the result, mapping
    to a sorted (possibly empty) id list so a name that resolved to nothing is
    visible to the caller rather than silently dropped."""
    # Union the poles across whatever date buckets the dataset holds, keeping one
    # entry per stopId (the same pole repeats once per day in the raw file).
    poles: dict[int, dict] = {}
    for stop in _iter_stops(stops_json):
        sid = stop.get("stopId")
        if isinstance(sid, int) and sid not in poles:
            poles[sid] = stop

    result: dict[str, list[int]] = {}
    for name in stop_names:
        ids = [
            sid
            for sid, stop in poles.items()
            if stop.get("stopName") == name
            and (zone is None or stop.get("zoneName") == zone)
        ]
        result[name] = sorted(ids)
    return result


def _iter_stops(stops_json: dict):
    """Yield pole records from either dataset shape (see `resolve_stop_ids`)."""
    inner = stops_json.get("stops")
    if isinstance(inner, list):
        yield from inner
        return
    for value in stops_json.values():
        if isinstance(value, dict) and isinstance(value.get("stops"), list):
            yield from value["stops"]


def fetch_departures(
    stop_ids: list[int], line: str, now: datetime, client: httpx.Client
) -> list[Departure] | Failure:
    """Fetch upcoming departures of `line` across `stop_ids`, merged for the core.

    Each pole is fetched independently: a pole that errors (network, non-200
    including 404) or returns an unparseable body contributes no rows but does not
    fail the whole region (DESIGN §2.6), so a dead pole never hides a live one.
    Only when *every* pole fails does this return `Failure`. An all-empty result
    (poles reachable, no departures) is a valid empty list, which the core draws
    as "brak odjazdów" — empty is not "down".

    Rows are returned unsorted and unfiltered by time: sorting, dropping past
    departures and phrasing are the core's job (DESIGN §3.1). `now` is accepted
    for interface symmetry with the other adapters and is unused here. `client` is
    an injected `httpx.Client` so tests stub it and hit no network."""
    any_reached = False
    rows: list[Departure] = []
    for stop_id in stop_ids:
        parsed = _fetch_one_pole(stop_id, line, client)
        if parsed is None:
            continue  # this pole failed to fetch or parse; others still count
        any_reached = True
        rows.extend(parsed)

    if not any_reached:
        # No pole was reachable and parseable — an honest region-down, not an
        # empty timetable. Distinguished from `rows == []` with some pole reached.
        return Failure(f"bus: no pole reachable among {stop_ids}")
    return rows


def _fetch_one_pole(
    stop_id: int, line: str, client: httpx.Client
) -> list[Departure] | None:
    """Fetch and parse one pole. Returns its `Departure` rows (possibly empty) on
    a clean 200, or `None` if the pole could not be reached or its body could not
    be parsed — `None` is "skip this pole", never turned into a screen error on
    its own (DESIGN §2.6)."""
    try:
        resp = client.get(
            _DEPARTURES_URL, params={"stopId": stop_id}, timeout=_TIMEOUT_S
        )
    except httpx.HTTPError:
        return None

    # A 404 for a pole is "no departures here", handled the same as an empty body
    # (DESIGN §2.6): skip the pole, do not fail the region.
    if resp.status_code != 200:
        return None

    try:
        return _parse_pole(resp.json(), line)
    except (ValueError, KeyError, TypeError, IndexError):
        # ValueError also covers json() on a non-JSON body and fromisoformat on a
        # malformed timestamp; a half-parsed pole is never returned.
        return None


def _parse_pole(payload: dict, line: str) -> list[Departure]:
    """Turn one pole's decoded response into `Departure`s for `line`.

    Reads `estimatedTime` as the departure time per DESIGN §2.3. The feed's
    `status` tells GPS-tracked from schedule-only: a REALTIME row is a bus being
    tracked, and its `estimatedTime` already includes any delay; a SCHEDULED row
    has no bus reporting yet, and its `estimatedTime` equals the timetable time.
    Both carry `estimatedTime`, so both are shown — the board just labels them
    differently (`realtime` flag). `delayInSeconds` is informational and unused
    once the estimate is read. A missing `departures` key, a non-list, or a
    matching-line row missing a field it needs raises and the caller skips the
    pole. Rows for other lines are filtered out before their fields are touched,
    so an oddly-shaped row for a line we do not show cannot fail our pole."""
    departures = payload["departures"]

    rows: list[Departure] = []
    for row in departures:
        short_name = str(row["routeShortName"])
        if short_name != line:
            continue
        # The feed stamps ISO times with a trailing "Z"; from_iso parses that on
        # Python 3.9 too (stdlib fromisoformat only accepts "Z" from 3.11 — the
        # deploy Pi is 3.9, DESIGN §5). Guard the naive case anyway so a format
        # without an offset is stamped UTC rather than leaking a naive datetime
        # into the core, which compares it against a tz-aware `now`.
        when = from_iso(row["estimatedTime"])
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        # Only an explicit REALTIME status is treated as GPS-tracked; anything else
        # (SCHEDULED, or a missing status) is schedule-only, so a lost status field
        # degrades safely to a clock time rather than a false live countdown.
        realtime = row.get("status") == "REALTIME"
        # `vehicleCode` is the fleet number painted on the bus (an int in the feed);
        # null for a schedule-only run with no vehicle assigned. Stringify it here so
        # the core and renderer never touch a raw number.
        code = row.get("vehicleCode")
        vehicle = str(code) if code is not None else None
        rows.append(
            Departure(
                line=short_name,
                headsign=row["headsign"],
                when=when,
                realtime=realtime,
                vehicle=vehicle,
            )
        )
    return rows


def fetch_stops(
    client: httpx.Client, url: str = _STOPS_URL
) -> dict | Failure:
    """Download and parse the daily stops dataset for `resolve_stop_ids`.

    Returns the raw parsed dict (date-keyed) on a clean 200, or `Failure` on any
    network error, non-200, or non-object body — never raising (DESIGN §2.6). The
    composition root (T08) calls this once and caches the result rather than
    re-downloading the ~9 MB file every cycle (DESIGN §3.5); if `url` has moved,
    re-resolving it is also T08's concern (see `_STOPS_URL`)."""
    try:
        resp = client.get(url, timeout=_STOPS_TIMEOUT_S)
    except httpx.HTTPError as exc:
        return Failure(f"stops: request failed: {exc}")

    if resp.status_code != 200:
        return Failure(f"stops: HTTP {resp.status_code}")

    try:
        data = resp.json()
    except ValueError as exc:
        return Failure(f"stops: unparseable body: {exc}")

    if not isinstance(data, dict):
        return Failure("stops: body was not a JSON object")
    return data
