"""BYOS server tests (DESIGN §2.5, §2.6, §4). Endpoint behaviour is checked with
synthetic requests against `App.handle` (no socket), plus one integration test
that binds a real server and drives it over HTTP so the `BaseHTTPRequestHandler`
wiring is exercised too.
"""

import json
import threading
import urllib.request
from datetime import datetime

from trmnl.core.model import WARSAW, ServiceHours
from trmnl.server import app as srv

# Service window 06:00–22:00 local, so 08:42 is in-service (→ 60s) and 03:00 is
# overnight (→ 1800s). Matches core/refresh.py's policy (DESIGN §2.5).
SERVICE = ServiceHours(start_hour=6, end_hour=22)
IN_SERVICE = datetime(2026, 9, 5, 8, 42, tzinfo=WARSAW)
OVERNIGHT = datetime(2026, 9, 5, 3, 0, tzinfo=WARSAW)

PLACEHOLDER_BYTES = b"BM-placeholder-bytes"
IMAGE_BYTES = b"BM-real-image-bytes"


def _app(tmp_path, *, now=IN_SERVICE, with_image=True, with_placeholder=True):
    """An App wired to files under tmp_path. `with_image` False leaves image_path
    absent (cold start); `with_placeholder` False leaves the placeholder absent."""
    image_path = tmp_path / "screen.bmp"
    startup_path = tmp_path / "startup.bmp"
    if with_image:
        image_path.write_bytes(IMAGE_BYTES)
    if with_placeholder:
        startup_path.write_bytes(PLACEHOLDER_BYTES)
    return srv.App(
        image_path=str(image_path),
        startup_path=str(startup_path),
        service=SERVICE,
        now=lambda: now,
    )


def _display(app, headers=None):
    return app.handle("GET", "/api/display", headers or {"ID": "AA:BB"})


# --- header parsing: case- and separator-insensitive (DESIGN §2.6) ----------


def test_headers_resolve_across_case_and_separator():
    for spelling in ("ACCESS_TOKEN", "Access-Token", "access_token", "access-token"):
        h = srv.RequestHeaders({spelling: "secret-42", "Host": "x"})
        assert h.get("access-token") == "secret-42"
        assert h.get("ACCESS_TOKEN") == "secret-42"
        assert h.get("AccessToken") == "secret-42"


def test_headers_missing_returns_default():
    h = srv.RequestHeaders({"ID": "AA:BB"})
    assert h.get("battery-voltage") is None
    assert h.get("battery-voltage", "n/a") == "n/a"


# --- /api/display -----------------------------------------------------------


def test_display_returns_valid_json_with_url_and_int_rate(tmp_path):
    resp = _display(_app(tmp_path))
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["image_url"].endswith(".bmp")
    assert isinstance(body["refresh_rate"], int)
    assert body["reset_firmware"] is False
    assert body["update_firmware"] is False
    assert body["filename"].endswith(".bmp")


def test_display_refresh_rate_follows_the_injected_clock(tmp_path):
    assert json.loads(_display(_app(tmp_path, now=IN_SERVICE)).body)["refresh_rate"] == 60
    assert json.loads(_display(_app(tmp_path, now=OVERNIGHT)).body)["refresh_rate"] == 1800


def test_display_succeeds_with_only_id_header(tmp_path):
    # No optional telemetry headers (Model, RSSI, Battery-Voltage, ...): still 200.
    resp = _display(_app(tmp_path), headers={"ID": "AA:BB:CC"})
    assert resp.status == 200
    assert "refresh_rate" in json.loads(resp.body)


def test_display_image_url_uses_the_request_host(tmp_path):
    resp = _display(_app(tmp_path), headers={"ID": "AA:BB", "Host": "192.168.1.50:8080"})
    body = json.loads(resp.body)
    assert body["image_url"].startswith("http://192.168.1.50:8080/")


def test_display_filename_changes_with_image_content(tmp_path):
    # A content-hashed filename: the same picture yields the same name (device
    # skips a needless flash), a changed picture a new name (DESIGN §2.5).
    app = _app(tmp_path)
    first = json.loads(_display(app).body)["filename"]
    (tmp_path / "screen.bmp").write_bytes(b"BM-a-different-image")
    second = json.loads(_display(app).body)["filename"]
    assert first != second


# --- /api/setup (FW GETs it with a trailing slash — FINDINGS 2026-09-05) ----


def test_setup_returns_keys_and_image_url(tmp_path):
    resp = _app(tmp_path).handle("GET", "/api/setup", {"ID": "AA:BB", "Host": "h:1"})
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["status"] == 200
    assert body["api_key"] == srv.DEFAULT_API_KEY
    assert body["friendly_id"] == srv.DEFAULT_FRIENDLY_ID
    assert body["image_url"].startswith("http://h:1/")


def test_setup_matches_trailing_slash(tmp_path):
    # The exact `/api/setup` match in the spike 404'd the real device's
    # `/api/setup/` (FINDINGS 2026-09-05); both must resolve now.
    app = _app(tmp_path)
    assert app.handle("GET", "/api/setup/", {"ID": "AA:BB"}).status == 200
    assert app.handle("GET", "/api/setup", {"ID": "AA:BB"}).status == 200


# --- /api/log: 204, never 5xx, even on a bad body (DESIGN §2.6) --------------


def test_log_accepts_valid_json(tmp_path):
    body = json.dumps({"logs": [{"message": "hi", "wifi_status": "ok"}]}).encode()
    resp = _app(tmp_path).handle("POST", "/api/log", {"ID": "AA:BB"}, body)
    assert resp.status == 204
    assert resp.body == b""


def test_log_never_errors_on_malformed_or_empty_body(tmp_path):
    app = _app(tmp_path)
    for body in (b"", b"not json {{{", b"\xff\xfe\x00garbage"):
        resp = app.handle("POST", "/api/log", {"ID": "AA:BB"}, body)
        assert resp.status == 204


# --- image route ------------------------------------------------------------


def test_image_serves_the_current_image(tmp_path):
    # A failed rebuild leaves image_path untouched (the loop's job, T08), so the
    # server just serves whatever is at the path — the last good image.
    resp = _app(tmp_path).handle("GET", "/abc123.bmp", {"ID": "AA:BB"})
    assert resp.status == 200
    assert resp.content_type == "image/bmp"
    assert resp.body == IMAGE_BYTES


def test_image_cold_start_serves_the_placeholder_not_404(tmp_path):
    app = _app(tmp_path, with_image=False)  # no image ever built yet
    resp = app.handle("GET", "/screen.bmp", {"ID": "AA:BB"})
    assert resp.status == 200
    assert resp.content_type == "image/bmp"
    assert resp.body == PLACEHOLDER_BYTES


def test_image_missing_everything_is_503_not_crash(tmp_path):
    app = _app(tmp_path, with_image=False, with_placeholder=False)
    resp = app.handle("GET", "/screen.bmp", {"ID": "AA:BB"})
    assert resp.status == 503


def test_unknown_route_is_404(tmp_path):
    assert _app(tmp_path).handle("GET", "/nope", {"ID": "AA:BB"}).status == 404


# --- integration: the real socket path --------------------------------------


def test_over_http_end_to_end(tmp_path):
    """Bind a real server on a loopback port and drive it over HTTP, so the
    BaseHTTPRequestHandler wiring (body read, header pass-through, response write)
    is exercised, not just App.handle."""
    app = _app(tmp_path)
    server = srv.make_server(app, host="127.0.0.1", port=0)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://{host}:{port}"
        with urllib.request.urlopen(f"{base}/api/display", timeout=5) as r:
            assert r.status == 200
            display = json.loads(r.read())
        assert display["refresh_rate"] == 60  # IN_SERVICE clock

        # The device would now GET image_url; do the same and expect the image.
        with urllib.request.urlopen(display["image_url"], timeout=5) as r:
            assert r.status == 200
            assert r.headers.get("Content-Type") == "image/bmp"
            assert r.read() == IMAGE_BYTES

        # A telemetry POST returns 204.
        req = urllib.request.Request(
            f"{base}/api/log", data=b'{"logs":[]}', method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 204
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
