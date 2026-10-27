import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "splashy_badge"))

import struct
import tempfile

from physics import LABEL_SCALE, LABEL_MAX_WIDTH
from lettering import GLYPHS, THICKNESS, TextMesh, inside, load_font, meshes, rotation, signed_area
from physics import HALF_Z, BOTTOM, TOP, MONA, Pool
from render import Renderer, TankView


SAMPLE = ("@cassidoo", "devex", "she/her")

class FakeScreen:
    width, height = 320, 240

    def __init__(self):
        self.calls = []

    def shape(self, shape):
        self.calls.append((self.pen, shape))

    def shapes(self, entries):
        self.calls.extend((pen, shape) for shape, pen in entries)

    def rectangle(self, *args):
        pass

    def line(self, *args):
        pass

    def circle(self, *args):
        pass

    def text(self, *args):
        pass

    def measure_text(self, text):
        return len(text) * 5, 8


class FakeMatrix:
    """Real 2D affine maths, composed by post-multiplication like mat3."""

    def __init__(self, m=(1, 0, 0, 1, 0, 0)):
        self.m = m

    def _then(self, a, b, c, d, tx=0, ty=0):
        p, q, r, s, x, y = self.m
        return FakeMatrix((p * a + q * c, p * b + q * d, r * a + s * c, r * b + s * d,
                           p * tx + q * ty + x, r * tx + s * ty + y))

    def translate(self, x, y):
        return self._then(1, 0, 0, 1, x, y)

    def scale(self, x, y=None):
        return self._then(x, 0, 0, x if y is None else y)

    def rotate_radians(self, angle):
        return self._then(math.cos(angle), -math.sin(angle), math.sin(angle), math.cos(angle))

    def multiply(self, other):
        return self._then(*other.m)

    def apply(self, x, y):
        p, q, r, s, tx, ty = self.m
        return p * x + q * y + tx, r * x + s * y + ty


class FakeShape:
    def __init__(self, *contours):
        self.contours = contours
        self.transform = None


class GeometryTests(unittest.TestCase):
    def test_front_face_is_exactly_the_screen(self):
        view = TankView(320, 240)
        for offset in (-40, 0, 40):
            view.offset_x, view.offset_y = offset, -offset
            self.assertEqual(view.project(-1, TOP, HALF_Z), (0, 0))
            self.assertEqual(view.project(1, BOTTOM, HALF_Z), (319, 239))
            self.assertEqual(view.project(1, TOP, HALF_Z), (319, 0))
            self.assertEqual(view.project(-1, BOTTOM, HALF_Z), (0, 239))

    def test_back_face_is_inset_and_parallel(self):
        view = TankView(320, 240)
        view.offset_x, view.offset_y = 30, -20
        a = view.project(-1, TOP, -HALF_Z)
        b = view.project(1, TOP, -HALF_Z)
        c = view.project(1, BOTTOM, -HALF_Z)
        d = view.project(-1, BOTTOM, -HALF_Z)
        self.assertEqual(a[1], b[1])
        self.assertEqual(b[0], c[0])
        self.assertEqual(c[1], d[1])
        self.assertEqual(d[0], a[0])
        for x, y in (a, b, c, d):
            self.assertTrue(0 < x < 319)
            self.assertTrue(0 < y < 239)

    def test_relabel_rebuilds_only_changed_words(self):
        renderer = Renderer(FakeScreen(), SimpleNamespace(rgb=lambda *a: a),
                            SimpleNamespace(nope="nope"), SimpleNamespace(custom=FakeShape),
                            FakeMatrix)
        caps, meshes_before = list(renderer.caps), renderer.meshes
        widths = renderer.set_labels(["@cassidoo", "", "they/them"], [1, 2])
        self.assertIs(renderer.caps[0], caps[0])
        self.assertIs(renderer.meshes[0], meshes_before[0])
        self.assertIsNone(renderer.caps[1])
        self.assertEqual(widths[1], 0)
        self.assertIsNot(renderer.caps[2], caps[2])

    def test_affine_decomposition_matches_matrix(self):
        renderer = Renderer(FakeScreen(), SimpleNamespace(rgb=lambda *a: a),
                            SimpleNamespace(nope="nope"), SimpleNamespace(custom=FakeShape),
                            FakeMatrix)
        for matrix in ((1.5, 0.7, -0.3, 0.8), (0.4, -1.2, 0.9, -0.2), (-60, 4, 3, 45)):
            result = renderer.affine(*matrix, 100, 50)
            for point in ((1, 0), (0, 1), (2.5, -1.5)):
                expected = (100 + matrix[0] * point[0] + matrix[1] * point[1],
                            50 + matrix[2] * point[0] + matrix[3] * point[1])
                for got, want in zip(result.apply(*point), expected):
                    self.assertAlmostEqual(got, want, places=6)

    def test_af_font_outlines_extrude_with_outward_walls(self):
        def glyph(char, advance, paths):
            return struct.pack(">HbbBBBB", ord(char), 0, -50, 50, 50, advance, len(paths))
        square = [(0, 0), (40, 0), (40, -50), (0, -50)]
        hole = [(10, -10), (10, -40), (30, -40), (30, -10)]
        chars = {c: [square, hole] if c in "aeodh@" else [square] for c in "@cassidoevxh/r"}
        records, counts, points = b"", b"", b""
        for char, paths in chars.items():
            records += glyph(char, 48, paths)
            for path in paths:
                counts += bytes((len(path),))
                points += b"".join(struct.pack("bb", *p) for p in path)
        data = (b"af!?" + struct.pack(">HHHH", 0, len(chars), sum(len(p) for p in chars.values()),
                                      len(points) // 2) + records + counts + points)
        with tempfile.NamedTemporaryFile(suffix=".af") as handle:
            handle.write(data)
            handle.flush()
            font = load_font(handle.name, "@cassidoo")
            larger = meshes(SAMPLE, path=handle.name)
            long = meshes(("@a-very-long-handle", "devex", "x"), handle.name)
        mesh = TextMesh("@cassidoo", font)
        self.assertGreater(mesh.width, TextMesh("@cassidoo").width)
        self.assertGreater(larger[0].width, larger[1].width * 2)
        self.assertGreater(larger[0].height, 0.1)
        # Custom labels shrink to fit the tank; unknown characters become spaces.
        self.assertLessEqual(long[0].width, LABEL_MAX_WIDTH[0] + 1e-9)
        self.assertLess(long[0].scale, LABEL_SCALE[0])
        self.assertEqual(long[1].scale, LABEL_SCALE[1])
        for first, second, nx, ny in mesh.sides:
            ax, ay = mesh.vertices[first]
            bx, by = mesh.vertices[second]
            probe = ((ax + bx) / 2 + nx * 0.001, (ay + by) / 2 + ny * 0.001)
            covered = sum(inside(probe, [mesh.vertices[i] for i in contour])
                          for contour in mesh.contours)
            self.assertEqual(covered % 2, 0)  # Normals point out of solid letter.

    def test_glyph_counters_and_extrusion(self):
        self.assertGreater(THICKNESS, 0.02)
        for glyph in ("a", "d", "e", "o", "@"):
            outer, hole = GLYPHS[glyph]
            self.assertGreater(signed_area(outer), 0)
            self.assertLess(signed_area(hole), 0)
        for mesh in meshes(SAMPLE, path="missing.af"):
            self.assertGreater(len(mesh.contours), 1)
            self.assertEqual(len(mesh.sides), len(mesh.vertices))
            self.assertLess(mesh.height, 0.15 * max(LABEL_SCALE))
            for first, second, nx, ny in mesh.sides:
                self.assertNotEqual(first, second)
                self.assertAlmostEqual(nx * nx + ny * ny, 1)

    def test_rotation_is_rigid_and_changes_depth(self):
        a, b, c, d, e, f, g, h, j = rotation(0.4, 0.2, -0.1)
        for row in ((a, b, c), (d, e, f), (g, h, j)):
            self.assertAlmostEqual(sum(v * v for v in row), 1)
        self.assertGreater(abs(g), 0.1)
        self.assertGreater(abs(h), 0.1)
        self.assertTrue(all(math.isfinite(v) for v in (a, b, c, d, e, f, g, h, j)))

    def test_water_is_transparent_and_text_has_no_backplate(self):
        screen = FakeScreen()
        color = SimpleNamespace(rgb=lambda *args: args)
        font = SimpleNamespace(nope="nope")
        shape = SimpleNamespace(custom=FakeShape)
        renderer = Renderer(screen, color, font, shape, FakeMatrix)
        pool = Pool()
        renderer.draw(pool)
        water = [pen for pen, _ in screen.calls if len(pen) == 4]
        self.assertTrue(water)
        self.assertTrue(all(0 < pen[3] < 128 for pen in water))
        screen.calls.clear()
        pool.add(0)
        renderer.draw_object(pool.objects[0])
        cap_pen, cap_contours = screen.calls[-1]
        self.assertEqual(len(cap_contours.contours), len(renderer.meshes[0].contours))
        self.assertGreater(len(screen.calls), 2)  # Cap plus layered extrusion walls.
        self.assertTrue(all(shape is renderer.caps[0] for _, shape in screen.calls))
        self.assertNotEqual(screen.calls[0][0], cap_pen)
        screen.calls.clear()
        pool.add(MONA)
        renderer.draw(pool)  # Falls back to a 2D silhouette without pico3d.
        self.assertTrue(pool.objects)

    def test_merged_water_strips_tile_each_row(self):
        screen = FakeScreen()
        renderer = Renderer(screen, SimpleNamespace(rgb=lambda *a: a), SimpleNamespace(nope=0),
                            SimpleNamespace(custom=FakeShape), FakeMatrix)
        pool = Pool()
        pool.disturb(0.2, 0.1, 2.5)
        for _ in range(8):
            pool.step(1 / 30)
        renderer.draw(pool)
        self.assertGreater(len(set(renderer.cells[:32])), 2)

        def area(flat):
            pts = list(zip(flat[0::2], flat[1::2]))
            return abs(sum(a[0] * b[1] - b[0] * a[1]
                           for a, b in zip(pts, pts[1:] + pts[:1]))) / 2

        for z in range(4):
            screen.calls.clear()
            renderer.surface_row(z)
            strips = [c for _, shape in screen.calls for c in shape.contours]
            self.assertEqual(sum((len(c) // 2 - 2) // 2 for c in strips), 8)
            points = renderer.points
            outline = ([v for k in range(z * 9, z * 9 + 9) for v in points[k]]
                       + [v for k in range(z * 9 + 17, z * 9 + 8, -1) for v in points[k]])
            self.assertAlmostEqual(sum(area(c) for c in strips), area(outline), places=2)


if __name__ == "__main__":
    unittest.main()
