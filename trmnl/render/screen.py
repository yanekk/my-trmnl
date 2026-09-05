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
    place the mock leans on wide letter-spacing — are drawn a glyph at a time."""
    for ch in text:
        draw.text((x, y), ch, font=font, fill=BLACK, anchor="lt")
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


def _region_label(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str) -> int:
    """Draw a region's uppercase title at its top-left and return the y at which
    content below it may start."""
    x0, y0, _, _ = box
    font = _font(_SANS_SB, 15)
    _tracked(draw, x0 + PAD, y0 + PAD, text, font, tracking=2.0)
    return y0 + PAD + 22


def _draw_unavailable(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str) -> None:
    """A source is down: its region shows only the title and a centred
    "niedostępne", visually distinct from an available-but-empty region
    (DESIGN §2.6)."""
    _region_label(draw, box, label)
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2 + 8
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
        _draw_unavailable(draw, WEATHER_BOX, _LABEL_WEATHER)
        return

    _region_label(draw, WEATHER_BOX, _LABEL_WEATHER)
    w = dash.weather

    # Icon top-right of the region.
    _draw_icon(draw, LEFT_W - PAD - 30, PAD + 44, 26, w.icon)

    # Big current temperature, top-left under the label.
    temp_font = _font(_SANS_SB, 82)
    temp_text = f"{w.temp_c}°"
    draw.text((PAD, 46), temp_text, font=temp_font, fill=BLACK, anchor="lt")
    temp_w = _text_width(temp_text, temp_font)

    # Condition word and the two meta lines, to the right of the temperature.
    side_x = int(PAD + temp_w + 22)
    draw.text((side_x, 58), w.condition, font=_font(_SANS_SB, 24), fill=BLACK, anchor="lt")
    meta = _font(_SANS, 18)
    draw.text((side_x, 92), f"odczuwalna {w.feels_like_c}°", font=meta, fill=BLACK, anchor="lt")
    draw.text((side_x, 116), f"wiatr {w.wind_kmh} km/h", font=meta, fill=BLACK, anchor="lt")

    _render_hours(draw, w.hours)


def _render_hours(draw: ImageDraw.ImageDraw, hours: list) -> None:
    """The rest-of-today strip along the bottom of the weather box: per hour a
    temperature, a hatched bar whose height tracks that temperature, a rain
    chance and the hour. The core already capped this to fit (WEATHER_HOURS), and
    near midnight it can be empty, which simply draws nothing."""
    if not hours:
        return
    strip_top = 150
    strip_left = PAD
    strip_right = LEFT_W - PAD
    n = len(hours)
    col_w = (strip_right - strip_left) // 6  # fixed 6-slot grid so 1..6 align left

    temps = [h.temp_c for h in hours]
    lo, hi = min(temps), max(temps)
    bar_top = strip_top + 22
    bar_max_h = 40
    bar_base = bar_top + bar_max_h

    small = _font(_SANS, 15)
    mono_h = _font(_MONO, 15)
    temp_f = _font(_SANS_SB, 19)

    for i, h in enumerate(hours):
        cx = strip_left + col_w * i + col_w // 2
        # temperature above the bar
        draw.text((cx, strip_top), f"{h.temp_c}°", font=temp_f, fill=BLACK, anchor="mt")
        # bar height scaled across the visible range; flat range → mid height
        if hi > lo:
            frac = (h.temp_c - lo) / (hi - lo)
            bh = 12 + int(frac * (bar_max_h - 12))
        else:
            bh = bar_max_h // 2
        bw = col_w - 14
        bx0 = cx - bw // 2
        bx1 = cx + bw // 2
        by0 = bar_base - bh
        draw.rectangle([bx0, by0, bx1, bar_base], outline=BLACK, width=1)
        _hatch_rect(draw, bx0 + 1, by0 + 1, bx1 - 1, bar_base - 1, spacing=4)
        # rain chance, then the hour, below the bar
        draw.text((cx, bar_base + 6), f"{h.rain_pct}%", font=mono_h, fill=BLACK, anchor="mt")
        draw.text((cx, bar_base + 26), h.label, font=mono_h, fill=BLACK, anchor="mt")


# --- buses region -----------------------------------------------------------


def _render_buses(draw: ImageDraw.ImageDraw, dash: Dashboard) -> None:
    if not dash.buses_region.available:
        _draw_unavailable(draw, BUSES_BOX, _LABEL_BUSES)
        _render_attribution(draw, dash)
        return

    content_top = _region_label(draw, BUSES_BOX, _LABEL_BUSES)
    left = LEFT_W + PAD
    right = WIDTH - PAD

    if not dash.buses:
        cx = (LEFT_W + WIDTH) // 2
        cy = (0 + TOP_H) // 2 + 8
        draw.text((cx, cy), _NO_DEPARTURES, font=_font(_SANS, 20), fill=BLACK, anchor="mm")
        _render_attribution(draw, dash)
        return

    line_f = _font(_MONO_SB, 22)
    dest_f = _font(_SANS, 18)
    time_f = _font(_MONO_SB, 20)

    # Reserve the strip above the attribution for the rows.
    rows_bottom = TOP_H - PAD - 20
    row_h = 34
    y = content_top + 4
    for idx, row in enumerate(dash.buses):
        if idx > 0:
            _dotted_hline(draw, left, right, y - 4)
        line_w = _text_width(row.line, line_f)
        draw.text((left, y), row.line, font=line_f, fill=BLACK, anchor="lt")
        # time, right-aligned; headsign fills the gap and is ellipsised to fit
        time_w = _text_width(row.label, time_f)
        draw.text((right, y + 1), row.label, font=time_f, fill=BLACK, anchor="rt")
        dest_x = left + int(line_w) + 12
        dest_max = right - time_w - 12 - dest_x
        dest = _ellipsize("→ " + row.headsign, dest_f, dest_max)
        draw.text((dest_x, y + 2), dest, font=dest_f, fill=BLACK, anchor="lt")
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
        _draw_unavailable(draw, CAL_BOX, _LABEL_CALENDAR)
        return

    _region_label(draw, CAL_BOX, _LABEL_CALENDAR)

    # Two day columns with a hairline between them.
    col_top = TOP_H + PAD + 26
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


def render(dashboard: Dashboard) -> Image.Image:
    """Draw the whole dashboard to an 800×480 1-bit image (DESIGN §2.1). Pure of
    clock and network; deterministic, so it is golden-tested (DESIGN §3.1)."""
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
