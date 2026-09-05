"""Throwaway BYOS server for the T00 spike — pure standard library, no deps.

It implements the minimum surface the TRMNL firmware needs to fetch and draw a
static image from a server we control (DESIGN.md 2.5, 5.2). Every request is
logged in full — path plus every header exactly as received — because the whole
point of T00 is to learn what the real device actually sends: the paths, the
header names and casing, and the firmware version. Read that log after the
device wakes; it is the evidence the task asks for.

Run:  python3 spike/server.py
It prints the LAN URL to enter in the device's wifi captive portal.

Throwaway: this whole spike/ directory is deleted once T00's findings are in.
"""

import json
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 2300
IMAGE = Path(__file__).with_name("spike.bmp")
REFRESH_RATE = 900  # seconds; fast refresh is a later concern (T02/T08), not the spike's


def lan_ip():
    """Best-effort LAN address. No packet is actually sent by connect() on UDP;
    it just makes the OS pick the interface that would route to the internet,
    which is the one the device shares on the home wifi."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


BASE = f"http://{lan_ip()}:{PORT}"


class Handler(BaseHTTPRequestHandler):
    # Quieten the default per-request line; we log headers ourselves below.
    def log_message(self, *args):
        pass

    def header(self, name):
        """Case- and separator-insensitive header lookup. Firmware versions
        differ on `ACCESS_TOKEN` vs `Access-Token` vs `access_token`, so match
        on the letters alone (DESIGN.md 2.6, FINDINGS: read headers loosely)."""
        want = name.lower().replace("-", "").replace("_", "")
        for k, v in self.headers.items():
            if k.lower().replace("-", "").replace("_", "") == want:
                return v
        return None

    def dump(self, body=None):
        print(f"\n>>> {self.command} {self.path}  from {self.client_address[0]}")
        for k, v in self.headers.items():
            print(f"      {k}: {v}")
        if body:
            print(f"      body: {body!r}")
        sys.stdout.flush()

    def send_json(self, obj, status=200):
        payload = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.dump()
        path = self.path.split("?", 1)[0]

        if path == "/api/setup":
            # Device's one-time registration. Any api_key/friendly_id is fine
            # for the spike; the device just needs a 200 with these fields.
            self.send_json(
                {
                    "api_key": "spike-key",
                    "friendly_id": "SPIKE",
                    "image_url": f"{BASE}/spike.bmp",
                    "status": 200,
                }
            )
        elif path == "/api/display":
            self.send_json(
                {
                    "filename": "spike",
                    "image_url": f"{BASE}/spike.bmp",
                    "refresh_rate": REFRESH_RATE,
                }
            )
        elif path == "/spike.bmp":
            data = IMAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/bmp")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_json({"error": "not found", "path": path}, status=404)

    def do_POST(self):
        length = int(self.header("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        self.dump(body)
        if self.path.split("?", 1)[0] == "/api/log":
            self.send_response(204)  # log accepted, no content
            self.end_headers()
        else:
            self.send_json({"error": "not found", "path": self.path}, status=404)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("TRMNL spike server (T00)")
    print(f"  serving {IMAGE.name} ({IMAGE.stat().st_size} bytes)")
    print(f"  enter this base URL in the device wifi captive portal:\n\n    {BASE}\n")
    print("  endpoints: /api/setup  /api/display  /spike.bmp  /api/log")
    print("  watching for device requests (Ctrl-C to stop)...")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
