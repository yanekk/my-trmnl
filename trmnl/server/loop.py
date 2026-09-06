"""The composition root and refresh loop (DESIGN §2.5, §2.6, §3.4, §3.5, task T08).

This is the one place the pieces are wired into a running whole: fetch the three
sources (each bounded and isolated), hand what came back plus the current time to
the pure core, render the image, and publish it atomically for the BYOS server to
serve — repeating on a cadence. Everything world-facing meets here; the core stays
pure and is reached only through `assemble`.

**Degradation lives here (DESIGN §2.6).** Each source is fetched independently, so
one that fails or times out becomes a `Failure` in `Sources` and only its region
degrades — one bad source never fails the build. If rendering or writing the image
itself fails, the last-good file is left untouched (the server keeps serving it)
and the loop carries on. Before the first build succeeds, the server falls back to
the committed cold-start placeholder, so the device is never handed a 404.

**The clock is read here, on purpose** (DESIGN §3.1): the composition root is the
world-facing side, so it reads the system clock and passes `now` into the pure
core and refresh policy. `build_once` and `run_loop` take `now`/`clock` as
arguments, so the whole loop is testable with a fixed clock and no real sleep.

**Cadence.** The loop rebuilds as often as the fastest device refresh — 120s (2 min)
during service hours, slower overnight — reusing the same refresh policy the server
reports to the device (`core/refresh.py`), so the served image is never more than
one interval stale (DESIGN §2.5).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Callable, Iterable

import httpx

from trmnl.adapters import (
    bus,
    calendar,
    config as config_mod,
    google_auth,
    vehicles,
    weather,
)
from trmnl.adapters.config import Config
from trmnl.core.assemble import assemble
from trmnl.core.model import Failure, ServiceHours, Sources, VehicleInfo
from trmnl.core.refresh import refresh_seconds
from trmnl.render import screen
from trmnl.render.screen import RegionLabels
from trmnl.server.app import App, make_server

log = logging.getLogger(__name__)


# --- dependencies the composition root holds --------------------------------


class Deps:
    """The live, world-facing dependencies a build cycle needs: one shared HTTP
    client, the Google OAuth credential (or None if it could not be loaded), and
    the resolved bus pole ids, which are looked up once from the daily stops
    dataset and cached (DESIGN §3.5) rather than re-downloaded every cycle.

    A failed stops download leaves the ids unresolved so the next cycle retries;
    a successful lookup is cached even when it resolves to nothing (a misconfigured
    stop name is not a transient fault). Tests pass `stop_ids` directly to skip the
    download.

    `vehicles` is the disk-cached ZTM vehicle database (T10), held across cycles so
    it is loaded once and refetched only on a cache miss; None disables the make/model
    lookup entirely (rows show numbers), which is what the loop tests use."""

    def __init__(
        self,
        http: httpx.Client,
        creds=None,
        stop_ids: list[int] | None = None,
        vehicles: "VehicleCache | None" = None,
    ):
        self.http = http
        self.creds = creds
        self._stop_ids: list[int] | None = list(stop_ids) if stop_ids is not None else None
        self.vehicles = vehicles

    def stop_ids(self, cfg: Config) -> list[int]:
        if self._stop_ids is not None:
            return self._stop_ids
        data = bus.fetch_stops(self.http)
        if isinstance(data, Failure):
            # Transient: do not cache, so the next cycle tries again once the box
            # has network / ZTM is back. Buses show "niedostępne" until then.
            log.warning("bus: stops dataset unavailable (%s); retrying next cycle", data.reason)
            return []
        mapping = bus.resolve_stop_ids(cfg.stops, data)
        ids = sorted({sid for pole_ids in mapping.values() for sid in pole_ids})
        self._stop_ids = ids  # cache even if empty: a bad stop name is not transient
        if not ids:
            log.warning("bus: no poles resolved for stops %s (zone Gdańsk)", cfg.stops)
        return ids


class VehicleCache:
    """The on-disk ZTM vehicle database — a `{fleet number → VehicleInfo}` lookup
    reloaded on startup and refetched only when a cycle's schedule holds a number
    not already cached (DESIGN §2.3, §3.1, T10).

    The parse and fetch are the adapter's (`adapters.vehicles`); the disk cache and
    the miss-trigger are the composition root's, keeping the core and adapter pure
    of storage (DESIGN §3.1). One download holds every vehicle, so after the first
    fetch only a genuinely new bus triggers another. Decisions owner took 2026-09-06:

    * A number still absent after a download stays a cache miss, so the next cycle
      re-downloads — an unknown vehicle hits ZTM every cycle until it appears, no
      suppression. That is `ensure` refetching whenever `wanted` is not a subset.
    * A failed fetch leaves the cached map intact and returns it, so a
      vehicle-database problem never fails the bus region (DESIGN §2.6) — the rows
      fall back to numbers.

    A corrupt or missing cache file loads as empty rather than raising, so a bad
    file self-heals on the first fetch instead of taking the dashboard down."""

    def __init__(self, path: str):
        self._path = path
        self._by_code: dict[str, VehicleInfo] = self._load()

    def _load(self) -> dict[str, VehicleInfo]:
        """The cache file as a lookup, or empty if it is missing/corrupt. The file
        is our own `{code: {brand, model}}` JSON (see `_persist`), not the ZTM
        wire shape, so it round-trips exactly what we stored."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return {}
        out: dict[str, VehicleInfo] = {}
        if isinstance(raw, dict):
            for code, info in raw.items():
                if isinstance(info, dict) and info.get("brand") and info.get("model"):
                    out[str(code)] = VehicleInfo(brand=info["brand"], model=info["model"])
        return out

    def _persist(self) -> None:
        """Rewrite the cache file atomically (temp sibling + os.replace, like the
        image), so a crash mid-write never leaves a half-written cache. A write
        failure is logged and swallowed: an un-persisted cache still works in
        memory this run, it just reloads empty next start."""
        data = {code: {"brand": v.brand, "model": v.model} for code, v in self._by_code.items()}
        tmp = f"{self._path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError as exc:
            log.warning("vehicles: could not persist cache to %s (%s)", self._path, exc)

    def ensure(self, codes: Iterable[str], client: httpx.Client) -> dict[str, VehicleInfo]:
        """Return the make/model lookup, downloading the whole database first if any
        of `codes` (this cycle's tracked fleet numbers) is not already cached. A
        successful download replaces the cache and rewrites the file; a failure keeps
        and returns the existing cache (DESIGN §2.6). Falsy codes (a schedule-only
        run's absent number) are ignored."""
        wanted = {c for c in codes if c}
        if not wanted or wanted.issubset(self._by_code):
            return self._by_code
        fetched = vehicles.fetch_vehicles(client)
        if isinstance(fetched, Failure):
            log.warning(
                "vehicles: database unavailable (%s); rows fall back to numbers",
                fetched.reason,
            )
            return self._by_code
        self._by_code = fetched
        self._persist()
        return self._by_code


@dataclass(frozen=True)
class BuildResult:
    """The outcome of one `build_once`. `sources` carries what each adapter
    returned (data or `Failure`) so a caller/test can see which regions degraded;
    `published` is whether a fresh image was written (False means the last-good
    image was kept after a render/write failure)."""

    sources: Sources
    published: bool
    reason: str = ""


# --- one build cycle --------------------------------------------------------


def build_once(cfg: Config, now: datetime, deps: Deps) -> BuildResult:
    """Fetch → assemble → render → publish, once. Never raises: a source failure
    degrades its region (DESIGN §2.6), and a render/write failure keeps the
    last-good image rather than crashing the loop."""
    sources = _fetch_sources(cfg, now, deps)
    vehicle_lookup = _ensure_vehicles(sources.bus, deps)
    dashboard = assemble(
        sources, now, near_minutes=cfg.near_minutes, vehicles=vehicle_lookup
    )
    labels = region_labels(cfg)
    try:
        image = screen.render(dashboard, labels)
        # save_bmp writes a temp sibling and os.replace's it over image_path, so a
        # crash before the rename leaves the last-good image whole (DESIGN §2.6).
        screen.save_bmp(image, cfg.image_path)
    except Exception as exc:  # noqa: BLE001 — last-good guarantee: never crash the loop
        log.error(
            "build: render/publish failed (%s); keeping last-good image at %s",
            exc,
            cfg.image_path,
        )
        return BuildResult(sources=sources, published=False, reason=f"render/publish: {exc}")
    return BuildResult(sources=sources, published=True)


def _ensure_vehicles(bus_result, deps: Deps) -> dict[str, VehicleInfo]:
    """This cycle's make/model lookup (DESIGN §2.3, T10). Collects the tracked fleet
    numbers from the departures and asks the disk cache to ensure them — a download
    only on a miss, the existing cache otherwise or on a failed fetch. When the bus
    fetch itself failed there are no rows to annotate, so an empty list is ensured
    (no fetch) and an empty lookup is fine. `deps.vehicles` None disables the feature
    (rows show numbers), which the loop tests rely on."""
    if deps.vehicles is None:
        return {}
    codes = (
        []
        if isinstance(bus_result, Failure)
        else [d.vehicle for d in bus_result if d.vehicle]
    )
    return deps.vehicles.ensure(codes, deps.http)


def _fetch_sources(cfg: Config, now: datetime, deps: Deps) -> Sources:
    """Fetch the three sources concurrently (DESIGN §3.4), each already bounded by
    its own timeout and each wrapped so any unexpected error becomes a `Failure`
    rather than failing the whole build."""
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="fetch") as ex:
        fw = ex.submit(_safe, "weather", _fetch_weather, cfg, now, deps)
        fb = ex.submit(_safe, "bus", _fetch_bus, cfg, now, deps)
        fc = ex.submit(_safe, "calendar", _fetch_calendar, cfg, now, deps)
        return Sources(weather=fw.result(), bus=fb.result(), calendar=fc.result())


def _safe(name: str, fn: Callable, *args):
    """Run one source fetch, turning any unexpected exception into a `Failure` so a
    single source can never fail the build (DESIGN §2.6). The adapters already
    return `Failure` on their known error paths; this is the backstop for anything
    they did not anticipate."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 — one bad source must not fail the build
        log.warning("%s: unexpected error, region degraded: %s", name, exc)
        return Failure(f"{name}: unexpected: {exc}")


def _fetch_weather(cfg: Config, now: datetime, deps: Deps):
    return weather.fetch_weather(cfg.lat, cfg.lon, now, deps.http)


def _fetch_bus(cfg: Config, now: datetime, deps: Deps):
    ids = deps.stop_ids(cfg)
    if not ids:
        # No poles resolved (stops dataset down, or a bad stop name): region down.
        return Failure("bus: no stop ids resolved")
    return bus.fetch_departures(ids, cfg.line, now, deps.http)


def _fetch_calendar(cfg: Config, now: datetime, deps: Deps):
    if deps.creds is None:
        # The token was missing/invalid at startup; calendar stays unavailable
        # rather than taking the whole dashboard down (DESIGN §2.6).
        return Failure("calendar: no credential loaded")
    return calendar.fetch_events(cfg.calendar_ids, now, deps.creds, deps.http)


# --- config → view wiring (kept out of the pure core) -----------------------


def region_labels(cfg: Config) -> RegionLabels:
    """The three region titles, suffixed from config and cased for the panel
    (DESIGN §7, the 2026-09-05 T03 decision): "POGODA · GDAŃSK",
    "ODJAZDY · HYNKA · 227", "KALENDARZ". Built here, in the composition root, so
    the city/line never reach the pure core or the view-model."""
    return RegionLabels(
        weather=f"POGODA · {cfg.place.upper()}",
        buses=f"ODJAZDY · {cfg.stops_label.upper()} · {cfg.line}",
        calendar="KALENDARZ",
    )


def service_hours(cfg: Config) -> ServiceHours:
    """The service window as whole hours for the refresh policy (`core/refresh.py`
    keys on the hour). The config loader guarantees whole hours and a valid window.
    A 00:00 end means midnight (end-of-day), so it maps to hour 24 — otherwise the
    policy's `start_hour <= hour < end_hour` would read [start, 0) as empty."""
    end_hour = 24 if cfg.service_end == time(0, 0) else cfg.service_end.hour
    return ServiceHours(start_hour=cfg.service_start.hour, end_hour=end_hour)


# --- the loop ---------------------------------------------------------------


def run_loop(
    cfg: Config,
    clock: Callable[[], datetime],
    deps: Deps,
    service: ServiceHours,
    *,
    sleep: Callable[[float], None] = _time.sleep,
    should_stop: Callable[[], bool] = lambda: False,
) -> None:
    """Rebuild the image on a cadence until `should_stop` is true. `clock` and
    `sleep` are injected so tests drive the loop with a fixed clock and no real
    sleep (DESIGN §3.1). The cadence is the same policy the server reports to the
    device, so the served image is never more than one interval stale (DESIGN
    §2.5). A truly unexpected crash in a cycle is logged and the loop continues."""
    while not should_stop():
        now = clock()
        try:
            build_once(cfg, now, deps)
        except Exception:  # noqa: BLE001 — the loop must outlive any single cycle
            log.exception("build cycle crashed unexpectedly; loop continues")
        sleep(refresh_seconds(now, service))


# --- process entry point (untestable glue: real clock, sockets, network) ----


def _clock() -> datetime:
    """The system clock as a tz-aware UTC datetime. The one clock read for the
    loop; the pure core and refresh policy take this as an argument (DESIGN §3.1)."""
    return datetime.now(timezone.utc)


def main(argv: list[str] | None = None) -> None:
    """Load config, wire the server and the loop, and run until interrupted. This
    is thin, untestable glue over the tested pieces (`load_config`, `build_once`,
    `run_loop`, `App`): it opens real sockets and a real HTTP client and reads the
    real clock, none of which the test command can reach (DESIGN §5.1)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    argv = sys.argv[1:] if argv is None else argv
    config_path = argv[0] if argv else os.environ.get("TRMNL_CONFIG", "config.toml")
    cfg = config_mod.load_config(config_path)

    # Load the calendar credential up front. A missing or invalid token only takes
    # the calendar region down (DESIGN §2.6); it must not stop the dashboard.
    creds = None
    try:
        creds = google_auth.load_credentials(cfg.token_path)
    except Exception as exc:  # noqa: BLE001 — degrade the region, do not abort
        log.warning(
            "calendar: could not load credential from %s (%s); "
            "calendar region will be unavailable",
            cfg.token_path,
            type(exc).__name__,
        )

    http = httpx.Client()
    deps = Deps(http=http, creds=creds, vehicles=VehicleCache(cfg.vehicle_cache_path))
    service = service_hours(cfg)

    app = App(
        image_path=cfg.image_path,
        startup_path=cfg.startup_path,
        service=service,
        now=_clock,
    )
    server = make_server(app, host=cfg.host, port=cfg.port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info(
        "serving on http://%s:%s — image %s, placeholder %s",
        cfg.host,
        cfg.port,
        cfg.image_path,
        cfg.startup_path,
    )
    try:
        run_loop(cfg, _clock, deps, service)
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        server.shutdown()
        server.server_close()
        http.close()


if __name__ == "__main__":
    main()
