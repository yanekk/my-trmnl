"""Vehicle-database adapter — ZTM's `baza-pojazdow.json` → `{fleet number →
VehicleInfo}` (DESIGN §2.3, §2.6, §3.1, task T10).

The database is one JSON file listing every ZTM vehicle by fleet number, each
record carrying `vehicleCode`, `brand` and `model`. This module is the
world-facing side: it fetches and parses that file into the core's plain
`VehicleInfo` lookup, keyed by the stringified fleet number so it joins directly
to a `Departure.vehicle` (which T06 already stringifies from the feed's int).

It reads no clock, does no disk I/O and holds no cache — the disk cache and the
miss-triggered refetch are the composition root's concern (DESIGN §3.1, and
`server/loop.VehicleCache`). Like the other adapters it never raises into the
caller: any network error, non-200, unparseable body or wrong shape comes back as
a `Failure` (DESIGN §2.6), so a vehicle-database problem falls the rows back to
numbers rather than failing the bus region.

A record missing `brand`/`model` (or not an object) is skipped rather than failing
the whole parse: one bad row must not lose the other ~509 vehicles. Only a body
that is not an object, or has no `results` list, is a `Failure` — that is a broken
download, not a sparse one.
"""

from __future__ import annotations

import httpx

from trmnl.core.model import Failure, VehicleInfo

# The vehicle database. One JSON file, ~340 KB, no key (DESIGN §2.3). Downloaded
# rarely — only when a cycle's schedule holds a fleet number not already cached
# (T10) — never every cycle.
_VEHICLES_URL = "https://files.cloudgdansk.pl/d/otwarte-dane/ztm/baza-pojazdow.json?v=2"

# Bounded like every other fetch so one slow source cannot stall the image
# (DESIGN §2.6). A touch longer than a per-pole bus fetch because the body is
# larger, but it is off the per-cycle path so the bound is generous.
_TIMEOUT_S = 15.0


def fetch_vehicles(
    client: httpx.Client, url: str = _VEHICLES_URL
) -> dict[str, VehicleInfo] | Failure:
    """Fetch and parse the ZTM vehicle database into `{fleet number → VehicleInfo}`.

    Returns the lookup on a clean 200 with a well-shaped body, or `Failure` on any
    network error, non-200, non-JSON body, or a body that is not an object or lacks
    a `results` list — never raising (DESIGN §2.6). Keys are stringified fleet
    numbers so they join to `Departure.vehicle`. A record that is not an object, or
    is missing a non-empty `brand`/`model`, is skipped, not fatal: a single bad row
    must not lose the whole database. `client` is injected so tests stub it and hit
    no network."""
    try:
        resp = client.get(url, timeout=_TIMEOUT_S)
    except httpx.HTTPError as exc:
        return Failure(f"vehicles: request failed: {exc}")

    if resp.status_code != 200:
        return Failure(f"vehicles: HTTP {resp.status_code}")

    try:
        data = resp.json()
    except ValueError as exc:
        return Failure(f"vehicles: unparseable body: {exc}")

    if not isinstance(data, dict):
        return Failure("vehicles: body was not a JSON object")
    results = data.get("results")
    if not isinstance(results, list):
        return Failure("vehicles: body missing a 'results' list")

    out: dict[str, VehicleInfo] = {}
    for rec in results:
        if not isinstance(rec, dict):
            continue
        code = rec.get("vehicleCode")
        brand = rec.get("brand")
        model = rec.get("model")
        # Skip a record that cannot fill a row rather than failing the parse. A bus
        # always carries brand and model (DESIGN §2.3); a record without them is a
        # non-bus or a partial row and is simply not looked up.
        if code is None or not brand or not model:
            continue
        out[str(code)] = VehicleInfo(brand=str(brand), model=str(model))
    return out
