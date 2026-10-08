# -*- coding: utf-8 -*-
"""Drawing robot (SPEC 6절 2단계, V-16): plan -> verify -> world -> browser ink. Run from engine/."""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from worldengine import png as pngcheck
from worldengine import draw as D, headless, robot as RB, world as WD  # noqa: E402

KIN = ENGINE.parent / "kinematics"
PLANE = {"origin": [0, 0, 0], "u": [1, 0, 0], "v": [0, 1, 0]}
BROWSER, WHY = headless.available()


class ChainTests(unittest.TestCase):
    def test_runtime_fixture_chains_match_the_urdfs(self):
        fx = json.loads((ENGINE / "runtime" / "tests" / "fixtures_chains.json").read_text(encoding="utf-8"))
        for name, chain in fx.items():
            with self.subTest(name):
                self.assertEqual(chain, RB.load_chain(KIN / (name + ".urdf")))

    def test_chain_roundtrip_through_reference_robot(self):
        ch = RB.load_chain(KIN / "planar_3_dof.urdf")
        self.assertEqual(RB.tip(ch, [0, 0, 0]), [3.0, 0.0, 0.0])


class SvgTests(unittest.TestCase):
    def test_moves_lines_close_relative(self):
        self.assertEqual(D.svg_path("M0 0 L1 0 L1 1 Z m 2 2 h 1 v 1"),
                         [[[0, 0], [1, 0], [1, 1], [0, 0]], [[2, 2], [3, 2], [3, 3]]])

    def test_curves_are_refused_not_flattened_silently(self):
        with self.assertRaises(ValueError):
            D.svg_path("M0 0 C 1 1 2 2 3 3")


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ch = RB.load_chain(KIN / "planar_3_dof.urdf")
        cls.q0, cls.home_err = D.home(cls.ch, [1.9, 0, 0], [-0.6, 0.7, 0.6])
        cls.p = D.plan(cls.ch, D.demo_strokes(), PLANE, q_home=cls.q0)

    def test_home_pose_is_not_folded(self):
        self.assertLess(self.home_err, 1e-6)
        self.assertTrue(all(abs(a) < 2.0 for a in self.q0), self.q0)

    def test_v16_demo_passes(self):
        v = self.p["verify"]
        self.assertTrue(v["pass"], v)
        self.assertLess(v["stroke_err_max_m"], 1e-4)
        self.assertLess(v["chord_err_max_m"], v["chord_tol_m"])
        self.assertEqual((v["unreachable"], v["limit_violations"], v["self_collisions"]), (0, 0, 0))

    def test_continuity_no_branch_jumps_while_drawing(self):
        tr = self.p["trajectory"]
        jumps = [max(abs(a - b) for a, b in zip(tr["q"][i], tr["q"][i - 1])) for i in range(1, len(tr["q"])) if tr["pen"][i] and tr["pen"][i - 1]]
        self.assertLess(max(jumps), 0.1)                 # 2 cm steps on a 3 m arm: a branch flip would be > 1 rad

    def test_deliberate_over_limit_drawing_is_detected(self):
        """V-16: 일부러 한계를 넘는 그림을 넣어 검출 확인 -- both with limits enforced (unreachable) and without (violations)."""
        ch = copy.deepcopy(self.ch); ch["joints"][0]["lower"], ch["joints"][0]["upper"] = -1.2, -0.9
        strokes = [D.star(1.9, 0.0, 0.6, 0.25)]
        enforced = D.plan(ch, strokes, PLANE, q_home=self.q0)["verify"]
        raw = D.plan(ch, strokes, PLANE, q_home=self.q0, opts={"enforce_limits": False})["verify"]
        self.assertFalse(enforced["pass"]); self.assertGreater(enforced["unreachable"], 0); self.assertEqual(enforced["limit_violations"], 0)
        self.assertFalse(raw["pass"]); self.assertGreater(raw["limit_violations"], 0)
        self.assertEqual(raw["limit_violation_first"][1], "joint1")

    def test_self_collision_is_detected(self):
        tr = copy.deepcopy(self.p["trajectory"])
        tr["q"][5] = [0.0, 2.9, 2.9]                      # fold link 3 back over link 1
        self.assertGreater(D.verify(self.ch, tr)["self_collisions"], 0)

    def test_generic_chain_six_dof(self):
        ch = RB.load_chain(KIN / "arm_6_dof.urdf")
        q0, _ = D.home(ch, [1.2, 0, 0.3], [0, 0.6, -1.0, 0.5, 0.3, 0])
        sq = [[[-0.2, -0.2], [0.2, -0.2], [0.2, 0.2], [-0.2, 0.2], [-0.2, -0.2]]]
        v = D.plan(ch, sq, {"origin": [1.2, 0, 0.3], "u": [1, 0, 0], "v": [0, 1, 0]}, q_home=q0, opts={"pen_lift_ik": 0.03})["verify"]
        self.assertTrue(v["pass"], v)

    def test_world_is_valid_and_carries_its_verification(self):
        w = D.world(self.p)
        self.assertEqual(WD.check(w), [])
        self.assertTrue(w["verify"]["V-16"]["pass"])


class CommittedWorldTests(unittest.TestCase):
    def test_committed_drawing_world_is_valid_and_passed(self):
        w = WD.load(ENGINE / "worlds" / "drawing_robot.world.json")
        self.assertEqual(WD.check(w), [])
        self.assertTrue(w["verify"]["V-16"]["pass"])
        tr = w["entities"][[e["id"] for e in w["entities"]].index("arm")]["trajectory"]
        self.assertEqual(RB.K.check_trajectory(RB.to_robot(w["entities"][3]["chain"]), tr["q"]), [])


@unittest.skipUnless(BROWSER, "no headless browser: %s" % WHY)
class BrowserInkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="we_draw_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_runtime_ink_matches_intended_strokes(self):
        w = WD.load(ENGINE / "worlds" / "drawing_robot.world.json")
        r = headless.render_world(w, self.tmp / "s.png", view="top", w=400, h=300, selftest="robot", timeout_s=120)
        self.assertTrue(r["ok"], r["reason"])
        x = r["result"]
        self.assertLess(x["ink_err_max_m"], 1e-4, x)      # runtime FK (JS) vs planner targets
        self.assertEqual(x["ink_segments"], x["pen_pairs"])
        self.assertGreater(x["mid_index"], 0)

    def test_mid_drawing_render(self):
        w = WD.load(ENGINE / "worlds" / "drawing_robot.world.json")
        t = w["verify"]["V-16"]["duration_s"] / 2
        r = headless.render_world(w, self.tmp / "m.png", view="aerial", w=640, h=400, t=t, timeout_s=120)
        self.assertTrue(r["ok"], r["reason"])
        st = pngcheck.stats(self.tmp / "m.png")
        self.assertEqual((st["w"], st["h"]), (640, 400))
        self.assertGreater(st["lum_sd"], 5.0, st)


if __name__ == "__main__":
    unittest.main()
