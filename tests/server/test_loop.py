"""Composition-root and refresh-loop tests (DESIGN §2.5, §2.6, §3.4, task T08).

These exercise the *wiring*, not the adapters (which have their own tests): that a
healthy cycle publishes a whole image, that any one source failing still publishes
with only its region degraded, that a render failure keeps the last-good image and
never crashes the loop, that the cold-start placeholder is served until the first
build, that config headings reach the renderer, and that the loop drives itself
from an injected clock with no real sleep.

The three source fetches are stubbed at `loop._fetch_weather/_fetch_bus/
_fetch_calendar`, so a test says what each source did without standing up HTTP —
the adapters' own error handling is covered by their suites.
"""

import os
from datetime import datetime, time, timedelta, timezone

import pytest
from PIL import Image

from trmnl.adapters.config import Config
from trmnl.core.model import (
    WARSAW,
    Departure,
    Event,
    Failure,
    ServiceHours,
    Sources,
    WeatherData,
)
from trmnl.render import screen
from trmnl.server import app as srv
from trmnl.server import loop

STARTUP_BMP = os.path.join(os.path.dirname(screen.__file__), "startup.bmp")

# A fixed clock: 2026-09-05 08:42 Europe/Warsaw is inside a 05–23 service window.
NOW = datetime(2026, 9, 5, 6, 42, tzinfo=timezone.utc)


def _config(tmp_path, **over) -> Config:
    base = dict(
        lat=54.372,
        lon=18.638,
        stops=["Hynka"],
        line="227",
        near_minutes=15,
        calendar_ids=["cal@example.com"],
        token_path=str(tmp_path / "token.json"),
        service_start=time(5, 0),
        service_end=time(23, 0),
        image_path=str(tmp_path / "screen.bmp"),
        startup_path=STARTUP_BMP,
        place="Gdańsk",
        stops_label="Hynka",
        host="127.0.0.1",
        port=8080,
    )
    base.update(over)
    return Config(**base)


def _deps() -> loop.Deps:
    # http is unused once the source fetches are stubbed; stop ids are pre-seeded
    # so no stops download happens.
    return loop.Deps(http=None, creds=object(), stop_ids=[1767, 1768])


# --- healthy source stubs (patched onto loop) -------------------------------


def _weather_ok(cfg, now, deps):
    return WeatherData(temp_c=12, condition_code=3, feels_like_c=10, wind_kmh=15, hourly=[])


def _bus_ok(cfg, now, deps):
    return [Departure("227", "Jelitkowo", now + timedelta(minutes=5))]


def _calendar_ok(cfg, now, deps):
    return [Event(start=now.astimezone(WARSAW), title="Spotkanie", all_day=False)]


def _all_healthy(monkeypatch):
    monkeypatch.setattr(loop, "_fetch_weather", _weather_ok)
    monkeypatch.setattr(loop, "_fetch_bus", _bus_ok)
    monkeypatch.setattr(loop, "_fetch_calendar", _calendar_ok)


# --- a healthy build publishes a whole image --------------------------------


def test_build_once_publishes_a_valid_whole_image(tmp_path, monkeypatch):
    _all_healthy(monkeypatch)
    cfg = _config(tmp_path)
    result = loop.build_once(cfg, NOW, _deps())

    assert result.published is True
    assert not isinstance(result.sources.weather, Failure)
    assert not isinstance(result.sources.bus, Failure)
    assert not isinstance(result.sources.calendar, Failure)
    # The published file is a whole, valid 1-bit 800×480 BMP, and the temp sibling
    # save_bmp used has been renamed away (no partial file left behind).
    img = Image.open(cfg.image_path)
    assert (img.format, img.mode, img.size) == ("BMP", "1", (800, 480))
    assert not os.path.exists(cfg.image_path + ".tmp")


# --- degradation: one source down still publishes (DESIGN §2.6) -------------


def test_one_source_failing_still_publishes_and_degrades_only_that_region(tmp_path, monkeypatch):
    _all_healthy(monkeypatch)
    monkeypatch.setattr(loop, "_fetch_bus", lambda cfg, now, deps: Failure("bus: timeout"))
    cfg = _config(tmp_path)
    result = loop.build_once(cfg, NOW, _deps())

    assert result.published is True
    assert isinstance(result.sources.bus, Failure)
    assert not isinstance(result.sources.weather, Failure)
    assert not isinstance(result.sources.calendar, Failure)
    assert os.path.exists(cfg.image_path)


def test_all_sources_failing_still_publishes_three_unavailable_regions(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "_fetch_weather", lambda cfg, now, deps: Failure("w"))
    monkeypatch.setattr(loop, "_fetch_bus", lambda cfg, now, deps: Failure("b"))
    monkeypatch.setattr(loop, "_fetch_calendar", lambda cfg, now, deps: Failure("c"))
    cfg = _config(tmp_path)
    result = loop.build_once(cfg, NOW, _deps())

    assert result.published is True
    assert isinstance(result.sources.weather, Failure)
    assert isinstance(result.sources.bus, Failure)
    assert isinstance(result.sources.calendar, Failure)
    img = Image.open(cfg.image_path)
    assert img.size == (800, 480)  # still a valid whole screen, all three "niedostępne"


def test_unexpected_source_exception_degrades_to_failure_not_crash(tmp_path, monkeypatch):
    # An adapter that raises something it did not anticipate must not fail the build:
    # _safe turns it into a Failure and the other regions still render.
    _all_healthy(monkeypatch)

    def boom(cfg, now, deps):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(loop, "_fetch_calendar", boom)
    cfg = _config(tmp_path)
    result = loop.build_once(cfg, NOW, _deps())

    assert result.published is True
    assert isinstance(result.sources.calendar, Failure)
    assert not isinstance(result.sources.weather, Failure)


# --- degradation: a render/write failure keeps the last-good image ----------


def test_render_failure_keeps_last_good_image_and_does_not_raise(tmp_path, monkeypatch):
    _all_healthy(monkeypatch)
    cfg = _config(tmp_path)
    last_good = b"BM-last-good-image"
    with open(cfg.image_path, "wb") as f:
        f.write(last_good)

    def boom(dashboard, labels=None):
        raise RuntimeError("renderer blew up")

    monkeypatch.setattr(loop.screen, "render", boom)
    result = loop.build_once(cfg, NOW, _deps())  # must not raise

    assert result.published is False
    # The last-good file is untouched: the server keeps serving it (DESIGN §2.6).
    with open(cfg.image_path, "rb") as f:
        assert f.read() == last_good


# --- cold start: the placeholder is served until the first build ------------


def test_placeholder_served_until_first_build_then_real_image(tmp_path, monkeypatch):
    _all_healthy(monkeypatch)
    cfg = _config(tmp_path)
    app = srv.App(
        image_path=cfg.image_path,
        startup_path=cfg.startup_path,
        service=loop.service_hours(cfg),
        now=lambda: NOW,
    )

    # Before any build, image_path does not exist → the committed placeholder is served.
    with open(cfg.startup_path, "rb") as f:
        placeholder = f.read()
    cold = app.handle("GET", "/x.bmp", {"ID": "AA:BB"})
    assert cold.status == 200
    assert cold.body == placeholder

    # After the first successful build, the real image is served instead.
    loop.build_once(cfg, NOW, _deps())
    warm = app.handle("GET", "/x.bmp", {"ID": "AA:BB"})
    assert warm.status == 200
    assert warm.body != placeholder
    with open(cfg.image_path, "rb") as f:
        assert warm.body == f.read()


# --- config headings reach the renderer -------------------------------------


def test_region_labels_are_suffixed_and_uppercased_from_config(tmp_path):
    labels = loop.region_labels(_config(tmp_path))
    assert labels.weather == "POGODA · GDAŃSK"
    assert labels.buses == "ODJAZDY · HYNKA · 227"
    assert labels.calendar == "KALENDARZ"


def test_build_once_passes_the_config_labels_to_the_renderer(tmp_path, monkeypatch):
    _all_healthy(monkeypatch)
    cfg = _config(tmp_path)
    seen = {}

    def spy_render(dashboard, labels=None):
        seen["labels"] = labels
        return screen.render(dashboard, labels)  # real render, so save_bmp works

    monkeypatch.setattr(loop.screen, "render", spy_render)
    loop.build_once(cfg, NOW, _deps())

    assert seen["labels"] == loop.region_labels(cfg)


# --- service hours mapping --------------------------------------------------


def test_service_hours_takes_the_hour_of_each_bound(tmp_path):
    cfg = _config(tmp_path, service_start=time(5, 0), service_end=time(23, 0))
    assert loop.service_hours(cfg) == ServiceHours(start_hour=5, end_hour=23)


# --- the loop drives itself from the injected clock, no real sleep ----------


def test_run_loop_calls_build_once_each_tick_with_the_injected_clock(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    service = ServiceHours(start_hour=5, end_hour=23)
    ticks = [
        datetime(2026, 9, 5, 6, 0, tzinfo=timezone.utc),   # 08:00 Warsaw → in service
        datetime(2026, 9, 5, 6, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 5, 1, 0, tzinfo=timezone.utc),   # 03:00 Warsaw → overnight
    ]
    clock_calls = iter(ticks)

    built_with: list[datetime] = []
    slept: list[float] = []

    monkeypatch.setattr(loop, "build_once", lambda c, now, d: built_with.append(now))

    def fake_clock():
        return next(clock_calls)

    def fake_sleep(seconds):
        slept.append(seconds)

    # Stop after three ticks so the loop terminates deterministically.
    loop.run_loop(
        cfg,
        fake_clock,
        _deps(),
        service,
        sleep=fake_sleep,
        should_stop=lambda: len(built_with) >= 3,
    )

    assert built_with == ticks
    # The cadence is the same refresh policy the device gets: 60s in service, 1800s
    # overnight — so the served image is never more than one interval stale.
    assert slept == [60, 60, 1800]


def test_run_loop_survives_a_crashing_cycle(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    service = ServiceHours(start_hour=5, end_hour=23)
    calls = {"n": 0}

    def crashing_build(c, now, d):
        calls["n"] += 1
        raise RuntimeError("cycle blew up")

    monkeypatch.setattr(loop, "build_once", crashing_build)
    # Two ticks: the loop must run the second even though the first raised.
    loop.run_loop(
        cfg,
        lambda: NOW,
        _deps(),
        service,
        sleep=lambda s: None,
        should_stop=lambda: calls["n"] >= 2,
    )
    assert calls["n"] == 2


# --- Deps: stop ids resolved once and cached (DESIGN §3.5) -------------------


def test_deps_caches_resolved_stop_ids_and_retries_after_a_download_failure(monkeypatch):
    cfg = Config(
        lat=0, lon=0, stops=["Hynka"], line="227", near_minutes=15,
        calendar_ids=["c"], token_path="t", service_start=time(5, 0),
        service_end=time(23, 0), image_path="i", startup_path="s",
        place="Gdańsk", stops_label="Hynka", host="127.0.0.1", port=8080,
    )
    # First call: the stops download fails → no ids, and nothing is cached.
    monkeypatch.setattr(loop.bus, "fetch_stops", lambda http: Failure("stops down"))
    deps = loop.Deps(http=None)
    assert deps.stop_ids(cfg) == []

    # Next cycle: the download succeeds → ids resolved and cached.
    fake_stops = {"stops": [
        {"stopId": 1767, "stopName": "Hynka", "zoneName": "Gdańsk"},
        {"stopId": 1768, "stopName": "Hynka", "zoneName": "Gdańsk"},
    ]}
    monkeypatch.setattr(loop.bus, "fetch_stops", lambda http: fake_stops)
    assert deps.stop_ids(cfg) == [1767, 1768]

    # A later download failure must not disturb the cached ids.
    monkeypatch.setattr(loop.bus, "fetch_stops", lambda http: Failure("down again"))
    assert deps.stop_ids(cfg) == [1767, 1768]
