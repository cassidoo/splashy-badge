import math
import sys

if sys.implementation.name == "micropython":
    import micropython
else:
    class micropython:
        native = staticmethod(lambda function: function)

# Fallback handle, title and pronouns. The handle defaults to the badge's
# GITHUB_USERNAME, and an empty label drops only Monas. Menu opens setup.
LABELS = ("@mona", "universe", "")
MONA = 3
PALETTE = ((65, 255, 135), (66, 220, 255), (151, 122, 255),
           (255, 119, 205), (255, 190, 82), (245, 250, 255))
NX, NZ = 9, 5
HALF_X, HALF_Z = 1.0, 0.56
BOTTOM, TOP = -0.72, 0.72
MIN_LEVEL, MAX_LEVEL = -0.57, 0.48
MAX_OBJECTS = 9
MAX_RINGS = 10
MAX_DROPS = 64
# It's a name tag: the handle is drawn much larger than the other words.
LABEL_SCALE = (1.35, 0.9, 0.9)
# Longer custom labels shrink to these widths so they still fit in the tank.
LABEL_MAX_WIDTH = (1.76, 1.3, 1.3)
# Half-widths of the extruded words, then the floating Mona. The word entries
# are replaced with measured widths whenever labels are (re)built.
OBJECT_RADII = [0.84, 0.32, 0.42, 0.15]
# Height of each object's centre above the floor when it rests there.
REST = (0.13, 0.09, 0.09, 0.09)
# Largest sub-step for the wave springs and buoyancy; they stay stable well
# beyond this (omega * h < 2), so slow frames never need many catch-up steps.
STEP = 0.05
WAVE_LIMIT = 0.19
# Words ride just above the waterline; Mona floats chest-deep. Heavier
# floaters sit lower, and anything denser than water sinks to the floor.
FLOAT_OFFSET = (0.012, 0.012, 0.012, -0.05)
SINKS = 1.0


def random_weight():
    import random
    weight = 0.3 + random.getrandbits(8) / 255 * 1.3
    # Nothing hovers neutrally; it either floats or clearly sinks.
    return 1.1 if 0.95 < weight < 1.1 else weight


def set_label_widths(widths):
    for kind, width in enumerate(widths):
        OBJECT_RADII[kind] = max(0.1, width / 2)


def clamp(value, low, high):
    return min(high, max(low, value))


class Pool:
    def __init__(self):
        self.level = -0.10
        self.target_level = self.level
        self.wave = [0.0] * (NX * NZ)
        self.speed = [0.0] * (NX * NZ)
        self.objects = []
        self.drops = []
        self.rings = []
        self.color_index = 0
        self.tilt_x = self.tilt_z = 0.0
        self.view_x = self.view_z = 0.0
        self.time = 0.0
        self.serial = 0

    def water(self, direction, dt):
        self.target_level = clamp(self.target_level + direction * dt * 0.38,
                                  MIN_LEVEL, MAX_LEVEL)

    def cycle_color(self):
        self.color_index = (self.color_index + 1) % len(PALETTE)

    def clear(self):
        del self.objects[:]
        del self.drops[:]
        del self.rings[:]

    def remove(self, kinds):
        self.objects[:] = [obj for obj in self.objects if obj[6] not in kinds]

    def disturb(self, x, z, strength):
        ix = int(clamp((x + HALF_X) / (2 * HALF_X) * (NX - 1), 0, NX - 1))
        iz = int(clamp((z + HALF_Z) / (2 * HALF_Z) * (NZ - 1), 0, NZ - 1))
        for j in range(max(0, iz - 2), min(NZ, iz + 3)):
            for i in range(max(0, ix - 2), min(NX, ix + 3)):
                distance = abs(i - ix) + abs(j - iz)
                # A sunken centre with a raised rim reads as a proper splash crater.
                self.speed[j * NX + i] += strength * (-1.0 if distance == 0 else
                                                      0.55 if distance == 1 else 0.18)

    def ring(self, x, z, size):
        if len(self.rings) >= MAX_RINGS:
            del self.rings[0]
        self.rings.append([x, z, 0.0, size])

    def splash(self, x, z, y, power):
        self.disturb(x, z, power)
        self.ring(x, z, min(1.0, 0.35 + power * 0.25))
        count = int(8 + power * 6)
        for n in range(count):
            if len(self.drops) >= MAX_DROPS:
                break
            angle = n * 6.2832 / count + self.time * 3.1
            jitter = (n * 37 + self.serial * 11) % 10
            spread = 0.45 + jitter * 0.09
            start = 0.04 + (jitter % 4) * 0.025
            self.drops.append([x + math.cos(angle) * start, y, z + math.sin(angle) * start,
                               math.cos(angle) * spread, 0.6 + power * 0.32
                               + (n % 4) * 0.2, math.sin(angle) * spread * 0.7, 1.4])

    def add(self, kind, weight=None):
        if kind not in (0, 1, 2, MONA):
            raise ValueError("unknown object")
        if len(self.objects) >= MAX_OBJECTS:
            return False
        x = (-0.52, 0.0, 0.52)[self.serial % 3]
        z = (-0.28, 0.28, -0.04)[self.serial % 3]
        self.serial += 1
        # Position, velocity, label, splash latch, yaw/pitch/roll, phase,
        # angular velocities, cached depth extent, local surface slopes,
        # weight relative to water, and local surface height.
        pitch = 0.0 if kind == MONA else 0.18
        obj = [x, TOP - 0.14, z, 0.0, -0.1, 0.0, kind, False,
               -0.25 + kind * 0.22, pitch, 0.0, self.serial * 1.7, 0.0, 0.0, 0.0, 0.0,
               0.0, 0.0, random_weight() if weight is None else weight, TOP]
        obj[15] = depth_extent(obj)
        self.objects.append(obj)
        return True

    @micropython.native
    def sample(self, x, z):
        """Surface height plus its x and z slopes at a world position."""
        fx = (x + HALF_X) * (NX - 1) / (2 * HALF_X)
        fz = (z + HALF_Z) * (NZ - 1) / (2 * HALF_Z)
        fx = 0.0 if fx < 0 else NX - 1.0 if fx > NX - 1 else fx
        fz = 0.0 if fz < 0 else NZ - 1.0 if fz > NZ - 1 else fz
        ix = int(fx)
        iz = int(fz)
        ix = NX - 2 if ix > NX - 2 else ix
        iz = NZ - 2 if iz > NZ - 2 else iz
        u, v = fx - ix, fz - iz
        wave = self.wave
        k = iz * NX + ix
        a, b, c, d = wave[k], wave[k + 1], wave[k + NX], wave[k + NX + 1]
        h = (self.level + self.tilt_x * x * 0.22 + self.tilt_z * z * 0.25
             + (a + (b - a) * u) * (1 - v) + (c + (d - c) * u) * v)
        h = BOTTOM + 0.025 if h < BOTTOM + 0.025 else TOP - 0.06 if h > TOP - 0.06 else h
        slope_x = self.tilt_x * 0.22 + ((b - a) * (1 - v) + (d - c) * v) * (NX - 1) / (2 * HALF_X)
        slope_z = self.tilt_z * 0.25 + ((c - a) * (1 - u) + (d - b) * u) * (NZ - 1) / (2 * HALF_Z)
        return h, slope_x, slope_z

    def surface(self, x, z):
        return self.sample(x, z)[0]

    def step(self, dt, tilt_x=0.0, tilt_z=0.0, wind_x=0.0, wind_z=0.0):
        dt = clamp(dt, 0.0, 0.1)
        blend = 1 - math.exp(-dt * 5)
        change_x = (clamp(tilt_x, -1, 1) - self.tilt_x) * blend
        change_z = (clamp(tilt_z, -1, 1) - self.tilt_z) * blend
        self.tilt_x += change_x
        self.tilt_z += change_z
        for z in range(NZ):
            self.speed[z * NX] -= change_x * 0.7
            self.speed[z * NX + NX - 1] += change_x * 0.7
        for x in range(NX):
            self.speed[x] -= change_z * 0.7
            self.speed[(NZ - 1) * NX + x] += change_z * 0.7
        self.view_x += (self.tilt_x * 0.10 - self.view_x) * blend
        self.view_z += (self.tilt_z * 0.09 - self.view_z) * blend
        # Slow frames take at most two stable wave sub-steps instead of many
        # tiny ones, so extra objects never snowball into a simulation backlog.
        # Floating objects are soft springs and need only one step per frame.
        if dt > STEP:
            self._waves(dt / 2, wind_x, wind_z)
            self._waves(dt / 2, wind_x, wind_z)
        else:
            self._waves(dt, wind_x, wind_z)
        self._float(dt)
        self._settle(dt, wind_x, wind_z)

    @micropython.native
    def _waves(self, dt, wind_x, wind_z):
        self.time += dt
        self.level += (self.target_level - self.level) * dt * 3
        wave, speed = self.wave, self.speed
        keep = 1 - 1.5 * dt
        last_x, last_z = NX - 1, NZ - 1
        for z in range(NZ):
            row = z * NX
            push_z = wind_z * (z / last_z - 0.5) * 0.7
            for x in range(NX):
                i = row + x
                h = wave[i]
                left = wave[i - 1] if x else h
                right = wave[i + 1] if x < last_x else h
                back = wave[i - NX] if z else h
                front = wave[i + NX] if z < last_z else h
                force = ((left + right + back + front - 4 * h) * 95 - h * 9
                         + wind_x * (x / last_x - 0.5) * 0.7 + push_z)
                speed[i] = speed[i] * keep + force * dt
        mean = 0.0
        for i in range(NX * NZ):
            h = wave[i] + speed[i] * dt
            h = WAVE_LIMIT if h > WAVE_LIMIT else -WAVE_LIMIT if h < -WAVE_LIMIT else h
            wave[i] = h
            mean += h
        mean /= NX * NZ
        for i in range(NX * NZ):
            wave[i] -= mean

    @micropython.native
    def _float(self, dt):
        speed = self.speed
        for obj in self.objects:
            x, y, z, vx, vy, vz, kind, wet = obj[:8]
            weight = obj[18]
            surface, obj[16], obj[17] = self.sample(x, z)
            obj[19] = surface
            sinks = weight >= SINKS
            target = surface + FLOAT_OFFSET[kind] - (weight - 0.5) * 0.16
            if not wet and y <= (surface if sinks else target) + 0.015:
                obj[7] = wet = True
                # Heavy entries throw a big crater and spray, then lose most of
                # their momentum to the water; heavier things keep more of it.
                self.splash(x, z, surface,
                            min(4.6, (0.8 + abs(vy) * 1.35) * (0.6 + weight * 0.45)))
                vy *= 0.6 if sinks else 0.42
                obj[13] += (0.9 if int(obj[11] * 3) & 1 else -0.9) + vx
                obj[14] += 1.6 if kind == MONA else -1.3
            if not wet or y > (surface + 0.02 if sinks else target + 0.06):
                vy -= 5.4 * dt
            elif sinks:
                # Dense things glide down through the water at a slow drift.
                vy += ((SINKS - weight) * 1.8 - vy * 2.6) * dt
            else:
                vy += ((target - y) * 34 - vy * 2.5) * dt
                # Bobbing pushes on the surface, so floating things make ripples.
                ix = int((x + HALF_X) * (NX - 1) / (2 * HALF_X) + 0.5)
                iz = int((z + HALF_Z) * (NZ - 1) / (2 * HALF_Z) + 0.5)
                if 0 <= ix < NX and 0 <= iz < NZ:
                    speed[iz * NX + ix] += (vy * 2.4 - (abs(vx) + abs(vz)) * 0.8) * dt
            x += vx * dt
            y += vy * dt
            z += vz * dt
            floor = BOTTOM + REST[kind]
            if y < floor:
                y = floor
                vy = -vy * 0.2 if vy < -0.3 else 0.0
            elif y > TOP - 0.12:
                y = TOP - 0.12
            radius = OBJECT_RADII[kind]
            if abs(x) > HALF_X - radius:
                x = clamp(x, -HALF_X + radius, HALF_X - radius)
                vx *= -0.45
            depth_radius = obj[15]
            if abs(z) > HALF_Z - depth_radius:
                z = clamp(z, -HALF_Z + depth_radius, HALF_Z - depth_radius)
                vz *= -0.45
            obj[0] = x
            obj[1] = y
            obj[2] = z
            obj[3] = vx
            obj[4] = vy
            obj[5] = vz

    @micropython.native
    def _settle(self, dt, wind_x, wind_z):
        """Once-per-frame forces, wobble, collisions, spray and rings."""
        time = self.time
        for obj in self.objects:
            x, z, kind, phase = obj[0], obj[2], obj[6], obj[11]
            # Sunken things ignore surface waves and only slide with the tilt.
            deep = obj[1] < obj[19] - 0.1
            if obj[7] and not deep:
                # Floating things slide down wave slopes and tip with the water.
                slope_x, slope_z = obj[16], obj[17]
                wind, drag = 0.55, 1.5
            else:
                slope_x = slope_z = 0.0
                wind, drag = 0.12, 1.5
                if obj[1] <= BOTTOM + REST[kind] + 0.005:
                    # Friction on the floor.
                    drag = 4.0
            obj[3] += (wind_x * wind - self.tilt_x * 0.45 - slope_x * 1.6
                       - obj[3] * drag) * dt
            obj[5] += (wind_z * wind - self.tilt_z * 0.45 - slope_z * 1.6
                       - obj[5] * drag) * dt
            if deep:
                # Resting poses stay still, which also keeps Mona's sprite cached.
                yaw = math.sin(phase) * 0.5 + obj[3] * 0.5
                pitch = (0.0 if kind == MONA else 0.22) + obj[5] * 0.4
            elif kind == MONA:
                # Mona slowly turns to look around while she paddles.
                yaw = math.sin(time * 0.22 + phase) * 1.1 + obj[3] * 0.8
                pitch = math.sin(time * 0.6 + phase) * 0.10 + obj[5] * 0.5 - slope_z * 0.8
            else:
                yaw = math.sin(time * 0.28 + phase) * 0.42 + obj[3] * 0.5
                pitch = (0.20 + math.sin(time * 0.5 + phase) * 0.12 + obj[5] * 0.4
                         - slope_z * 0.9)
            roll = -self.tilt_x * 0.22 + slope_x * 0.9
            if not deep:
                roll += math.sin(time * 0.7 + phase) * 0.07
            # Springy angles overshoot and wobble instead of easing rigidly.
            for index, target_angle in ((8, yaw), (9, pitch), (10, roll)):
                spin = obj[index + 4]
                spin += ((target_angle - obj[index]) * 16 - spin * 2.6) * dt
                obj[index + 4] = spin
                obj[index] += spin * dt
            obj[15] = depth_extent(obj)

        objects = self.objects
        for i, a in enumerate(objects):
            for b in objects[i + 1:]:
                if abs(a[1] - b[1]) > 0.15:
                    continue
                dx, dz = b[0] - a[0], b[2] - a[2]
                overlap_x = OBJECT_RADII[a[6]] + OBJECT_RADII[b[6]] - abs(dx)
                overlap_z = a[15] + b[15] - abs(dz)
                if overlap_x > 0 and overlap_z > 0:
                    axis, delta, overlap = ((3, dx, overlap_x) if overlap_x < overlap_z
                                            else (5, dz, overlap_z))
                    push = (1 if delta >= 0 else -1) * overlap * dt * 14
                    a[axis] -= push
                    b[axis] += push
        near = self.level + 0.25
        drops = self.drops
        for i in range(len(drops) - 1, -1, -1):
            drop = drops[i]
            drop[6] -= dt
            drop[4] -= dt * 3.4
            drop[0] += drop[3] * dt
            drop[1] += drop[4] * dt
            drop[2] += drop[5] * dt
            if abs(drop[0]) >= HALF_X - 0.01:
                drop[0] = clamp(drop[0], -HALF_X + 0.01, HALF_X - 0.01)
                drop[3] *= -0.4
            if abs(drop[2]) >= HALF_Z - 0.01:
                drop[2] = clamp(drop[2], -HALF_Z + 0.01, HALF_Z - 0.01)
                drop[5] *= -0.4
            if drop[4] < 0 and drop[1] < near and drop[1] < self.surface(drop[0], drop[2]):
                # Falling droplets leave tiny ripples where they land.
                self.disturb(drop[0], drop[2], 0.12)
                if i % 4 == 0:
                    self.ring(drop[0], drop[2], 0.22)
                del drops[i]
            elif drop[6] <= 0:
                del drops[i]
        for i in range(len(self.rings) - 1, -1, -1):
            self.rings[i][2] += dt
            if self.rings[i][2] > 0.9:
                del self.rings[i]


@micropython.native
def depth_extent(obj):
    if obj[6] == MONA:
        return OBJECT_RADII[MONA]
    return (0.06 + OBJECT_RADII[obj[6]] * abs(math.sin(obj[8]))
            + 0.08 * abs(math.sin(obj[9])))


class Motion:
    def __init__(self, reading):
        self.origin = reading[:3]
        self.gyro_bias = reading[3:]
        self.x = self.z = 0.0

    def read(self, reading, dt, inverted=False):
        ax, ay, az, gx, gy, gz = reading
        magnitude = max(1, math.sqrt(ax * ax + ay * ay + az * az))
        # Relative raw sensor units avoid assuming a firmware full-scale setting.
        tx = clamp((ax - self.origin[0]) / magnitude, -1, 1)
        tz = clamp((ay - self.origin[1]) / magnitude, -1, 1)
        blend = 1 - math.exp(-min(dt, 0.1) * 4)
        self.x += clamp((gy - self.gyro_bias[1]) / 32768, -1, 1) * dt * 2
        self.z += clamp((gx - self.gyro_bias[0]) / 32768, -1, 1) * dt * 2
        self.x += (tx - self.x) * blend
        self.z += (tz - self.z) * blend
        sign = -1 if inverted else 1
        return self.x * sign, self.z * sign
