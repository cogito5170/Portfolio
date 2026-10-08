# -*- coding: utf-8 -*-
"""worldengine baseline tests. Run from engine/:  python3 -m unittest discover -s tests -v

The headless test renders for real (vendored three.js + Chromium) and is skipped -- visibly -- when no
browser is available; it never passes on a fallback image.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from worldengine import headless, html, layout, pipeline, scene as S  # noqa: E402
import pngcheck  # noqa: E402


class SceneTests(unittest.TestCase):
    def test_examples_convert_to_valid_scenes(self):
        ex = layout.examples()
        self.assertGreaterEqual(len(ex), 6)
        for name, L in ex.items():
            with self.subTest(name=name):
                self.assertEqual(S.check(layout.to_scene(L)), [])

    def test_check_reports_problems_instead_of_fixing(self):
        sc = S.new("bad", y_axis="up", bounds=(1, -1, 1))
        sc["boxes"].append({"id": "x", "type": "spaceship", "x0": 1, "y0": 0, "x1": 0, "y1": 1, "h": 1})
        bad = S.check(sc)
        self.assertTrue(any("y_axis" in b for b in bad))
        self.assertTrue(any("bounds" in b for b in bad))
        self.assertTrue(any("spaceship" in b for b in bad))
        self.assertTrue(any("x1<=x0" in b for b in bad))
        self.assertEqual(sc["y_axis"], "up")          # untouched

    def test_save_load_roundtrip(self):
        sc = layout.to_scene(layout.examples()["hongdae/F1"])
        with tempfile.TemporaryDirectory() as d:
            p = S.save(sc, Path(d) / "s.json")
            self.assertEqual(json.loads(Path(p).read_text(encoding="utf-8")), json.loads(json.dumps(sc)))


class HtmlTests(unittest.TestCase):
    def test_page_is_self_contained_except_three(self):
        sc = layout.to_scene(layout.examples()["hongdae/F1"])
        with tempfile.TemporaryDirectory() as d:
            page = Path(html.write(sc, Path(d) / "p.html")).read_text(encoding="utf-8")
        self.assertIn('"three/addons/"', page)
        self.assertIn("window.__done", page)
        self.assertNotIn("__THREE__", page)            # placeholder replaced

    def test_vendored_three_matches_declared_version(self):
        head = (ENGINE / "vendor" / "three" / "build" / "three.module.js").read_text(encoding="utf-8")[:2000]
        self.assertIn("const REVISION = '%s';" % html.THREE_VERSION.split(".")[1], head)


class PipelineHonestyTests(unittest.TestCase):
    def test_no_browser_never_claims_a_render(self):
        sc = layout.to_scene(layout.examples()["store_module/tobe"])
        with tempfile.TemporaryDirectory() as d:
            r = pipeline.run(sc, d, "t", views=["aerial"], try_browser=False)
            v = r["views"]["aerial"]
            self.assertFalse(v["backend"].startswith("three.js"))
            if v["png"] is None:
                self.assertEqual(v["backend"], pipeline.NONE)
                self.assertIn("matplotlib", v["reason"])
            else:
                self.assertEqual(v["backend"], pipeline.FALLBACK)
            self.assertTrue(Path(r["html"]).exists())


@unittest.skipUnless(headless.available()[0], "no headless browser: %s" % headless.available()[1])
class HeadlessRenderTests(unittest.TestCase):
    def test_render_is_full_frame_and_not_blank(self):
        sc = layout.to_scene(layout.examples()["hongdae/F1"])
        with tempfile.TemporaryDirectory() as d:
            p = html.write(sc, Path(d) / "p.html")
            png = Path(d) / "aerial.png"
            r = headless.render(p, png, view="aerial", w=640, h=400, timeout_s=120)
            self.assertTrue(r["ok"], r["reason"])
            self.assertTrue(r["backend"].startswith("three.js r170"))
            st = pngcheck.stats(png)
        self.assertEqual((st["w"], st["h"]), (640, 400))
        self.assertGreater(st["distinct"], 200, st)    # a blank/cleared canvas has a handful of colours
        self.assertGreater(st["lum_sd"], 10.0, st)
        self.assertGreater(st["bottom_distinct"], 5, st)

    def test_page_error_is_reported_not_screenshotted(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "broken.html"
            p.write_text('<!doctype html><html><body><script>window.__err = "boom";</script></body></html>', encoding="utf-8")
            r = headless.render(p, Path(d) / "x.png", w=200, h=100, timeout_s=60)
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["reason"])


if __name__ == "__main__":
    unittest.main()
