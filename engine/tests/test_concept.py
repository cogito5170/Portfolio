# -*- coding: utf-8 -*-
"""Concept card (SPEC 6절 2단계 '개념 카드 1개'): a concept's rules change the plan, are measured on the result,
and anything the runtime cannot do is reported, not dropped. Run from engine/."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from worldengine import concept as CP, draw as D, robot as RB, world as WD  # noqa: E402

PLANE = {"origin": [0, 0, 0], "u": [1, 0, 0], "v": [0, 1, 0]}


class ConceptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ch = RB.load_chain(ENGINE.parent / "kinematics" / "planar_3_dof.urdf")
        cls.q0, _ = D.home(cls.ch, [1.9, 0, 0], [-0.6, 0.7, 0.6])

    def _run(self, concepts):
        eff, opts, strokes = CP.apply(concepts, "arm", D.demo_strokes())
        p = D.plan(self.ch, strokes, PLANE, q_home=self.q0, opts=opts)
        return eff, CP.measure(eff, p["verify"]), p["verify"]

    def test_demo_concept_card_is_valid_and_sourced_honestly(self):
        w = {"format": "world/1", "name": "w", "entities": [{"type": "box", "id": "arm"}], "concepts": [CP.KLEE_WALK]}
        self.assertEqual(WD.check(w), [])
        kinds = {s["kind"] for s in CP.KLEE_WALK["sources"]}
        self.assertNotIn("quote", kinds)                    # a paraphrase must not pose as a quote

    def test_concept_changes_the_drawing_and_is_kept(self):
        _, _, without = self._run([])
        eff, ok, with_ = self._run([CP.KLEE_WALK])
        self.assertGreater(without["pen_lifts"], 0)
        self.assertEqual(with_["pen_lifts"], 0)
        self.assertGreater(with_["duration_s"], without["duration_s"])   # slower pen
        self.assertTrue(ok, eff)
        self.assertTrue(all(e["applied"] and e["met"] for e in eff), eff)
        self.assertTrue(with_["pass"], with_)                            # V-16 still holds

    def test_unknown_or_unsupported_rules_are_reported(self):
        c = copy.deepcopy(CP.KLEE_WALK)
        c["rules"] = [{"param": "pen.colour", "value": "gold"}, {"param": "pen.lifts", "value": 3}]
        eff, _, _ = CP.apply([c], "arm", D.demo_strokes())
        self.assertEqual([e["applied"] for e in eff], [False, False])
        self.assertTrue(all(e["note"] for e in eff))

    def test_concept_for_another_entity_does_not_apply(self):
        c = copy.deepcopy(CP.KLEE_WALK); c["drives"] = ["someone_else"]
        eff, opts, _ = CP.apply([c], "arm", D.demo_strokes())
        self.assertEqual((eff, opts), ([], {}))

    def test_measure_catches_a_rule_the_plan_broke(self):
        eff, _, _ = CP.apply([CP.KLEE_WALK], "arm", D.demo_strokes())
        self.assertFalse(CP.measure(eff, {"pen_lifts": 2, "pen_speed_max_mps": 0.15}))
        self.assertFalse(CP.measure(eff, {"pen_lifts": 0, "pen_speed_max_mps": 0.25}))

    def test_committed_world_carries_card_and_measured_effects(self):
        w = WD.load(ENGINE / "worlds" / "drawing_robot.world.json")
        self.assertEqual(WD.check(w), [])
        self.assertEqual([c["id"] for c in w["concepts"]], ["line_walk"])
        eff = w["verify"]["concept_effects"]
        self.assertTrue(eff and all(e["met"] for e in eff), eff)
        self.assertEqual(w["verify"]["V-16"]["pen_lifts"], 0)
        self.assertTrue(w["verify"]["V-16"]["pass"])


if __name__ == "__main__":
    unittest.main()
