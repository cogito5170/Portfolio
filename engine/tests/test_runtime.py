# -*- coding: utf-8 -*-
"""Modular runtime (engine/runtime) tests: the JS/Python contract, real renders, and the phone controls measured
in a real browser. Run from engine/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from worldengine import png as pngcheck
from worldengine import headless, layout, world as WD  # noqa: E402

FIX = ENGINE / "runtime" / "tests" / "fixtures_check.json"
GARDEN = ENGINE / "worlds" / "contradiction_garden.world.json"
NODE = shutil.which("node")
BROWSER, WHY = headless.available()


class WorldContractTests(unittest.TestCase):
    def test_demo_world_valid(self):
        self.assertEqual(WD.check(WD.load(GARDEN)), [])

    def test_from_scene_wraps_legacy_store(self):
        w = WD.from_scene(layout.to_scene(layout.examples()["hongdae/F1"]))
        self.assertEqual(WD.check(w, known_types={"retail.store"}), [])
        self.assertEqual(w["entities"][0]["type"], "retail.store")

    @unittest.skipUnless(NODE, "node not installed")
    def test_python_and_js_check_agree_message_for_message(self):
        fx = json.loads(FIX.read_text(encoding="utf-8"))
        js = json.loads(subprocess.run([NODE, str(ENGINE / "runtime" / "tests" / "check_cli.mjs"), str(FIX)],
                                       capture_output=True, text=True, check=True).stdout)
        for f, j in zip(fx, js):
            with self.subTest(f["name"]):
                self.assertEqual(WD.check(f["world"], set(f["known"]) if "known" in f else None), j)

    @unittest.skipUnless(NODE, "node not installed")
    def test_node_unit_tests(self):
        tests = sorted(str(p) for p in (ENGINE / "runtime" / "tests").glob("*.test.mjs"))
        p = subprocess.run([NODE, "--test", *tests], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout[-3000:] + p.stderr[-2000:])


def _assert_picture(tc, png, w, h):
    st = pngcheck.stats(png)
    tc.assertEqual((st["w"], st["h"]), (w, h))
    tc.assertGreater(st["distinct"], 200, st)
    tc.assertGreater(st["lum_sd"], 10.0, st)
    tc.assertGreater(st["bottom_distinct"], 1, st)        # no flat band where the viewport fell short of the window
    return st


@unittest.skipUnless(BROWSER, "no headless browser: %s" % WHY)
class RuntimeRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="we_rt_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_demo_world_aerial_desktop(self):
        r = headless.render_world(GARDEN, self.tmp / "a.png", view="aerial", w=800, h=500, t=2.0, timeout_s=120)
        self.assertTrue(r["ok"], r["reason"])
        _assert_picture(self, self.tmp / "a.png", 800, 500)

    def test_demo_world_walk_child_phone_portrait(self):
        r = headless.render_world(GARDEN, self.tmp / "p.png", mode="walk", eye="child", w=390, h=844, timeout_s=120)
        self.assertTrue(r["ok"], r["reason"])
        _assert_picture(self, self.tmp / "p.png", 390, 844)

    def test_legacy_store_through_retail_plugin(self):
        w = WD.from_scene(layout.to_scene(layout.examples()["hongdae/F1"]))
        r = headless.render_world(w, self.tmp / "s.png", view="aerial", w=800, h=500, timeout_s=120)
        self.assertTrue(r["ok"], r["reason"])
        _assert_picture(self, self.tmp / "s.png", 800, 500)

    def test_invalid_world_is_an_error_not_a_picture(self):
        w = WD.load(GARDEN); w["entities"].append({"type": "dragon"})
        r = headless.render_world(w, self.tmp / "x.png", w=200, h=100, timeout_s=60)
        self.assertFalse(r["ok"])
        self.assertIn("dragon", r["reason"])


@unittest.skipUnless(BROWSER, "no headless browser: %s" % WHY)
class PhoneControlTests(unittest.TestCase):
    """XR-12, measured in a real browser through the real event listeners (synthetic touch PointerEvents)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="we_touch_"))
        r = headless.render_world(GARDEN, cls.tmp / "t.png", view="eye", w=390, h=844, selftest="touch", timeout_s=120)
        assert r["ok"], r["reason"]
        cls.r = r["result"]
        r = headless.render_world(GARDEN, cls.tmp / "c.png", view="eye", w=390, h=844, selftest="collide", timeout_s=120)
        assert r["ok"], r["reason"]
        cls.c = r["result"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_joystick_walk_distance_matches_kinematics(self):
        w = self.r["walk"]
        self.assertAlmostEqual(w["moved"], w["expected"], delta=0.01 * w["expected"])
        self.assertAlmostEqual(w["along_yaw"], w["moved"], delta=1e-6)       # straight ahead, no drift

    def test_release_stops(self):
        self.assertEqual(self.r["after_release"], 0)

    def test_drag_look(self):
        self.assertAlmostEqual(self.r["look"]["dyaw"], self.r["look"]["expected"], places=9)

    def test_eye_heights_child_adult(self):
        self.assertAlmostEqual(self.r["eye_child"], 1.1, places=6)
        self.assertAlmostEqual(self.r["eye_adult"], 1.7, places=6)

    def test_two_finger_pinch_zooms_in(self):
        p = self.r["pinch"]
        self.assertLess(p["d1"], 0.9 * p["d0"], p)

    def test_walk_stops_at_solid_object(self):
        c = self.c
        self.assertNotIn("error", c)
        self.assertGreater(c["x"], c["start_x"] + 1.0)                       # it did walk
        self.assertLessEqual(c["x"], c["wall_x0"] - c["radius"] + 1e-6)      # but not into the object
        self.assertGreater(c["x"], c["wall_x0"] - c["radius"] - 0.05)


if __name__ == "__main__":
    unittest.main()
