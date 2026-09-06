"""Weather adapter tests (DESIGN §2.2, §2.6, §4). Parsing is checked against a
recorded Open-Meteo response; every error path is checked with a stubbed client.
No test touches the network — the `client` is always a stub.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from trmnl.adapters.weather import fetch_weather
from trmnl.core.model import Failure, WeatherData

FIXTURES = Path(__file__).parent / "fixtures"

# The adapter ignores `now` (the core trims the hourly strip); a fixed tz-aware
# value stands in for it everywhere.
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
LAT, LON = 54.35, 18.6875


def _fixture() -> dict:
    return json.loads((FIXTURES / "open_meteo_gdansk.json").read_text())


class _StubResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        # A non-JSON body: httpx raises inside .json(); we simulate that by
        # carrying an exception to raise instead of returning a dict.
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _StubClient:
    """Stands in for an httpx.Client. Records the call so a test can assert what
    was requested, and either returns a canned response or raises."""

    def __init__(self, *, status=200, payload=None, raises=None):
        self._status = status
        self._payload = payload
        self._raises = raises
        self.calls: list[dict] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if self._raises is not None:
            raise self._raises
        return _StubResponse(self._status, self._payload)


# --- the happy path ---------------------------------------------------------


def test_normal_response_parses_into_weatherdata():
    client = _StubClient(payload=_fixture())
    result = fetch_weather(LAT, LON, NOW, client)

    assert isinstance(result, WeatherData)
    assert result.temp_c == 17  # 17.4 rounded
    assert result.condition_code == 3
    assert result.feels_like_c == 16  # 16.1 rounded
    assert result.wind_kmh == 20  # 19.8 rounded
    assert len(result.hourly) == 48


def test_hourly_points_are_tz_aware_utc_and_typed():
    result = fetch_weather(LAT, LON, NOW, _StubClient(payload=_fixture()))
    assert isinstance(result, WeatherData)

    first = result.hourly[0]
    assert first.time == datetime(2026, 9, 5, 0, 0, tzinfo=timezone.utc)
    assert first.time.tzinfo is not None
    # Every value the core draws must be a plain int, not a float or a string.
    for pt in result.hourly:
        assert isinstance(pt.temp_c, int)
        assert isinstance(pt.rain_pct, int)
        assert isinstance(pt.code, int)
    assert isinstance(result.temp_c, int)
    assert isinstance(result.wind_kmh, int)
    assert isinstance(result.feels_like_c, int)


def test_is_day_parsed_as_bool_for_current_and_every_hour():
    # The fixture carries both day and night hours (hour 0 UTC is night, midday is
    # day), so this proves is_day is read per point as a bool, not one global value.
    result = fetch_weather(LAT, LON, NOW, _StubClient(payload=_fixture()))
    assert isinstance(result, WeatherData)
    assert result.is_day is True  # current time is midday
    assert result.hourly[0].is_day is False  # 00:00 UTC — night
    for pt in result.hourly:
        assert isinstance(pt.is_day, bool)  # never 0/1 ints leaking through
    # At least one day and one night hour, so the flag genuinely varies.
    flags = [pt.is_day for pt in result.hourly]
    assert True in flags and False in flags


def test_null_or_absent_is_day_falls_back_to_day_not_failure():
    # A null current flag, a null hour flag, and a wholly-absent hourly array all
    # fall back to day (True) rather than failing the fetch (DESIGN §2.6).
    bad = _fixture()
    bad["current"]["is_day"] = None
    bad["hourly"]["is_day"][0] = None
    result = fetch_weather(LAT, LON, NOW, _StubClient(payload=bad))
    assert isinstance(result, WeatherData)
    assert result.is_day is True
    assert result.hourly[0].is_day is True

    missing = _fixture()
    del missing["hourly"]["is_day"]
    del missing["current"]["is_day"]
    result2 = fetch_weather(LAT, LON, NOW, _StubClient(payload=missing))
    assert isinstance(result2, WeatherData)
    assert result2.is_day is True
    assert all(pt.is_day is True for pt in result2.hourly)


def test_null_precipitation_probability_reads_as_zero():
    # The fixture's last two hours carry a null chance (real far-horizon shape);
    # they must parse as 0%, not fail the whole fetch.
    result = fetch_weather(LAT, LON, NOW, _StubClient(payload=_fixture()))
    assert isinstance(result, WeatherData)
    assert result.hourly[-1].rain_pct == 0
    assert result.hourly[-2].rain_pct == 0


def test_request_asks_for_metric_units_and_the_given_point():
    client = _StubClient(payload=_fixture())
    fetch_weather(LAT, LON, NOW, client)

    assert len(client.calls) == 1
    params = client.calls[0]["params"]
    assert params["latitude"] == LAT
    assert params["longitude"] == LON
    assert params["temperature_unit"] == "celsius"
    assert params["wind_speed_unit"] == "kmh"
    # timezone=GMT is what makes the returned timestamps UTC; the parser then
    # stamps them tz-aware UTC unconditionally. If this param regressed, the API
    # would return Warsaw-local times, the parser would mislabel them as UTC, and
    # every hour on the screen would be silently off by the offset — with no other
    # test to catch it. Lock it here, alongside the 2-day span the tz-boundary
    # coverage depends on and the field lists the parser reads.
    assert params["timezone"] == "GMT"
    assert params["forecast_days"] == 2
    assert params["current"] == "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day"
    assert params["hourly"] == "temperature_2m,precipitation_probability,weather_code,is_day"
    # A timeout is always set so one slow source cannot stall the image (§2.6).
    assert client.calls[0]["timeout"] is not None


# --- the failure paths (DESIGN §2.6) ----------------------------------------


def test_non_200_returns_failure():
    result = fetch_weather(LAT, LON, NOW, _StubClient(status=500, payload=_fixture()))
    assert isinstance(result, Failure)


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("timed out"),
        httpx.ReadTimeout("slow"),
    ],
)
def test_network_error_returns_failure(exc):
    result = fetch_weather(LAT, LON, NOW, _StubClient(raises=exc))
    assert isinstance(result, Failure)


def test_non_json_body_returns_failure():
    result = fetch_weather(
        LAT, LON, NOW, _StubClient(payload=ValueError("not json"))
    )
    assert isinstance(result, Failure)


def test_missing_current_block_returns_failure():
    bad = _fixture()
    del bad["current"]
    assert isinstance(fetch_weather(LAT, LON, NOW, _StubClient(payload=bad)), Failure)


def test_missing_current_field_returns_failure():
    bad = _fixture()
    del bad["current"]["temperature_2m"]
    assert isinstance(fetch_weather(LAT, LON, NOW, _StubClient(payload=bad)), Failure)


def test_null_hourly_weather_code_falls_back_not_fails():
    # A null hourly weather_code is unusual but must not fail the whole fetch: it
    # degrades only that hour's icon (code -1 → the core's fallback), unlike a
    # null temperature which is malformed.
    bad = _fixture()
    bad["hourly"]["weather_code"][0] = None
    result = fetch_weather(LAT, LON, NOW, _StubClient(payload=bad))
    assert isinstance(result, WeatherData)
    assert result.hourly[0].code == -1


def test_null_temperature_is_malformed_not_a_half_filled_object():
    bad = _fixture()
    bad["current"]["temperature_2m"] = None
    assert isinstance(fetch_weather(LAT, LON, NOW, _StubClient(payload=bad)), Failure)


def test_missing_hourly_block_returns_failure():
    bad = _fixture()
    del bad["hourly"]
    assert isinstance(fetch_weather(LAT, LON, NOW, _StubClient(payload=bad)), Failure)


def test_misaligned_hourly_arrays_return_failure():
    # A short temperature array against a full time array is a malformed body,
    # caught by the parser's explicit length check rather than silently truncated.
    bad = _fixture()
    bad["hourly"]["temperature_2m"] = bad["hourly"]["temperature_2m"][:10]
    assert isinstance(fetch_weather(LAT, LON, NOW, _StubClient(payload=bad)), Failure)
