import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "splashy_badge"))

from physics import Pool, Motion, PALETTE, MAX_LEVEL, MIN_LEVEL, MAX_OBJECTS, BOTTOM, TOP
from controls import Controls
from physics import MONA, REST, HALF_X, OBJECT_RADII, SINKS, random_weight


class Input:
    def __init__(self, pressed=(), held=(), direction=(0, 0)):
        self.p, self.h = pressed, held
        self.d = SimpleNamespace(x=direction[0], y=direction[1])

    def pressed(self, action):
        return action in self.p

    def held(self, action):
        return action in self.h

    def direction(self):
        return self.d


class PoolTests(unittest.TestCase):
    def advance(self, pool, seconds=6, **kwargs):
        for _ in range(int(seconds * 60)):
            pool.step(1 / 60, **kwargs)

    def test_water_limits(self):
        pool = Pool()
        pool.water(1, 100)
        self.assertEqual(pool.target_level, MAX_LEVEL)
        pool.water(-1, 100)
        self.assertEqual(pool.target_level, MIN_LEVEL)

    def test_objects_float_and_are_bounded(self):
        pool = Pool()
        for n in range(MAX_OBJECTS):
            self.assertTrue(pool.add(n % 3, 0.5))
        self.assertFalse(pool.add(0))
        self.advance(pool, 12, tilt_x=0.7, tilt_z=-0.8, wind_x=1, wind_z=-1)
        for obj in pool.objects:
            self.assertTrue(obj[7])
            self.assertLess(abs(obj[1] - pool.surface(obj[0], obj[2]) - 0.04), 0.1)
            self.assertLessEqual(abs(obj[0]), HALF_X - OBJECT_RADII[obj[6]] + 1e-9)
            self.assertLessEqual(abs(obj[2]), 0.471)
            self.assertTrue(all(math.isfinite(v) for v in obj[:6]))
        pool.clear()
        self.assertFalse(pool.objects)
        self.assertFalse(pool.drops)

    def test_waves_remain_stable_and_conserve_mean(self):
        pool = Pool()
        pool.disturb(0, 0, 2)
        self.advance(pool, 20, wind_x=1, wind_z=-1, tilt_x=1, tilt_z=-1)
        self.assertAlmostEqual(sum(pool.wave), 0, places=7)
        for h in pool.wave:
            self.assertLess(abs(h), 0.2)
        for x in (-1, 0, 1):
            for z in (-0.56, 0, 0.56):
                self.assertGreater(pool.surface(x, z), BOTTOM)
                self.assertLess(pool.surface(x, z), TOP)
        self.advance(pool, 15)
        self.assertLess(max(abs(h) for h in pool.wave), 0.001)

    def test_fixed_timestep_frame_independence(self):
        a, b = Pool(), Pool()
        a.add(0, 0.5)
        b.add(0, 0.5)
        for _ in range(120):
            a.step(1 / 30, 0.3, 0.2, 1, 0)
        for _ in range(240):
            b.step(1 / 60, 0.3, 0.2, 1, 0)
        self.assertAlmostEqual(a.time, b.time, places=6)
        self.assertLess(abs(a.objects[0][1] - b.objects[0][1]), 0.01)

    def test_color_cycles_once_per_press(self):
        pool = Pool()
        for _ in PALETTE:
            pool.cycle_color()
        self.assertEqual(pool.color_index, 0)

    def test_tilt_excites_waves_without_wind(self):
        pool = Pool()
        pool.step(1 / 30, tilt_x=0.8)
        self.assertGreater(max(abs(h) for h in pool.wave), 0)

    def test_input_sources_are_separate(self):
        pool = Pool()
        controls = Controls("up", "down", "left", "right", "select", "back")
        badge = SimpleNamespace(buttons=Input(("left", "right", "select")),
                                pad=Input())
        controls.apply(badge, pool, 0.1)
        self.assertEqual([obj[6] for obj in pool.objects], [0, 1, 2])
        badge.buttons = Input(held=("up",))
        badge.pad = Input(direction=(0, -1))
        target = pool.target_level
        self.assertEqual(controls.apply(badge, pool, 0.1)[:2], (0, -1))
        self.assertGreater(pool.target_level, target)
        badge.buttons = Input()
        badge.pad = Input(("back",))
        controls.apply(badge, pool, 0.1)
        self.assertEqual(pool.color_index, 1)
        badge.pad = Input(held=("back",))
        controls.apply(badge, pool, 0.1)
        self.assertEqual(pool.color_index, 1)
        badge.pad = Input(("select",))
        controls.apply(badge, pool, 0.1)
        self.assertFalse(pool.objects)

    def test_each_word_drops_once_then_monas(self):
        controls = Controls("up", "down", "left", "right", "select", "back")
        pool = Pool()
        badge = SimpleNamespace(buttons=Input(("left", "right")), pad=Input())
        controls.apply(badge, pool, 0.1)
        self.assertEqual([obj[6] for obj in pool.objects], [0, 1])
        badge.buttons = Input(("left", "right", "select"))
        controls.apply(badge, pool, 0.1)
        self.assertEqual([obj[6] for obj in pool.objects], [0, 1, MONA, MONA, 2])
        pool.clear()
        badge.buttons = Input(("left",))
        controls.apply(badge, pool, 0.1)
        self.assertEqual([obj[6] for obj in pool.objects], [0])

    def test_weights_float_high_low_or_sink(self):
        pool = Pool()
        for weight in (0.3, 0.9, 1.5):
            pool.add(MONA, weight)
        for obj, x in zip(pool.objects, (-0.6, 0.0, 0.6)):
            obj[0], obj[2] = x, 0.0
        for _ in range(900):
            pool.step(1 / 30)
        light, heavy_floater, sinker = pool.objects
        self.assertGreater(light[1], heavy_floater[1])
        self.assertGreater(heavy_floater[1], pool.level - 0.25)
        self.assertAlmostEqual(sinker[1], BOTTOM + REST[MONA], places=3)
        weights = [random_weight() for _ in range(300)]
        self.assertTrue(all(0.3 <= w <= 1.6 and not 0.95 < w < 1.1 for w in weights))
        self.assertTrue(0.2 < sum(w >= SINKS for w in weights) / 300 < 0.6)

    def test_landing_splashes_with_rings_and_spray(self):
        pool = Pool()
        pool.add(MONA, 0.5)
        peak = 0.0
        for _ in range(90):
            pool.step(1 / 30)
            peak = max(peak, max(abs(h) for h in pool.wave))
            if pool.rings and pool.drops:
                break
        self.assertTrue(pool.rings)
        self.assertGreater(len(pool.drops), 10)
        for _ in range(4):
            pool.step(1 / 30)
            peak = max(peak, max(abs(h) for h in pool.wave))
        self.assertGreater(peak, 0.02)
        for _ in range(120):
            pool.step(1 / 30)
        self.assertFalse(pool.drops)
        self.assertFalse(pool.rings)
        mona = pool.objects[0]
        self.assertLess(mona[1], pool.surface(mona[0], mona[2]))
        pool.clear()
        self.assertFalse(pool.rings)

    def test_motion_neutral_and_inversion(self):
        initial = (1000, -2000, -16000, 100, -200, 0)
        motion = Motion(initial)
        self.assertEqual(motion.read(initial, 0.02), (0, 0))
        sample = (8000, -2000, -13000, 100, 4000, 0)
        x, z = motion.read(sample, 0.05)
        self.assertGreater(x, 0)
        self.assertEqual(z, 0)
        other = Motion(initial)
        ix, iz = other.read(sample, 0.05, True)
        self.assertAlmostEqual(ix, -x)
        self.assertEqual(iz, -z)
        self.assertTrue(all(math.isfinite(v) for v in motion.read((0,) * 6, 0.05)))


if __name__ == "__main__":
    unittest.main()
