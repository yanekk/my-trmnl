# T07 — Google Calendar adapter (OAuth, read-only)

**Phase:** 2 · **Depends on:** T02 · **Weight:** medium-heavy (one-time OAuth needs the owner)

## Goal

Read the owner's Google Calendar and turn upcoming events into the core's `Event` list, so the
calendar region reflects new events within minutes. Access is Google sign-in (OAuth) with a
read-only scope; the one-time consent and the Google Cloud project are the owner's to set up,
and the resulting refresh token lives only on the home box. Event parsing is tested against
recorded API responses, so the suite needs no live Google account.

## Design sections this implements

DESIGN.md §2.4 (OAuth over iCal, read-only, token on the box, today+tomorrow), §2.6 (a fetch
failure marks the region unavailable), §3.5 (the refresh token is the one stored secret),
§5.1/§5.2 (the consent is hand-verified; read-only scope is a seatbelt).

## Files

- `trmnl/adapters/calendar.py` — the auth handling and `fetch_events(...)`.
- `trmnl/adapters/google_auth.py` — token load/refresh from the stored credential.
- `tests/adapters/fixtures/gcal_events_*.json`.
- `tests/adapters/test_calendar.py`.

## Interface

```python
def fetch_events(calendar_ids: list[str], now: datetime, creds, client)
        -> list[Event] | Failure
```

- Requests events from `now` through the end of tomorrow (Europe/Warsaw), read-only scope
  `https://www.googleapis.com/auth/calendar.readonly`.
- Timed and all-day events both map to `Event`; all-day is flagged so the core places it
  without a time. Times come back tz-aware; bucketing into today/tomorrow stays in the core.
- A refresh-token load/refresh failure, a non-200, or a network error returns `Failure`.
- The stored token file is written with restricted permissions and never logged.

## Tests

- [ ] A recorded events response parses into `Event`s, timed and all-day distinguished.
- [ ] A recurring event's expanded instances are handled (use `singleEvents`-style fixtures).
- [ ] A cancelled/declined event is excluded (per whatever fields the fixture carries).
- [ ] A 401/expired-credential path returns `Failure`, not a raise.
- [ ] A network error returns `Failure`.
- [ ] The token is never written to logs (assert the logger is not called with the secret).

## Done when

- [ ] `fetch_events` returns `Event`s from fixtures and `Failure` on every error path.
- [ ] The read-only scope is what the code requests (asserted in a test).
- [ ] Tests hit no network; the suite is green and quiet.

## Needs a person

The OAuth setup cannot be done by the test command. Raise this and wait for the owner.

```
1. In Google Cloud Console: create a project, enable the Calendar API, create an OAuth
   client (Desktop app), download the client secret JSON to the box.
2. Run the one-time consent helper:  <the auth command>
   It opens a Google sign-in; grant READ-ONLY calendar access. Seatbelt: the scope is
   read-only, so nothing can be changed or deleted; the token stays on the box.
```

Expect: a refresh token is stored locally and a test fetch lists your next events.
Tell me: did consent complete; which calendar id(s) to read (primary, or others by id).
Record the calendar id(s) in config and note completion (dated) in FINDINGS.
