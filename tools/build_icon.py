"""Generate splashy_badge/icon.png: a 24x24 RGBA water droplet."""
import math
import struct
import zlib
from pathlib import Path

SIZE = 24
SAMPLES = 6
TIP = (12.0, 1.2)
CENTRE = (12.0, 15.0)
RADIUS = 7.6
OUTLINE = 1.15
LIGHT = (150, 226, 255)
DEEP = (18, 92, 196)
WAVE_LIGHT = (92, 196, 250)
WAVE_DEEP = (10, 58, 150)
RIM = (6, 30, 78)
SHINE = (255, 255, 255)


def edge_distance(x, y):
    """Signed distance (approximate) inside the teardrop; positive is inside."""
    cx, cy = CENTRE
    tx, ty = TIP
    inside = RADIUS - math.hypot(x - cx, y - cy)
    dx, dy = cx - tx, cy - ty
    d = math.hypot(dx, dy)
    half = math.asin(RADIUS / d)
    px, py = x - tx, y - ty
    along = (px * dx + py * dy) / d
    if 0 < along < d * math.cos(half) ** 2:
        across = abs(px * dy - py * dx) / d
        inside = max(inside, along * math.sin(half) - across * math.cos(half))
    return inside


def wave_y(x):
    return 15.6 + 1.1 * math.sin((x - 4.0) * 0.75)


def mix(a, b, t):
    t = min(1.0, max(0.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def shade(x, y):
    inside = edge_distance(x, y)
    if inside < 0:
        return None
    if inside < OUTLINE:
        return RIM
    body = mix(LIGHT, DEEP, (y - 2) / 20 + (x - 6) / 40)
    if y > wave_y(x):
        body = mix(WAVE_LIGHT, WAVE_DEEP, (y - wave_y(x)) / 6.5)
        if y - wave_y(x) < 0.9:
            body = mix(body, SHINE, 0.75)
    # curved highlight on the upper left of the bulb
    hx, hy = x - 9.3, y - 12.2
    arc = math.hypot(hx, hy)
    if 2.1 < arc < 3.5 and hx < 0.6 and hy < 1.2:
        body = mix(body, SHINE, 0.95)
    if math.hypot(x - 10.4, y - 6.6) < 0.95:
        body = mix(body, SHINE, 0.9)
    return body


def build():
    rows = []
    for py in range(SIZE):
        row = bytearray()
        for px in range(SIZE):
            total = [0.0, 0.0, 0.0]
            hits = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    c = shade(px + (sx + 0.5) / SAMPLES, py + (sy + 0.5) / SAMPLES)
                    if c is not None:
                        hits += 1
                        for i in range(3):
                            total[i] += c[i]
            if hits:
                row += bytes(round(total[i] / hits) for i in range(3))
                row.append(round(255 * hits / SAMPLES ** 2))
            else:
                row += b"\0\0\0\0"
        rows.append(b"\0" + bytes(row))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
    png += chunk(b"IEND", b"")
    (Path(__file__).resolve().parents[1] / "splashy_badge" / "icon.png").write_bytes(png)


if __name__ == "__main__":
    build()
