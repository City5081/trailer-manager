#!/usr/bin/env python3
"""Render app/static/logo.svg to PNG.

    python3 tools/render_logo.py [size ...]

Kept as a script so the PNG can be regenerated from the same geometry as the
SVG instead of being a hand-edited copy that slowly drifts apart from it.
Needs Pillow: pip install pillow
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"

# Geometry of logo.svg, in its 64x64 viewBox.
TOP = (0x5A, 0xA8, 0xFF)          # gradient start  #5aa8ff
BOTTOM = (0x2F, 0x7F, 0xE0)       # gradient end    #2f7fe0
HOLE = (0x12, 0x15, 0x1A)         # sprocket holes  #12151a at 55%
BODY = (2, 6, 60, 52, 10)         # x, y, w, h, radius
HOLES = [(7, 13), (7, 29), (7, 45), (51, 13), (51, 29), (51, 45)]
HOLE_SIZE, HOLE_RADIUS = 6, 2
PLAY = [(26, 21.5), (44, 32), (26, 42.5)]

SUPERSAMPLE = 4                   # draw large, shrink down: cheap antialiasing


def render(size):
    scale = size * SUPERSAMPLE / 64
    canvas = size * SUPERSAMPLE

    def s(value):
        return value * scale

    # Rounded body, filled with a vertical gradient.
    gradient = Image.new("RGB", (1, canvas))
    for y in range(canvas):
        t = y / max(1, canvas - 1)
        gradient.putpixel((0, y), tuple(
            round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)))
    gradient = gradient.resize((canvas, canvas))

    mask = Image.new("L", (canvas, canvas), 0)
    x, y, w, h, r = BODY
    ImageDraw.Draw(mask).rounded_rectangle(
        [s(x), s(y), s(x + w), s(y + h)], radius=s(r), fill=255)

    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    image.paste(gradient, (0, 0), mask)

    draw = ImageDraw.Draw(image, "RGBA")
    for hx, hy in HOLES:
        draw.rounded_rectangle(
            [s(hx), s(hy), s(hx + HOLE_SIZE), s(hy + HOLE_SIZE)],
            radius=s(HOLE_RADIUS), fill=HOLE + (140,))       # .55 opacity
    draw.polygon([(s(px), s(py)) for px, py in PLAY], fill=(255, 255, 255, 255))

    return image.resize((size, size), Image.LANCZOS)


def main(sizes):
    for size in sizes:
        name = "logo.png" if size == 512 else "logo-{}.png".format(size)
        path = STATIC / name
        render(size).save(path)
        print("{}  {}x{}  {:.1f} kB".format(name, size, size,
                                            path.stat().st_size / 1024))


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [512, 192, 64])
