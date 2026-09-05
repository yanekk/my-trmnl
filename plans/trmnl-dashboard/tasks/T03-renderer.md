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

- `trmnl/render/screen.py` — `render(dashboard) -> PIL.Image` and `save_bmp(image, path)`.
- Bundled TrueType font files (an open-licensed family; the mock used IBM Plex).
- `tests/render/golden/*.png` — reference images.
- `tests/render/test_screen.py`.

## Interface

```python
def render(dashboard: Dashboard) -> Image.Image:   # mode "1", size (800, 480)
def save_bmp(image: Image.Image, path: str) -> None # writes a 1-bit BMP3, via temp+rename
```

Fixed layout constants (region boxes, margins, font sizes) live in this module. Shading is a
1-bit dither pattern (e.g. a diagonal hatch), never a grey fill, matching the panel's physical
capability. An unavailable region draws its label plus "niedostępne" centred, so a source
outage is legible on the wall.

`save_bmp` writes to a temp path and renames over the target so a concurrent fetch never sees a
partial file (DESIGN §2.6, §3.5).

## Tests

- [ ] `render` output is mode "1" and exactly 800×480 for a fully-populated view-model.
- [ ] Golden compare: a fixed sample `Dashboard` renders pixel-identical to a committed PNG.
- [ ] Golden compare: weather region unavailable → the "niedostępne" variant matches its golden.
- [ ] Golden compare: empty bus list renders (no rows) without error and matches its golden.
- [ ] Long headsign / many events do not overflow their region (clipped or ellipsised, tested).
- [ ] `save_bmp` produces a file that re-opens as 1-bit 800×480, and writes via temp+rename
      (target never exists in a partial state — assert the temp name is used).

## Done when

- [ ] A representative `Dashboard` renders to a 1-bit 800×480 BMP that visually matches the mock's
      layout, checked once by eye and then locked by golden tests.
- [ ] Golden tests cover the populated, one-region-unavailable, and empty-bus cases.
- [ ] The suite is green and quiet; regenerating goldens is a documented one-liner for when the
      layout genuinely changes.

## Needs a person

One look, not a loop. After the golden tests pass, the owner may want to eyeball the rendered
BMP once to confirm it reads well as a real 1-bit image (dither, contrast, legibility) — the
tests prove it is stable, not that it is pleasant. Hand over the generated file for a glance;
this is optional and does not block the task if the layout matches the mock.
