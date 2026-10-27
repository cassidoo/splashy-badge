import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "splashy_badge"))

import nametag
from controls import Controls
from physics import LABELS, MONA, OBJECT_RADII, Pool, set_label_widths
from test_pool import Input

BUTTONS = {name: name for name in ("up", "down", "left", "right", "select", "back", "menu")}


class FakeState:
    def __init__(self, saved=None):
        self.saved = saved

    def load(self, key, data):
        if self.saved is not None:
            data.update(self.saved)

    def save(self, key, data):
        self.key, self.saved = key, data


class FakeScreen:
    def __init__(self):
        self.texts = []

    def clear(self):
        self.texts = []

    def rectangle(self, *args):
        pass

    def text(self, value, *args):
        self.texts.append(value)

    def measure_text(self, value):
        return len(value) * 6, 8


def setup(labels=LABELS, username=None):
    return nametag.Setup(FakeScreen(), SimpleNamespace(rgb=lambda *a: a), SimpleNamespace(),
                         labels, BUTTONS, username)


def press(screen_setup, *names):
    result = True
    for name in names:
        result = screen_setup.update(lambda button: button == name)
    return result


def tap(screen_setup, label):
    """Move right along the current key row to a label, then press it."""
    for _ in range(12):
        if screen_setup.rows[screen_setup.key_row][screen_setup.key_column].label == label:
            return press(screen_setup, "select")
        press(screen_setup, "right")
    raise AssertionError("no key " + label)


class NametagTests(unittest.TestCase):
    def test_load_defaults_cleans_and_saves(self):
        self.assertEqual(nametag.load(FakeState()), (list(LABELS), False))
        self.assertEqual(nametag.load(FakeState({"labels": "bad"})), (list(LABELS), False))
        loaded, saved = nametag.load(FakeState({"labels": ["  @me\n", 7, "x" * 40]}))
        self.assertTrue(saved)
        self.assertEqual(loaded, ["@me", LABELS[1], "x" * nametag.MAX_LENGTH])
        state = FakeState()
        self.assertTrue(nametag.save(["@me", "", "they/them"], state))
        self.assertEqual(state.key, "splashy_badge")
        self.assertEqual(nametag.load(state), (["@me", "", "they/them"], True))

    def test_first_launch_defaults_to_badge_username(self):
        labels, saved = nametag.load(FakeState(), "octo-dev")
        self.assertFalse(saved)
        self.assertEqual(labels, ["@octo-dev", "universe", ""])
        self.assertEqual(nametag.load(FakeState(), "@@x")[0][0], "@x")
        self.assertEqual(nametag.load(FakeState(), " ")[0][0], LABELS[0])
        self.assertEqual(nametag.presets(0, "octo-dev")[0], "@octo-dev")
        s = setup(labels, "octo-dev")
        s.welcome = True
        s.draw()
        self.assertIn("Welcome! Make it yours", s.screen.texts)
        self.assertIn("(Monas only)", s.screen.texts)

    def test_pick_presets_and_type_custom_labels(self):
        s = setup(username="octocat")
        press(s, "right")
        self.assertEqual(s.labels[0], "@octocat")
        press(s, "down", "right", "down", "left")
        self.assertEqual(s.labels[1:], ["devex", "any/all"])
        # Type on the keyboard: delete everything, enter "Hi", finish with Menu.
        press(s, "up", "select")
        self.assertEqual(s.typing, 1)
        for _ in range(10):
            press(s, "back")
        self.assertEqual(s.value, "")
        press(s, "down", "down", "down")           # the action row
        tap(s, "aA")                               # shift stays on
        press(s, "up", "up")
        tap(s, "H")
        press(s, "up")
        tap(s, "I")
        self.assertEqual(s.value, "HI")
        self.assertTrue(press(s, "menu"))
        self.assertIsNone(s.typing)
        self.assertEqual(s.labels[1], "HI")
        self.assertFalse(press(s, "back"))

    def test_done_row_and_drawing(self):
        s = setup()
        s.draw()
        self.assertIn(LABELS[0], s.screen.texts)
        press(s, "up")
        self.assertFalse(press(s, "select"))
        s = setup()
        press(s, "select")
        s.draw()
        self.assertIn("done", s.screen.texts)

    def test_empty_label_drops_monas_and_widths_update_radii(self):
        labels = ["@me", "", "they"]
        pool = Pool()
        controls = Controls(1, 2, 3, 4, 5, 6, labels)
        controls.apply(SimpleNamespace(buttons=Input(pressed=(4,)), pad=Input()), pool, 1 / 60)
        self.assertEqual(pool.objects[0][6], MONA)
        pool.add(0)
        pool.remove([0])
        self.assertEqual([obj[6] for obj in pool.objects], [MONA])
        before = list(OBJECT_RADII)
        try:
            set_label_widths([1.0, 0.0, 0.5])
            self.assertEqual(OBJECT_RADII[:3], [0.5, 0.1, 0.25])
        finally:
            OBJECT_RADII[:] = before


if __name__ == "__main__":
    unittest.main()
