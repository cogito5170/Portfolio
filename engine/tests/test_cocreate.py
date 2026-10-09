# -*- coding: utf-8 -*-
"""Co-creation system (SPEC CC-01..CC-10). No network and no API key: providers are scripted (tests/cocreate_fakes.py);
the Anthropic and Gemini adapters are checked against fake transports for the request they build, not against the
real services."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import cocreate_fakes as F  # noqa: E402
from worldengine import footprint as FP, headless, world as WD  # noqa: E402
from worldengine.cocreate import agents as AG, lenses as LZ, measure as MS, production as PR, providers as PV, run as RN, schema as S  # noqa: E402
from worldengine.studio import agent as SA, server as SV, session as SS  # noqa: E402

WORLD = json.loads((HERE.parent / "worlds" / "ref_yeobaek.world.json").read_text(encoding="utf-8"))


def walk(n):
    if isinstance(n, dict):
        yield n
        for v in n.values():
            yield from walk(v)
    elif isinstance(n, list):
        for v in n:
            yield from walk(v)


class SchemaTests(unittest.TestCase):
    def test_every_object_closed_and_fully_required_no_bounds(self):
        for m in (S.CreativeBrief, S.IdeaDraft, S.RebuttalSet, S.CuratorReport, S.Realization):
            sc = S.json_schema(m)
            for n in walk(sc):
                if isinstance(n.get("properties"), dict) and n.get("type") == "object":
                    self.assertIs(n.get("additionalProperties"), False, m.__name__)
                    self.assertEqual(sorted(n["required"]), sorted(n["properties"]), m.__name__)
                for k in ("minimum", "maximum", "pattern", "minLength", "maxItems", "default"):
                    self.assertNotIn(k, {kk for kk, vv in n.items() if not isinstance(vv, dict)}, (m.__name__, k))

    def test_curator_has_no_number_anywhere(self):
        """CC-05: the curator gives reasons; there is no field a score could go in."""
        types = {n.get("type") for n in walk(S.json_schema(S.CuratorReport))}
        self.assertFalse(types & {"number", "integer"}, types)

    def test_brief_rules(self):
        b = json.loads(json.dumps(F.BRIEF))
        S.CreativeBrief.model_validate(b)
        b["constraints"]["forbidden"][1]["kind"] = None
        with self.assertRaises(ValueError):
            S.CreativeBrief.model_validate(b)
        b["constraints"]["forbidden"][1].update(kind="colour", value="red")
        with self.assertRaises(ValueError):
            S.CreativeBrief.model_validate(b)
        b = json.loads(json.dumps(F.BRIEF)); b["extra"] = 1
        with self.assertRaises(ValueError):
            S.CreativeBrief.model_validate(b)

    def test_reference_world_is_valid(self):
        self.assertEqual(WD.check(AG.REFERENCE), [])


class LensTests(unittest.TestCase):
    def test_views_are_built_in_code_and_differ(self):
        v = {k: LZ.view(k, F.BRIEF) for k in LZ.LENSES}
        self.assertNotIn("artist", v["emotion"]); self.assertIn("desired_effect", v["emotion"]["intent"])
        self.assertEqual(v["form"]["intent"], {"theme": "외로움"}); self.assertIn("artist", v["form"])
        self.assertEqual(set(v["audience"]), {"schema", "intent", "environment", "forbidden"})
        self.assertEqual(v["invert"], F.BRIEF)
        for a in v:
            for b in v:
                if a != b:
                    self.assertNotEqual(v[a], v[b], (a, b))

    def test_round1_alone_round2_sees_all(self):
        cards = [{"id": k, "lens_ko": LZ.LENSES[k]["ko"], **F.IDEAS[k]} for k in F.IDEAS]
        for k in LZ.LENSES:
            _, p1 = LZ.round1_prompt(k, F.BRIEF)
            self.assertFalse([c["title"] for c in cards if c["title"] in p1])
            s2, p2 = LZ.round2_prompt(k, F.BRIEF, cards)
            self.assertTrue(all(c["title"] in p2 for c in cards))
            self.assertIn("id: %s" % k, s2)

    def test_studio_assistant_marks_what_it_added(self):
        self.assertIn("제가 더한 것", SA.SYSTEM)                       # CC-07, decision 3: co-creator


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="we_cocreate_"))
        self.session = SS.Session(WORLD)

    def run_to_choose(self, **kw):
        R, a, g = F.router(**kw)
        r = RN.Run(R, self.session, self.tmp)
        r.start(F.SAID)
        return r, a, g

    def test_waits_for_the_artist_twice(self):
        r, a, g = self.run_to_choose()
        self.assertEqual(r.state["stage"], "brief_review")
        self.assertEqual(r.state["brief"]["intent"]["said"], F.SAID)          # verbatim, whatever the model wrote
        self.assertFalse([c for c in a.calls + g.calls if c["model"] == "IdeaDraft"])
        r.confirm_brief()
        self.assertEqual(r.state["stage"], "choose")
        self.assertFalse([c for c in a.calls + g.calls if c["model"] == "Realization"])
        self.assertEqual(len(self.session.proposals), 0)
        with self.assertRaises(ValueError):
            r.confirm_brief()

    def test_round1_independent_round2_rebuts_others_only(self):
        r, a, g = self.run_to_choose(); r.confirm_brief()
        self.assertEqual([c["id"] for c in r.state["cards"]], list(LZ.LENSES))
        self.assertEqual({c["provider"] for c in r.state["cards"]}, {"anthropic", "gemini"})
        titles = {k: v["title"] for k, v in F.IDEAS.items()}
        for c in a.calls + g.calls:
            if c["model"] == "IdeaDraft":
                self.assertFalse([t for t in titles.values() if t in c["prompt"]])
            if c["model"] == "RebuttalSet":
                self.assertTrue(all(t in c["prompt"] for t in titles.values()))
        self.assertEqual(len(r.state["rebuttals"]), 12)
        self.assertFalse([x for x in r.state["rebuttals"] if x["by"] == x["target"]])
        self.assertEqual(len(r.state["dropped_rebuttals"]), 4)

    def test_measurement_is_indicators_and_flags(self):
        r, *_ = self.run_to_choose(); r.confirm_brief()
        m = r.state["measured"]["ideas"]
        self.assertEqual([v["value"] for v in m["audience"]["machine_forbidden"]], ["#ff0000"])
        self.assertEqual(m["audience"]["judged_flags"][0]["types"], ["person"])
        self.assertEqual(m["invert"]["needs"], ["관객 수에 따라 빛을 바꾸는 기능 (엔진에 없음)"])
        self.assertTrue(all(not v["world_errors"] for v in m.values()))
        self.assertEqual(len(r.state["measured"]["pairs"]), 6)
        w = MS.sketch_world(r.state["cards"][1], r.state["brief"])
        self.assertAlmostEqual(m["form"]["covered_m2"], FP.area_table(w)["covered_m2"])
        self.assertEqual([p["idea"] for p in r.state["curator"]["shortlist"]], ["form", "emotion"])    # unknown id dropped

    def test_artist_may_choose_outside_shortlist_and_nothing_applies(self):
        r, *_ = self.run_to_choose(); r.confirm_brief()
        n0 = len(self.session.versions)
        r.choose("audience", "사람 모양은 빼고")
        self.assertEqual(r.state["stage"], "done", r.state.get("error"))
        self.assertEqual(r.state["choice"]["in_shortlist"], False)
        z = r.state["realization"]
        self.assertEqual(self.session.proposals[z["proposal"]]["status"], "pending")
        self.assertEqual(len(self.session.versions), n0)                      # A-02: the artist applies, not the run
        self.session.apply(z["proposal"])
        self.assertEqual(self.session.world["name"], "실현: chosen")
        self.assertEqual([w["ok"] for w in z["works"]], [True])

    def test_production_plan_numbers_come_from_the_world(self):
        r, *_ = self.run_to_choose(); r.confirm_brief(); r.choose("form")
        p, w = r.state["realization"]["plan"], r.state["realization"]["world"]
        fp = {f["id"]: f for f in FP.footprints(w)}
        c1 = next(b for b in p["bodies"] if b["id"] == "c1")
        self.assertEqual((c1["width_m"], c1["depth_m"], c1["height_m"]), (0.45, 0.45, 0.9))
        self.assertEqual(c1["footprint_m2"], round(fp["c1"]["area"], 3))
        self.assertEqual(p["area"], FP.area_table(w))
        self.assertTrue(all(u["value"] == PR.CHECK for u in p["unknown"]))
        self.assertTrue(all(n["by"].startswith("AI") for n in p["notes"]))
        self.assertIn("마이크", " ".join(p["devices"]))
        self.assertTrue((self.tmp / r.id / "production.md").is_file())

    def test_realizer_gets_one_retry_then_stops(self):
        bad = {"format": "world/1", "name": "x", "entities": [{"id": "s", "type": "sound", "pos": [0, 0, 0], "recipe": "tone"}]}
        seq = iter([F.realization("x", bad), F.realization("ok")])
        r, *_ = self.run_to_choose(realize=lambda s, p: next(seq)); r.confirm_brief(); r.choose("form")
        self.assertEqual(r.state["stage"], "done")
        self.assertEqual(r.state["usage"][-1]["attempts"], 2)
        red = json.loads(F.realization("x")["world_json"]); red["materials"]["ply"]["color"] = "#ff0000"
        r, *_ = self.run_to_choose(realize=lambda s, p: F.realization("x", red)); r.confirm_brief(); r.choose("form")
        self.assertEqual(r.state["stage"], "error")
        self.assertIn("forbidden", r.state["error"]["reason"])
        self.assertEqual([p for p in self.session.proposals.values() if p["kind"] == "cocreate" and p["world"].get("name") == "x"], [])

    def test_a_lens_may_fail_but_two_ideas_are_the_minimum(self):
        R, a, g = F.router()
        R.by_role["form"] = F.Scripted("gemini", "fake-g", F.script(), fail={"IdeaDraft"})
        r = RN.Run(R, self.session, self.tmp); r.start(F.SAID); r.confirm_brief()
        self.assertEqual(r.state["stage"], "choose")
        self.assertEqual([c["id"] for c in r.state["cards"]], ["emotion", "invert", "audience"])
        self.assertEqual(r.state["lane_errors"][0]["lens"], "form")
        broken = F.Scripted("anthropic", "x", F.script(), fail={"IdeaDraft"})
        R2 = PV.Router({k: broken for k in PV.ROLES}, broken)
        r = RN.Run(R2, self.session, self.tmp); r.start(F.SAID); r.confirm_brief()
        self.assertEqual(r.state["stage"], "error")

    def test_events_resume_and_run_survives_restart(self):
        r, *_ = self.run_to_choose(); r.confirm_brief()
        ev = r.events.since(0)
        self.assertEqual([e["seq"] for e in ev], list(range(1, len(ev) + 1)))
        self.assertEqual(r.events.since(5), ev[5:])
        kinds = [e["kind"] for e in ev]
        for k in ("said", "brief", "brief_confirmed", "card", "rebuttals", "measured", "curator"):
            self.assertIn(k, kinds)
        t0 = threading.Timer(0.2, lambda: r.events.add("ping"))
        t0.start()
        self.assertEqual(r.events.since(len(ev), wait=5)[0]["kind"], "ping")       # long poll wakes on the next event
        again = RN.Run.load(self.tmp / r.id, F.router()[0], self.session)
        self.assertEqual(again.state["stage"], "choose")
        self.assertEqual(len(again.events.since(0)), len(ev) + 1)
        again.choose("emotion")
        self.assertEqual(again.state["stage"], "done")

    def test_private_data_only(self):
        r, *_ = self.run_to_choose(); r.confirm_brief()
        self.assertTrue(str(r.dir).startswith(str(self.tmp)))
        self.assertTrue((r.dir / "events.jsonl").is_file() and (r.dir / "state.json").is_file())
        self.assertFalse(list((HERE.parent / "worldengine").rglob("*.jsonl")))          # nothing written inside the engine


class FakeMessages:
    def __init__(self, answers):
        self.answers, self.requests = list(answers), []

    def create(self, **kw):
        self.requests.append(kw)
        a = self.answers.pop(0)
        return a if isinstance(a, dict) and "content" in a else {"content": [{"type": "text", "text": a}], "stop_reason": "end_turn",
                                                                 "usage": {"input_tokens": 3, "output_tokens": 2}}


class ProviderTests(unittest.TestCase):
    def test_anthropic_structured_output_and_one_retry(self):
        m = FakeMessages(["{not json", json.dumps({"rebuttals": []})])
        p = PV.Anthropic(type("C", (), {"messages": m})(), "model-x")
        obj, meta = p.complete("sys", "prompt", S.RebuttalSet)
        self.assertEqual(obj.rebuttals, [])
        self.assertEqual((meta["attempts"], meta["usage"]["input_tokens"]), (2, 6))
        rq = m.requests[0]
        self.assertEqual(rq["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(rq["output_config"]["format"]["schema"], S.json_schema(S.RebuttalSet))
        self.assertNotIn("tool_choice", rq)
        self.assertIn("형식 검사에서 떨어졌다", m.requests[1]["messages"][0]["content"])
        m2 = FakeMessages(["{", "{"])
        with self.assertRaises(PV.ProviderError):
            PV.Anthropic(type("C", (), {"messages": m2})(), "x").complete("s", "p", S.RebuttalSet)
        m3 = FakeMessages([{"content": [], "stop_reason": "refusal"}])
        with self.assertRaises(PV.ProviderError):
            PV.Anthropic(type("C", (), {"messages": m3})(), "x").complete("s", "p", S.RebuttalSet)

    def test_gemini_request_shape_and_key_in_header_only(self):
        seen = []

        def post(url, headers, body):
            seen.append((url, headers, body))
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({"rebuttals": []})}]}, "finishReason": "STOP"}],
                    "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 4}}
        obj, meta = PV.Gemini("SECRET-KEY-123", "gemini-test", post).complete("sys", "prompt", S.RebuttalSet)
        url, h, body = seen[0]
        self.assertTrue(url.endswith("/models/gemini-test:generateContent"))
        self.assertEqual(h["x-goog-api-key"], "SECRET-KEY-123")
        self.assertNotIn("SECRET-KEY-123", url + json.dumps(body))
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "sys")
        self.assertEqual(meta["usage"], {"input_tokens": 7, "output_tokens": 4})
        blocked = PV.Gemini("k", "m", lambda u, h, b: {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]})
        with self.assertRaises(PV.ProviderError):
            blocked.complete("s", "p", S.RebuttalSet)

    def test_router_from_env_falls_back_and_says_so(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(PV.from_env(None)[0])
            R, note = PV.from_env(object())
            self.assertEqual({p.name for p in R.by_role.values()}, {"anthropic"})
            self.assertIn("gemini 이 없어 anthropic", note)
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k", "WE_GEMINI_MODEL": "gm", "WE_COCREATE_CURATOR": "gemini"}, clear=True):
            R, note = PV.from_env(object())
            self.assertEqual(note, "")
            self.assertEqual({r: p.name for r, p in R.by_role.items()},
                             {"brief": "anthropic", "emotion": "anthropic", "form": "gemini", "invert": "anthropic", "audience": "gemini",
                              "curator": "gemini", "realizer": "anthropic"})
            self.assertNotIn("k", json.dumps(R.describe()).replace("gemini", ""))


class StudioRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="we_costudio_"))
        self.R, *_ = F.router()
        self.st = SV.Studio(WORLD, "작가", None, self.tmp / "data", router=self.R)
        self.srv = SV.http.server.ThreadingHTTPServer(("127.0.0.1", 0), SV.make_handler(self.st))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()

    def call(self, path, body=None, token=True):
        url = self.base + path + (("&" if "?" in path else "?") + "t=" + self.st.token if token else "")
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def wait_stage(self, rid, stage):
        after = 0
        for _ in range(40):
            code, r = self.call("/api/cocreate/%s/events?after=%d&wait=5" % (rid, after))
            after = r["events"][-1]["seq"] if r["events"] else after
            if r["stage"] == stage:
                return r
        self.fail("stage %s not reached" % stage)

    def test_flow_over_http_needs_token(self):
        self.assertEqual(self.call("/api/cocreate", {"text": "x"}, token=False)[0], 403)
        code, r = self.call("/api/cocreate", {"text": F.SAID})
        self.assertEqual(code, 200, r)
        rid = r["run"]
        self.wait_stage(rid, "brief_review")
        bad = json.loads(json.dumps(self.st.runs[rid].state["brief"])); bad["constraints"]["forbidden"][1]["value"] = "red"
        self.assertEqual(self.call("/api/cocreate/%s/brief" % rid, {"brief": bad})[0], 400)
        self.assertEqual(self.call("/api/cocreate/%s/brief" % rid, {})[0], 200)
        self.wait_stage(rid, "choose")
        self.assertEqual(self.call("/api/cocreate/%s/choose" % rid, {"idea": "nope"})[0], 400)
        with urllib.request.urlopen(self.base + "/api/cocreate/%s/plan/form.svg?t=%s" % (rid, self.st.token)) as f:
            self.assertTrue(f.read().startswith(b"<svg"))
        self.assertEqual(self.call("/api/cocreate/%s/choose" % rid, {"idea": "invert"})[0], 200)
        self.wait_stage(rid, "done")
        code, s = self.call("/api/cocreate/%s" % rid)
        self.assertNotIn("world", s["realization"])
        code, st = self.call("/api/state")
        self.assertTrue(st["cocreate"])
        self.assertEqual([p["kind"] for p in st["proposals"]], ["cocreate"])
        self.assertEqual(self.call("/api/cocreate/zzz/events")[0], 404)

    def test_page_drives_itself_at_phone_width(self):
        ok, why = headless.available()
        if not ok:
            self.skipTest(why)
        url = self.base + "/cocreate?t=%s&selftest=1&choose=audience" % self.st.token
        r = headless.run_live(url, 90, 390, 800)
        self.assertTrue(r["ok"], r.get("reason"))
        res = r["result"]
        self.assertEqual(res["stage"], "done")
        self.assertEqual(len(res["cards"]), 4)
        self.assertEqual(res["departures"], 4)
        self.assertEqual(res["rebuttals"], 12)
        self.assertIn("lane-audience", res["bad"])
        self.assertEqual(res["picks"], ["lane-emotion", "lane-form"])
        self.assertTrue(all(w > 0 for w in res["plans"]), res["plans"])
        self.assertLessEqual(res["width"]["scroll"], res["width"]["inner"])
        self.assertLessEqual(res["width_done"]["scroll"], res["width_done"]["inner"])
        self.assertIn("확인 필요", res["plan"])
        self.assertEqual((res["chosen"], res["buttons_left"]), ("작가가 고름 (추천 밖)", 0))
        self.assertEqual(res["replay"], res["after"])
        edited = self.st.runs[next(iter(self.st.runs))].state["brief"]
        self.assertIn("작가가 더한 탐구", edited["exploration"])


if __name__ == "__main__":
    unittest.main()
