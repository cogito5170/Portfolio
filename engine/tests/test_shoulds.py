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

import shutil  # noqa: E402

import zipfile  # noqa: E402

from worldengine import footprint as FP, headless, licenses as LC, preserve as PV, robot as RB, video as VD, world as WD  # noqa: E402
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


class TourVideoTests(unittest.TestCase):
    def test_srt_times(self):
        caps = [{"t": 1.0, "text": "가", "seconds": 3}, {"t": 2.5, "text": "나", "seconds": 4}, {"t": 9.0, "text": "다", "seconds": 4}]
        self.assertEqual(VD.srt(caps, 10.0), "1\n00:00:01,000 --> 00:00:02,500\n가\n\n2\n00:00:02,500 --> 00:00:06,500\n나\n\n"
                                               "3\n00:00:09,000 --> 00:00:10,000\n다\n")

    @unittest.skipUnless(headless.available()[0] and shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs a browser and ffmpeg/ffprobe")
    def test_tour_video_has_every_frame_and_the_captions(self):
        w = WD.load(ENGINE / "worlds" / "talking_garden.world.json")
        with tempfile.TemporaryDirectory() as d:
            r = VD.tour_video(w, Path(d) / "t.mp4", w=320, h=180, fps=8)
            self.assertTrue(r["ok"], r.get("reason"))
            pr = VD.probe(r["mp4"])
            sub = Path(r["srt"]).read_text(encoding="utf-8")
        print("\nTOUR VIDEO %d frames, %.1f s, %s, %d captions" % (r["frames"], r["seconds"], r["encoder"], len(r["captions"])), file=sys.stderr)
        v = next(x for x in pr["streams"] if x["codec_type"] == "video")
        self.assertEqual((v["width"], v["height"], int(v["nb_frames"])), (320, 180, r["frames"]))
        self.assertTrue(any(x["codec_type"] == "subtitle" for x in pr["streams"]))
        stops = [st["caption"] for st in w["tours"][0]["stops"]]
        self.assertEqual([c["text"] for c in r["captions"]], stops)                  # every stop's caption, in order
        for c in stops:
            self.assertIn(c, sub)
        self.assertTrue(r["ended"])
        self.assertAlmostEqual(float(pr["format"]["duration"]), r["seconds"], delta=0.2)


class PreservationTests(unittest.TestCase):
    """N-06: a bundle plays and regenerates with the code that made it."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.zip = cls.tmp / "baroque.zip"
        cls.r = PV.bundle(WD.load(ENGINE / "worlds" / "ref_festival_baroque.world.json"), cls.zip)

    def rewrite(self, name, fn):
        out = self.tmp / ("t_%s.zip" % abs(hash(name)))
        with zipfile.ZipFile(self.zip) as a, zipfile.ZipFile(out, "w") as b:
            for i in a.infolist():
                data = a.read(i.filename)
                b.writestr(i, fn(data) if i.filename == name else data)
        return out

    def test_replay_regenerates_every_work_with_the_bundled_code(self):
        self.assertTrue(self.r["ok"], self.r)
        r = PV.replay(self.zip)
        print("\nBUNDLE %d files, %d bytes; replay %s" % (self.r["files"], self.r["bytes"], r["works"]), file=sys.stderr)
        self.assertTrue(r["ok"], r)
        self.assertEqual([w["identical"] for w in r["works"]], [True, True, True])
        self.assertTrue(r["engine"].startswith(r["dir"]))                          # ran from inside the bundle, not this repo
        m = json.loads(zipfile.ZipFile(self.zip).read("MANIFEST.json"))
        self.assertEqual(sorted(m["plugins"]), ["image_svg", "plotter", "sound_synth"])
        self.assertEqual(m["format"], "bundle/1")
        names = zipfile.ZipFile(self.zip).namelist()
        for must in ("index.html", "replay.py", "LICENSES.md", "work/world.json", "engine/vendor/three/LICENSE", "kinematics/kinematics.py"):
            self.assertIn(must, names)
        self.assertFalse(any("tests/" in n or "__pycache__" in n for n in names))

    def test_a_changed_file_is_found(self):
        r = PV.replay(self.rewrite("work/works/1_image_svg.svg", lambda b: b.replace(b"<svg", b"<svg data-x='1'", 1)))
        self.assertFalse(r["ok"]); self.assertEqual(r["integrity"]["changed"], ["work/works/1_image_svg.svg"])

    def test_the_bundled_plugin_is_what_runs(self):
        r = PV.replay(self.rewrite("engine/plugins/sound_synth/plugin.py", lambda b: b.replace(b"* 104729", b"* 104723", 1)))
        self.assertFalse(r["ok"])
        self.assertEqual([w["identical"] for w in r["works"]], [True, True, False])  # the edited copy made a different sound

    def test_paths_outside_the_bundle_are_refused(self):
        bad = self.tmp / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("../escape.txt", "x")
        self.assertFalse(PV.replay(bad)["ok"])

    @unittest.skipUnless(headless.available()[0], "no browser")
    def test_the_bundled_runtime_opens_the_work(self):
        d = self.tmp / "open"
        with zipfile.ZipFile(self.zip) as z:
            z.extractall(d)
        r = headless._shoot(d, "engine/runtime/index.html?world=../../work/world.json&works=../../work/works.json&headless=1&w=480&h=300", d / "s.png", 480, 300, 120)
        self.assertTrue(r["ok"], r.get("reason"))


class LicenseTableTests(unittest.TestCase):
    def test_facts_from_the_repository(self):
        rows = {r["component"]: r for r in LC.table()}
        three = rows["three.js r170 (vendor/three)"]
        self.assertEqual((three["license"], three["commercial"], three["shipped"]), ("MIT", "가능", True))
        core = next(r for k, r in rows.items() if k.startswith("worldengine core"))
        if not (REPO / "LICENSE").exists():
            self.assertEqual(core["license"], "없음 — 저장소 주인이 정할 일")           # not invented
        model = next(r for k, r in rows.items() if r["kind"].startswith("AI model"))
        from worldengine.studio import config
        self.assertIn(config.model(), model["component"]); self.assertEqual(model["commercial"], "확인 필요")
        self.assertTrue(all(r["notes"] == "AI 모델 없음 (절차적)" for k, r in rows.items() if k.startswith("plugin ")))

    def test_a_plugin_that_uses_a_model_says_so(self):
        r = LC.plugin_row("x", {"version": "1", "medium": "image", "uses_model": {"provider": "P", "model": "m-1", "terms": "P terms"}})
        self.assertIn("m-1", r["notes"])
        self.assertIn("확인 필요", LC.plugin_row("y", {"version": "1", "medium": "image"})["notes"])   # undeclared is not 'none'

    def test_published_site_and_bundle_carry_it(self):
        from worldengine import site
        with tempfile.TemporaryDirectory() as d:
            site.build(Path(d) / "s", world_files=[ENGINE / "worlds" / "ref_yeobaek.world.json"])
            md = (Path(d) / "s" / "LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("three.js r170", md); self.assertIn("plugin sound_synth", md)
        self.assertNotIn("스튜디오 대화 조수", md)                                   # a work's table lists what it contains


if __name__ == "__main__":
    unittest.main()
