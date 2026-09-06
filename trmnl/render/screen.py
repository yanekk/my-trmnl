"""view-model -> 800x480 1-bit image (DESIGN §2.1, §3.1).

This is the world-facing-but-deterministic side of the boundary: it touches no
clock and no network, so although it is not "pure" (it uses Pillow and, in
`save_bmp`, the filesystem) the same `Dashboard` always yields the same pixels.
That is what lets the layout be locked down with golden-image tests instead of a
person's eye (DESIGN §3.1, §4).

The panel is physically 1-bit black/white e-ink with no grey (DESIGN §2.1), so
everything here draws in mode "1": text and rules are solid black, and the only
"shading" is a diagonal hatch (`_hatch_rect`) — never a grey value, which the
hardware cannot show. Fonts are bundled (IBM Plex, OFL) rather than taken from
the system, both for licence-clean redistribution and because golden tests need
the exact same glyphs on the dev Mac and in the Docker image.

The renderer makes no decisions: every string it draws is already finished in the
view-model (the Polish condition word, "za N min", the local-time labels). It only
lays them out. The one thing it derives is the calendar day headers' date/weekday,
computed from `now_local` which the core already localized — no clock is read.

The mock's top strip (clock, date, "updated") is intentionally not drawn
(DESIGN §2.1, §7). Region titles are the plain Polish words; the mock's
"· Gdańsk" / "· Linia 227" suffixes are config (city, line) that the view-model
does not carry, so they are not drawn here (see PROGRESS T03 note).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from trmnl.core.model import Dashboard

# --- canvas -----------------------------------------------------------------

WIDTH, HEIGHT = 800, 480
# Mode "1" pixel values: 0 is black, 1 is white. Every fill in this module is
# one of these two — there is no third value on the panel (DESIGN §2.1).
BLACK, WHITE = 0, 1

# Region boxes. The mock's grid is columns 1.55fr:1fr and rows 1fr:0.92fr; these
# constants are that split rounded to whole pixels, with no top bar (DESIGN §7):
# weather top-left, buses top-right, calendar full-width across the bottom.
LEFT_W = 486   # weather column width; buses take the rest of the top row
TOP_H = 250    # height of the weather+buses row; calendar takes the rest
PAD = 16       # inner margin inside every region

WEATHER_BOX = (0, 0, LEFT_W, TOP_H)
BUSES_BOX = (LEFT_W, 0, WIDTH, TOP_H)
CAL_BOX = (0, TOP_H, WIDTH, HEIGHT)

# --- fonts ------------------------------------------------------------------

_FONT_DIR = Path(__file__).resolve().parent / "fonts"
_SANS = "IBMPlexSans-Regular.ttf"
_SANS_SB = "IBMPlexSans-SemiBold.ttf"
_MONO = "IBMPlexMono-Regular.ttf"
_MONO_SB = "IBMPlexMono-SemiBold.ttf"


@lru_cache(maxsize=None)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_DIR / name), size)


# Weekday abbreviations, Monday-first to match datetime.weekday(). Used only for
# the calendar day headers ("Dziś · pt 5.09"), derived from now_local.
_WEEKDAYS_PL = ("pn", "wt", "śr", "cz", "pt", "sb", "nd")

# Region titles. Plain words on purpose: the city and line live in config, not in
# the view-model, so they are added later (T08) if wanted, not guessed here.
_LABEL_WEATHER = "POGODA"
_LABEL_BUSES = "ODJAZDY"
_LABEL_CALENDAR = "KALENDARZ"

_UNAVAILABLE = "niedostępne"
_NO_DEPARTURES = "brak odjazdów"
_NO_EVENTS = "Brak wydarzeń"


@dataclass(frozen=True)
class RegionLabels:
    """The three region titles, already cased for the panel. The defaults are the
    plain Polish words, so a `render()` with no labels draws exactly what the
    golden tests expect and they stay valid. The composition root (T08) passes
    config-suffixed, uppercased titles like "POGODA · GDAŃSK" and
    "ODJAZDY · HYNKA · 227" (DESIGN §7, the 2026-09-05 T03 decision), keeping the
    city/line out of the pure core and out of the view-model."""

    weather: str = _LABEL_WEATHER
    buses: str = _LABEL_BUSES
    calendar: str = _LABEL_CALENDAR


# --- low-level drawing helpers ----------------------------------------------


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> float:
    return font.getlength(text)


def _tracked(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    tracking: float,
) -> None:
    """Draw `text` at (x, y) with extra pixels of letter-spacing between glyphs.
    Pillow has no tracking of its own, so the small uppercase labels — the one
    place the mock leans on wide letter-spacing — are drawn a glyph at a time.

    Each glyph is anchored on the shared baseline (y + ascent, anchor "ls"), not
    top-anchored: a top anchor aligns each glyph's own bounding box, so an accented
    capital (Ń, Ś) — whose box is taller because of the accent — was pushed down
    and sat below the line of its neighbours. Baseline-anchoring keeps every
    glyph's body on the line and lets only the accent rise above it. `y` stays the
    text's top, so callers are unaffected."""
    baseline = y + font.getmetrics()[0]  # ascent: top → baseline
    for ch in text:
        draw.text((x, baseline), ch, font=font, fill=BLACK, anchor="ls")
        x += _text_width(ch, font) + tracking


def _ellipsize(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> str:
    """Trim `text` and append "…" so it fits within `max_width`. Returns the text
    unchanged if it already fits. Used so a long headsign or event title is cut
    cleanly instead of overrunning its region (DESIGN §2.3; T03 overflow test)."""
    if _text_width(text, font) <= max_width:
        return text
    ell = "…"
    ell_w = _text_width(ell, font)
    trimmed = text
    while trimmed and _text_width(trimmed, font) + ell_w > max_width:
        trimmed = trimmed[:-1]
    return trimmed + ell if trimmed else ell


def _vehicle_line(
    maker: str | None,
    number: str,
    font: ImageFont.FreeTypeFont,
    max_width: float,
) -> str:
    """The finished second line under a bus row's time (DESIGN §2.3, T10). With a
    known make it is "{maker} · {number}"; with none it is the number (or "—")
    alone. When the combined text overruns `max_width` the model is trimmed —
    trailing words dropped, then the remainder ellipsized — while the brand (the
    first word of `maker`) and the number are always kept (owner decision 1,
    2026-09-06)."""
    if not maker:
        return number
    full = f"{maker} · {number}"
    if _text_width(full, font) <= max_width:
        return full
    # Drop trailing model words, keeping at least the brand, until it fits.
    words = maker.split()
    for cut in range(len(words) - 1, 0, -1):
        candidate = f"{' '.join(words[:cut])} · {number}"
        if _text_width(candidate, font) <= max_width:
            return candidate
    # Even "brand · number" overruns: ellipsize the brand but keep "· number", so
    # the number is never lost to a very long single-word brand.
    suffix = f" · {number}"
    brand = _ellipsize(words[0], font, max_width - _text_width(suffix, font))
    return brand + suffix


def _hatch_rect(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    spacing: int = 4,
) -> None:
    """Fill the rectangle with a 45° diagonal hatch — the panel's only way to
    show a shaded area, since it has no grey (DESIGN §2.1). Lines run at slope 1
    (one pixel down per pixel right), so clipping to the box is exact arithmetic.
    This is the 1-bit stand-in for the mock's diagonal repeating-gradient fills
    (the hourly bars and the all-day badge)."""
    w = x1 - x0
    h = y1 - y0
    i = -h
    while i <= w:
        ax, ay = x0 + i, y0
        bx, by = x0 + i + h, y1
        if ax < x0:  # slope 1 → shift start down by however far we clip in x
            ay += x0 - ax
            ax = x0
        if bx > x1:
            by -= bx - x1
            bx = x1
        if ax <= x1 and bx >= x0 and ay <= y1 and by >= y0:
            draw.line([(ax, ay), (bx, by)], fill=BLACK, width=1)
        i += spacing


def _draw_unavailable(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    """A source is down: its region shows a centred "niedostępne", visually
    distinct from an available-but-empty region which draws its short empty line
    (DESIGN §2.6). Region titles were dropped (owner, 2026-09-06), so this is the
    whole of a down region."""
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    draw.text((cx, cy), _UNAVAILABLE, font=_font(_SANS, 22), fill=BLACK, anchor="mm")


# --- weather icons ----------------------------------------------------------
# Small line-art icons, drawn from primitives so they scale with the layout and
# need no image assets. Keys match core.assemble's icon vocabulary; an unknown
# key falls back to a plain cloud, same as the core's condition fallback.


def _icon_sun(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    rr = int(r * 0.5)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=BLACK, width=2)
    for k in range(8):
        # eight rays; integer-ish trig via a fixed table keeps it deterministic
        dx, dy = _RAYS[k]
        d.line(
            [(cx + dx * (rr + 3) // 10, cy + dy * (rr + 3) // 10),
             (cx + dx * r // 10, cy + dy * r // 10)],
            fill=BLACK, width=2,
        )


# unit ray directions ×10 (so integer maths), N/NE/E/…: deterministic, no float
_RAYS = ((0, -10), (7, -7), (10, 0), (7, 7), (0, 10), (-7, 7), (-10, 0), (-7, -7))


def _icon_cloud(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    """A rounded cloud outline centred on (cx, cy), fitting roughly in ±r."""
    w = r
    h = int(r * 0.7)
    left = cx - w
    right = cx + w
    base = cy + h // 2
    # three bumps on a flat base
    d.ellipse([left, base - h, left + h, base], outline=BLACK, width=2)
    d.ellipse([cx - h // 2, base - int(h * 1.4), cx + h // 2, base], outline=BLACK, width=2)
    d.ellipse([right - h, base - h, right, base], outline=BLACK, width=2)
    d.rectangle([left + h // 2, base - h // 2, right - h // 2, base], fill=WHITE)
    d.line([(left + h // 2, base), (right - h // 2, base)], fill=BLACK, width=2)


def _icon_part_cloud(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    _icon_sun(d, cx + r // 3, cy - r // 3, int(r * 0.7))
    _icon_cloud(d, cx, cy + r // 4, int(r * 0.8))


def _icon_drops(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, n: int) -> None:
    _icon_cloud(d, cx, cy - r // 3, int(r * 0.85))
    base = cy + int(r * 0.5)
    span = int(r * 1.1)
    for k in range(n):
        x = cx - span // 2 + span * k // max(1, n - 1)
        d.line([(x, base), (x - 3, base + 8)], fill=BLACK, width=2)


def _icon_snow(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    _icon_cloud(d, cx, cy - r // 3, int(r * 0.85))
    base = cy + int(r * 0.5)
    for k in range(3):
        x = cx - r // 2 + r * k // 2
        d.text((x, base), "*", font=_font(_SANS_SB, max(12, r // 2)), fill=BLACK, anchor="mt")


def _icon_fog(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    for k in range(4):
        y = cy - r + k * (2 * r // 3)
        pad = 3 if k % 2 else 0
        d.line([(cx - r + pad, y), (cx + r - pad, y)], fill=BLACK, width=2)


def _icon_storm(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    _icon_cloud(d, cx, cy - r // 3, int(r * 0.85))
    base = cy + int(r * 0.4)
    d.line([(cx + 2, base), (cx - 6, base + 10), (cx + 4, base + 10), (cx - 4, base + 20)],
           fill=BLACK, width=2, joint="curve")


_ICONS = {
    "sun": _icon_sun,
    "part-cloud": _icon_part_cloud,
    "cloud": _icon_cloud,
    "fog": _icon_fog,
    "drizzle": lambda d, cx, cy, r: _icon_drops(d, cx, cy, r, 3),
    "rain": lambda d, cx, cy, r: _icon_drops(d, cx, cy, r, 4),
    "snow": _icon_snow,
    "storm": _icon_storm,
}


def _draw_icon(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, key: str) -> None:
    _ICONS.get(key, _icon_cloud)(d, cx, cy, r)


# --- weather region ---------------------------------------------------------


def _render_weather(draw: ImageDraw.ImageDraw, dash: Dashboard) -> None:
    if not dash.weather_region.available or dash.weather is None:
        _draw_unavailable(draw, WEATHER_BOX)
        return

    w = dash.weather

    # No region title and no big icon anymore (owner, 2026-09-06). The big current
    # temperature and its condition word start on the same top line.
    top = PAD + 4
    temp_font = _font(_SANS_SB, 82)
    temp_text = f"{w.temp_c}°"
    draw.text((PAD, top), temp_text, font=temp_font, fill=BLACK, anchor="lt")
    temp_w = _text_width(temp_text, temp_font)

    side_x = int(PAD + temp_w + 20)
    cond = _ellipsize(w.condition, _font(_SANS_SB, 24), LEFT_W - PAD - side_x)
    draw.text((side_x, top), cond, font=_font(_SANS_SB, 24), fill=BLACK, anchor="lt")
    # Feels-like and wind on one values-only line: "13° · 20 km/h".
    draw.text(
        (side_x, top + 34),
        f"{w.feels_like_c}° · {w.wind_kmh} km/h",
        font=_font(_SANS, 18),
        fill=BLACK,
        anchor="lt",
    )

    _render_hours(draw, w.hours)


def _render_hours(draw: ImageDraw.ImageDraw, hours: list) -> None:
    """The next-hours strip along the bottom of the weather box. Each column is
    stacked hour / icon / temperature / rain (owner, 2026-09-06). The core already
    capped this to fit (WEATHER_HOURS) and rolls it across midnight; an empty strip
    (fetch lacked future hours) draws nothing."""
    if not hours:
        return
    strip_left = PAD
    strip_right = LEFT_W - PAD
    col_w = (strip_right - strip_left) // 6  # fixed 6-slot grid so 1..6 align left

    hour_f = _font(_MONO, 15)
    temp_f = _font(_SANS_SB, 19)
    rain_f = _font(_MONO, 14)

    # A compact stack, each element close to the next (owner, 2026-09-06). Offsets
    # are from the block top; the whole block is then centred vertically in the
    # space below the current-conditions block. Icons stay prominent (r=20) but the
    # column is packed rather than spread.
    icon_r = 20
    OFF_HOUR, OFF_ICON, OFF_TEMP, OFF_RAIN, BLOCK_H = 0, 34, 56, 78, 92
    region_top = 104
    region_bottom = TOP_H - PAD
    y0 = region_top + (region_bottom - region_top - BLOCK_H) // 2

    for i, h in enumerate(hours):
        cx = strip_left + col_w * i + col_w // 2
        draw.text((cx, y0 + OFF_HOUR), h.label, font=hour_f, fill=BLACK, anchor="mt")
        _draw_icon(draw, cx, y0 + OFF_ICON, icon_r, h.icon)
        draw.text((cx, y0 + OFF_TEMP), f"{h.temp_c}°", font=temp_f, fill=BLACK, anchor="mt")
        draw.text((cx, y0 + OFF_RAIN), f"{h.rain_pct}%", font=rain_f, fill=BLACK, anchor="mt")


# --- buses region -----------------------------------------------------------


def _render_buses(draw: ImageDraw.ImageDraw, dash: Dashboard) -> None:
    if not dash.buses_region.available:
        _draw_unavailable(draw, BUSES_BOX)
        _render_attribution(draw, dash)
        return

    left = LEFT_W + PAD
    right = WIDTH - PAD

    if not dash.buses:
        cx = (LEFT_W + WIDTH) // 2
        cy = (0 + TOP_H) // 2
        draw.text((cx, cy), _NO_DEPARTURES, font=_font(_SANS, 20), fill=BLACK, anchor="mm")
        _render_attribution(draw, dash)
        return

    line_f = _font(_MONO_SB, 22)
    dest_f = _font(_SANS, 18)
    time_f = _font(_MONO_SB, 20)
    veh_f = _font(_SANS, 11)  # same small font as the attribution (owner, 2026-09-06)

    # No region title now, so rows start at the top of the box. No separator
    # between rows (owner, 2026-09-06). Each row is two lines — the departure and,
    # under the time, the vehicle number — so row_h reserves both and every row is
    # the same height. Reserve the strip above the attribution.
    rows_bottom = TOP_H - PAD - 24
    row_h = 38
    y = PAD + 4
    for row in dash.buses:
        line_w = _text_width(row.line, line_f)
        draw.text((left, y), row.line, font=line_f, fill=BLACK, anchor="lt")
        # time, right-aligned; headsign fills the gap and is ellipsised to fit
        time_w = _text_width(row.label, time_f)
        draw.text((right, y + 1), row.label, font=time_f, fill=BLACK, anchor="rt")
        dest_x = left + int(line_w) + 12
        dest_max = right - time_w - 12 - dest_x
        dest = _ellipsize("→ " + row.headsign, dest_f, dest_max)
        draw.text((dest_x, y + 2), dest, font=dest_f, fill=BLACK, anchor="lt")
        # Make/model and number under the time, right-aligned, small — the number
        # alone (or "—") when the make is unknown, so every row draws the same shape.
        # The line spans the full row width so a long make has room before trimming.
        veh_text = _vehicle_line(row.maker, row.vehicle, veh_f, right - left)
        draw.text((right, y + 24), veh_text, font=veh_f, fill=BLACK, anchor="rt")
        y += row_h
        if y > rows_bottom:
            break

    _render_attribution(draw, dash)


def _render_attribution(draw: ImageDraw.ImageDraw, dash: Dashboard) -> None:
    """The CC-BY credit for the bus feed (DESIGN §2.3), small and right-aligned in
    the bottom-right of the buses box so it is always on screen but never loud.
    Always drawn, so the licence credit can never silently drop off."""
    draw.text(
        (WIDTH - PAD, TOP_H - PAD),
        dash.attribution,
        font=_font(_SANS, 11),
        fill=BLACK,
        anchor="rs",
    )


# --- calendar region --------------------------------------------------------


def _render_calendar(draw: ImageDraw.ImageDraw, dash: Dashboard) -> None:
    if not dash.calendar_region.available:
        _draw_unavailable(draw, CAL_BOX)
        return

    # No KALENDARZ title (owner, 2026-09-06); the DZIŚ/JUTRO day headers stay and
    # move up to the top of the region.
    col_top = TOP_H + PAD + 4
    mid = WIDTH // 2
    draw.line([(mid, col_top - 6), (mid, HEIGHT - PAD)], fill=BLACK, width=1)

    today_date = dash.now_local
    tomorrow_date = dash.now_local + timedelta(days=1)
    _render_day(
        draw, PAD, mid - PAD, col_top,
        "DZIŚ", today_date, dash.today,
    )
    _render_day(
        draw, mid + PAD, WIDTH - PAD, col_top,
        "JUTRO", tomorrow_date, dash.tomorrow,
    )


def _day_suffix(when) -> str:
    return f"{_WEEKDAYS_PL[when.weekday()]} {when.day}.{when.month:02d}"


def _render_day(
    draw: ImageDraw.ImageDraw,
    x0: int,
    x1: int,
    y0: int,
    heading: str,
    when,
    events: list,
) -> None:
    # Heading: "DZIŚ" then a lighter date suffix, e.g. "· pt 5.09".
    head_f = _font(_SANS_SB, 16)
    _tracked(draw, x0, y0, heading, head_f, tracking=1.5)
    hx = x0 + int(_text_width(heading, head_f)) + len(heading) * 2 + 8
    draw.text((hx, y0 + 1), f"· {_day_suffix(when)}", font=_font(_SANS, 15), fill=BLACK, anchor="lt")

    y = y0 + 28
    bottom = HEIGHT - PAD
    row_h = 26

    if not events:
        draw.text((x0, y), _NO_EVENTS, font=_font(_SANS, 18), fill=BLACK, anchor="lt")
        return

    time_f = _font(_MONO_SB, 17)
    title_f = _font(_SANS, 18)
    time_col = 60  # width reserved for the "09:30" column, with a gap to the title

    for idx, ev in enumerate(events):
        # If the next row would overflow, stop and say how many are hidden.
        remaining = len(events) - idx
        if y + row_h > bottom and remaining > 0:
            draw.text((x0, y), f"+{remaining} więcej", font=_font(_SANS, 15), fill=BLACK, anchor="lt")
            return
        if idx > 0:
            _dotted_hline(draw, x0, x1, y - 4)
        if ev.all_day:
            _allday_badge(draw, x0, y, x1, ev.title, title_f)
        else:
            draw.text((x0, y), ev.label, font=time_f, fill=BLACK, anchor="lt")
            title = _ellipsize(ev.title, title_f, x1 - (x0 + time_col))
            draw.text((x0 + time_col, y), title, font=title_f, fill=BLACK, anchor="lt")
        y += row_h


def _allday_badge(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y: int,
    x1: int,
    title: str,
    font: ImageFont.FreeTypeFont,
) -> None:
    """An all-day event: a bordered chip with a hatched left cap and no time, so
    it reads differently from a timed row (DESIGN §2.4). The hatch is confined to
    the cap rather than laid behind the text, which would muddy it on 1-bit."""
    cap = 12  # width of the hatched "all-day" marker at the left of the chip
    title = _ellipsize(title, font, x1 - x0 - cap - 20)
    tw = _text_width(title, font)
    bx1 = x0 + cap + int(tw) + 12
    by1 = y + 22
    draw.rectangle([x0, y, bx1, by1], outline=BLACK, width=1)
    _hatch_rect(draw, x0 + 1, y + 1, x0 + cap, by1 - 1, spacing=4)
    draw.line([(x0 + cap, y), (x0 + cap, by1)], fill=BLACK, width=1)
    draw.text((x0 + cap + 6, y + 2), title, font=font, fill=BLACK, anchor="lt")


# --- shared -----------------------------------------------------------------


def _dotted_hline(draw: ImageDraw.ImageDraw, x0: int, x1: int, y: int, gap: int = 4) -> None:
    """A dotted rule between rows, matching the mock's dotted separators."""
    x = x0
    while x < x1:
        draw.point((x, y), fill=BLACK)
        x += gap


def _dividers(draw: ImageDraw.ImageDraw) -> None:
    draw.line([(LEFT_W, 0), (LEFT_W, TOP_H)], fill=BLACK, width=1)  # weather | buses
    draw.line([(0, TOP_H), (WIDTH, TOP_H)], fill=BLACK, width=1)     # top row / calendar


# --- public API -------------------------------------------------------------


def render(dashboard: Dashboard, labels: RegionLabels | None = None) -> Image.Image:
    """Draw the whole dashboard to an 800×480 1-bit image (DESIGN §2.1). Pure of
    clock and network; deterministic, so it is golden-tested (DESIGN §3.1).

    `labels` is retained for interface and config compatibility but is no longer
    drawn: the region titles (POGODA/ODJAZDY/KALENDARZ) were removed to cut
    verbosity (owner, 2026-09-06). The calendar's DZIŚ/JUTRO day headers stay."""
    _ = labels
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)
    _dividers(draw)
    _render_weather(draw, dashboard)
    _render_buses(draw, dashboard)
    _render_calendar(draw, dashboard)
    return img


def render_startup() -> Image.Image:
    """The bundled cold-start placeholder the server serves before the first real
    image exists (DESIGN §2.6, §3.5): a centred "Uruchamianie…" on a blank panel,
    so the device is never handed a 404 or a blank screen."""
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)
    draw.text((WIDTH // 2, HEIGHT // 2), "Uruchamianie…", font=_font(_SANS_SB, 40),
              fill=BLACK, anchor="mm")
    return img


def save_bmp(image: Image.Image, path: str) -> None:
    """Write a 1-bit BMP3 to `path`, atomically. The image is written to a sibling
    temp file and os.replace'd over the target, so a device fetch mid-write never
    sees a partial file (DESIGN §2.6, §3.5). os.replace is atomic on the same
    filesystem, which the temp sibling guarantees."""
    if image.mode != "1":
        image = image.convert("1")
    tmp = f"{path}.tmp"
    image.save(tmp, format="BMP")
    os.replace(tmp, path)
