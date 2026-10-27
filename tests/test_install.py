import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import install  # noqa: E402

MENU = (
    "import math\nimport os\nfrom icons import ICONS\n\n"
    "def tiles(root, slug, path):\n"
    "        if True:\n"
    + install.MENU_ANCHOR
    + "            return icon_key\n"
)


class MenuPatchTest(unittest.TestCase):
    def test_adds_hook_once(self):
        patched = install.patch_menu_source(MENU)
        self.assertIn("\nimport json\nimport os\n", patched)
        self.assertLess(patched.index(install.MENU_MARKER), patched.index(install.MENU_ANCHOR))
        self.assertEqual(install.patch_menu_source(patched), patched)
        compile(patched, "app.py", "exec")

    def test_unknown_menu_is_left_alone(self):
        self.assertIsNone(install.patch_menu_source("import os\nprint('menu')\n"))

    def test_menu_icon_is_a_white_glyph_in_menu_space(self):
        with open(os.path.join(ROOT, "splashy_badge", "menu_icon.json")) as f:
            contours = json.load(f)
        self.assertEqual(len(contours), 3)
        for contour in contours:
            self.assertEqual(len(contour) % 2, 0)
            self.assertTrue(all(-0.5 <= v <= 0.5 for v in contour))


if __name__ == "__main__":
    unittest.main()
