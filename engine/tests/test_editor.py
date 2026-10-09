# -*- coding: utf-8 -*-
"""World editor (T-01) with forbidden list (W-01), glossary (W-05), rule switches (E-03), generator enforcement (X-03)
and direct edits as studio versions (E-01). Browser tests drive the editor's own controls on a PC-size and a
phone-size screen. Run from engine/."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from worldengine import constraints as CS, headless, plugins as PL, world as WD  # noqa: E402
from worldengine.studio import server as SV, session as SS, tools as TL  # noqa: E402

NODE = shutil.which("node")
BROWSER, WHY = headless.available()
RULES_FIX = ENGINE / "runtime" / "tests" / "fixtures_rules.json"
YEOBAEK = WD.load(ENGINE / "worlds" / "ref_yeobaek.world.json")
BAROQUE = WD.load(ENGINE / "worlds" / "ref_festival_baroque.world.json")


class RulesTests(unittest.TestCase):
    @unittest.skipUnless(NODE, "node not installed")
    def test_python_and_js_violations_agree(self):
        fx = json.loads(RULES_FIX.read_text(encoding="utf-8"))
        js = json.loads(subprocess.run([NODE, str(ENGINE / "runtime" / "tests" / "check_cli.mjs"), str(RULES_FIX), "violations"],
                                       capture_output=True, text=True, check=True).stdout)
        self.assertEqual(len(fx), len(js))
        for f, j in zip(fx, js):
            with self.subTest(f["name"]):
                self.assertEqual(CS.violations(f["world"]), j)
                self.assertEqual(WD.check(f["world"]), [])

    def test_switches_and_per_body_exceptions(self):
        by = {f["name"]: f["world"] for f in json.loads(RULES_FIX.read_text(encoding="utf-8"))}
        self.assertEqual(CS.violations(by["dimension series switched off"]), [])
        kinds = [(v["entity"], v["field"]) for v in CS.violations(by["forbidden kinds"])]
        self.assertIn(("arm", "type"), kinds)                       # "robot" forbids robot.arm ...
        self.assertNotIn(("rob", "type"), kinds)                    # ... but not a type merely starting with the letters
        self.assertNotIn("bx", [v["entity"] for v in CS.violations(by["forbidden kinds"])])     # ignore_rules: forbidden
        self.assertFalse(any(v["value"] == "전쟁" for v in CS.violations(by["forbidden kinds"])))  # switched-off item

    def test_reference_worlds_have_no_violations(self):
        for n in ("ref_yeobaek", "ref_festival_baroque", "ref_modulor", "drawing_robot", "contradiction_garden", "talking_garden"):
            with self.subTest(n):
                self.assertEqual(CS.violations(WD.load(ENGINE / "worlds" / (n + ".world.json"))), [])


class GeneratorEnforcementTests(unittest.TestCase):
    """X-03: the core measures what a plugin made against the world's rules, and refuses it."""
    def setUp(self):
        self.P = PL.discover()

    def test_reference_outputs_obey_their_worlds(self):
        for n in ("ref_yeobaek", "ref_festival_baroque", "ref_modulor"):
            w = WD.load(ENGINE / "worlds" / (n + ".world.json"))
            for name, p in self.P.items():
                with self.subTest(world=n, plugin=name):
                    self.assertEqual(PL.generate(p, w)["rules"], {"ok": True, "violations": []})

    def test_forbidden_colour_in_output_is_refused_unless_switched_off(self):
        w = copy.deepcopy(YEOBAEK)
        ink = w["rules"]["constraints"][[c["kind"] for c in w["rules"]["constraints"]].index("palette")]["colours"][-1]
        w["forbidden"] = [{"kind": "colour", "value": ink}]
        with self.assertRaises(PL.RuleViolation) as cm:
            PL.generate(self.P["plotter"], w)
        self.assertEqual(cm.exception.violations[0]["kind"], "forbidden")
        r = PL.generate(self.P["plotter"], w, enforce=False)                  # review screens see it, marked
        self.assertFalse(r["rules"]["ok"])
        w["forbidden"][0]["enabled"] = False                                  # E-03: the artist switches it off
        self.assertTrue(PL.generate(self.P["plotter"], w)["rules"]["ok"])

    def test_budget_and_palette_on_svg(self):
        w = copy.deepcopy(BAROQUE)
        w["rules"]["constraints"] = [{"kind": "max_elements", "value": 5}]
        with self.assertRaises(PL.RuleViolation) as cm:                       # the plotter does not shrink to a budget:
            PL.generate(self.P["plotter"], w)                                 # the core refuses its 11 elements
        self.assertEqual([(v["kind"], v["value"]) for v in cm.exception.violations], [("max_elements", 11)])
        w["rules"]["constraints"][0]["enabled"] = False
        self.assertTrue(PL.generate(self.P["plotter"], w)["rules"]["ok"])
        w["rules"]["constraints"] = [{"kind": "palette", "colours": ["#000000", "#ffffff"]}]
        out = PL.generate(self.P["image_svg"], w)                             # image_svg uses the palette as given
        self.assertTrue(out["rules"]["ok"])
        bad = copy.deepcopy(w); bad["rules"]["constraints"][0]["colours"] = ["#000000"]
        r = PL.generate(self.P["plotter"], bad, enforce=False)                # one colour: ink only, no sheet -- obeys
        self.assertTrue(r["rules"]["ok"], r["rules"])
        self.assertNotIn("<rect", r["artifact"])

    def test_conformance_reports_rule_breaking_as_x03_not_as_a_crash(self):
        from worldengine import conformance as CF
        blind = {"name": "blind", "version": "0", "medium": "image", "translate": lambda a: {"n": 3},
                 "generate": lambda w, i, p: {"artifact": '<svg xmlns="http://www.w3.org/2000/svg">' + '<rect fill="#ff00ff"/>' * p["n"] + "</svg>", "media_type": "image/svg+xml"},
                 "self_assess": lambda w, a: {"score": 0.5, "notes": "x"}, "ports": lambda w, p: {"palette": ["#ff00ff"], "tempo_bpm": None, "events": []}}
        rows = {r["clause"]: r for r in CF.run(blind, [YEOBAEK])}
        self.assertTrue(rows["G-01"]["ok"])
        self.assertFalse(rows["X-03"]["ok"])
        self.assertIn("palette", rows["X-03"]["detail"])
        self.assertTrue(rows["V-05"]["ok"])                                    # the other clauses are still judged

    def test_plotter_paper_comes_from_the_palette(self):
        svg = PL.generate(self.P["plotter"], YEOBAEK)["artifact"]
        self.assertNotIn("#fffdf7", svg)                                       # it used an off-palette sheet before X-03

    def test_studio_preview_reports_refusal(self):
        w = copy.deepcopy(YEOBAEK); w["forbidden"] = [{"kind": "word", "value": "svg"}]
        r = TL.run(SS.Session(w), "preview", {"plugin": "image_svg"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["violations"][0]["kind"], "forbidden")
        self.assertIn("작가", r["note"])

    def test_agent_sees_glossary_and_active_forbidden_items(self):
        w = copy.deepcopy(YEOBAEK)
        w["glossary"] = [{"term": "숨", "meaning": "쉬는 곳"}]
        w["forbidden"] = [{"kind": "word", "value": "네온"}, {"kind": "word", "value": "꺼둠", "enabled": False}]
        d = TL.run(SS.Session(w), "describe_world", {})
        self.assertEqual(d["glossary"], w["glossary"])
        self.assertEqual([f["value"] for f in d["forbidden"]], ["네온"])


class DirectEditTests(unittest.TestCase):
    """E-01: what the artist changes in the editor becomes a version of the work."""
    def test_edit_is_a_version_that_can_be_reverted(self):
        s = SS.Session(YEOBAEK)
        w = s.world; w["glossary"] = [{"term": "숨", "meaning": "쉬는 곳"}]
        r = s.edit(w, "용어")
        self.assertEqual((r["version"], s.versions[-1]["why"]), (1, "작가가 직접 고침: 용어"))
        self.assertIn("기타: 용어집", r["summary"])
        self.assertTrue(s.edit(w)["unchanged"])                                # same world again: no new version
        p = TL.run(s, "propose_revert", {"to_version": 0, "why": "아까가 나았어"})
        s.apply(p["proposal"])
        self.assertNotIn("glossary", s.world)

    def test_invalid_edit_refused(self):
        s = SS.Session(YEOBAEK)
        w = s.world; w["forbidden"] = [{"kind": "colour", "value": "pink"}]
        with self.assertRaises(ValueError):
            s.edit(w)
        self.assertEqual(len(s.versions), 1)

    def test_concept_text_edits_are_seen(self):
        w = WD.load(ENGINE / "worlds" / "drawing_robot.world.json")
        s = SS.Session(w); w2 = s.world; w2["concepts"][0]["statement"] += " (고침)"
        self.assertIn("개념 고침: " + w2["concepts"][0]["id"], s.edit(w2)["summary"])

    def test_edit_endpoint_needs_the_token(self):
        with tempfile.TemporaryDirectory() as d:
            st = SV.Studio(YEOBAEK, "t", None, data=d)
            srv = SV.http.server.ThreadingHTTPServer(("127.0.0.1", 0), SV.make_handler(st))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                body = json.dumps({"world": YEOBAEK}).encode()
                url = "http://127.0.0.1:%d/api/edit" % srv.server_address[1]
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}))
                self.assertEqual(cm.exception.code, 403)
                self.assertEqual(len(st.session.versions), 1)
            finally:
                srv.shutdown(); srv.server_close()


@unittest.skipUnless(BROWSER, "no browser: " + WHY)
class EditorBrowserTests(unittest.TestCase):
    def run_editor(self, world, w, h):
        with tempfile.TemporaryDirectory() as d:
            r = headless.render_world(world, Path(d) / "e.png", w=w, h=h, selftest="editor", timeout_s=180, page="editor.html")
        self.assertTrue(r["ok"], r.get("reason"))
        return r["result"]

    def check_run(self, res, w, h):
        S = res["steps"]
        self.assertEqual(S["start"]["errors"], 0)
        self.assertEqual(S["tap"]["picked"], S["tap"]["wanted"])                          # tap in 3D selects that body
        self.assertEqual(S["move"]["pos"][:2], S["move"]["want"])
        self.assertEqual(S["move"]["object"], S["move"]["want"])                          # and the 3D body moved
        self.assertEqual((S["slider"]["density"], S["slider"]["undo_steps"]), (0.2, 1))    # one drag = one undo step
        self.assertEqual((S["palette"]["after_colour"], S["palette"]["rule_off"], S["palette"]["rule_on"], S["palette"]["ignored"]), (1, 0, 1, 0))
        self.assertIs(S["palette"]["enabled_field"], False)
        self.assertIn("palette", S["palette"]["ignore_rules"])
        self.assertGreaterEqual(S["forbidden"]["hits"], 1)
        self.assertEqual(S["forbidden"]["off"], 0)
        self.assertTrue(S["forbidden"]["bad_colour_refused"])
        self.assertTrue(S["glossary"]["duplicate_refused"])
        self.assertEqual((S["add"]["bodies"], S["add"]["in_scene"]), (1, True))
        self.assertEqual((S["duplicate"]["after_dup"], S["duplicate"]["first_press_kept"], S["duplicate"]["after_delete"], S["duplicate"]["in_scene"]), (2, True, 1, False))
        self.assertTrue(S["rename_refused"])
        self.assertTrue(S["invalid"]["export_blocked"])
        self.assertEqual(S["invalid"]["after_undo"], 0)
        self.assertEqual((S["undo"]["undone"], S["undo"]["redone"]), (1, 1))
        ex = res["exported"]
        self.assertEqual(WD.check(ex), [])                                                # Python accepts what the editor wrote
        self.assertEqual(CS.violations(ex), res["js_violations"])
        self.assertEqual(ex["glossary"], [{"term": "숨", "meaning": "비어 있는 곳이 아니라 쉬는 곳"}])
        self.assertEqual(res["memory"]["before"], res["memory"]["after"])                 # reloads free the old scene
        L = res["layout"]
        self.assertEqual(L["inner"], [w, h])
        self.assertLessEqual(L["scroll_width"], w)                                        # nothing wider than the screen
        self.assertGreaterEqual(L["min_target_px"], 44)
        self.assertEqual(L["canvas"], L["view"])
        return L

    def test_pc(self):
        L = self.check_run(self.run_editor(YEOBAEK, 1280, 800), 1280, 800)
        self.assertFalse(L["stacked"])

    def test_phone(self):
        L = self.check_run(self.run_editor(BAROQUE, 390, 844), 390, 844)
        self.assertTrue(L["stacked"])                                                     # 3D on top, controls below

    def test_save_from_editor_becomes_a_studio_version(self):
        with tempfile.TemporaryDirectory() as d:
            st = SV.Studio(YEOBAEK, "t", None, data=d)
            srv = SV.http.server.ThreadingHTTPServer(("127.0.0.1", 0), SV.make_handler(st))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                url = "http://127.0.0.1:%d/runtime/editor.html?studio=1&t=%s&headless=1&selftest=editor_save&w=390&h=844" % (srv.server_address[1], st.token)
                r = headless.render_url(url, Path(d) / "s.png", 390, 844, timeout_s=120, real_time_s=10)
            finally:
                srv.shutdown(); srv.server_close()
        self.assertTrue(r["ok"], r.get("reason"))
        self.assertTrue(r["result"]["save_visible"])
        self.assertIn("판 1", r["result"]["status"])
        self.assertEqual([v["why"] for v in st.session.versions], ["시작", "작가가 직접 고침: 편집기에서 직접 고침"])
        self.assertEqual(st.session.world["rules"]["axes"]["texture"], 0.77)


if __name__ == "__main__":
    unittest.main()
