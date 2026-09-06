# T11 — Moon icons at night (day/night-aware weather icons)

**Phase:** 4 (enhancement, post-deploy) · **Depends on:** T02, T03, T05 · **Weight:** medium-light

Owner-added amendment (2026-09-06), agreed after the dashboard was running. Requirements settled
with the owner this session; the three decisions are recorded below and in DESIGN §2.2.

## Goal

The weather icons never look at the time of day, so a clear night draws a sun. Make the clear and
the mostly/partly-clear icons day/night aware: at night draw a crescent moon for a clear sky and a
moon-behind-a-cloud for mostly/partly clear. Every other icon (cloud, fog, drizzle, rain, snow,
storm) is unchanged — those read the same at night, and adding night variants is glyph work for no
visible gain.

The only icons on screen are the hourly strip's: the big current-conditions icon was removed on
2026-09-06 (DESIGN §2.2), so the strip is the visible change and is exactly where the sun-after-
sunset shows. The core's icon selection is made day/night aware uniformly, which also fixes the
(currently undrawn) current-conditions icon key so the view-model stays correct if a big icon is
ever restored.

## The three decisions (owner, 2026-09-06)

1. **Both current conditions and the hourly strip.** The icon selection is day/night aware
   everywhere it is computed. Only the strip is drawn today, so that is the visible effect.
2. **Partly-cloudy at night → moon-behind-cloud.** WMO codes 1 and 2 ("mostly sunny" / "partly
   cloudy"), which map to `part-cloud` by day, map to a moon-behind-cloud by night.
3. **Only `sun` and `part-cloud` change.** Every other icon key is identical day and night.

## Design sections this implements

DESIGN §2.2 (the weather icon is now chosen from the WMO code and the hour's day/night flag; a
clear or mostly-clear sky shows a moon after dark). No change to §2.6 — a missing day/night flag
falls back to day (the sun), never to a failure.

## Data source

Open-Meteo, already fetched (DESIGN §2.2). It carries a per-hour and current `is_day` flag (1 by
day, 0 at night) that the request does not yet ask for. Verified on this machine 2026-09-06: a
request adding `is_day` to `current` and `hourly` returns it for both, as `0`/`1` integers, with
the value flipping across sunrise in the hourly array (see FINDINGS). A null or absent `is_day`
is treated as day (draw the sun), the safe fallback — the same spirit as a null weather code
falling back to the neutral cloud (DESIGN §2.6).

## Files

- `trmnl/adapters/weather.py` — add `is_day` to the `_CURRENT` and `_HOURLY` request variables;
  parse it into `WeatherData.is_day` and each `HourPoint.is_day` as a bool (`int(x) == 1`), with a
  null or absent value → `True` (day), never a `Failure`.
- `trmnl/core/model.py` — `HourPoint` gains `is_day: bool = True`; `WeatherData` gains
  `is_day: bool = True`. The default is day, which is today's behaviour and the safe fallback, so
  existing construction that omits it is unaffected.
- `trmnl/core/assemble.py` — `_icon_for(code, is_day=True)` returns the night variant when
  `is_day` is False: `sun` → `moon`, `part-cloud` → `part-cloud-night`; every other key
  unchanged. `_weather_view` passes `w.is_day`; `_weather_hours` passes each `pt.is_day`.
- `trmnl/render/screen.py` — `_icon_moon` (a crescent, line-art in the same primitive style as
  `_icon_sun`) and `_icon_part_cloud_night` (moon behind a cloud, mirroring `_icon_part_cloud`);
  register the keys `moon` and `part-cloud-night` in `_ICONS`. The renderer stays day/night
  unaware — it draws whatever resolved icon key the core hands it (the boundary is DESIGN §3.1).
- `tests/adapters/test_weather.py`, `tests/core/test_assemble.py`, `tests/render/test_screen.py`,
  and the affected `tests/render/golden/` images (regenerated).

## Interface

```python
# core/assemble.py — the day/night decision lives here, on the pure side.
def _icon_for(code: int, is_day: bool = True) -> str

# core/model.py
@dataclass(frozen=True)
class HourPoint:
    time: datetime
    temp_c: int
    rain_pct: int
    code: int
    is_day: bool = True

@dataclass(frozen=True)
class WeatherData:
    temp_c: int
    condition_code: int
    feels_like_c: int
    wind_kmh: int
    is_day: bool = True
    hourly: list[HourPoint] = field(default_factory=list)
```

- The night override applies only to the two keys the owner chose (`sun`, `part-cloud`); the
  `_WEATHER` code→(word, key) table is unchanged, and the override is a small day→night key map
  read after it. The condition **word** ("Bezchmurnie" etc.) is not changed by night — only the
  icon glyph.
- The renderer holds no clock and no day/night flag: the resolved key already encodes it. Adding
  the two glyphs is the whole renderer change.
- `is_day` defaults to `True` (day) so the cold path and any construction that omits it keep the
  current sun-by-default behaviour; the adapter always sets it explicitly from the feed.

## Tests

- [ ] `fetch_weather` parses `is_day` into `WeatherData.is_day` and every `HourPoint.is_day` as a
      bool (1 → True, 0 → False), from a fixture that carries both day and night hours.
- [ ] A null or absent `is_day` (current or an hour) → `True` (day), and never a `Failure`.
- [ ] `_icon_for(0, is_day=False) == "moon"` and `_icon_for(0, is_day=True) == "sun"`;
      `_icon_for(1, is_day=False) == "part-cloud-night"` and `_icon_for(2, is_day=False) ==
      "part-cloud-night"`, while by day both are `"part-cloud"`.
- [ ] A non-clear code is identical day and night: e.g. `_icon_for(61, is_day=False) ==
      _icon_for(61, is_day=True) == "rain"`; an unknown code still falls back to `"cloud"`
      regardless of `is_day`.
- [ ] `assemble`: an hourly strip built from night hours yields `moon`/`part-cloud-night` icons
      where the code is clear/mostly-clear, and day hours yield `sun`/`part-cloud` — proving the
      per-hour flag drives the strip, not one global value.
- [ ] Renderer: the `moon` and `part-cloud-night` keys draw their glyphs (a night golden that
      includes a clear-night and a partly-cloudy-night hour); the day goldens are unchanged except
      where a strip hour is deliberately night. Goldens regenerated.
- [ ] No test hits the network (the adapter is stubbed as in `test_weather.py`).

## Done when

- [ ] After sunset, a clear hour in the strip shows a moon and a mostly/partly-clear hour shows a
      moon-behind-cloud; by day the same hours show the sun and sun-behind-cloud — all from
      fixtures and goldens.
- [ ] Every other weather icon is byte-for-byte identical day and night; a missing day/night flag
      draws the sun, never a blank or a failure.
- [ ] The suite is green and quiet on the Mac; and on the Pi 3.9 (`--ignore=tests/render`),
      because this parses external data (see CLAUDE.md deploy note).

## Needs a person

The mapping and the glyphs are fully testable here. What only the device shows: that the moon
reads clearly as a moon on the real e-ink at the strip's small icon size, and that after sunset
the live strip actually shows moons. Fold this into the next on-device pass — look at the strip
after dark — and record it dated in FINDINGS.
