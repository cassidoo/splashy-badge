import math
from array import array

from physics import NX, NZ, HALF_X, HALF_Z, BOTTOM, TOP, PALETTE, MONA, LABELS
from lettering import meshes, rotation, THICKNESS, micropython
from shading import shade, SINES, TURN


EYE_HEIGHT = 0.34


class TankView:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.half_w, self.half_h = (width - 1) / 2, (height - 1) / 2
        self.offset_x = self.offset_y = 0.0

    @micropython.native
    def project(self, x, y, z):
        depth = (HALF_Z - z) / (2 * HALF_Z)
        factor = 1 / (1 + depth * 0.65)
        return (self.half_w + self.half_w * x * factor
                + self.offset_x * (1 - factor),
                self.half_h - self.half_h * y / TOP * factor
                + self.offset_y * (1 - factor))


class Renderer(TankView):
    def __init__(self, screen, color, font, shape, matrix, mona=None):
        super().__init__(screen.width, screen.height)
        self.screen, self.shape = screen, shape
        self.matrix = matrix
        self.mona = mona
        self.small_font = font.nope
        self.white = color.rgb(214, 248, 255)
        self.muted = color.rgb(112, 162, 179)
        self.body = color.rgb(8, 104, 146, 92)
        self.side_water = color.rgb(12, 81, 112, 48)
        self.ripple = color.rgb(190, 248, 255, 190)
        self.meniscus = color.rgb(150, 236, 248, 110)
        self.foam = color.rgb(225, 252, 255, 235)
        self.spray = color.rgb(160, 232, 245, 120)
        self.caustic = color.rgb(42, 175, 188, 45)
        self.glint = color.rgb(255, 255, 255, 230)
        self.rings = tuple(color.rgb(215, 250, 255, 30 + i * 22) for i in range(8))
        self.mona_fallback = (color.rgb(24, 14, 39), color.rgb(255, 175, 198))
        self.edges = tuple(color.rgb(*rgb) for rgb in PALETTE)
        self.dim_edges = tuple(color.rgb(*(int(v * 0.48) for v in rgb)) for rgb in PALETTE)
        self.background = tuple(color.rgb(5, 12 + i, 23 + i * 2) for i in range(8))
        # Rows run back to front: grazing back rows reflect more sky (Fresnel).
        self.water_colors = tuple(
            tuple(color.rgb(min(255, 22 + i * 7 + row * 26), min(255, 120 + i * 7 + row * 16),
                            min(255, 160 + i * 5 + row * 12), 34 + i * 4 + row * 20)
                  for i in range(16))
            for row in range(3, -1, -1))
        self.specular = tuple(color.rgb(200, 245, 255, 30 + i * 22) for i in range(10))
        self.text_colors = tuple(
            tuple(color.rgb(*(int(channel * (0.30 + shade * 0.0875)) for channel in rgb))
                  for shade in range(9))
            for rgb in ((255, 173, 218), (255, 220, 137), (180, 191, 255)))
        self.set_labels(LABELS)
        self.points = [(0, 0)] * (NX * NZ)
        # Wave heights in thousandths and per-cell shading bytes for the kernel.
        self.heights = array("i", bytes(4 * NX * NZ))
        self.cells = bytearray(96)
        self.last_level = None
        self.level_until = 0.0

    def line(self, a, b, pen):
        self.screen.pen = pen
        self.screen.line(a[0], a[1], b[0], b[1])

    def polygon(self, points, pen):
        self.screen.pen = pen
        self.screen.shape(self.shape.custom(array("f", (v for p in points for v in p))))

    def set_labels(self, labels, kinds=None):
        """Build each word's extruded outline once; returns the word widths.
        With kinds, only those words are rebuilt."""
        built = meshes(labels, kinds=kinds)
        if kinds is not None:
            built = tuple(new or old for new, old in zip(built, self.meshes))
        self.meshes = built
        self.caps = [] if kinds is None else self.caps
        for kind, mesh in enumerate(self.meshes):
            if kinds is not None and kind not in kinds:
                continue
            contours = []
            for indices in mesh.contours:
                points = array("f")
                for index in indices:
                    points.extend(mesh.vertices[index])
                contours.append(points)
            cap = self.shape.custom(*contours) if contours else None
            if kinds is None:
                self.caps.append(cap)
            else:
                self.caps[kind] = cap
        return [mesh.width for mesh in self.meshes]

    def text(self, value, x, y, pen, centered=False):
        self.screen.pen = pen
        self.screen.font = self.small_font
        if centered:
            x -= self.screen.measure_text(value)[0] / 2
        self.screen.text(value, x, y)

    def draw_mona(self, obj):
        if self.mona is not None:
            x, y = self.project(obj[0], obj[1], obj[2])
            self.mona.draw(obj, x, y)
            return
        # Without pico3d (tests, emulators) Mona is a simple silhouette.
        x, y, z = obj[:3]
        cx, cy = self.project(x, y + 0.09, z)
        factor = 1 / (1 + (HALF_Z - z) / (2 * HALF_Z) * 0.65)
        self.screen.pen = self.mona_fallback[0]
        self.screen.circle(cx, cy, 16 * factor)
        self.screen.pen = self.mona_fallback[1]
        self.screen.circle(cx, cy + 3 * factor, 10 * factor)

    def affine(self, p, q, r, s, tx, ty):
        """Build an arbitrary 2D affine mat3 from rotate-scale-rotate (SVD)."""
        e, f, g, h = (p + s) / 2, (p - s) / 2, (r + q) / 2, (r - q) / 2
        major, minor = math.sqrt(e * e + h * h), math.sqrt(f * f + g * g)
        a1, a2 = math.atan2(g, f), math.atan2(h, e)
        return (self.matrix().translate(tx, ty).rotate_radians((a2 + a1) / 2)
                .scale(major + minor, major - minor).rotate_radians((a2 - a1) / 2))

    @micropython.native
    def draw_object(self, obj):
        kind = obj[6]
        if kind == MONA:
            self.draw_mona(obj)
            return
        geometry = self.caps[kind]
        if geometry is None:
            return
        x, y, z = obj[:3]
        a, b, c, d, e, f, g, h, j = rotation(obj[8], obj[9], obj[10])
        cx, cy = self.project(x, y, z)
        factor = 1 / (1 + (HALF_Z - z) / (2 * HALF_Z) * 0.65)
        sx, sy = self.half_w * factor, -self.half_h / TOP * factor
        # Small words are drawn as an orthographic slice through the true
        # perspective centre, so their cached outline never needs rebuilding.
        p, q, r, s = sx * a, sx * b, sy * d, sy * e
        half = THICKNESS * self.meshes[kind].scale / 2
        fx, fy = self.project(x + c * half, y + f * half, z + j * half)
        dx, dy = fx - cx, fy - cy
        toward = j * (2.28 - z) - c * x - f * y > 0
        if not toward:
            dx, dy = -dx, -dy
        # The big name fills far more pixels per layer, so it gets fewer layers.
        layers = max(2, min(4 if kind == 0 else 5, int(math.sqrt(dx * dx + dy * dy) * 1.6 + 1.5)))
        palette = self.text_colors[kind]
        side = max(1, min(4, int(2.5 - c * 1.2 + f * 1.4)))
        screen = self.screen
        matrix = self.matrix
        base = self.affine(p, q, r, s, 0, 0)
        # Paint from the far cap to the near cap; the stack forms the walls.
        for layer in range(layers + 1):
            t = layer / layers * 2 - 1
            geometry.transform = matrix().translate(cx + dx * t, cy + dy * t).multiply(base)
            if layer == layers:
                light = (c * -0.35 + f * 0.7 + j * 0.55) if toward else 0.2
                screen.pen = palette[max(5, min(8, int(6.5 + light * 2)))]
            else:
                screen.pen = palette[max(0, side - 1 + layer * 2 // layers)]
            screen.shape(geometry)

    @micropython.native
    def draw_ring(self, pool, ring):
        x, z, age, size = ring
        fade = 1 - age / 0.9
        radius = (0.05 + age * 0.55) * size
        y = (pool.surface(x, z) + 0.006) / TOP
        half_w, half_h = self.half_w, self.half_h
        ox, oy = self.offset_x, self.offset_y
        screen = self.screen
        screen.pen = self.rings[max(0, min(7, int(fade * 8 * size + 0.5)))]
        last = None
        for n in range(11):
            angle = n * 0.6283
            px = x + math.cos(angle) * radius
            pz = z + math.sin(angle) * radius * 0.8
            if abs(px) < HALF_X and abs(pz) < HALF_Z:
                f = 1 / (1 + (HALF_Z - pz) / (2 * HALF_Z) * 0.65)
                point = (half_w + half_w * px * f + ox * (1 - f),
                         half_h - half_h * y * f + oy * (1 - f))
                if last is not None:
                    screen.line(last[0], last[1], point[0], point[1])
                last = point
            else:
                last = None

    @micropython.native
    def floor(self, time):
        """Faint moving light patterns on the floor stay visible through water."""
        screen = self.screen
        screen.pen = self.caustic
        half_w, half_h = self.half_w, self.half_h
        ox, oy = self.offset_x, self.offset_y
        y = BOTTOM / TOP
        for row in range(3):
            z = -HALF_Z + row * HALF_Z
            f = 1 / (1 + (HALF_Z - z) / (2 * HALF_Z) * 0.65)
            g = 1 / (1 + (HALF_Z - z - 0.03) / (2 * HALF_Z) * 0.65)
            sy = half_h - half_h * y * f + oy * (1 - f)
            for col in range(5):
                x = -0.9 + col * 0.42 + row * 0.12
                bend = math.sin(col * 1.9 + row * 2.6 + time * 0.8) * 0.06
                ex = x + 0.2
                screen.line(half_w + half_w * x * f + ox * (1 - f), sy,
                            half_w + half_w * ex * g + ox * (1 - g),
                            half_h - half_h * y * g + oy * (1 - g) + bend * half_h)

    @micropython.native
    def surface_points(self, pool):
        half_w, half_h = self.half_w, self.half_h
        ox, oy = self.offset_x, self.offset_y
        wave, points, heights = pool.wave, self.points, self.heights
        low, high = BOTTOM + 0.025, TOP - 0.06
        for z in range(NZ):
            wz = -HALF_Z + z * (2 * HALF_Z) / (NZ - 1)
            f = 1 / (1 + (HALF_Z - wz) / (2 * HALF_Z) * 0.65)
            base = pool.level + pool.tilt_z * wz * 0.25
            for x in range(NX):
                wx = -HALF_X + x * (2 * HALF_X) / (NX - 1)
                w = wave[z * NX + x]
                heights[z * NX + x] = int(w * 1000)
                height = base + pool.tilt_x * wx * 0.22 + w
                height = low if height < low else high if height > high else height
                points[z * NX + x] = (half_w + half_w * wx * f + ox * (1 - f),
                                      half_h - half_h * height / TOP * f + oy * (1 - f))

    @micropython.native
    def surface_row(self, z):
        screen, points, cells = self.screen, self.points, self.cells
        colors = self.water_colors[z]
        # Neighbouring quads of one shade merge into a strip, and strips of one
        # shade are filled together as a single multi-contour shape.
        groups = {}
        row = z * NX
        start = 0
        for x in range(1, NX):
            shade = cells[z * 8 + start]
            if x < NX - 1 and cells[z * 8 + x] == shade:
                continue
            strip = array("f")
            for k in range(row + start, row + x + 1):
                strip.append(points[k][0])
                strip.append(points[k][1])
            for k in range(row + NX + x, row + NX + start - 1, -1):
                strip.append(points[k][0])
                strip.append(points[k][1])
            if shade in groups:
                groups[shade].append(strip)
            else:
                groups[shade] = [strip]
            start = x
        custom = self.shape.custom
        for shade in groups:
            screen.pen = colors[shade]
            screen.shape(custom(*groups[shade]))
        # Glossy crest lines brighten where the slope catches the light, and
        # sun glints sparkle where the surface tilts towards the viewer.
        specular = self.specular
        row += NX
        for x in range(NX - 1):
            level = cells[32 + z * 8 + x]
            if level:
                a, b = points[row + x], points[row + x + 1]
                screen.pen = specular[min(9, level * 2)]
                screen.line(a[0], a[1], b[0], b[1])
            tilt = cells[64 + z * 8 + x]
            if tilt < 30:
                continue
            px, py = points[row + x]
            size = 1 + (tilt > 80) + (tilt > 150)
            screen.pen = self.glint if tilt > 80 else specular[min(9, tilt // 10)]
            screen.line(px - size * 2, py, px + size * 2 + 1, py)
            if size > 1:
                screen.line(px, py - size + 1, px, py + size)

    @micropython.native
    def draw_drops(self, drops):
        screen = self.screen
        half_w, half_h = self.half_w, self.half_h
        ox, oy = self.offset_x, self.offset_y
        spray, foam = self.spray, self.foam
        for drop in drops:
            x, y, z = drop[0], drop[1] / TOP, drop[2]
            f = 1 / (1 + (HALF_Z - z) / (2 * HALF_Z) * 0.65)
            px = half_w + half_w * x * f + ox * (1 - f)
            py = half_h - half_h * y * f + oy * (1 - f)
            # A short streak trails back along the droplet's velocity.
            screen.pen = spray
            screen.line(px - drop[3] * 6 * f, py + drop[4] * 5 * f, px, py)
            screen.pen = foam
            screen.rectangle(px - 1, py - 1, 2, 2)

    def draw(self, pool, wind_x=0.0, wind_z=0.0, full=False):
        self.offset_x = pool.view_x * self.width * 2
        # A slightly raised eye looks down into the pool so its surface reads.
        self.offset_y = pool.view_z * self.height * 2 - EYE_HEIGHT / TOP * self.half_h
        monas = [obj for obj in pool.objects if obj[6] == MONA]
        if self.mona is not None and monas:
            # Stale Mona sprites are re-rendered on screen before the frame paints over them.
            self.mona.begin(self.offset_x, self.offset_y, self.half_w, self.half_h, monas,
                            self.project)
        for i, pen in enumerate(self.background):
            self.screen.pen = pen
            top = i * self.height // len(self.background)
            bottom = (i + 1) * self.height // len(self.background)
            self.screen.rectangle(0, top, self.width, bottom - top)
        edge, dim = self.edges[pool.color_index], self.dim_edges[pool.color_index]
        corners = [self.project(x, y, z) for z in (-HALF_Z, HALF_Z)
                   for y in (BOTTOM, TOP) for x in (-HALF_X, HALF_X)]
        for a, b in ((0, 1), (0, 2), (1, 3), (2, 3),
                     (0, 4), (1, 5), (2, 6), (3, 7)):
            self.line(corners[a], corners[b], dim)
        self.floor(pool.time)
        self.surface_points(pool)
        self.polygon([self.points[z * NX] for z in range(NZ)] + [corners[4], corners[0]],
                     self.side_water)
        self.polygon([self.points[z * NX + NX - 1] for z in range(NZ)]
                     + [corners[5], corners[1]], self.side_water)
        time = pool.time * TURN
        shade(self.heights, SINES, self.cells, int(time * 1.4) & 63,
              int(time * 2.2) & 63, int(time * 1.9) & 63)
        objects = sorted(pool.objects, key=lambda o: o[2])
        rings = sorted(pool.rings, key=lambda r: r[1])
        next_object = next_ring = 0
        row_depth = 2 * HALF_Z / (NZ - 1)
        back = self.points[:NX]
        # A bright reflection where the surface meets the back glass.
        self.screen.pen = self.specular[6]
        for x in range(NX - 1):
            self.screen.line(back[x][0], back[x][1], back[x + 1][0], back[x + 1][1])
        # Rows are painted back to front with objects slotted in by depth, so
        # nearer water tints only the submerged parts of floating things.
        for z in range(NZ - 1):
            limit = -HALF_Z + (z + 0.5) * row_depth
            while next_object < len(objects) and objects[next_object][2] < limit:
                self.draw_object(objects[next_object])
                next_object += 1
            self.surface_row(z)
            while next_ring < len(rings) and rings[next_ring][1] < limit + row_depth:
                self.draw_ring(pool, rings[next_ring])
                next_ring += 1
        while next_object < len(objects):
            self.draw_object(objects[next_object])
            next_object += 1
        while next_ring < len(rings):
            self.draw_ring(pool, rings[next_ring])
            next_ring += 1
        front = (NZ - 1) * NX
        self.polygon(self.points[front:front + NX] + [corners[5], corners[4]], self.body)
        for x in range(NX - 1):
            a, b = self.points[front + x], self.points[front + x + 1]
            self.line(a, b, self.ripple)
            # A soft meniscus band hugs the glass just under the waterline.
            self.line((a[0], a[1] + 2), (b[0], b[1] + 2), self.meniscus)
        for column in (0, NX - 1):
            for z in range(NZ - 1):
                self.line(self.points[z * NX + column], self.points[(z + 1) * NX + column],
                          self.meniscus)
        self.draw_drops(pool.drops)
        # Front corners stay at the physical screen corners, even while tilting.
        for a, b in ((4, 5), (4, 6), (5, 7), (6, 7)):
            self.line(corners[a], corners[b], edge)
        if self.last_level is not None and self.last_level != pool.target_level:
            self.level_until = pool.time + 1.2
        self.last_level = pool.target_level
        if full:
            self.text("POOL FULL - A clears objects", self.width / 2, 12, self.white, True)
        elif pool.time < self.level_until:
            percent = int(round((pool.target_level - BOTTOM) / (TOP - BOTTOM) * 100))
            self.text("%d%%" % percent, self.width - 32, 10, self.muted)
