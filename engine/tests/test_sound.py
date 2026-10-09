# -*- coding: utf-8 -*-
"""M-02 procedural sound plugin (plugins/sound_synth), added as a plugin only: a fresh V-02 check.
Run from engine/."""
from __future__ import annotations

import copy
import io
import sys
import unittest
import wave
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from worldengine import conformance as CF, plugins as PL, world as WD  # noqa: E402

REF = {n: WD.load(ENGINE / "worlds" / (n + ".world.json")) for n in ("ref_yeobaek", "ref_festival_baroque", "ref_modulor")}
CORE = sorted([*(ENGINE / "worldengine").rglob("*.py"), *(ENGINE / "runtime" / "src").rglob("*.js"), ENGINE / "runtime" / "index.html"])


class SoundPluginTests(unittest.TestCase):
    P = PL.discover()["sound_synth"]

    def test_conformance_on_every_reference_world(self):
        rows = CF.run(self.P, list(REF.values()))
        self.assertEqual(len(rows), 3 * 6)
        self.assertEqual([r for r in rows if not r["ok"]], [])

    def test_the_core_does_not_know_it(self):
        """V-02: the medium arrived as a directory; no core file names it."""
        hits = [str(f.relative_to(ENGINE)) for f in CORE if "__pycache__" not in f.parts and "sound_synth" in f.read_text(encoding="utf-8")]
        self.assertEqual(hits, [])

    def test_wav_length_follows_tempo_and_bars_and_is_reproducible(self):
        for n, w in REF.items():
            with self.subTest(n):
                p = self.P["translate"](PL.axes_of(w))
                r = PL.generate(self.P, w)
                f = wave.open(io.BytesIO(r["artifact"]), "rb")
                self.assertEqual((f.getnchannels(), f.getsampwidth(), f.getframerate()), (1, 2, 16000))
                want = min(12.0, 4 * p["bars"] * 60 / p["tempo_bpm"])
                self.assertAlmostEqual(f.getnframes() / 16000, want, places=3)
                self.assertEqual(PL.regenerate(self.P, r["recipe"], w)["artifact"], r["artifact"])     # V-05

    def test_the_worlds_colours_are_its_pitches(self):
        from importlib import util
        mod = util.spec_from_file_location("ss", self.P["path"]); m = util.module_from_spec(mod); mod.loader.exec_module(m)
        sets = {n: m.pitches(w) for n, w in REF.items()}
        self.assertEqual(len({tuple(v) for v in sets.values()}), 3)                      # three worlds, three pitch sets
        no_pal = copy.deepcopy(REF["ref_yeobaek"]); no_pal["rules"]["constraints"] = []
        self.assertEqual(len(m.pitches(no_pal)), 6)                                      # no palette: the pentatonic
        off = copy.deepcopy(REF["ref_yeobaek"])
        for c in off["rules"]["constraints"]:
            c["enabled"] = False                                                         # E-03: palette switched off
        self.assertEqual(m.pitches(off), m.pitches(no_pal))

    def test_axes_move_the_sound(self):
        w = copy.deepcopy(REF["ref_modulor"])
        a = PL.generate(self.P, w)["notes"]
        w["rules"]["axes"]["motion"] = 1.0; w["rules"]["axes"]["density"] = 1.0
        b = PL.generate(self.P, w)["notes"]
        self.assertNotEqual(a, b)
        self.assertIn("160 bpm", b)


if __name__ == "__main__":
    unittest.main()
