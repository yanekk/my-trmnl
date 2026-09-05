"""Google OAuth for the calendar adapter — scope, load, refresh, one-time consent
(DESIGN §2.4, §3.5, §5.1, §5.2).

The owner's calendar is read over Google's API with an OAuth credential, not the
secret iCal link, because OAuth reflects new events within minutes (DESIGN §2.4).
This module owns the credential end to end: the read-only scope it is granted, the
refresh token stored on the box, refreshing the short-lived access token each
cycle, and — run once, by the owner — the interactive consent that mints the
refresh token in the first place.

Two seatbelts live here (DESIGN §5.2):

* **Read-only scope.** `SCOPES` requests only `calendar.readonly`, so no bug or
  compromise can alter or delete calendar data. Asserted by a test.
* **The token stays on the box, unlogged.** `store_credentials` writes the refresh
  token owner-only (0o600) from creation, and nothing here ever logs it (DESIGN
  §3.5).

The consent flow (`run_consent`) needs the owner's Google account and a Google
Cloud project and opens a browser, so it cannot be driven by the test command
(DESIGN §5.1) and is run by hand. Load, refresh and token storage are exercised
against fakes with no network.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.oauth2.credentials import Credentials

# Read-only is the seatbelt (DESIGN §5.2): the app can read the calendar and
# nothing more, so no bug or compromise can change or delete an event. Widening
# this list is a security decision, never a refactor.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def load_credentials(token_path: str | Path) -> Credentials:
    """Load the stored authorized-user credential (the refresh token plus its
    client id/secret and token URI) from `token_path`. Raises if the file is
    missing or is not valid authorized-user JSON; the caller (T08) turns that into
    a calendar region marked unavailable rather than a crash. The scopes are pinned
    read-only, so even a token minted with broader scope is used read-only here."""
    return Credentials.from_authorized_user_file(str(token_path), SCOPES)


def ensure_fresh(creds: Credentials) -> None:
    """Refresh the short-lived access token in place if it has expired.

    The access token lives about an hour; because the adapter talks to Google over
    httpx rather than google-auth's own transport, nothing refreshes it for us, so
    every fetch cycle calls this first. A refresh failure (revoked or expired
    refresh token, transport error) raises, and `fetch_events` turns that into a
    `Failure` (DESIGN §2.6). Does nothing when the current token is still valid."""
    if creds.valid:
        return
    # Imported lazily: the requests-based transport (and its `requests` dependency)
    # is needed only when a refresh actually happens, never at import time.
    from google.auth.transport.requests import Request

    creds.refresh(Request())


def store_credentials(creds: Credentials, token_path: str | Path) -> None:
    """Write `creds` (its refresh token) to `token_path` owner-only.

    The file is created with mode 0o600 from the start — not chmod'd afterwards —
    so the secret is never briefly world-readable (DESIGN §3.5, §5.2). The token is
    never logged. Used by `run_consent`, and re-usable if a token is ever rotated."""
    path = Path(token_path)
    data = creds.to_json()
    # O_CREAT with mode 0o600 fixes the permissions at creation. open() does not
    # change an existing file's mode, so chmod as well to cover overwriting one.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def run_consent(client_secret_path: str | Path, token_path: str | Path) -> None:
    """One-time interactive consent: open a Google sign-in, request read-only
    calendar access, and store the resulting refresh token at `token_path`.

    Run by the owner, once, on the box (DESIGN §5.1) — it opens a browser and
    cannot be driven by the test command. The read-only scope (`SCOPES`) is the
    seatbelt: the consent screen can grant read access and nothing else. On
    completion the refresh token is written 0o600 and never printed."""
    # Lazily imported: google-auth-oauthlib is needed only for this one-time,
    # owner-run flow, never during a normal fetch cycle.
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0)
    store_credentials(creds, token_path)
