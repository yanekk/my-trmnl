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
from trmnl.adapters.isotime import from_iso
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
            events.extend(_parse(resp.json(), *_window_days(now)))
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


def _window_days(now: datetime) -> tuple[date, date]:
    """The two Europe/Warsaw calendar days the screen shows: today and tomorrow.
    A multi-day all-day event is expanded across only these (see `_parse`)."""
    today = now.astimezone(WARSAW).date()
    return today, today + timedelta(days=1)


def _parse(payload: dict, first_day: date, last_day: date) -> list[Event]:
    """Turn one events.list response into `Event`s, dropping cancelled and
    owner-declined items.

    A timed event carries `start.dateTime` (tz-aware) and becomes one `Event` at
    that instant. An all-day event carries `start.date`/`end.date` (floating dates,
    `end` exclusive) and is expanded into one `Event` per calendar day it covers
    that falls within [`first_day`, `last_day`] — today and tomorrow — each placed
    at Europe/Warsaw local midnight so the core buckets it by day (the contract in
    `core.model.Event`). This is why a running multi-day event (a vacation started
    days ago) still shows on every day it covers rather than vanishing (owner
    decision 2026-09-06; the model carries no `end`, so the span is expanded here).
    A non-cancelled item missing the fields it needs raises and the caller returns
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
            # Google stamps timed events with an offset ("+02:00") or "Z"; from_iso
            # accepts both on Python 3.9 (stdlib fromisoformat only takes "Z" from
            # 3.11 — the deploy Pi is 3.9, DESIGN §5).
            events.append(
                Event(
                    start=from_iso(start["dateTime"]),
                    title=title,
                    all_day=False,
                )
            )
        else:
            # All-day: `start.date`/`end.date` are "YYYY-MM-DD" with `end`
            # exclusive; a single-day event has end = start + 1 day. Emit one row
            # per covered day inside the visible window, at Warsaw local midnight.
            events.extend(_all_day_span(item, start, title, first_day, last_day))
    return events


def _all_day_span(
    item: dict, start: dict, title: str, first_day: date, last_day: date
) -> list[Event]:
    """One all-day `Event` per calendar day the item covers within [`first_day`,
    `last_day`]. Google's `end.date` is exclusive; when it is absent the event is
    treated as a single day (`start.date` + 1). Days outside the window are
    dropped because the screen only shows today and tomorrow, so a long event does
    not expand into hundreds of rows the core would discard anyway."""
    d0 = date.fromisoformat(start["date"])
    end = item.get("end", {})
    d_end = date.fromisoformat(end["date"]) if "date" in end else d0 + timedelta(days=1)

    day = max(d0, first_day)
    # d_end is exclusive, so the last covered day is d_end - 1; clip to the window.
    last = min(d_end - timedelta(days=1), last_day)
    rows: list[Event] = []
    while day <= last:
        rows.append(
            Event(
                start=datetime(day.year, day.month, day.day, tzinfo=WARSAW),
                title=title,
                all_day=True,
            )
        )
        day += timedelta(days=1)
    return rows


def _declined(item: dict) -> bool:
    """True if the owner (the `self` attendee) declined this event, so it should
    not show. An event with no attendee list (a personal event) is never
    declined."""
    for attendee in item.get("attendees", []):
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return True
    return False
