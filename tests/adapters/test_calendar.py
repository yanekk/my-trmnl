"""Calendar adapter tests (DESIGN §2.4, §2.6, §5.1, §5.2, §4). Event parsing is
checked against a recorded Google Calendar events.list response; every error path
is checked with a stubbed client and a fake credential. No test touches the
network and none needs a live Google account (task T07).

The fixture `gcal_events_sample.json` carries the real shapes the feed produces: a
timed event, an all-day event, two expanded instances of one recurring event
(singleEvents), an untitled event, an instance the owner declined, and a cancelled
instance (id + status only). The window is anchored to NOW below.
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

from trmnl.adapters import google_auth
from trmnl.adapters.calendar import fetch_events
from trmnl.core.model import WARSAW, Event, Failure

FIXTURES = Path(__file__).parent / "fixtures"

# NOW = 2026-09-05 12:00 Europe/Warsaw (10:00 UTC). The fixture's events sit this
# afternoon and tomorrow; the adapter returns them all (bucketing is the core's
# job), so `now` only drives the request window here.
NOW = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)

ACCESS_TOKEN = "ya29.SECRET-ACCESS-TOKEN"
CAL_ID = "primary"


def _fixture() -> dict:
    return json.loads((FIXTURES / "gcal_events_sample.json").read_text())


class _FakeCreds:
    """Stands in for a google.oauth2 Credentials. `valid` gates whether
    `ensure_fresh` tries to refresh; `refresh` records or raises so both the happy
    and the expired paths are exercised without google-auth touching the network."""

    def __init__(self, *, token=ACCESS_TOKEN, valid=True, refresh_raises=None):
        self.token = token
        self.valid = valid
        self._refresh_raises = refresh_raises
        self.refreshed = False

    def refresh(self, request):
        self.refreshed = True
        if self._refresh_raises is not None:
            raise self._refresh_raises
        self.valid = True


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
    """Stands in for an httpx.Client. Routes each GET to a per-calendar entry keyed
    by a substring of the URL, so one client can model several calendars behaving
    differently. An entry is a `_StubResponse` to return or an `Exception` to
    raise; records every call so a test can assert URL, params and headers."""

    def __init__(self, *, by_cal=None, default=None):
        self._by_cal = by_cal or {}
        self._default = default
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        entry = self._default
        for key, value in self._by_cal.items():
            if key in url:
                entry = value
                break
        if isinstance(entry, Exception):
            raise entry
        return entry


# --- the happy path: parsing (DESIGN §2.4) ----------------------------------


def test_recorded_response_parses_into_events():
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(_fixture())))
    assert isinstance(result, list)
    assert all(isinstance(e, Event) for e in result)
    # Dentysta, Urlop (all-day), Trening x2, untitled = 5. Declined and cancelled
    # are dropped.
    assert len(result) == 5
    titles = sorted(e.title for e in result)
    assert titles == ["(bez tytułu)", "Dentysta", "Trening", "Trening", "Urlop"]


def test_timed_and_all_day_are_distinguished():
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(_fixture())))
    by_title = {e.title: e for e in result if e.title != "Trening"}

    dentysta = by_title["Dentysta"]
    assert dentysta.all_day is False
    assert dentysta.start == datetime.fromisoformat("2026-09-05T14:30:00+02:00")
    assert dentysta.start.tzinfo is not None

    urlop = by_title["Urlop"]
    assert urlop.all_day is True
    # An all-day event is placed at Warsaw local midnight of its date so the core
    # can bucket it by day (core.model.Event contract).
    assert urlop.start == datetime(2026, 9, 6, tzinfo=WARSAW)
    assert urlop.start.tzinfo is not None


def test_recurring_event_instances_are_each_an_event():
    # singleEvents=true expands the weekly Trening into one Event per occurrence in
    # the window; both instances come back, at their own start times.
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(_fixture())))
    trening = sorted(
        (e for e in result if e.title == "Trening"), key=lambda e: e.start
    )
    assert len(trening) == 2
    assert trening[0].start == datetime.fromisoformat("2026-09-05T18:00:00+02:00")
    assert trening[1].start == datetime.fromisoformat("2026-09-06T18:00:00+02:00")


def test_cancelled_event_is_excluded():
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(_fixture())))
    # The cancelled instance carries only id + status; it must be skipped, not
    # raise on its missing `start`, and not add a row. The fixture holds two
    # confirmed Trening instances plus one cancelled — exactly two must survive.
    assert not isinstance(result, Failure)
    assert sum(1 for e in result if e.title == "Trening") == 2


def test_declined_event_is_excluded():
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(_fixture())))
    assert "Spotkanie zespołu" not in {e.title for e in result}


def test_untitled_event_gets_a_placeholder_title():
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(_fixture())))
    assert "(bez tytułu)" in {e.title for e in result}


def test_empty_window_is_an_empty_list_not_a_failure():
    # Reachable calendar, no events in the window → available-but-empty, which the
    # core draws as "Brak wydarzeń" (DESIGN §2.6). Not a Failure.
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok({"items": []})))
    assert result == []
    assert not isinstance(result, Failure)


def test_events_from_several_calendars_are_merged():
    client = _StubClient(
        by_cal={
            "calendars/primary/": _ok(_fixture()),
            "calendars/work%40example.com/": _ok({"items": _fixture()["items"][:1]}),
        }
    )
    result = fetch_events(["primary", "work@example.com"], NOW, _FakeCreds(), client)
    assert isinstance(result, list)
    # primary contributes 5, the work calendar its single Dentysta row = 6.
    assert len(result) == 6
    assert len(client.calls) == 2


# --- multi-day all-day events (owner decision 2026-09-06, T08) ---------------


def _all_day(start, end, summary="Urlop"):
    return {"items": [{"status": "confirmed", "summary": summary,
                       "start": {"date": start}, "end": {"date": end}}]}


def test_multi_day_all_day_event_shows_on_every_covered_day_in_the_window():
    # A vacation running 09-04..09-07 (end exclusive 09-08) that started before
    # today must show on today AND tomorrow, not vanish (owner decision). NOW is
    # 09-05 Warsaw, so the window is today 09-05 and tomorrow 09-06.
    result = fetch_events(
        [CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(_all_day("2026-09-04", "2026-09-08")))
    )
    assert isinstance(result, list)
    starts = sorted(e.start for e in result)
    assert starts == [
        datetime(2026, 9, 5, tzinfo=WARSAW),
        datetime(2026, 9, 6, tzinfo=WARSAW),
    ]
    assert all(e.all_day and e.title == "Urlop" for e in result)


def test_single_day_all_day_event_still_yields_one_row():
    # The common case (end = start + 1 day) is unchanged: exactly one row.
    result = fetch_events(
        [CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(_all_day("2026-09-06", "2026-09-07")))
    )
    assert [e.start for e in result] == [datetime(2026, 9, 6, tzinfo=WARSAW)]


def test_all_day_event_beyond_tomorrow_is_dropped():
    # Days outside today/tomorrow are never drawn, so they are not emitted: an
    # event wholly on the day after tomorrow yields no rows.
    result = fetch_events(
        [CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(_all_day("2026-09-07", "2026-09-08")))
    )
    assert result == []


def test_all_day_event_without_an_end_is_treated_as_one_day():
    # Defensive: a malformed item missing end.date falls back to a single day.
    payload = {"items": [{"status": "confirmed", "summary": "Święto",
                          "start": {"date": "2026-09-05"}}]}
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(payload)))
    assert [e.start for e in result] == [datetime(2026, 9, 5, tzinfo=WARSAW)]


# --- the request shape (DESIGN §2.4, §2.6) ----------------------------------


def test_request_asks_for_expanded_events_in_the_window_with_the_token():
    client = _StubClient(default=_ok(_fixture()))
    fetch_events([CAL_ID], NOW, _FakeCreds(token=ACCESS_TOKEN), client)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    params = call["params"]
    # singleEvents expands recurrences; orderBy is only valid alongside it.
    assert params["singleEvents"] == "true"
    assert params["orderBy"] == "startTime"
    assert params["showDeleted"] == "false"
    # The window runs from now through the end of tomorrow (Europe/Warsaw); timeMax
    # is the exclusive start of the day after tomorrow.
    assert params["timeMin"] == NOW.isoformat()
    assert params["timeMax"] == datetime(2026, 9, 7, tzinfo=WARSAW).isoformat()
    # The access token rides in the Authorization header, never the URL or params.
    assert call["headers"]["Authorization"] == f"Bearer {ACCESS_TOKEN}"
    # A timeout is always set so one slow source cannot stall the image (§2.6).
    assert call["timeout"] is not None


def test_calendar_id_is_url_encoded():
    client = _StubClient(default=_ok({"items": []}))
    fetch_events(["work@example.com"], NOW, _FakeCreds(), client)
    # An email-style id must be percent-encoded into the path, not left raw.
    assert client.calls[0]["url"].endswith("/calendars/work%40example.com/events")


# --- the failure paths (DESIGN §2.6) ----------------------------------------


def test_expired_credential_refresh_failure_returns_failure():
    # The refresh token is revoked/expired: ensure_fresh raises, and the adapter
    # returns Failure rather than letting it propagate.
    creds = _FakeCreds(valid=False, refresh_raises=RuntimeError("invalid_grant"))
    result = fetch_events([CAL_ID], NOW, creds, _StubClient(default=_ok(_fixture())))
    assert isinstance(result, Failure)
    assert creds.refreshed is True


def test_http_401_returns_failure():
    # A rejected access token comes back as 401 from Google, not as a raise.
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_StubResponse(401, {})))
    assert isinstance(result, Failure)


def test_non_200_returns_failure():
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_StubResponse(500, {})))
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
    result = fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=exc))
    assert isinstance(result, Failure)


def test_non_json_body_returns_failure():
    result = fetch_events(
        [CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(ValueError("not json")))
    )
    assert isinstance(result, Failure)


def test_missing_items_key_returns_failure():
    result = fetch_events(
        [CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok({"kind": "calendar#events"}))
    )
    assert isinstance(result, Failure)


def test_confirmed_event_missing_start_returns_failure():
    bad = _fixture()
    del bad["items"][0]["start"]  # Dentysta, confirmed, now malformed
    assert isinstance(
        fetch_events([CAL_ID], NOW, _FakeCreds(), _StubClient(default=_ok(bad))), Failure
    )


def test_one_failing_calendar_fails_the_whole_region():
    # Calendar is one source: a second calendar erroring takes the region down
    # rather than rendering a partial day.
    client = _StubClient(
        by_cal={
            "calendars/primary/": _ok(_fixture()),
            "calendars/broken/": _StubResponse(500, {}),
        }
    )
    result = fetch_events(["primary", "broken"], NOW, _FakeCreds(), client)
    assert isinstance(result, Failure)


# --- the seatbelts (DESIGN §5.2, §3.5) --------------------------------------


def test_requested_scope_is_read_only():
    # The read-only scope is the seatbelt: OAuth can only grant read access, so no
    # bug can alter or delete calendar data (DESIGN §5.2).
    assert google_auth.SCOPES == ["https://www.googleapis.com/auth/calendar.readonly"]
    assert all(s.endswith(".readonly") for s in google_auth.SCOPES)


def test_access_token_is_never_logged(caplog):
    # A failing fetch must never leak the token into the log or the Failure reason
    # (DESIGN §3.5).
    with caplog.at_level(logging.DEBUG):
        result = fetch_events(
            [CAL_ID], NOW, _FakeCreds(token=ACCESS_TOKEN), _StubClient(default=_StubResponse(401, {}))
        )
    assert isinstance(result, Failure)
    assert ACCESS_TOKEN not in caplog.text
    assert ACCESS_TOKEN not in result.reason


def test_stored_token_file_is_owner_only(tmp_path):
    # store_credentials writes the refresh token 0o600 from creation (DESIGN §3.5,
    # §5.2). A fake credential stands in for a real one; only to_json() is used.
    class _Cred:
        def to_json(self):
            return '{"refresh_token": "1//SECRET-REFRESH"}'

    token_path = tmp_path / "token.json"
    google_auth.store_credentials(_Cred(), token_path)
    assert token_path.read_text() == '{"refresh_token": "1//SECRET-REFRESH"}'
    assert oct(os.stat(token_path).st_mode & 0o777) == "0o600"


def test_store_credentials_overwrites_to_owner_only(tmp_path):
    # Overwriting a pre-existing, world-readable file must still end at 0o600.
    class _Cred:
        def to_json(self):
            return "{}"

    token_path = tmp_path / "token.json"
    token_path.write_text("stale")
    os.chmod(token_path, 0o644)
    google_auth.store_credentials(_Cred(), token_path)
    assert oct(os.stat(token_path).st_mode & 0o777) == "0o600"
