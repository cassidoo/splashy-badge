import math
import struct
import sys

from physics import LABELS, LABEL_SCALE, LABEL_MAX_WIDTH

if sys.implementation.name == "micropython":
    import micropython
else:
    class micropython:
        native = staticmethod(lambda function: function)

UNIT = 0.014
# Lato Black ships on the badge; x-height 58 font units becomes 0.136 world units.
FONT_PATH = "/system/assets/fonts/lato-900.af"
FONT_UNIT = 0.00235
THICKNESS = 0.062

# Fallback low-poly letter outlines; extra contours are counters, not backplates.
GLYPHS = {
    "@": (
        ((1, 0), (5, 0), (6, 1), (6, 6), (3, 6), (2, 5), (2, 2),
         (4, 2), (4, 5), (5, 5), (5, 1), (1, 1), (1, 7), (5, 7),
         (5, 8), (1, 8), (0, 7), (0, 1)),
        ((3, 3), (3, 5), (3.5, 5), (3.5, 3)),
    ),
    "a": (
        ((1, 0), (4, 0), (5, 1), (5, 7), (1, 7), (0, 6), (0, 4),
         (1, 3), (3.6, 3), (3.6, 1.4), (1, 1.4)),
        ((1.4, 4.4), (1.4, 5.6), (3.6, 5.6), (3.6, 4.4)),
    ),
    "c": (
        ((1, 0), (4, 0), (5, 1), (4, 2), (3.5, 1.4), (1.4, 1.4),
         (1.4, 5.6), (3.5, 5.6), (4, 5), (5, 6), (4, 7), (1, 7),
         (0, 6), (0, 1)),
    ),
    "d": (
        ((3.6, 0), (5, 0), (5, 7), (1, 7), (0, 6), (0, 3), (1, 2),
         (3.6, 2)),
        ((1.4, 3.4), (1.4, 5.6), (3.6, 5.6), (3.6, 3.4)),
    ),
    "e": (
        ((1, 0), (4, 0), (5, 1), (5, 4), (1.4, 4), (1.4, 5.6),
         (4.7, 5.6), (4.7, 7), (1, 7), (0, 6), (0, 1)),
        ((1.4, 1.4), (1.4, 2.7), (3.6, 2.7), (3.6, 1.4)),
    ),
    "h": (
        ((0, 0), (1.4, 0), (1.4, 2), (4, 2), (5, 3), (5, 7),
         (3.6, 7), (3.6, 3.4), (1.4, 3.4), (1.4, 7), (0, 7)),
    ),
    "i": (
        ((1.8, 0), (3.2, 0), (3.2, 1.4), (1.8, 1.4)),
        ((1.8, 2.4), (3.2, 2.4), (3.2, 7), (1.8, 7)),
    ),
    "o": (
        ((1, 0), (4, 0), (5, 1), (5, 6), (4, 7), (1, 7), (0, 6), (0, 1)),
        ((1.4, 1.4), (1.4, 5.6), (3.6, 5.6), (3.6, 1.4)),
    ),
    "r": (
        ((0, 0), (1.4, 0), (1.4, 1), (2.5, 0), (4.5, 0), (4.5, 1.5),
         (2.5, 1.5), (1.4, 2.6), (1.4, 7), (0, 7)),
    ),
    "s": (
        ((1, 0), (5, 0), (5, 1.4), (1.4, 1.4), (1.4, 2.8), (4, 2.8),
         (5, 3.8), (5, 6), (4, 7), (0, 7), (0, 5.6), (3.6, 5.6),
         (3.6, 4.2), (1, 4.2), (0, 3.2), (0, 1)),
    ),
    "v": (
        ((0, 0), (1.5, 0), (2.5, 5.2), (3.5, 0), (5, 0), (3.4, 7), (1.6, 7)),
    ),
    "x": (
        ((0, 0), (1.6, 0), (2.5, 2.3), (3.4, 0), (5, 0), (3.4, 3.5),
         (5, 7), (3.4, 7), (2.5, 4.7), (1.6, 7), (0, 7), (1.6, 3.5)),
    ),
    "/": (
        ((3.5, 0), (5, 0), (1.5, 7), (0, 7)),
    ),
}


def signed_area(points):
    return sum(a[0] * b[1] - b[0] * a[1]
               for a, b in zip(points, points[1:] + points[:1])) / 2


def inside(point, polygon):
    x, y = point
    result = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            result = not result
    return result


def simplify(points, tolerance):
    """Drop nearly collinear outline points; keeps glyph rebuilds cheap."""
    points = list(points)
    changed = True
    while changed and len(points) > 4:
        changed = False
        i = 0
        while i < len(points) and len(points) > 4:
            ax, ay = points[i - 1]
            bx, by = points[i]
            cx, cy = points[(i + 1) % len(points)]
            dx, dy = cx - ax, cy - ay
            length = math.sqrt(dx * dx + dy * dy) or 1
            if abs((bx - ax) * dy - (by - ay) * dx) / length < tolerance:
                del points[i]
                changed = True
            else:
                i += 1
    return points


def load_font(path, chars):
    """Read outlines from a Badgeware alright-fonts (.af) file."""
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:4] != b"af!?":
        raise ValueError("not an af font")
    flags, glyph_count, path_count, _ = struct.unpack_from(">HHHH", data, 4)
    offset = 12
    records = []
    for _ in range(glyph_count):
        records.append(struct.unpack_from(">HbbBBBB", data, offset))
        offset += 8
    wide = flags & 1
    counts = (struct.unpack_from(">%dH" % path_count, data, offset) if wide
              else data[offset:offset + path_count])
    offset += path_count * (2 if wide else 1)
    glyphs = {}
    path_index = 0
    for codepoint, _, _, _, _, advance, paths in records:
        char = chr(codepoint)
        outlines = []
        for _ in range(paths):
            count = counts[path_index]
            path_index += 1
            if char in chars:
                outlines.append([struct.unpack_from("bb", data, offset + 2 * k)
                                 for k in range(count)])
            offset += 2 * count
        if char in chars:
            glyphs[char] = (advance, outlines)
    del data
    return glyphs


class TextMesh:
    def __init__(self, label, font=None, scale=1.0, max_width=None):
        self.vertices = []
        self.contours = []
        self.sides = []
        if font is None:
            glyphs = [(7 if c == "@" else 6, [[(x, y - 7) for x, y in outline]
                                              for outline in GLYPHS.get(c.lower(), ())])
                      for c in label]
            unit, middle, tolerance = UNIT * scale, -3.5, 0
        else:
            blank = font.get(" ", (24, []))
            glyphs = [font.get(c, blank) for c in label]
            unit, middle, tolerance = FONT_UNIT * scale, -29, 0.9
        total = sum(advance for advance, _ in glyphs)
        if max_width and total * unit > max_width:
            scale *= max_width / (total * unit)
            unit = max_width / total
        self.scale = scale
        self.width = total * unit
        top = bottom = 0
        cursor = 0
        for advance, outlines in glyphs:
            contours = [[((cursor + x - total / 2) * unit, (middle - y) * unit)
                         for x, y in simplify(outline, tolerance)]
                        for outline in outlines if len(outline) > 2]
            for points in contours:
                # Outer walls run clockwise and counters anti-clockwise, so the
                # side normals below always point out of the solid letter.
                depth = sum(1 for other in contours
                            if other is not points and inside(points[0], other))
                if (signed_area(points) > 0) == (depth % 2 == 0):
                    points.reverse()
                top = max(top, max(p[1] for p in points))
                bottom = min(bottom, min(p[1] for p in points))
                indices = tuple(range(len(self.vertices), len(self.vertices) + len(points)))
                self.vertices.extend(points)
                self.contours.append(indices)
                for a, b in zip(indices, indices[1:] + indices[:1]):
                    ax, ay = self.vertices[a]
                    bx, by = self.vertices[b]
                    dx, dy = bx - ax, by - ay
                    length = math.sqrt(dx * dx + dy * dy) or 1
                    self.sides.append((a, b, -dy / length, dx / length))
            cursor += advance
        self.height = 2 * max(top, -bottom)
        self.contours = tuple(self.contours)


@micropython.native
def rotation(yaw, pitch, roll):
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    return (cr * cy - sr * sp * sy, -sr * cp, cr * sy + sr * sp * cy,
            sr * cy + cr * sp * sy, cr * cp, sr * sy - cr * sp * cy,
            -cp * sy, sp, cp * cy)


def meshes(labels=LABELS, path=FONT_PATH, kinds=None):
    """Build word meshes; with kinds, only those are built and the rest are None."""
    kinds = range(len(labels)) if kinds is None else kinds
    try:
        font = load_font(path, " " + "".join(labels[kind] for kind in kinds))
    except (OSError, ValueError):
        font = None
    return tuple(TextMesh(label, font, LABEL_SCALE[kind], LABEL_MAX_WIDTH[kind])
                 if kind in kinds else None for kind, label in enumerate(labels))
