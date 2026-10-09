# -*- coding: utf-8 -*-
"""`python3 -m worldengine studio --world W --artist NAME [--host 0.0.0.0] [--port 8100]`

One artist, one world, one process. The phone or PC opens the printed URL. The API key and the vocabulary stay
in this process: the page only ever receives worlds, summaries and previews.

Routes (all /api routes need the random token printed at start, ?t=... or X-Studio-Token):
  GET  /                      studio page             GET /runtime/*, /vendor/three/*   runtime files (whitelist)
  GET  /api/state             versions, proposals, approvals, variant sets, last preview
  GET  /api/world.json        current world, or ?proposal=pN for that proposal's world
  GET  /api/board/<set>       variant board
  POST /api/message {text, images:[{media_type,data}]}     POST /api/apply {proposal, axes?, note?}
  POST /api/reject {proposal, note}    POST /api/approve {approval}    POST /api/decline {approval}
"""
from __future__ import annotations

import base64
import binascii
import copy
import http.server
import json
import mimetypes
import secrets
import shutil
import threading
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from worldengine import headless
from worldengine.studio import agent as AG, board as BD, config, diff as DF, session as SS, vocab as VC

ENGINE = Path(__file__).resolve().parents[2]
STATIC = {"runtime": ENGINE / "runtime", "vendor": ENGINE / "vendor"}
PAGE = Path(__file__).with_name("studio.html")


def executors(out_dir: Path) -> dict:
    """What runs after the artist approves (A-06). drive_device drives the SIMULATED device only (RB-06)."""
    def render_highres(s, args):
        out_dir.mkdir(parents=True, exist_ok=True)
        png = out_dir / ("render_v%d.png" % s.versions[-1]["n"])
        r = headless.render_world(s.world, png, view=args.get("view", "aerial"), w=2560, h=1600)
        return {"file": str(png) if r["ok"] else None, "backend": r["backend"], "reason": r["reason"]}

    def publish(s, args):
        from worldengine import site
        dest = out_dir / "publish"
        tmp_worlds = out_dir / "publish_src"
        tmp_worlds.mkdir(parents=True, exist_ok=True)
        (tmp_worlds / "work.world.json").write_text(json.dumps(s.world, ensure_ascii=False), encoding="utf-8")
        from worldengine import assets as AS
        r = site.build(dest, world_files=[tmp_worlds / "work.world.json"], assets=AS.Store(out_dir.parent))     # only the files this work uses
        return {"built": r["out"], "deployed": False, "reason": "폴더만 만들었다. 인터넷 배포는 저장소 주인의 Pages 스위치가 필요하다"}

    def delete_work(s, args):
        s.versions[:] = [s.versions[0]]
        s.proposals.clear()
        return {"deleted": True, "kept": "처음 판만 남겼다"}

    def promote_plugin(s, args):
        from worldengine import promote
        return promote.install(args["code"], args["name"], "1", args["rows"], out_dir.parent)

    def drive_device(s, args):
        """RB-06: only the SIMULATED device is wired here. The trajectory must pass the host guard and then the
        device's own firmware limits; a real device needs its own bridge (hardware) and is not connected."""
        from worldengine import device as DV
        arm = next((e for e in s.world.get("entities") or [] if e.get("type") == "robot.arm" and e.get("trajectory")), None)
        if arm is None:
            return {"device": "simulated", "ok": False, "reason": "이 세계에는 궤적을 가진 로봇 팔이 없다"}
        dev = DV.SimDevice(arm["chain"])
        try:
            r = DV.Bridge(arm["chain"], dev).drive(arm["trajectory"])
        finally:
            dev.close()
        return {"device": "simulated", "real_device": "연결 안 됨 (실제 장치 다리는 하드웨어가 필요하다)", **r}

    return {"render_highres": render_highres, "publish": publish, "delete_work": delete_work, "promote_plugin": promote_plugin,
            "drive_device": drive_device}


class Studio:
    def __init__(self, world: dict, artist: str, client=None, data=None):
        self.data = Path(data or config.data_dir())
        from worldengine import ledger as LG
        self.ledger = LG.Ledger(artist, self.data)
        self.session = SS.Session(world, executors(self.data / "out"), self.ledger)
        self.vocab = VC.Vocab(artist, self.data)
        self.client = client
        self.agent = AG.Agent(client, self.session, self.vocab) if client is not None else None
        self.token = secrets.token_urlsafe(16)
        self.last_text = ""
        self.lock = threading.Lock()

    def state(self) -> dict:
        s = self.session
        return {"world": s.versions[-1]["world"]["name"], "version": s.versions[-1]["n"], "history": s.history(),
                "proposals": [{k: p[k] for k in ("id", "kind", "why", "status", "label", "variant_set") if k in p} | {"understood_as": DF.summary_ko(p["diff"]),
                               "axes": (p["world"].get("rules") or {}).get("axes", {})} for p in s.proposals.values()],
                "approvals": [{k: a[k] for k in ("id", "kind", "why", "status")} | {"message": SS.NEEDS_APPROVAL[a["kind"]], "result": a.get("result")} for a in s.approvals.values()],
                "variant_sets": [{"id": v["id"], "why": v["why"]} for v in s.variant_sets],
                "preview": (getattr(s, "previews", None) or [None])[-1],
                "agent": self.agent is not None}

    def message(self, body: dict) -> dict:
        if self.agent is None:
            return {"error": "에이전트가 연결돼 있지 않다 (서버에 ANTHROPIC_API_KEY 와 anthropic 패키지가 필요하다). 제안·적용·되돌리기 화면은 그대로 쓸 수 있다."}
        self.last_text = body.get("text", "")
        imgs = [(i["media_type"], i["data"]) for i in body.get("images", [])][:4]
        return self.agent.send(self.last_text, imgs)

    def apply(self, body: dict) -> dict:
        p = self.session.proposals[body["proposal"]]
        edited = None
        if body.get("axes"):
            edited = copy.deepcopy(p["world"])
            edited.setdefault("rules", {}).setdefault("axes", {}).update({k: max(0.0, min(1.0, float(v))) for k, v in body["axes"].items()})
            self.vocab.record(self.last_text or p["why"], (p["world"].get("rules") or {}).get("axes", {}), edited["rules"]["axes"], body.get("note", ""))
        return self.session.apply(body["proposal"], edited)


def make_handler(st: Studio):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode("utf-8")
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

        def _authed(self, q):
            return (q.get("t", [""])[0] or self.headers.get("X-Studio-Token", "")) == st.token

        def do_GET(self):
            u = urlparse(self.path); q = parse_qs(u.query); parts = [p for p in u.path.split("/") if p]
            if u.path == "/":
                return self._send(200, PAGE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            if parts and parts[0] in STATIC:
                base = STATIC[parts[0]].resolve()
                f = (STATIC[parts[0]] / "/".join(parts[1:])).resolve()
                if base in f.parents and f.is_file() and "tests" not in f.relative_to(base).parts:
                    return self._send(200, f.read_bytes(), (mimetypes.guess_type(f.name)[0] or "application/octet-stream").replace("text/javascript", "application/javascript"))
                return self._send(404, {"error": "not found"})
            if parts[:1] != ["api"]:
                return self._send(404, {"error": "not found"})
            if not self._authed(q):
                return self._send(403, {"error": "token"})
            with st.lock:
                if parts[1:] == ["state"]:
                    return self._send(200, st.state())
                if parts[1:] == ["world.json"]:
                    pid = q.get("proposal", [None])[0]
                    return self._send(200, st.session.proposals[pid]["world"] if pid in st.session.proposals else st.session.versions[-1]["world"])
                if len(parts) == 3 and parts[1] == "asset":                 # E-02: the artist's own files, to the artist's pages only
                    from worldengine import assets as AS
                    got = AS.Store(st.data).get(unquote(parts[2]))
                    return self._send(200, got[0], got[1]) if got else self._send(404, {"error": "no such file"})
                if parts[1:] == ["assets"]:
                    from worldengine import assets as AS
                    return self._send(200, {"assets": AS.Store(st.data).names()})
                if len(parts) == 3 and parts[1] == "board":
                    return self._send(200, BD.build(st.session, parts[2], render=True), "text/html; charset=utf-8")
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            u = urlparse(self.path); q = parse_qs(u.query)
            if not u.path.startswith("/api/") or not self._authed(q):
                return self._send(403, {"error": "token"})
            n = int(self.headers.get("Content-Length", 0))
            if n > 12 * 1024 * 1024:
                return self._send(413, {"error": "too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            try:
                with st.lock:
                    act = u.path[5:]
                    if act == "message":
                        return self._send(200, st.message(body))
                    if act == "apply":
                        return self._send(200, st.apply(body))
                    if act == "asset":                                       # E-02: import into the private folder
                        from worldengine import assets as AS
                        return self._send(200, AS.Store(st.data).put(str(body.get("name", "")), base64.b64decode(body.get("data", ""), validate=True)))
                    if act == "edit":                                        # E-01: the editor's direct changes
                        return self._send(200, st.session.edit(body["world"], str(body.get("why", ""))[:200]))
                    if act == "reject":
                        st.session.reject(body["proposal"], body.get("note", "")); return self._send(200, {"ok": True})
                    if act == "approve":
                        return self._send(200, st.session.approve(body["approval"]))
                    if act == "decline":
                        st.session.decline(body["approval"]); return self._send(200, {"ok": True})
            except (KeyError, ValueError, binascii.Error) as e:
                return self._send(400, {"error": str(e)})
            return self._send(404, {"error": "not found"})
    return H


def make_client():
    """The real client, or None with the reason. Never raises: the studio still works without the agent."""
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None, "ANTHROPIC_API_KEY 가 없다"
    try:
        import anthropic
    except ImportError:
        return None, "anthropic 패키지가 없다 (pip install anthropic)"
    return anthropic.Anthropic(), ""


def serve(world: dict, artist: str, host="127.0.0.1", port=8100):
    client, why = make_client()
    st = Studio(world, artist, client)
    srv = http.server.ThreadingHTTPServer((host, port), make_handler(st))
    print("스튜디오: http://%s:%d/?t=%s" % ("localhost" if host == "127.0.0.1" else host, port, st.token))
    print("에이전트:", "연결됨 (모델 %s)" % config.model() if client else "없음 — " + why)
    if host != "127.0.0.1":
        print("주의: 같은 네트워크에서 열린다. 위 주소(토큰 포함)를 아는 사람만 쓸 수 있다.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
