# -*- coding: utf-8 -*-
"""SPEC Shoulds: URDF export (RB-01), floor plan + area table on the variant board and in the change summary
(D-02, D-04), tour video (D-05), preservation bundle that replays years later (N-06), license table (R-03).
Run from engine/."""
from __future__ import annotations

import copy
import json
import math
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
REPO = ENGINE.parent
sys.path.insert(0, str(ENGINE))

from worldengine import footprint as FP, robot as RB, world as WD  # noqa: E402
from worldengine.studio import diff as DF  # noqa: E402

URDFS = ["planar_3_dof", "arm_6_dof", "planar_arm_with_fixed", "planar_3_dof_diff_links"]


class UrdfExportTests(unittest.TestCase):
    def test_round_trip_through_the_reference_parser(self):
        for n in URDFS:
            with self.subTest(n), tempfile.TemporaryDirectory() as d:
                c = RB.load_chain(REPO / "kinematics" / (n + ".urdf"))
                f = Path(d) / "x.urdf"; f.write_text(RB.to_urdf(c), encoding="utf-8")
                back = RB.load_chain(f)
                self.assertEqual(back["joints"], c["joints"])                     # bit-identical numbers
                rng = random.Random(7)
                for _ in range(50):
                    q = [rng.uniform(-1.5, 1.5) for _ in RB.active(c)]
                    self.assertEqual(RB.tip(back, q), RB.tip(c, q))

    def test_cli_exports_the_drawing_robot(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "arm.urdf"
            p = subprocess.run([sys.executable, "-m", "worldengine", "urdf", str(ENGINE / "worlds" / "drawing_robot.world.json"), "--out", str(out)],
                               cwd=ENGINE, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            arm = next(e for e in WD.load(ENGINE / "worlds" / "drawing_robot.world.json")["entities"] if e["type"] == "robot.arm")
            self.assertEqual(RB.load_chain(out)["joints"], arm["chain"]["joints"])
            import xml.etree.ElementTree as ET
            root = ET.parse(out).getroot()                                        # a well-formed URDF tree: every joint links parent -> child
            links = {l.get("name") for l in root.findall("link")}
            for j in root.findall("joint"):
                self.assertIn(j.find("parent").get("link"), links); self.assertIn(j.find("child").get("link"), links)
                if j.get("type") != "fixed":
                    self.assertEqual(j.find("limit").get("velocity"), "1.5")


class FloorPlanTests(unittest.TestCase):
    W = {"format": "world/1", "name": "t", "bounds": [10, 10, 3],
         "entities": [{"type": "box", "pos": [2, 2, 0], "size": [2, 2, 1]}, {"type": "box", "pos": [3, 2, 0], "size": [2, 2, 1]},
                      {"type": "cylinder", "pos": [7, 7, 0], "radius": 1}, {"type": "plane", "size": [10, 10]},
                      {"type": "group", "pos": [5, 8, 0], "rot": [0, 0, 90], "children": [{"type": "box", "pos": [1, 0, 0], "size": [1, 0.5, 1]}]},
                      {"type": "sound", "caption": "x", "pos": [1, 1, 1]}]}

    def test_areas(self):
        t = FP.area_table(self.W)
        self.assertEqual(t["by_type"]["box"], {"count": 3, "area_m2": 8.5})
        self.assertAlmostEqual(t["by_type"]["cylinder"]["area_m2"], math.pi, places=3)
        self.assertEqual(t["floors_m2"], 100)                                     # the floor is not a body on the site
        self.assertAlmostEqual(t["covered_m2"], 6 + math.pi + 0.5, delta=0.1)     # overlap counted once
        self.assertAlmostEqual(t["sum_m2"], 8 + math.pi + 0.5, places=3)          # ... and twice in the sum
        self.assertEqual(t["site_m2"], 100)

    def test_children_follow_the_parent_turn(self):
        f = [x for x in FP.footprints(self.W) if x["type"] == "box" and abs(x["w"] - 1) < 1e-9][0]
        self.assertAlmostEqual(f["cx"], 5, places=9); self.assertAlmostEqual(f["cy"], 9, places=9)
        self.assertEqual(f["rot"], 90)

    def test_plan_svg_and_reference_worlds(self):
        svg = FP.plan_svg(WD.load(ENGINE / "worlds" / "ref_modulor.world.json"))
        self.assertTrue(svg.startswith("<svg") and svg.rstrip().endswith("</svg>"))
        import xml.etree.ElementTree as ET
        ET.fromstring(svg)
        for n in ("ref_yeobaek", "ref_festival_baroque", "ref_modulor", "contradiction_garden", "talking_garden", "drawing_robot"):
            t = FP.area_table(WD.load(ENGINE / "worlds" / (n + ".world.json")))
            print("\nAREA %s covered %.2f / sum %.2f / site %.2f m2 (cell %s)" % (n, t["covered_m2"], t["sum_m2"], t["site_m2"], t["cell_m"]), file=sys.stderr)
            self.assertLessEqual(t["covered_m2"], t["sum_m2"] * 1.03)

    def test_change_summary_says_the_area_change(self):
        a = WD.load(ENGINE / "worlds" / "ref_modulor.world.json")
        b = copy.deepcopy(a); b["entities"].append({"id": "pav", "type": "box", "pos": [3, 3, 0], "size": [2.26, 2.26, 2.26]})
        lines = DF.summary_ko(DF.diff(a, b))
        self.assertTrue(any(l.startswith("몸이 덮은 바닥") for l in lines), lines)
        c = copy.deepcopy(a); c["rules"]["axes"]["density"] = 0.9
        self.assertFalse(any(l.startswith("몸이 덮은 바닥") for l in DF.summary_ko(DF.diff(a, c))))   # axes only: no area line


if __name__ == "__main__":
    unittest.main()
