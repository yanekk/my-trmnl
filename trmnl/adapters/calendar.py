"""Calendar adapter — Google Calendar → the core's `Event` list (DESIGN §2.4, §2.6, §3.1).

The owner's calendar is read over Google's REST API with a read-only OAuth
credential (DESIGN §2.4); `google_auth` owns the credential and this module owns
the fetch. It reads no clock and makes no display decisions — event start times
come back tz-aware and the core (`assemble._calendar_buckets`) sorts them into
today/tomorrow in Europe/Warsaw and phrases the labels.

`singleEvents=true` asks Google to expand recurring events into individual
instances, so a weekly event arrives as one `Event` per occurrence in the window
rather than a rule we would have to expand ourselves. Cancelled events and
instances the owner declined are dropped: the screen shows what the owner is
actually doing, not what they said no to.

Failure, never an exception (DESIGN §2.6): a credential refresh failure, a non-200
status (401 rejected token included), a network error, or an unparseable body each
return a `Failure` marker, so the refresh loop never catches and `assemble` marks
the region "niedostępne". The calendar is one source: if any configured calendar
errors, the whole region is `Failure` — unlike buses, whose poles are isolated by
DESIGN §2.6, the plan gives no per-calendar isolation and typical use is one
calendar. An empty window (reachable, no events) is a valid empty list, which the
core draws as "Brak wydarzeń".
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from urllib.parse import quote

import httpx

from trmnl.adapters import google_auth
from trmnl.core.model import WARSAW, Event, Failure

log = logging.getLogger(__name__)

# Google Calendar REST v3. Called directly over httpx (like the other adapters)
# rather than through the discovery client, so a fetch is one plain GET per
# calendar and tests stub the client.
_API = "https://www.googleapis.com/calendar/v3"

# One slow source must not delay the whole image (DESIGN §2.6), so every fetch is
# bounded. Set on the call so the guarantee holds whatever client is injected.
_TIMEOUT_S = 10.0

# A two-day window never holds enough events to page, so we ask for plenty and
# read the first page only. (Google caps a page at 2500; its default is 250.)
_MAX_RESULTS = 250

# Google shows an event with no summary as "(No title)"; the Polish UI shows the
# Polish equivalent. Used so an untitled event still draws a row rather than a
# blank. Owner may prefer other wording — noted for confirmation.
_UNTITLED = "(bez tytułu)"


def fetch_events(
    calendar_ids: list[str], now: datetime, creds, client: httpx.Client
) -> list[Event] | Failure:
    """Fetch the owner's events from `now` through the end of tomorrow (Europe/
    Warsaw) across `calendar_ids`, merged for the core.

    Returns a list of `Event` (possibly empty) on success, or `Failure` on a
    credential refresh failure, any non-200, a network error, or an unparseable
    body — never raising (DESIGN §2.6). `creds` is a Google OAuth credential
    (`google_auth`); its access token is refreshed here if stale. `client` is an
    injected `httpx.Client` so tests stub it and hit no network. Bucketing into
    today/tomorrow and every time label stay in the core (DESIGN §3.1)."""
    try:
        google_auth.ensure_fresh(creds)
    except Exception as exc:  # revoked/expired refresh token, transport error
        # Never log the token or the exception payload verbatim — only that the
        # refresh failed, and only the exception type (DESIGN §3.5).
        log.warning("calendar: credential refresh failed")
        return Failure(f"calendar: credential refresh failed: {type(exc).__name__}")

    time_min, time_max = _window(now)
    headers = {"Authorization": f"Bearer {creds.token}"}
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",  # expand recurring events into instances
        "orderBy": "startTime",  # valid only with singleEvents; core re-sorts anyway
        "showDeleted": "false",
        "maxResults": _MAX_RESULTS,
    }

    events: list[Event] = []
    for cal_id in calendar_ids:
        url = f"{_API}/calendars/{quote(cal_id, safe='')}/events"
        try:
            resp = client.get(url, params=params, headers=headers, timeout=_TIMEOUT_S)
        except httpx.HTTPError as exc:
            log.warning("calendar: request failed: %s", type(exc).__name__)
            return Failure(f"calendar: request failed: {exc}")

        if resp.status_code != 200:
            # Covers 401 (token rejected) and 403/404 (bad calendar id / no access).
            log.warning("calendar: HTTP %s", resp.status_code)
            return Failure(f"calendar: HTTP {resp.status_code}")

        try:
            events.extend(_parse(resp.json()))
        except (ValueError, KeyError, TypeError) as exc:
            # ValueError also covers json() on a non-JSON body and fromisoformat on
            # a malformed timestamp; a half-parsed response is never returned.
            log.warning("calendar: unparseable body: %s", type(exc).__name__)
            return Failure(f"calendar: unparseable body: {exc}")

    return events


def _window(now: datetime) -> tuple[str, str]:
    """The [timeMin, timeMax) RFC3339 bounds: from `now` to the start of the day
    after tomorrow in Europe/Warsaw — i.e. through the end of tomorrow. Google's
    timeMax is exclusive. An all-day event covering today is still returned because
    its span overlaps `now`, so a mid-day `now` does not hide today's all-day
    events (the core keeps them regardless)."""
    now_local = now.astimezone(WARSAW)
    end_date = now_local.date() + timedelta(days=2)
    time_max = datetime(end_date.year, end_date.month, end_date.day, tzinfo=WARSAW)
    return now.isoformat(), time_max.isoformat()


def _parse(payload: dict) -> list[Event]:
    """Turn one events.list response into `Event`s, dropping cancelled and
    owner-declined items.

    A timed event carries `start.dateTime` (tz-aware); an all-day event carries
    `start.date` (a floating date), which is placed at Europe/Warsaw local midnight
    so the core can bucket it by day (the contract in `core.model.Event`). A
    non-cancelled item missing the fields it needs raises and the caller returns
    `Failure`; a cancelled item (which may be only id+status) is skipped before its
    fields are touched."""
    items = payload["items"]

    events: list[Event] = []
    for item in items:
        if item.get("status") == "cancelled":
            continue  # a deleted event or a cancelled recurring instance
        if _declined(item):
            continue  # the owner said no; not something they are doing
        start = item["start"]
        title = item.get("summary", _UNTITLED)
        if "dateTime" in start:
            events.append(
                Event(
                    start=datetime.fromisoformat(start["dateTime"]),
                    title=title,
                    all_day=False,
                )
            )
        else:
            # All-day: `date` is "YYYY-MM-DD", no time. Place it at Warsaw local
            # midnight so the core buckets it into the right calendar day.
            d = date.fromisoformat(start["date"])
            events.append(
                Event(
                    start=datetime(d.year, d.month, d.day, tzinfo=WARSAW),
                    title=title,
                    all_day=True,
                )
            )
    return events


def _declined(item: dict) -> bool:
    """True if the owner (the `self` attendee) declined this event, so it should
    not show. An event with no attendee list (a personal event) is never
    declined."""
    for attendee in item.get("attendees", []):
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return True
    return False
