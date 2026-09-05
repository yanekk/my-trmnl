"""Generate the throwaway 800x480 1-bit BMP the spike serves.

Run once to (re)produce spike.bmp; the committed spike.bmp is what the server
actually hands the device, so the server itself needs no Pillow at runtime.
The picture is deliberately unmistakable — corner ticks, a frame and big text —
so that when it appears on the panel we know it is *our* image and not a stock
TRMNL screen, and that the whole 800x480 area is being drawn the right way up.

Throwaway: this whole spike/ directory is deleted once T00's findings are in.
"""

from PIL import Image, ImageDraw, ImageFont

W, H = 800, 480

# mode "1" is 1 bit per pixel. In Pillow's "1" images 0 is black, 255 is white.
img = Image.new("1", (W, H), 1)  # white background
d = ImageDraw.Draw(img)


def font(size):
    # Fall back to the default bitmap font if no TrueType face is found; the
    # spike only needs legible-enough text, not typography.
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def centered(text, cy, f):
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.text(((W - (r - l)) / 2 - l, cy - (b - t) / 2 - t), text, font=f, fill=0)


# A 3px frame just inside the edge proves the panel draws to its corners.
for i in range(3):
    d.rectangle([i, i, W - 1 - i, H - 1 - i], outline=0)

# Corner ticks so orientation and full extent are obvious at a glance.
tick = 40
for cx, cy in ((0, 0), (W, 0), (0, H), (W, H)):
    x = cx if cx == 0 else cx - tick
    y = cy if cy == 0 else cy - tick
    d.rectangle([x + 8, y + 8, x + tick, y + tick], fill=0)

centered("TRMNL SPIKE", H // 2 - 70, font(96))
centered("IT DISPLAYS OUR IMAGE", H // 2 + 20, font(40))
centered("T00 - server we control -> panel", H // 2 + 80, font(28))

# A hatch band to confirm fine 1-bit detail survives the panel (no smearing).
for x in range(60, W - 60, 6):
    d.line([(x, H - 60), (x, H - 40)], fill=0)

# BMP3 = classic 40-byte BITMAPINFOHEADER, which Pillow writes for BMP by
# default. 1-bit mode gives a 1bpp BMP, exactly the device contract.
img.save("spike/spike.bmp", format="BMP")
print("wrote spike/spike.bmp", img.size, img.mode)
