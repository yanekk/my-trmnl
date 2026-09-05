"""The BYOS HTTP edge the TRMNL firmware talks to (DESIGN §2.5, §2.6, §3.4, §5.2).

The device provisions itself at `/api/setup`, asks what to show at `/api/display`,
fetches the image from a `.bmp` route, and posts telemetry to `/api/log`. That is
the whole protocol; there is nothing to click and nothing to push.

**Why the standard library, not a framework.** The API is four tiny endpoints, so
`http.server` carries it with no extra dependency to pin, update or break on the
home box (DESIGN §5 leaves the choice to this task; the dependency policy would
need the owner's sign-off to add a framework, and there is nothing here to justify
one). The request logic lives in `App.handle`, which takes a parsed request and
returns a `Response` — no socket — so it is tested exhaustively with synthetic
requests (DESIGN §4). `_Handler` is the thin `BaseHTTPRequestHandler` that reads a
real request off the wire and calls `App.handle`.

**The clock is read here, on purpose.** The server is the world-facing side of the
boundary (DESIGN §3.1), so it reads the system clock and passes `now` into the pure
refresh policy (`core/refresh.py`); the policy itself never touches a clock.

**The device is never handed a 404 or a blank** (DESIGN §2.6, §3.5). The refresh
loop (T08) writes the current image atomically to a fixed `image_path`. Until that
file exists — cold start, or just after a box reboot — the bundled "Uruchamianie…"
placeholder at `startup_path` is served instead. A failed rebuild is the loop's
concern, not the server's: the loop simply does not overwrite the good file, so the
server keeps serving whatever is at `image_path` (the last good image).
"""

from __future__ import annotations

import hashlib
import http.server
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Mapping

from trmnl.core.model import ServiceHours
from trmnl.core.refresh import refresh_seconds

_log = logging.getLogger(__name__)

# Not secrets: the server is LAN-only (DESIGN §5.2), so these just identify our
# server to the device during setup. Overridable, but a fixed value is fine for a
# single-owner household. friendly_id is the short human id TRMNL assigns a device.
DEFAULT_API_KEY = "trmnl-local"
DEFAULT_FRIENDLY_ID = "LOCAL1"


# --- request headers --------------------------------------------------------


def _norm_header(key: str) -> str:
    """Fold a header name to a case- and separator-insensitive key. Firmware
    versions vary the spelling — `Access-Token`, `ACCESS_TOKEN`, `access_token`
    all mean one thing (DESIGN §2.6; FINDINGS 2026-09-05) — so both hyphen and
    underscore are stripped and the rest lowered before any lookup."""
    return key.lower().replace("-", "").replace("_", "")


class RequestHeaders:
    """A case- and separator-insensitive view over whatever header mapping the
    request arrived with (a stdlib `HTTPMessage` on the wire, a plain dict in
    tests). Lookups go through `_norm_header`, so `get("access-token")` finds a
    header that was sent as `ACCESS_TOKEN`."""

    def __init__(self, raw: Mapping[str, str]):
        self._d: dict[str, str] = {}
        for k, v in raw.items():
            self._d[_norm_header(k)] = v

    def get(self, name: str, default: str | None = None) -> str | None:
        return self._d.get(_norm_header(name), default)


# --- response ---------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    """A response independent of the socket, so `App.handle` is unit-testable.
    An empty `content_type` means send no Content-Type header (used for 204)."""

    status: int
    body: bytes
    content_type: str = "application/json"
    headers: dict = field(default_factory=dict)


def _json_response(status: int, payload: dict) -> Response:
    return Response(status, json.dumps(payload).encode("utf-8"), "application/json")


def _read_bytes(path: str) -> bytes | None:
    """Read a file whole, or None if it is not there. `open` is fine here: the
    boundary guard scans only `trmnl/core/`, and the server is world-facing."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


# --- the application --------------------------------------------------------


class App:
    """The BYOS request logic. `now` is the injected clock (a zero-arg callable
    returning a tz-aware datetime); `service` is the service-hours window the
    refresh policy keys off. `image_path` is the fixed path the refresh loop (T08)
    writes; `startup_path` is the bundled cold-start placeholder served until that
    file first exists (DESIGN §2.6, §3.5)."""

    def __init__(
        self,
        *,
        image_path: str,
        startup_path: str,
        service: ServiceHours,
        now: Callable[[], datetime],
        api_key: str = DEFAULT_API_KEY,
        friendly_id: str = DEFAULT_FRIENDLY_ID,
    ):
        self.image_path = image_path
        self.startup_path = startup_path
        self.service = service
        self.now = now
        self.api_key = api_key
        self.friendly_id = friendly_id

    # --- routing ------------------------------------------------------------

    def handle(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> Response:
        h = RequestHeaders(headers)
        # FW 1.5.12 GETs `/api/setup/` with a trailing slash and the spike's exact
        # `/api/setup` match 404'd it (FINDINGS 2026-09-05). Normalising the
        # trailing slash off every route makes that a non-issue for good.
        route = path.rstrip("/") or "/"
        if method == "GET" and route == "/api/setup":
            return self._setup(h)
        if method == "GET" and route == "/api/display":
            return self._display(h)
        if method == "POST" and route == "/api/log":
            return self._log(h, body)
        # The image route: the device fetches whatever URL we handed it in
        # `image_url`, and we choose a content-hashed `.bmp` name (see
        # `_image_filename`), so any `*.bmp` GET maps to the one served image.
        if method == "GET" and path.endswith(".bmp"):
            return self._image()
        _log.info("unhandled request %s %s", method, path)
        return _json_response(404, {"error": "not found"})

    # --- image selection ----------------------------------------------------

    def _served_image_path(self) -> str:
        """The current image if the loop has written one, else the cold-start
        placeholder — the device is never handed a 404 or a blank (DESIGN §2.6)."""
        if os.path.exists(self.image_path):
            return self.image_path
        return self.startup_path

    def _image_filename(self) -> str:
        """A filename keyed to the served image's content. The firmware caches the
        last filename it drew and, when the name is unchanged, can skip the draw —
        so hashing the content means an unchanged screen costs no full-screen flash
        while a changed one redraws (DESIGN §2.5). The name is ours to choose: the
        device fetches whatever `image_url` we return, and the `.bmp` route serves
        the one current image regardless of the name in the path. Falls back to a
        fixed name only if there is no image at all to hash."""
        data = _read_bytes(self._served_image_path())
        if not data:
            return "screen.bmp"
        return f"{hashlib.sha256(data).hexdigest()[:16]}.bmp"

    @staticmethod
    def _base_url(headers: RequestHeaders) -> str:
        """The scheme+host the device reached us on, taken from its `Host` header
        so `image_url` resolves on the LAN rather than a hardcoded address
        (DESIGN §5.2). Scheme is http: the server is plain LAN, not TLS."""
        host = headers.get("Host") or "localhost"
        return f"http://{host}"

    # --- endpoints ----------------------------------------------------------

    def _setup(self, headers: RequestHeaders) -> Response:
        device_id = headers.get("ID", "")
        _log.info("setup: id=%s fw=%s", device_id, headers.get("FW-Version"))
        return _json_response(
            200,
            {
                "status": 200,
                "api_key": self.api_key,
                "friendly_id": self.friendly_id,
                "image_url": f"{self._base_url(headers)}/{self._image_filename()}",
            },
        )

    def _display(self, headers: RequestHeaders) -> Response:
        # World-facing side reads the clock and hands it to the pure policy.
        rate = refresh_seconds(self.now(), self.service)
        filename = self._image_filename()
        _log.info(
            "display: id=%s battery=%s rssi=%s -> %s @ %ss",
            headers.get("ID"),
            headers.get("Battery-Voltage"),
            headers.get("RSSI"),
            filename,
            rate,
        )
        return _json_response(
            200,
            {
                "filename": filename,
                "image_url": f"{self._base_url(headers)}/{filename}",
                "refresh_rate": rate,
                "reset_firmware": False,
                "update_firmware": False,
            },
        )

    def _log(self, headers: RequestHeaders, body: bytes) -> Response:
        # Telemetry and error reports the device POSTs (FINDINGS 2026-09-05). We
        # log them and never answer 5xx — a device whose log POST fails just retries
        # and a 500 storm helps no one; the log is diagnostics, not a contract.
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
            _log.info("device log: id=%s %s", headers.get("ID"), payload)
        except (ValueError, UnicodeDecodeError) as exc:
            _log.warning(
                "device log: id=%s unparseable body (%s): %r",
                headers.get("ID"),
                exc,
                body[:200],
            )
        return Response(204, b"", content_type="")

    def _image(self) -> Response:
        data = _read_bytes(self._served_image_path())
        if data is None:
            # Neither a built image nor the placeholder is on disk. This is a
            # deployment fault (the placeholder is committed and must be present),
            # so it is logged loudly; 503 lets the device retry on its next wake.
            _log.error(
                "no image to serve: neither %s nor %s exists",
                self.image_path,
                self.startup_path,
            )
            return _json_response(503, {"error": "no image available"})
        return Response(200, data, content_type="image/bmp")


# --- socket wiring ----------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    """Thin adapter from a real request to `App.handle`. `app` is set on a
    per-server subclass by `make_server`."""

    app: App = None  # set by make_server

    def _dispatch(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        resp = self.app.handle(method, self.path, self.headers, body)
        self.send_response(resp.status)
        if resp.content_type:
            self.send_header("Content-Type", resp.content_type)
        self.send_header("Content-Length", str(len(resp.body)))
        for k, v in resp.headers.items():
            self.send_header(k, v)
        self.end_headers()
        if resp.body:
            self.wfile.write(resp.body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def log_message(self, fmt: str, *args) -> None:
        # Route the stdlib access log into our logger instead of stderr.
        _log.debug("http %s - " + fmt, self.address_string(), *args)


def make_server(
    app: App,
    host: str = "0.0.0.0",
    port: int = 8080,
) -> http.server.ThreadingHTTPServer:
    """Bind the BYOS server. Threading so one slow device fetch cannot block
    another request. Host defaults to every interface on the box; the LAN-only
    seatbelt (DESIGN §5.2) is that the box is not exposed to the public internet
    (no port-forward), which is a deploy property confirmed at T09, not something
    the code can assert here."""
    bound = type("_BoundHandler", (_Handler,), {"app": app})
    return http.server.ThreadingHTTPServer((host, port), bound)
