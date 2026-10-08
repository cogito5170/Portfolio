# -*- coding: utf-8 -*-
"""Stage 4 (SPEC 6절 4단계): world physics, spatial sound, interaction, captions, tour, low-spec, talking character
(CH-01..04), V-18 scenario. No network, no key: live replies use a scripted fake client. Run from engine/.

V-18 driver, plainly: headless Chromium (chromium_headless_shell or full Chromium) started from Python, the page
runs the `scenario` self-test, which dispatches PointerEvents into the canvas and the joystick so the runtime's own
listeners handle them. It is not Playwright (not installable in this environment)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from worldengine import character as CH, exhibit as EX, headless, world as WD  # noqa: E402

GARDEN = ENGINE / "worlds" / "talking_garden.world.json"
SENTINEL_KEY = "sk-ant-TEST-SENTINEL-0000"
BROWSER, WHY = headless.available()


def walk(es):
    for e in es or []:
        yield e; yield from walk(e.get("children"))


class FakeClient:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []
        self.messages = self

    def create(self, **kw):
        self.requests.append(json.loads(json.dumps(kw, ensure_ascii=False)))
        return {"content": [{"type": "text", "text": self.replies.pop(0)}], "stop_reason": "end_turn"}


class CaptionCoverageTests(unittest.TestCase):
    def test_every_sound_line_and_tour_stop_in_every_repo_world_has_a_caption(self):
        sounds = lines = stops = 0
        for f in sorted((ENGINE / "worlds").glob("*.world.json")):
            w = WD.load(f)
            with self.subTest(f.name):
                self.assertEqual(WD.check(w), [])
                for e in walk(w["entities"]):
                    if e["type"] == "sound":
                        sounds += 1; self.assertTrue(e["caption"])
                    if e["type"] == "character":
                        lines += len(e["lines"]); self.assertTrue(all(e["lines"]))
                for t in w.get("tours", []):
                    stops += len(t["stops"]); self.assertTrue(all(s["caption"] for s in t["stops"]))
        self.assertGreater(sounds, 0); self.assertGreater(lines, 0); self.assertGreater(stops, 0)    # the test actually saw some

    def test_missing_captions_are_rejected(self):
        w = WD.load(GARDEN)
        w["entities"].append({"type": "sound", "id": "mute"})
        w["tours"][0]["stops"][0]["caption"] = ""
        bad = WD.check(w)
        self.assertTrue(any("sound without caption" in b for b in bad))
        self.assertTrue(any("caption is required" in b for b in bad))


@unittest.skipUnless(BROWSER, "no headless browser: %s" % WHY)
class RuntimeExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="we_exp_"))
        cls.res = {}
        for st, q in [("scenario", None), ("audio", None), ("physics", None), ("lowspec", {"lowspec": 1})]:
            r = headless.render_world(GARDEN, cls.tmp / (st + ".png"), view="eye", w=390, h=844, selftest=st, timeout_s=120, query=q)
            assert r["ok"], (st, r["reason"])
            cls.res[st] = r["result"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_v18_scenario(self):
        s = self.res["scenario"]
        self.assertEqual([(x["step"], x["ok"]) for x in s["steps"]],
                         [("enter", True), ("move+near", True), ("tap", True), ("talk", True), ("tour", True)])

    def test_sound_only_after_a_gesture_and_every_started_sound_captioned(self):
        a, s = self.res["audio"], self.res["scenario"]["steps"]
        self.assertTrue(a["before_gesture_null"]); self.assertTrue(a["after_gesture_created"])
        self.assertEqual(a["started"], a["sources"]); self.assertTrue(a["captioned"])
        self.assertTrue(s[0]["audio_before_gesture"])          # in the scenario too: nothing before the first touch

    def test_world_rules_drive_physics(self):
        p = self.res["physics"]
        self.assertEqual((p["time_scale"], p["g"]), (0.6, 1.62))
        self.assertAlmostEqual(p["world_t"], 2.0 * 0.6)
        self.assertAlmostEqual(p["spin_rad"], 15 * 3.141592653589793 / 180 * 1.2, places=9)
        self.assertAlmostEqual(p["drop_z"], 3 - 0.5 * 1.62 * 1.2 ** 2, places=9)

    def test_lowspec(self):
        self.assertEqual(self.res["lowspec"], {"lowspec": True, "pixel_ratio": 1, "shadows": False, "env": False})


class CharacterSafetyTests(unittest.TestCase):
    world = WD.load(GARDEN)

    def test_persona_comes_from_the_world(self):
        p = CH.persona(self.world, CH.find_character(self.world))
        for part in ("말하는 정원", "산책자", "느린 달의 정원", "어서 와요", "느긋하고 다정한"):
            self.assertIn(part, p)

    def test_pii_never_reaches_the_model(self):
        fc = FakeClient(["반가워요"])
        CH.Talk(self.world, fc).reply("s1", "내 메일은 kim.minsu@example.com 이고 전화는 010-1234-5678, 주민번호 900101-1234567 이야")
        sent = json.dumps(fc.requests, ensure_ascii=False)
        for secret in ("kim.minsu@example.com", "010-1234-5678", "900101-1234567"):
            self.assertNotIn(secret, sent)
        self.assertIn("[개인정보]", sent)

    def test_blocked_input_gets_persona_refusal_without_a_model_call(self):
        fc = FakeClient([])
        r = CH.Talk(self.world, fc).reply("s1", "f u c k you")
        self.assertEqual((r["reply"], r["filtered"]), (CH.REFUSAL, "input")); self.assertEqual(fc.requests, [])

    def test_blocked_or_long_output_is_replaced_or_cut(self):
        r = CH.Talk(self.world, FakeClient(["이건 porn 이야기"])).reply("s1", "안녕")
        self.assertEqual((r["reply"], r["filtered"]), (CH.REFUSAL, "output"))
        r = CH.Talk(self.world, FakeClient(["가" * 1000])).reply("s1", "안녕")
        self.assertEqual(len(r["reply"]), CH.MAX_OUT_CHARS)

    def test_length_caps_on_the_way_in_and_out(self):
        fc = FakeClient(["네"])
        CH.Talk(self.world, fc).reply("s1", "나" * 5000)
        self.assertEqual(len(fc.requests[0]["messages"][-1]["content"]), CH.MAX_IN)
        self.assertEqual(fc.requests[0]["max_tokens"], CH.MAX_TOKENS)

    def test_memory_is_short_and_forgets(self):
        now = [0.0]
        t = CH.Talk(self.world, FakeClient(["a%d" % i for i in range(20)]), clock=lambda: now[0])
        for i in range(10):
            t.reply("s1", "말 %d" % i)
        self.assertLessEqual(len(t.mem["s1"]["turns"]), 2 * CH.KEEP_TURNS)
        now[0] += CH.TTL_S + 1
        t.reply("s2", "다른 사람")
        self.assertNotIn("s1", t.mem)

    def test_exhibit_writes_nothing_logs_nothing_and_keeps_the_key(self):
        tmp = Path(tempfile.mkdtemp(prefix="we_exh_"))
        home, cwd = tmp / "home", tmp / "cwd"
        home.mkdir(); cwd.mkdir()
        old = os.getcwd()
        try:
            os.chdir(cwd)
            with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL_KEY, "HOME": str(home), "WE_STUDIO_DIR": str(tmp / "data")}):
                talk = CH.Talk(self.world, FakeClient(["안녕하세요, 산책자예요."] * 30))
                srv = EX.http.server.ThreadingHTTPServer(("127.0.0.1", 0), EX.make_handler(self.world, talk))
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                base = "http://127.0.0.1:%d" % srv.server_address[1]

                def call(path, data=None):
                    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"})
                    try:
                        with urllib.request.urlopen(req, timeout=30) as r:
                            return r.status, r.read().decode("utf-8", "replace")
                    except urllib.error.HTTPError as e:
                        return e.code, e.read().decode("utf-8", "replace")
                with mock.patch("sys.stderr") as err, mock.patch("sys.stdout") as out:
                    bodies = [call("/world.json")[1], call("/runtime/index.html")[1], call("/api/talk", {"sid": "v1", "text": "안녕, 내 번호는 010-9999-8888"})[1]]
                    self.assertFalse(err.write.called or out.write.called)          # no request log
                for b in bodies:
                    self.assertNotIn(SENTINEL_KEY, b); self.assertNotIn("010-9999-8888", b)
                self.assertIn("산책자", bodies[2])
                self.assertEqual(call("/api/talk", {"text": "x" * 5000})[0], 413)
                codes = [call("/api/talk", {"sid": "v2", "text": "또"})[0] for _ in range(EX.RATE[0] + 2)]
                self.assertIn(429, codes)
                self.assertEqual(call("/runtime/../worldengine/character.py")[0], 404)
                srv.shutdown()
            files = [str(p) for p in tmp.rglob("*") if p.is_file()]
            self.assertEqual(files, [])                                           # nothing written anywhere
        finally:
            os.chdir(old)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_without_key_exhibit_uses_scripted_lines(self):
        h = EX.make_handler(self.world, None)
        self.assertTrue(callable(h))
        with mock.patch.dict(os.environ, {}, clear=True):
            from worldengine.studio import server as S
            self.assertIsNone(S.make_client()[0])


if __name__ == "__main__":
    unittest.main()
