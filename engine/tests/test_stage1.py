# -*- coding: utf-8 -*-
"""Stage 1 core (SPEC 6절 1단계): five-ingredient worlds, generator plugin contract, conformance kit (G-05),
reference worlds expressed without core changes (V-01), V-02 by hashing, V-05, V-04 first measurement.
Run from engine/."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from worldengine import conformance as CF, constraints as CS, headless, measure as MS, plugins as PL, world as WD  # noqa: E402
from worldengine import png as pngcheck  # noqa: E402

REF = ["ref_yeobaek", "ref_festival_baroque", "ref_modulor"]
CORE_TYPES = {"group", "box", "cylinder", "cone", "sphere", "capsule", "torus", "plane", "ground", "text", "light", "terrain", "path", "person", "arch"}
BROWSER, WHY = headless.available()


def core_manifest() -> dict:
    """sha256 of every core file: the Python package and the runtime (plugins/ is not core)."""
    files = sorted([*(ENGINE / "worldengine").rglob("*.py"), *(ENGINE / "runtime" / "src").rglob("*.js"), ENGINE / "runtime" / "index.html"])
    return {str(f.relative_to(ENGINE)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files if "__pycache__" not in f.parts}


NEW_PLUGIN = textwrap.dedent('''
    """A plugin written by the test, outside the repo: if this registers and conforms, adding plugins needs no core edit."""
    def translate(axes):
        return {"bars": 1 + int(round(20 * axes.get("density", 0.5))), "seed": 1}
    def _rules(world):                                   # a well-behaved plugin reads the world's palette and budget (X-03)
        cs = [c for c in (world.get("rules") or {}).get("constraints") or [] if c.get("enabled", True) is not False]
        pal = next((c["colours"] for c in cs if c["kind"] == "palette"), ["#ffffff", "#333333"])
        cap = next((c["value"] - 1 for c in cs if c["kind"] == "max_elements"), 10 ** 6)
        return pal[0], pal[-1], max(1, cap)
    def generate(world, intent, params):
        bg, ink, cap = _rules(world)
        bars = "".join('<rect x="%d" y="10" width="4" height="80" fill="%s"/>' % (10 + 8 * i, ink) for i in range(min(params["bars"], cap)))
        return {"artifact": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><rect x="0" y="0" width="200" height="100" fill="%s"/>' % bg + bars + "</svg>",
                "media_type": "image/svg+xml"}
    def self_assess(world, artifact):
        return {"score": 1.0, "notes": "bars drawn"}
    def ports(world, params):
        return {"palette": ["#333333"], "tempo_bpm": None, "events": []}
    PLUGIN = {"name": "test_bars", "version": "0", "medium": "image", "translate": translate, "generate": generate,
              "self_assess": self_assess, "ports": ports}
''')


class ReferenceWorldTests(unittest.TestCase):
    worlds = {n: WD.load(ENGINE / "worlds" / (n + ".world.json")) for n in REF}

    def test_valid_five_ingredient_worlds(self):
        for n, w in self.worlds.items():
            with self.subTest(n):
                self.assertEqual(WD.check(w), [])
                self.assertTrue(w["concepts"] and w["rules"]["axes"] and w["entities"] and w["expressions"])
                self.assertTrue(any(e.get("behaviors") for e in w["entities"]) or n == "ref_modulor")

    def test_bodies_use_core_types_only(self):
        """V-01: no world-specific entity type -- each is expressed with the core plugin as it is."""
        def types(es):
            for e in es:
                yield e["type"]; yield from types(e.get("children", []))
        for n, w in self.worlds.items():
            with self.subTest(n):
                self.assertLessEqual(set(types(w["entities"])), CORE_TYPES)

    def test_worlds_keep_their_own_rules(self):
        for n, w in self.worlds.items():
            with self.subTest(n):
                self.assertEqual(CS.violations(w), [])

    def test_constraint_checker_catches_planted_violations(self):
        w = json.loads(json.dumps(self.worlds["ref_modulor"]))
        w["entities"].append({"id": "rogue", "type": "box", "pos": [1, 1, 0], "size": [1.0, 0.43, 0.43]})       # 1.0 m is not in the series
        w["materials"]["neon"] = {"color": "#00ff00"}
        v = CS.violations(w)
        self.assertIn(("rogue", "size", 1.0, "dimension_series"), [(x["entity"], x["field"], x["value"], x["kind"]) for x in v])
        self.assertIn("palette", [x["kind"] for x in v])
        y = json.loads(json.dumps(self.worlds["ref_yeobaek"]))
        y["entities"] += [{"type": "sphere", "radius": 0.1}] * 5
        self.assertIn("max_elements", [x["kind"] for x in CS.violations(y)])

    def test_modulor_numbers_are_the_cited_series_and_labelled(self):
        w = self.worlds["ref_modulor"]
        c = w["rules"]["constraints"][0]
        self.assertEqual(sorted(c["series"]["red"] + c["series"]["blue"]), c["values_m"])
        red = c["series"]["red"]
        self.assertEqual(red[-2], 1.83)                                   # the 183 cm figure the series is built on
        src = w["concepts"][0]["sources"][0]
        self.assertEqual((src["who"], src["kind"]), ("Le Corbusier", "paraphrase"))
        self.assertIn("Le Modulor", src["where"])

    @unittest.skipUnless(BROWSER, "no headless browser: %s" % WHY)
    def test_each_renders_through_the_unmodified_runtime(self):
        tmp = Path(tempfile.mkdtemp(prefix="we_ref_"))
        try:
            for n, w in self.worlds.items():
                with self.subTest(n):
                    r = headless.render_world(w, tmp / (n + ".png"), view="aerial", w=480, h=300, t=2.0, timeout_s=120)
                    self.assertTrue(r["ok"], r["reason"])
                    st = pngcheck.stats(tmp / (n + ".png"))
                    self.assertGreater(st["distinct"], 20, st)          # not blank (여백 is nearly empty and the Modulor street flat-shaded by design)
                    self.assertGreater(st["lum_sd"], 2.0, st)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PluginTests(unittest.TestCase):
    worlds = [WD.load(ENGINE / "worlds" / (n + ".world.json")) for n in REF]

    def test_conformance_all_plugins_all_reference_worlds(self):
        """V-06 / G-05: every bundled plugin passes every clause on every reference world (incl. V-05 reproducibility)."""
        rows = []
        for p in PL.discover().values():
            rows += CF.run(p, self.worlds)
        self.assertEqual(len(rows), len(PL.discover()) * 3 * 6)
        self.assertEqual([r for r in rows if not r["ok"]], [])

    def test_v02_new_plugin_needs_no_core_change(self):
        before = core_manifest()
        tmp = Path(tempfile.mkdtemp(prefix="we_plug_"))
        try:
            (tmp / "test_bars").mkdir()
            (tmp / "test_bars" / "plugin.py").write_text(NEW_PLUGIN, encoding="utf-8")
            found = PL.discover(extra_dirs=[tmp])
            self.assertIn("test_bars", found)
            rows = CF.run(found["test_bars"], self.worlds)
            self.assertEqual([r for r in rows if not r["ok"]], [])
            for p in found.values():                                       # register and use every plugin
                PL.generate(p, self.worlds[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(core_manifest(), before)                          # 0 core bytes changed

    def test_conformance_kit_fails_a_broken_plugin(self):
        bad = dict(PL.discover()["image_svg"])
        bad["generate"] = lambda world, intent, params: {"artifact": "<svg/>%f" % __import__("random").random(), "media_type": "image/svg+xml"}
        rows = CF.run(bad, self.worlds[:1])
        self.assertFalse(next(r for r in rows if r["clause"] == "V-05")["ok"])
        self.assertFalse(next(r for r in rows if r["clause"] == "G-02")["ok"])

    def test_recipe_from_another_world_version_is_refused(self):
        p = PL.discover()["image_svg"]
        r = PL.generate(p, self.worlds[0])
        w2 = json.loads(json.dumps(self.worlds[0])); w2["version"] = "1.1"
        with self.assertRaises(ValueError):
            PL.regenerate(p, r["recipe"], w2)

    def test_edited_translation_is_used(self):
        p = PL.discover()["image_svg"]
        w = self.worlds[1]
        params = p["translate"](PL.axes_of(w)); params["n"] = 5
        r = PL.generate(p, w, params=params)
        self.assertEqual(r["recipe"]["params"]["n"], 5)
        self.assertEqual(r["artifact"].count("<circle") + r["artifact"].count("<rect") + r["artifact"].count("<path") + r["artifact"].count("<line") - 1, 5)


class MeasureTests(unittest.TestCase):
    def test_measurer_is_independent_of_plugins(self):
        src = (ENGINE / "worldengine" / "measure.py").read_text(encoding="utf-8")
        self.assertNotIn("plugins", src.replace("plugins never call it", ""))
        self.assertNotIn("self_assess", src)

    def test_measurer_on_known_svgs(self):
        empty = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect x="0" y="0" width="100" height="100" fill="#ffffff"/></svg>'
        self.assertEqual(MS.axes(empty)["density"], 0.0)
        circles = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' + "".join(
            '<circle cx="%d" cy="50" r="2" fill="#%s"/>' % (i * 5, c) for i, c in enumerate(["ff0000", "00ff00", "0000ff", "ffff00"] * 5)) + "</svg>"
        a = MS.axes(circles)
        self.assertEqual(a["form"], 1.0)
        self.assertAlmostEqual(a["colour"], 0.5 * 3 / 7 + 0.5 * 1.0)
        self.assertAlmostEqual(a["density"], __import__("math").log1p(20) / __import__("math").log1p(400))

    def test_v04_first_measurement_is_reported(self):
        """No target yet (SPEC: 측정 후 목표 설정). The test pins the method's output shape, not a pass threshold."""
        worlds = {n: WD.load(ENGINE / "worlds" / (n + ".world.json")) for n in REF}
        res = [{"plugin": pn, "world": n, "svg": PL.generate(p, w)["artifact"]} for pn, p in PL.discover().items()
               if p["medium"] in ("image", "drawing") for n, w in worlds.items()]                # the SVG measurer reads pictures
        rows = MS.distinctness(res, worlds)
        self.assertEqual(len(rows), 6)
        for r in rows:
            self.assertIn(r["own_rank"], (1, 2, 3))
            self.assertEqual(set(r["measured"]), set(MS.MEASURED))


if __name__ == "__main__":
    unittest.main()
