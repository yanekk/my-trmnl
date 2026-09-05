"""Renderer golden tests (DESIGN §3.1, §4). The renderer is deterministic — the
same view-model always yields the same pixels — so the layout is locked down by
comparing to committed reference PNGs instead of a person's eye.

Regenerating the goldens (only when the layout genuinely changes):

    docker compose run --rm -e REGEN_GOLDENS=1 test

That rewrites every golden from the current renderer, so run it deliberately and
eyeball the results. Goldens must be generated in the same environment the tests
run in (the Docker image), because FreeType hinting is what makes the pixels
exact; a golden made elsewhere can differ by a pixel and fail here.
"""

import os

import pytest
from PIL import Image

from trmnl.core.model import (
    ATTRIBUTION,
    WARSAW,
    BusRow,
    Dashboard,
    EventView,
    HourView,
    Region,
    WeatherView,
)
from trmnl.render import screen

from datetime import datetime

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
_REGEN = os.environ.get("REGEN_GOLDENS") == "1"

NOW = datetime(2026, 9, 5, 8, 42, tzinfo=WARSAW)


# --- sample view-models -----------------------------------------------------


def _region(available=True):
    return Region(available=available, as_of=NOW if available else None)


def _weather_view():
    return WeatherView(
        temp_c=12,
        condition="Pochmurno",
        icon="cloud",
        feels_like_c=10,
        wind_kmh=15,
        hours=[
            HourView(label="09", temp_c=13, rain_pct=10),
            HourView(label="10", temp_c=13, rain_pct=20),
            HourView(label="11", temp_c=14, rain_pct=40),
            HourView(label="12", temp_c=14, rain_pct=60),
            HourView(label="13", temp_c=13, rain_pct=55),
            HourView(label="14", temp_c=12, rain_pct=30),
        ],
    )


def _buses_full():
    return [
        BusRow(line="227", headsign="Jelitkowo", label="za 3 min"),
        BusRow(line="227", headsign="Chełm Cienista", label="08:49"),
        BusRow(line="227", headsign="Jelitkowo", label="08:57"),
        BusRow(line="227", headsign="Chełm Cienista", label="09:04"),
        BusRow(line="227", headsign="Jelitkowo", label="09:12"),
    ]


def _today_events():
    return [
        EventView(label="09:30", title="Standup zespołu", all_day=False),
        EventView(label="13:00", title="Lunch z Aną", all_day=False),
        EventView(label="16:00", title="Dentysta", all_day=False),
        EventView(label="18:30", title="Trening", all_day=False),
    ]


def _tomorrow_events():
    return [
        EventView(label="", title="Urodziny Piotra", all_day=True),
        EventView(label="10:00", title="Przegląd auta", all_day=False),
        EventView(label="19:00", title="Kino — Diuna", all_day=False),
    ]


def _dashboard(**overrides):
    """A fully-populated dashboard; pass keyword overrides to vary one region."""
    base = dict(
        now_local=NOW,
        weather=_weather_view(),
        weather_region=_region(),
        buses=_buses_full(),
        buses_region=_region(),
        today=_today_events(),
        tomorrow=_tomorrow_events(),
        calendar_region=_region(),
        attribution=ATTRIBUTION,
    )
    base.update(overrides)
    return Dashboard(**base)


# --- golden helper ----------------------------------------------------------


def _assert_golden(img: Image.Image, name: str):
    path = os.path.join(GOLDEN_DIR, f"{name}.png")
    if _REGEN:
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        img.save(path)
        return
    assert os.path.exists(path), (
        f"golden {name}.png missing — regenerate with "
        f"`docker compose run --rm -e REGEN_GOLDENS=1 test`"
    )
    golden = Image.open(path)
    assert (img.mode, img.size) == (golden.mode, golden.size)
    assert img.tobytes() == golden.tobytes(), f"{name} differs from its golden"


# --- shape ------------------------------------------------------------------


def test_render_is_1bit_800x480():
    img = screen.render(_dashboard())
    assert img.mode == "1"
    assert img.size == (800, 480)


def test_startup_is_1bit_800x480():
    img = screen.render_startup()
    assert img.mode == "1"
    assert img.size == (800, 480)


# --- goldens ----------------------------------------------------------------


def test_golden_populated():
    _assert_golden(screen.render(_dashboard()), "populated")


def test_golden_weather_unavailable():
    d = _dashboard(weather=None, weather_region=_region(available=False))
    _assert_golden(screen.render(d), "weather_unavailable")


def test_golden_buses_empty():
    d = _dashboard(buses=[])
    _assert_golden(screen.render(d), "buses_empty")


def test_golden_calendar_empty_today():
    d = _dashboard(today=[])
    _assert_golden(screen.render(d), "calendar_empty_today")


def test_golden_startup():
    _assert_golden(screen.render_startup(), "startup")


# --- empty is not the same as unavailable (DESIGN §2.6) ---------------------


def test_empty_bus_differs_from_unavailable():
    empty = screen.render(_dashboard(buses=[]))
    down = screen.render(_dashboard(buses=[], buses_region=_region(available=False)))
    assert empty.tobytes() != down.tobytes()


def test_empty_calendar_differs_from_unavailable():
    empty = screen.render(_dashboard(today=[]))
    down = screen.render(_dashboard(today=[], calendar_region=_region(available=False)))
    assert empty.tobytes() != down.tobytes()


# --- overflow: long headsign / many events stay inside the region -----------


def test_long_headsign_and_many_events_do_not_overflow():
    long_bus = [BusRow(line="227", headsign="X" * 200, label="za 3 min")]
    many = [EventView(label=f"{8 + i:02d}:00", title=f"Zdarzenie numer {i} " * 5,
                      all_day=False) for i in range(30)]
    d = _dashboard(buses=long_bus, today=many, tomorrow=many)
    img = screen.render(d)
    # It must still be exactly one panel — nothing pushed the canvas larger, and
    # rendering did not raise on content far bigger than the region.
    assert img.mode == "1"
    assert img.size == (800, 480)


def test_ellipsize_trims_to_width():
    from PIL import ImageDraw
    img = Image.new("1", (10, 10), 1)
    ImageDraw.Draw(img)  # not needed, but proves the font loads
    font = screen._font(screen._SANS, 18)
    short = screen._ellipsize("Krótki", font, 500)
    assert short == "Krótki"
    long = screen._ellipsize("Bardzo długi napis który się nie zmieści", font, 60)
    assert long.endswith("…")
    assert screen._text_width(long, font) <= 60


# --- save_bmp: atomic, and a valid 1-bit BMP --------------------------------


def test_committed_startup_bmp_is_1bit_800x480():
    """The cold-start placeholder ships as a committed BMP the server serves
    before the first real image exists (DESIGN §2.6, §3.5). Regenerate it with:
        docker compose run --rm -v "$PWD":/app --entrypoint python test \\
            -c "from trmnl.render import screen; \\
                screen.save_bmp(screen.render_startup(), 'trmnl/render/startup.bmp')"
    """
    path = os.path.join(os.path.dirname(screen.__file__), "startup.bmp")
    assert os.path.exists(path), "committed startup.bmp is missing"
    im = Image.open(path)
    assert im.format == "BMP"
    assert im.mode == "1"
    assert im.size == (800, 480)


def test_save_bmp_writes_1bit_bmp(tmp_path):
    out = tmp_path / "screen.bmp"
    screen.save_bmp(screen.render(_dashboard()), str(out))
    assert out.exists()
    reopened = Image.open(str(out))
    assert reopened.format == "BMP"
    assert reopened.mode == "1"
    assert reopened.size == (800, 480)


def test_save_bmp_uses_temp_then_rename(tmp_path, monkeypatch):
    """The target is never written directly: a .tmp sibling is os.replace'd over
    it, so a concurrent fetch never sees a partial file (DESIGN §2.6, §3.5)."""
    out = tmp_path / "screen.bmp"
    seen = {}
    real_replace = os.replace

    def spy(src, dst):
        seen["src"] = src
        seen["dst"] = dst
        # target must not exist yet — proof the image went to the temp first
        seen["target_absent_before_rename"] = not os.path.exists(dst)
        real_replace(src, dst)

    monkeypatch.setattr(screen.os, "replace", spy)
    screen.save_bmp(screen.render_startup(), str(out))

    assert seen["src"] == f"{out}.tmp"
    assert seen["dst"] == str(out)
    assert seen["target_absent_before_rename"] is True
    assert out.exists()
    assert not os.path.exists(f"{out}.tmp")
