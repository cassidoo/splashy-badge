"""Generate Splashy Badge's icons from one vector water droplet.

splashy_badge/menu_icon.json  white menu glyph: contours in the menu's
                              -0.5..0.5 space, filled even-odd.
splashy_badge/icon.png        the same glyph as a 24x24 white-on-transparent PNG.
"""

import json
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "splashy_badge")

TIP = (0.0, -0.44)
CENTRE = (0.0, 0.12)
RADIUS = 0.31


def droplet():
    distance = CENTRE[1] - TIP[1]
    spread = math.acos(RADIUS / distance)
    start = -math.pi / 2 + spread
    end = 3 * math.pi / 2 - spread
    points = [TIP]
    steps = 28
    for i in range(steps + 1):
        a = start + (end - start) * i / steps
        points.append((CENTRE[0] + RADIUS * math.cos(a), CENTRE[1] + RADIUS * math.sin(a)))
    return points


def wave(y=0.15, amplitude=0.035, thickness=0.06, half_width=0.2, steps=14):
    def curve(x):
        return y + amplitude * math.sin(x / half_width * math.pi * 1.25)

    top = [(-half_width + 2 * half_width * i / steps, 0.0) for i in range(steps + 1)]
    top = [(x, curve(x) - thickness / 2) for x, _ in top]
    bottom = [(x, curve(x) + thickness) for x, _ in reversed(top)]
    return top + bottom


def shine(inner=0.17, outer=0.225, start=200, end=250, steps=6):
    angles = [math.radians(start + (end - start) * i / steps) for i in range(steps + 1)]
    arc = lambda r, seq: [(CENTRE[0] + r * math.cos(a), CENTRE[1] + r * math.sin(a)) for a in seq]
    return arc(outer, angles) + arc(inner, reversed(angles))


def contours():
    return [droplet(), wave(), shine()]


def flat(contour):
    return [round(v, 4) for point in contour for v in point]


def inside(x, y, shapes):
    hit = False
    for contour in shapes:
        j = len(contour) - 1
        for i, (xi, yi) in enumerate(contour):
            xj, yj = contour[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                hit = not hit
            j = i
    return hit


def png(size=24, samples=6, margin=0.04):
    shapes = contours()
    span = 1.0 - 2 * margin
    raw = b""
    for py in range(size):
        row = b"\x00"
        for px in range(size):
            hits = 0
            for sy in range(samples):
                for sx in range(samples):
                    x = ((px + (sx + 0.5) / samples) / size - 0.5) / span
                    y = ((py + (sy + 0.5) / samples) / size - 0.5) / span
                    hits += inside(x, y, shapes)
            row += bytes((255, 255, 255, round(255 * hits / samples**2)))
        raw += row

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def build():
    with open(os.path.join(APP, "menu_icon.json"), "w") as f:
        json.dump([flat(c) for c in contours()], f, separators=(",", ":"))
        f.write("\n")
    with open(os.path.join(APP, "icon.png"), "wb") as f:
        f.write(png())


if __name__ == "__main__":
    build()
