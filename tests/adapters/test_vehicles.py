"""Vehicle-database adapter tests (DESIGN §2.3, §2.6, §4, task T10). Parsing is
checked against a trimmed real `baza-pojazdow.json`; every error path is checked
with a stubbed client. No test touches the network — `client` is always a stub.
"""

import json
from pathlib import Path

import httpx
import pytest

from trmnl.adapters.vehicles import fetch_vehicles
from trmnl.core.model import Failure, VehicleInfo

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture() -> dict:
    return json.loads((FIXTURES / "ztm_vehicles_sample.json").read_text())


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


class _StubClient:
    """Stands in for an httpx.Client. Records the call so a test can assert what was
    requested, and either returns a canned response or raises."""

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


def test_normal_response_parses_into_a_code_to_vehicleinfo_map():
    result = fetch_vehicles(_StubClient(payload=_fixture()))
    assert isinstance(result, dict)
    # A known bus code maps to the right make/model.
    assert result["2520"] == VehicleInfo(brand="Solaris", model="Urbino 12")
    assert result["2762"] == VehicleInfo(brand="Mercedes-Benz", model="Conecto")


def test_keys_are_strings_so_they_join_to_the_stringified_feed_code():
    result = fetch_vehicles(_StubClient(payload=_fixture()))
    assert all(isinstance(k, str) for k in result)
    # The departures feed's vehicleCode is an int stringified in T06; the lookup
    # key must be the same string, so "3112" (not 3112) is present.
    assert "3112" in result


def test_a_record_missing_brand_or_model_is_skipped_not_fatal():
    # The fixture carries a bus with empty brand/model (code 9998): it must be
    # dropped, leaving the well-formed records intact rather than failing the parse.
    result = fetch_vehicles(_StubClient(payload=_fixture()))
    assert isinstance(result, dict)
    assert "9998" not in result
    assert "2520" in result  # the good records survive


def test_a_timeout_is_always_set():
    client = _StubClient(payload=_fixture())
    fetch_vehicles(client)
    # One slow source must not stall the whole image (DESIGN §2.6).
    assert client.calls[0]["timeout"] is not None


# --- the failure paths (DESIGN §2.6) — Failure, never a raise ---------------


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("timed out"),
        httpx.ReadTimeout("slow"),
    ],
)
def test_network_error_returns_failure(exc):
    assert isinstance(fetch_vehicles(_StubClient(raises=exc)), Failure)


def test_non_200_returns_failure():
    assert isinstance(fetch_vehicles(_StubClient(status=503, payload=_fixture())), Failure)


def test_non_json_body_returns_failure():
    assert isinstance(
        fetch_vehicles(_StubClient(payload=ValueError("not json"))), Failure
    )


def test_body_missing_results_returns_failure():
    bad = _fixture()
    del bad["results"]
    assert isinstance(fetch_vehicles(_StubClient(payload=bad)), Failure)


def test_results_not_a_list_returns_failure():
    bad = _fixture()
    bad["results"] = {"nope": "not a list"}
    assert isinstance(fetch_vehicles(_StubClient(payload=bad)), Failure)


def test_body_not_an_object_returns_failure():
    assert isinstance(fetch_vehicles(_StubClient(payload=["a", "list"])), Failure)
