"""Bus adapter tests (DESIGN §2.3, §2.6, §4). Stop resolution is checked against a
trimmed real stops dataset; departure parsing against recorded ckan2 responses,
including the empty, 404 and broken shapes the feed really produces. Every error
path uses a stubbed client — no test touches the network.

The fixtures are recorded from the live feed on 2026-09-05: `ckan_stops_sample`
holds both real Hynka poles in Gdańsk (1767, 1768) plus a synthetic same-named
pole in Gdynia (9999) to exercise the zone filter; the `hynka_1767`/`hynka_1768`
departure bodies are the real line-227 rows, with a non-227 row added to 1768 to
exercise line filtering.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from trmnl.adapters.bus import (
    fetch_departures,
    fetch_stops,
    resolve_stop_ids,
)
from trmnl.core.model import Departure, Failure

FIXTURES = Path(__file__).parent / "fixtures"

# The adapter ignores `now` (the core sorts and trims); a fixed tz-aware value
# stands in for it everywhere.
NOW = datetime(2026, 9, 5, 19, 0, tzinfo=timezone.utc)

# The two real Hynka poles serving line 227, opposite directions (DESIGN §2.3).
HYNKA_TO_CHELM = 1767
HYNKA_TO_JELITKOWO = 1768


def _dep(name: str) -> dict:
    return json.loads((FIXTURES / f"ckan_departures_{name}.json").read_text())


def _stops() -> dict:
    return json.loads((FIXTURES / "ckan_stops_sample.json").read_text())


class _StubResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        # A non-JSON body: httpx raises inside .json(); simulated by carrying an
        # exception to raise instead of returning a dict.
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _ok(payload) -> _StubResponse:
    return _StubResponse(200, payload)


class _StubClient:
    """Stands in for an httpx.Client. Routes a `/departures` GET to a per-stopId
    entry and a `/stops` GET to a single entry, so one client can model several
    poles behaving differently in the same call. An entry is either a
    `_StubResponse` to return or an `Exception` to raise; records every call so a
    test can assert what was requested."""

    def __init__(self, *, by_stop=None, default=None, stops=None):
        self._by_stop = by_stop or {}
        self._default = default
        self._stops = stops
        self.calls: list[dict] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if params and "stopId" in params:
            entry = self._by_stop.get(params["stopId"], self._default)
        else:
            entry = self._stops
        if isinstance(entry, Exception):
            raise entry
        return entry


# --- resolve_stop_ids -------------------------------------------------------


def test_resolve_finds_a_stops_poles():
    result = resolve_stop_ids(["Hynka"], _stops())
    assert result == {"Hynka": [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO]}


def test_resolve_keeps_both_direction_poles():
    # A name with two direction poles must resolve to both ids, sorted (DESIGN §2.3).
    ids = resolve_stop_ids(["Hynka"], _stops())["Hynka"]
    assert HYNKA_TO_CHELM in ids and HYNKA_TO_JELITKOWO in ids
    assert ids == sorted(ids)


def test_resolve_zone_filter_excludes_same_name_in_another_city():
    # The synthetic Gdynia "Hynka" (9999) must not leak into a Gdańsk resolution.
    assert 9999 not in resolve_stop_ids(["Hynka"], _stops())["Hynka"]


def test_resolve_zone_none_matches_on_name_alone():
    ids = resolve_stop_ids(["Hynka"], _stops(), zone=None)["Hynka"]
    assert 9999 in ids
    assert ids == [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO, 9999]


def test_resolve_unknown_name_maps_to_empty_list():
    # A name that resolves to nothing is present but empty, not dropped.
    assert resolve_stop_ids(["Nie ma takiego"], _stops()) == {"Nie ma takiego": []}


def test_resolve_handles_multiple_names_at_once():
    result = resolve_stop_ids(["Hynka", "Jelitkowo Kapliczna"], _stops())
    assert result["Hynka"] == [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO]
    assert result["Jelitkowo Kapliczna"] == [122]


def test_resolve_accepts_pre_unwrapped_stops_shape():
    # `resolve` accepts either the raw date-keyed dataset or an already-unwrapped
    # {stops: [...]} dict; feed it the inner shape and it still resolves.
    raw = _stops()
    day = next(iter(raw))
    unwrapped = {"stops": raw[day]["stops"]}
    assert resolve_stop_ids(["Hynka"], unwrapped)["Hynka"] == [
        HYNKA_TO_CHELM,
        HYNKA_TO_JELITKOWO,
    ]


# --- fetch_departures: the happy paths --------------------------------------


def test_parses_recorded_response_filtered_to_the_line():
    client = _StubClient(by_stop={HYNKA_TO_JELITKOWO: _ok(_dep("hynka_1768"))})
    result = fetch_departures([HYNKA_TO_JELITKOWO], "227", NOW, client)

    assert isinstance(result, list)
    # The 1768 body has two 227 rows plus one 199 row; only the 227s survive.
    assert len(result) == 2
    assert all(isinstance(d, Departure) for d in result)
    assert all(d.line == "227" for d in result)
    assert all(d.headsign == "Jelitkowo" for d in result)


def test_other_lines_at_the_same_pole_are_excluded():
    client = _StubClient(by_stop={HYNKA_TO_JELITKOWO: _ok(_dep("hynka_1768"))})
    result = fetch_departures([HYNKA_TO_JELITKOWO], "227", NOW, client)
    assert "199" not in {d.line for d in result}


def test_estimated_time_is_read_as_utc_and_tz_aware():
    client = _StubClient(by_stop={HYNKA_TO_JELITKOWO: _ok(_dep("hynka_1768"))})
    result = fetch_departures([HYNKA_TO_JELITKOWO], "227", NOW, client)
    first = min(result, key=lambda d: d.when)
    assert first.when == datetime(2026, 9, 5, 19, 9, 49, tzinfo=timezone.utc)
    assert first.when.tzinfo is not None
    assert first.when.utcoffset() == timezone.utc.utcoffset(None)


def test_status_sets_the_realtime_flag():
    # The feed's `status` marks GPS-tracked (REALTIME) vs schedule-only (SCHEDULED);
    # a missing status degrades to schedule-only, not a false live countdown.
    payload = {
        "departures": [
            {"routeShortName": "227", "headsign": "GPS",
             "estimatedTime": "2026-09-05T19:10:00Z", "status": "REALTIME",
             "vehicleCode": 3112},
            {"routeShortName": "227", "headsign": "Rozkład",
             "estimatedTime": "2026-09-05T19:52:00Z", "status": "SCHEDULED"},
            {"routeShortName": "227", "headsign": "BezStatusu",
             "estimatedTime": "2026-09-05T19:20:00Z"},
        ]
    }
    client = _StubClient(by_stop={HYNKA_TO_JELITKOWO: _ok(payload)})
    result = fetch_departures([HYNKA_TO_JELITKOWO], "227", NOW, client)
    assert {d.headsign: d.realtime for d in result} == {
        "GPS": True,
        "Rozkład": False,
        "BezStatusu": False,
    }
    # vehicleCode (an int in the feed) is stringified; absent → None (the core
    # renders that as "—").
    assert {d.headsign: d.vehicle for d in result} == {
        "GPS": "3112",
        "Rozkład": None,
        "BezStatusu": None,
    }


def test_departures_from_several_poles_are_merged():
    # Both directions of Hynka: 1767 gives one 227 toward Chełm, 1768 two toward
    # Jelitkowo. The merged list carries all three for the core to sort.
    client = _StubClient(
        by_stop={
            HYNKA_TO_CHELM: _ok(_dep("hynka_1767")),
            HYNKA_TO_JELITKOWO: _ok(_dep("hynka_1768")),
        }
    )
    result = fetch_departures(
        [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO], "227", NOW, client
    )
    assert len(result) == 3
    assert {d.headsign for d in result} == {"Chełm Cienista", "Jelitkowo"}


def test_empty_pole_yields_no_rows_and_is_not_a_failure():
    client = _StubClient(by_stop={HYNKA_TO_JELITKOWO: _ok(_dep("empty"))})
    result = fetch_departures([HYNKA_TO_JELITKOWO], "227", NOW, client)
    assert result == []
    assert not isinstance(result, Failure)


def test_a_404_for_one_pole_still_returns_the_others_rows():
    # 1767 is 404 (no departures here); 1768 is live. The region renders 1768.
    client = _StubClient(
        by_stop={
            HYNKA_TO_CHELM: _StubResponse(404, {}),
            HYNKA_TO_JELITKOWO: _ok(_dep("hynka_1768")),
        }
    )
    result = fetch_departures(
        [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO], "227", NOW, client
    )
    assert isinstance(result, list)
    assert len(result) == 2


def test_one_unparseable_pole_still_returns_the_others_rows():
    client = _StubClient(
        by_stop={
            HYNKA_TO_CHELM: _ok(ValueError("not json")),
            HYNKA_TO_JELITKOWO: _ok(_dep("hynka_1768")),
        }
    )
    result = fetch_departures(
        [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO], "227", NOW, client
    )
    assert isinstance(result, list)
    assert len(result) == 2


def test_request_sends_stopid_and_a_timeout():
    client = _StubClient(by_stop={HYNKA_TO_JELITKOWO: _ok(_dep("hynka_1768"))})
    fetch_departures([HYNKA_TO_JELITKOWO], "227", NOW, client)
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["params"]["stopId"] == HYNKA_TO_JELITKOWO
    # A timeout is always set so one slow pole cannot stall the image (§2.6).
    assert call["timeout"] is not None


# --- fetch_departures: the failure paths (DESIGN §2.6) ----------------------


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("timed out"),
        httpx.ReadTimeout("slow"),
    ],
)
def test_every_pole_network_error_returns_failure(exc):
    client = _StubClient(by_stop={HYNKA_TO_CHELM: exc, HYNKA_TO_JELITKOWO: exc})
    result = fetch_departures(
        [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO], "227", NOW, client
    )
    assert isinstance(result, Failure)


def test_every_pole_non_200_returns_failure():
    client = _StubClient(default=_StubResponse(500, {}))
    result = fetch_departures(
        [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO], "227", NOW, client
    )
    assert isinstance(result, Failure)


def test_every_pole_unparseable_returns_failure():
    client = _StubClient(default=_ok(ValueError("not json")))
    result = fetch_departures(
        [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO], "227", NOW, client
    )
    assert isinstance(result, Failure)


def test_body_missing_departures_key_returns_failure():
    # A 200 whose body lacks `departures` is unparseable for every pole → Failure.
    client = _StubClient(default=_ok({"lastUpdate": "2026-09-05T19:00:00Z"}))
    result = fetch_departures(
        [HYNKA_TO_CHELM, HYNKA_TO_JELITKOWO], "227", NOW, client
    )
    assert isinstance(result, Failure)


def test_no_stop_ids_is_a_failure_not_an_empty_board():
    # With nothing to fetch, no pole was reached, so the region is down, not a
    # silently empty timetable.
    assert isinstance(fetch_departures([], "227", NOW, _StubClient()), Failure)


# --- fetch_stops ------------------------------------------------------------


def test_fetch_stops_returns_the_parsed_dataset():
    client = _StubClient(stops=_ok(_stops()))
    result = fetch_stops(client)
    assert isinstance(result, dict)
    assert result == _stops()


def test_fetch_stops_non_200_returns_failure():
    assert isinstance(fetch_stops(_StubClient(stops=_StubResponse(503, {}))), Failure)


def test_fetch_stops_network_error_returns_failure():
    client = _StubClient(stops=httpx.ConnectError("refused"))
    assert isinstance(fetch_stops(client), Failure)


def test_fetch_stops_non_object_body_returns_failure():
    client = _StubClient(stops=_ok([1, 2, 3]))
    assert isinstance(fetch_stops(client), Failure)


def test_fetch_stops_uses_a_timeout():
    client = _StubClient(stops=_ok(_stops()))
    fetch_stops(client)
    assert client.calls[0]["timeout"] is not None


# --- the dead endpoint (DESIGN §2.3) ----------------------------------------


def test_legacy_delays_endpoint_is_not_used():
    # The legacy /delays path is dead (404) and must not be requested (DESIGN §2.3).
    # The guard targets a `/delays` that closes a URL string literal, so the
    # module's own prose explaining *why* it is avoided (backtick-wrapped) does
    # not trip it while an actual `"…/delays"` request would.
    source = (Path(__file__).parents[2] / "trmnl" / "adapters" / "bus.py").read_text()
    assert '/delays"' not in source
    assert "/delays'" not in source
    assert "/departures" in source
