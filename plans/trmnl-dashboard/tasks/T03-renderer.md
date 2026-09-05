# T03 — Pillow renderer: view-model → 800×480 1-bit BMP

**Phase:** 1 · **Depends on:** T01, T02 · **Weight:** heavy

## Goal

Draw the dashboard. Take a `Dashboard` view-model and produce the exact 800×480 1-bit image the
device displays, laid out like the approved mock: weather top-left, buses top-right, calendar
across the bottom, hairline rules between regions, hatched fills where the mock shows shading,
Polish labels, and the data-source attribution. Because Pillow is deterministic, the same
view-model always yields the same pixels, so the layout is locked down with golden-image tests
rather than a person's eye.

## Design sections this implements

DESIGN.md §2.1 (the screen, 1-bit truth, dithering not grey), §2.2–§2.4 (region contents),
§2.6 (an unavailable region draws "niedostępne"), §3.1 (renderer is deterministic, golden-tested).

## Files

- `trmnl/render/screen.py` — `render(dashboard) -> PIL.Image`, `save_bmp(image, path)`, and
  `render_startup() -> PIL.Image` for the bundled cold-start placeholder.
- Bundled TrueType font files (an open-licensed family; the mock used IBM Plex).
- A committed startup placeholder BMP (the output of `render_startup`), served by the server on
  cold start (DESIGN §2.6, §3.5).
- `tests/render/golden/*.png` — reference images.
- `tests/render/test_screen.py`.

## Interface

```python
def render(dashboard: Dashboard) -> Image.Image:    # mode "1", size (800, 480)
def save_bmp(image: Image.Image, path: str) -> None # writes a 1-bit BMP3, via temp+rename
def render_startup() -> Image.Image:                # the "Uruchamianie…" placeholder, mode "1"
```

Fixed layout constants (region boxes, margins, font sizes) live in this module. Shading is a
1-bit dither pattern (e.g. a diagonal hatch), never a grey fill, matching the panel's physical
capability. An unavailable region draws its label plus "niedostępne" centred, so a source
outage is legible on the wall.

An available region that is genuinely empty draws a short line, not a blank: a calendar day
with no events draws "Brak wydarzeń", an empty bus list draws "brak odjazdów" (DESIGN §2.4,
§2.6, §7). This is a different state from "niedostępne" and must be visually distinguishable.

`render_startup` draws the bundled cold-start placeholder ("Uruchamianie…" centred), which the
server serves before the first real image exists (DESIGN §2.6). The mock's top strip (clock,
date, "updated") is intentionally not drawn (DESIGN §2.1, §7).

`save_bmp` writes to a temp path and renames over the target so a concurrent fetch never sees a
partial file (DESIGN §2.6, §3.5).

## Tests

- [ ] `render` output is mode "1" and exactly 800×480 for a fully-populated view-model.
- [ ] Golden compare: a fixed sample `Dashboard` renders pixel-identical to a committed PNG.
- [ ] Golden compare: weather region unavailable → the "niedostępne" variant matches its golden.
- [ ] Golden compare: empty bus list renders "brak odjazdów" (not a blank, not "niedostępne")
      and matches its golden.
- [ ] Golden compare: a calendar day with no events renders "Brak wydarzeń" and matches its
      golden; empty differs visibly from "niedostępne".
- [ ] Golden compare: `render_startup` matches its committed placeholder golden and is 1-bit 800×480.
- [ ] Long headsign / many events do not overflow their region (clipped or ellipsised, tested).
- [ ] `save_bmp` produces a file that re-opens as 1-bit 800×480, and writes via temp+rename
      (target never exists in a partial state — assert the temp name is used).

## Done when

- [ ] A representative `Dashboard` renders to a 1-bit 800×480 BMP that visually matches the mock's
      layout, checked once by eye and then locked by golden tests.
- [ ] Golden tests cover the populated, one-region-unavailable, empty-bus ("brak odjazdów"),
      empty-calendar-day ("Brak wydarzeń"), and startup-placeholder cases.
- [ ] The committed startup placeholder BMP exists and re-opens as 1-bit 800×480.
- [ ] The suite is green and quiet; regenerating goldens is a documented one-liner for when the
      layout genuinely changes.

## Needs a person

One look, not a loop. After the golden tests pass, the owner may want to eyeball the rendered
BMP once to confirm it reads well as a real 1-bit image (dither, contrast, legibility) — the
tests prove it is stable, not that it is pleasant. Hand over the generated file for a glance;
this is optional and does not block the task if the layout matches the mock.
