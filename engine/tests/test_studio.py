# -*- coding: utf-8 -*-
"""Studio (SPEC 6절 3단계: A-01..A-07, D-01..D-04, V-13 harness). No network and no API key anywhere: the model is
a scripted fake client, outbound sockets are blocked during agent tests. Run from engine/."""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ENGINE = Path(__file__).resolve().parent.parent
REPO = ENGINE.parent
sys.path.insert(0, str(ENGINE))

from worldengine import world as WD  # noqa: E402
from worldengine.studio import agent as AG, board as BD, config, server as SV, session as SS, tools as TL, v13, vocab as VC  # noqa: E402

YEOBAEK = WD.load(ENGINE / "worlds" / "ref_yeobaek.world.json")
SENTINEL_KEY = "sk-ant-TEST-SENTINEL-0000"


class FakeClient:
    """Scripted stand-in for anthropic.Anthropic(): each call to messages.create returns the next scripted response
    (dicts shaped like the API's). Every request is recorded."""
    def __init__(self, script):
        self.script, self.requests = list(script), []
        self.messages = self

    def create(self, **kw):
        self.requests.append(copy.deepcopy({k: v for k, v in kw.items() if k != "messages"}) | {"n_messages": len(kw["messages"])})
        return self.script.pop(0)


def tool(name, inp, i="t1"):
    return {"stop_reason": "tool_use", "usage": {"input_tokens": 100, "output_tokens": 20},
            "content": [{"type": "text", "text": ""}, {"type": "tool_use", "id": i, "name": name, "input": inp}]}


def text(t):
    return {"stop_reason": "end_turn", "usage": {"input_tokens": 120, "output_tokens": 10}, "content": [{"type": "text", "text": t}]}


def _no_net(addr, *a, **k):
    host = addr[0] if isinstance(addr, tuple) else addr
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise AssertionError("network access attempted: %r" % (addr,))
    return _real_cc(addr, *a, **k)


_real_cc = socket.create_connection


class NoNetwork(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch("socket.create_connection", _no_net); self.p.start()
        self.tmp = Path(tempfile.mkdtemp(prefix="we_studio_"))
        self.env = mock.patch.dict(os.environ, {"WE_STUDIO_DIR": str(self.tmp / "data")}); self.env.start()

    def tearDown(self):
        self.p.stop(); self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class SessionTests(NoNetwork):
    def test_proposal_changes_nothing_until_applied_and_versions_keep_history(self):
        s = SS.Session(YEOBAEK)
        r = TL.run(s, "propose_axes", {"changes": {"density": 0.4}, "why": "조금 채운다"})
        self.assertFalse(r["applied"]); self.assertIn("밀도 축 0.05 → 0.40", r["understood_as"])
        self.assertEqual(s.world["rules"]["axes"]["density"], 0.05)
        s.apply(r["proposal"])
        self.assertEqual(s.world["rules"]["axes"]["density"], 0.4)
        rv = TL.run(s, "propose_revert", {"to_version": 0, "why": "아까가 나았다"})
        s.apply(rv["proposal"])
        self.assertEqual(s.world["rules"]["axes"]["density"], 0.05)
        self.assertEqual([v["n"] for v in s.history()], [0, 1, 2])          # going back is a new version (A-05)

    def test_artist_can_correct_before_applying(self):
        s = SS.Session(YEOBAEK)
        pid = TL.run(s, "propose_axes", {"changes": {"density": 0.6}, "why": "w"})["proposal"]
        w = copy.deepcopy(s.proposals[pid]["world"]); w["rules"]["axes"]["density"] = 0.2
        s.apply(pid, w)
        self.assertEqual(s.world["rules"]["axes"]["density"], 0.2)
        self.assertIn("작가가 고쳐서 적용", s.history()[-1]["why"])

    def test_bad_proposals_are_refused_with_reasons(self):
        s = SS.Session(YEOBAEK)
        self.assertFalse(TL.run(s, "propose_entities", {"add": [{"id": "line", "type": "box", "pos": [0, 0, 0]}], "edit": [], "remove": [], "why": ""})["ok"])
        self.assertIn("없는 id", TL.run(s, "propose_entities", {"add": [], "edit": [], "remove": ["ghost"], "why": ""})["error"])
        self.assertIn("재질", TL.run(s, "propose_entities", {"add": [{"id": "n", "type": "box", "pos": [0, 0, 0], "material": "gold"}], "edit": [], "remove": [], "why": ""})["error"])
        self.assertFalse(TL.run(s, "propose_variants", {"variants": [{"label": "a", "interpretation": "", "axes": {}}], "why": ""})["ok"])

    def test_rule_warnings_on_constraint_breaking_bodies(self):
        mod = WD.load(ENGINE / "worlds" / "ref_modulor.world.json")
        r = TL.run(SS.Session(mod), "propose_entities", {"add": [{"id": "odd", "type": "box", "pos": [1, 1, 0], "size": [1.0, 1.0, 1.0]}], "edit": [], "remove": [], "why": ""})
        self.assertTrue(r["ok"]); self.assertTrue(any("dimension_series" in x for x in r["rule_warnings"]))

    def test_tool_schemas_are_strict(self):
        def closed(sch):
            if sch.get("type") == "object":
                self.assertIs(sch.get("additionalProperties"), False, sch)
                for v in sch["properties"].values():
                    closed(v)
            if sch.get("type") == "array":
                closed(sch["items"])
        for t in TL.TOOLS:
            self.assertTrue(t["strict"]); closed(t["input_schema"])


class ApprovalTests(NoNetwork):
    """A-06: every costly or irreversible action is queued and provably does not run until approved."""

    def test_agent_requests_never_run(self):
        calls = []
        spy = {k: (lambda kind: lambda s, a: calls.append(kind) or {"done": kind})(k) for k in SS.NEEDS_APPROVAL}
        s = SS.Session(YEOBAEK, spy)
        for k in sorted(SS.NEEDS_APPROVAL):
            with self.subTest(k):
                fc = FakeClient([tool("request_action", {"kind": k, "why": "작가가 원함"}), text("승인을 기다려요")])
                turn = AG.Agent(fc, s).send("해 줘")
                self.assertEqual(len(turn["approvals"]), 1)
                a = s.approvals[turn["approvals"][0]]
                self.assertEqual((a["kind"], a["status"]), (k, "waiting"))
                self.assertEqual(calls, [])                                  # nothing ran
        self.assertFalse((self.tmp / "data" / "out").exists())             # no render, no publish folder
        aid = next(a for a in s.approvals if s.approvals[a]["kind"] == "publish")
        self.assertEqual(s.approve(aid), {"ran": True, "done": "publish"})  # only the artist's approve() runs it
        self.assertEqual(calls, ["publish"])

    def test_real_executors_do_not_run_on_request(self):
        st = SV.Studio(YEOBAEK, "tester", FakeClient([tool("request_action", {"kind": "render_highres", "why": "w"}), tool("request_action", {"kind": "delete_work", "why": "w"}, "t2"),
                                                       tool("request_action", {"kind": "publish", "why": "w"}, "t3"), text("기다림")]), self.tmp / "data")
        st.message({"text": "고해상도 렌더, 삭제, 공개 해 줘"})
        self.assertEqual(len(st.session.versions), 1)
        self.assertFalse((self.tmp / "data" / "out").exists())
        self.assertEqual({a["status"] for a in st.session.approvals.values()}, {"waiting"})

    def test_publish_ships_exactly_the_artists_work(self):
        s = SS.Session(YEOBAEK, SV.executors(self.tmp / "out"))
        r = s.approve(s.request("publish", {}, "w")["approval"])
        listed = json.loads((Path(r["built"]) / "site.json").read_text(encoding="utf-8"))["worlds"]
        self.assertEqual([w["file"] for w in listed], ["work.world.json"])
        self.assertFalse(r["deployed"])

    def test_drive_device_has_no_executor(self):
        s = SS.Session(YEOBAEK, SV.executors(self.tmp / "out"))
        aid = s.request("drive_device", {}, "w")["approval"]
        r = s.approve(aid)
        self.assertFalse(r["ran"]); self.assertIn("연결돼 있지 않다", r["reason"])


class AgentTests(NoNetwork):
    def test_conversation_produces_proposal_not_change(self):
        fc = FakeClient([tool("describe_world", {}), tool("propose_axes", {"changes": {"density": 0.3}, "why": "'조금 더'를 밀도 0.3 으로"}, "t2"), text("이렇게 바꿔 볼까요?")])
        s = SS.Session(YEOBAEK)
        turn = AG.Agent(fc, s).send("조금 더 채워 줘")
        self.assertEqual(turn["reply"], "이렇게 바꿔 볼까요?")
        self.assertEqual(len(turn["proposals"]), 1)
        self.assertEqual(len(s.versions), 1)
        self.assertEqual(turn["usage"]["requests"], 3)

    def test_model_id_comes_from_config(self):
        fc = FakeClient([text("ok"), text("ok")])
        AG.Agent(fc, SS.Session(YEOBAEK)).send("안녕")
        self.assertEqual(fc.requests[0]["model"], config.DEFAULT_MODEL)
        with mock.patch.dict(os.environ, {"WE_MODEL": "some-other-model"}):
            AG.Agent(fc, SS.Session(YEOBAEK)).send("안녕")
        self.assertEqual(fc.requests[1]["model"], "some-other-model")
        self.assertTrue(all(t["strict"] for t in fc.requests[0]["tools"]))
        self.assertEqual(fc.requests[0]["thinking"], {"type": "adaptive"})
        self.assertNotIn("tool_choice", fc.requests[0])                       # forced tool_choice is rejected by this model

    def test_no_model_id_literals_outside_config(self):
        hits = [str(p.relative_to(ENGINE)) for p in (ENGINE / "worldengine").rglob("*.py")
                if p.name != "config.py" and re.search(r"claude-[a-z]", p.read_text(encoding="utf-8"))]
        self.assertEqual(hits, [])

    def test_images_reach_the_model_as_image_blocks(self):
        fc = FakeClient([text("봤어요")])
        ag = AG.Agent(fc, SS.Session(YEOBAEK))
        ag.send("이 사진 느낌으로", images=[("image/jpeg", "AAAA")])
        self.assertEqual(ag.messages[0]["content"][0], {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}})

    def test_cannot_do_is_surfaced_and_nothing_proposed(self):
        fc = FakeClient([tool("cannot_do", {"request": "향기", "reason": "냄새를 내는 출력이 없다", "alternatives": ["향을 개념 카드로 적기", "색과 움직임으로 암시하기"]}), text("지금은 못 해요")])
        turn = AG.Agent(fc, SS.Session(YEOBAEK)).send("향기가 나게 해 줘")
        self.assertEqual(turn["refusals"][0]["reason"], "냄새를 내는 출력이 없다")
        self.assertEqual(turn["proposals"], [])

    def test_tool_errors_go_back_to_the_model_as_errors(self):
        fc = FakeClient([tool("propose_revert", {"to_version": 9, "why": "w"}), text("그 판은 없네요")])
        ag = AG.Agent(fc, SS.Session(YEOBAEK))
        ag.send("9번 판으로")
        res = ag.messages[2]["content"][0]
        self.assertTrue(res["is_error"]); self.assertIn("판 9 은 없다", res["content"])

    def test_turn_cap(self):
        fc = FakeClient([tool("describe_world", {}, "t%d" % i) for i in range(config.MAX_TURNS)])
        self.assertEqual(AG.Agent(fc, SS.Session(YEOBAEK)).send("계속")["stop_reason"], "max_turns")


class VariantBoardTests(NoNetwork):
    def test_ambiguous_request_gets_variants_and_a_board(self):
        fc = FakeClient([tool("propose_variants", {"why": "'미래적'은 여러 뜻", "variants": [
            {"label": "A 차가운 금속", "interpretation": "색을 빼고 형태를 단단히", "axes": {"colour": 0.0, "form": 0.1}},
            {"label": "B 빛나는 밀도", "interpretation": "밀도와 움직임을 올림", "axes": {"density": 0.5, "motion": 0.6}},
            {"label": "C 그대로 비움", "interpretation": "여백은 두고 질감만", "axes": {"texture": 0.4}}]}), text("세 가지로 읽었어요")])
        s = SS.Session(YEOBAEK)
        turn = AG.Agent(fc, s).send("좀 더 미래적으로")
        self.assertEqual(len(turn["variant_sets"]), 1); self.assertEqual(len(turn["proposals"]), 3)
        page = BD.build(s, turn["variant_sets"][0], self.tmp / "board", render=False)
        for lab in ("A 차가운 금속", "B 빛나는 밀도", "C 그대로 비움", "레시피 (D-03)", "기준 판: 0", "<svg"):
            self.assertIn(lab, page)
        self.assertEqual(len(s.versions), 1)


    @unittest.skipUnless(__import__("worldengine.headless", fromlist=["x"]).available()[0], "no headless browser")
    def test_board_with_3d_views(self):
        s = SS.Session(YEOBAEK)
        TL.run(s, "propose_variants", {"why": "w", "variants": [{"label": "A", "interpretation": "i", "axes": {"density": 0.5}},
                                                              {"label": "B", "interpretation": "j", "axes": {"colour": 0.8}}]})
        page = BD.build(s, "v1", None, render=True)
        self.assertEqual(page.count('alt="3D" src="data:image/png;base64,'), 2)


class VocabAndServerTests(NoNetwork):
    def test_vocab_lives_outside_repo_and_reaches_the_model_only(self):
        self.assertNotIn(REPO.resolve(), Path(Path.home() / ".worldengine").resolve().parents)
        st = SV.Studio(YEOBAEK, "작가 1", FakeClient([tool("propose_axes", {"changes": {"density": 0.6}, "why": "w"}), text("?"), text("ok")]), self.tmp / "data")
        st.message({"text": "보라빛-마커-단어 로 채워"})
        pid = next(iter(st.session.proposals))
        st.apply({"proposal": pid, "axes": {"density": 0.25}, "note": "덜"})
        vf = self.tmp / "data" / "vocab" / "작가_1.json"
        self.assertTrue(vf.exists()); self.assertIn("보라빛-마커-단어", vf.read_text(encoding="utf-8"))
        st.message({"text": "다음"})
        self.assertIn("보라빛-마커-단어", st.client.requests[-1]["system"])   # the model sees it (server side)

    def test_server_never_sends_key_or_vocab_and_needs_token(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL_KEY}):
            st = SV.Studio(YEOBAEK, "a", FakeClient([tool("propose_axes", {"changes": {"density": 0.6}, "why": "w"}), text("?")]), self.tmp / "data")
            st.vocab.record("비밀-어휘-표식", {}, {}, "")
            srv = SV.http.server.ThreadingHTTPServer(("127.0.0.1", 0), SV.make_handler(st))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = "http://127.0.0.1:%d" % srv.server_address[1]
            try:
                def get(path, data=None):
                    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"})
                    try:
                        with urllib.request.urlopen(req, timeout=60) as r:
                            return r.status, r.read().decode("utf-8", "replace")
                    except urllib.error.HTTPError as e:
                        return e.code, e.read().decode("utf-8", "replace")
                t = "?t=" + st.token
                bodies = [get("/")[1], get("/api/state" + t)[1], get("/api/world.json" + t)[1], get("/runtime/index.html")[1],
                          get("/runtime/src/main.js")[1], get("/api/message" + t, {"text": "채워"})[1], get("/api/state" + t)[1]]
                for b in bodies:
                    self.assertNotIn(SENTINEL_KEY, b); self.assertNotIn("비밀-어휘-표식", b)
                self.assertEqual(get("/api/state")[0], 403)                                       # token required
                self.assertEqual(get("/api/message", {"text": "x"})[0], 403)
                for bad in ("/runtime/../worldengine/studio/config.py", "/runtime/%2e%2e/worldengine/studio/config.py",
                            "/vendor/../../.gitignore", "/runtime/tests/runtime.test.mjs", "/worldengine/studio/vocab.py"):
                    self.assertEqual(get(bad)[0], 404, bad)
                pid = json.loads(get("/api/state" + t)[1])["proposals"][0]["id"]
                self.assertEqual(json.loads(get("/api/apply" + t, {"proposal": pid})[1])["version"], 1)
            finally:
                srv.shutdown()

    def test_no_key_like_strings_in_tracked_files(self):
        files = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True).stdout.split()
        pat = re.compile(r"sk-ant-(?!TEST-SENTINEL)[A-Za-z0-9_-]{8,}")
        hits = [f for f in files if (REPO / f).is_file() and (REPO / f).stat().st_size < 5_000_000 and pat.search((REPO / f).read_text(encoding="utf-8", errors="ignore"))]
        self.assertEqual(hits, [])

    def test_private_paths_are_gitignored(self):
        for p in ("engine/studio_data/vocab/a.json", "x/vocab/b.json", ".env", ".worldengine/studio/vocab/c.json"):
            r = subprocess.run(["git", "check-ignore", "-q", p], cwd=REPO)
            self.assertEqual(r.returncode, 0, p)

    def test_ci_has_no_key(self):
        for f in (REPO / ".github" / "workflows").glob("*.yml"):
            self.assertNotIn("ANTHROPIC_API_KEY", f.read_text(encoding="utf-8"), f)

    def test_studio_without_agent_says_so(self):
        st = SV.Studio(YEOBAEK, "a", None, self.tmp / "data")
        self.assertIn("에이전트가 연결돼 있지 않다", st.message({"text": "x"})["error"])
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(SV.make_client()[0])


class V13HarnessTests(NoNetwork):
    def test_seed_set_is_labelled_developer_written(self):
        d = v13.load()
        self.assertIn("개발자 작성", d["label"]); self.assertIn("작가의 말이 아니다", d["label"])
        self.assertGreaterEqual(len(d["items"]), 20)
        kinds = {i["expect"]["kind"] for i in d["items"]}
        for k in ("axes", "entities", "concept", "variants", "approval", "refuse", "revert"):
            self.assertIn(k, kinds)

    def test_scorer_accepts_in_scope_and_rejects_out_of_scope(self):
        it = {"id": "x", "world": "ref_festival_baroque", "request": "비워", "expect": {"kind": "axes", "axes": {"density": "-"}, "keep": ["colour"]}}
        good = v13.run([it], lambda: FakeClient([tool("propose_axes", {"changes": {"density": 0.5}, "why": "w"}), text("ok")]))[0]
        wrong_dir = v13.run([it], lambda: FakeClient([tool("propose_axes", {"changes": {"density": 1.0}, "why": "w"}), text("ok")]))[0]
        spill = v13.run([it], lambda: FakeClient([tool("propose_axes", {"changes": {"density": 0.5, "colour": 0.2}, "why": "w"}), text("ok")]))[0]
        self.assertTrue(good["ok"], good); self.assertFalse(wrong_dir["ok"]); self.assertFalse(spill["ok"])

    def test_scorer_kinds(self):
        d = {i["id"]: i for i in v13.load()["items"]}
        cases = [
            ("refuse-1", [tool("cannot_do", {"request": "향기", "reason": "출력 없음", "alternatives": ["색으로"]}), text("못 해요")], True),
            ("refuse-1", [tool("propose_axes", {"changes": {"colour": 0.4}, "why": "향기를 색으로"}), text("바꿨어요")], False),   # substitution
            ("approve-1", [tool("request_action", {"kind": "publish", "why": "w"}), text("승인 대기")], True),
            ("ambig-1", [tool("propose_variants", {"why": "w", "variants": [{"label": "a", "interpretation": "i", "axes": {"colour": 0.0}}, {"label": "b", "interpretation": "i", "axes": {"motion": 0.5}}]}), text("둘")], True),
            ("revert-1", [tool("propose_revert", {"to_version": 0, "why": "w"}), text("되돌릴까요")], True),
            ("add-2", [tool("propose_entities", {"add": [{"id": "p1", "type": "person", "pos": [20, 12, 0]}], "edit": [], "remove": [], "why": "w"}), text("세웠어요")], True),
            ("concept-2", [tool("propose_concept", {"id": "c", "title": "모듈러", "statement": "s", "sources": [{"who": "Le Corbusier", "kind": "paraphrase", "where": "Le Modulor (1950)"}], "why": "w"}), text("달았어요")], True),
        ]
        for cid, script, want in cases:
            with self.subTest(cid, want=want):
                self.assertEqual(v13.run([d[cid]], lambda s=script: FakeClient(list(s)))[0]["ok"], want)

    def test_bound_is_a_hard_cap(self):
        b = v13.bound(24)
        self.assertEqual(b["max_requests"], 24 * config.MAX_TURNS)
        self.assertEqual(b["max_output_tokens"], 24 * config.MAX_TURNS * config.MAX_TOKENS)


if __name__ == "__main__":
    unittest.main()
