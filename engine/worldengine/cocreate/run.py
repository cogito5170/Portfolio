# -*- coding: utf-8 -*-
"""One co-creation run (CC-01..CC-09): the artist's words -> brief (artist confirms) -> round 1: four lenses alone,
in parallel -> round 2: each lens rebuts the others -> measurement -> curator -> the ARTIST chooses -> realisation
(a proposal in the studio session, works, production plan).

    r = Run(router, session=None, root=dir)
    r.start("외로움을 표현하고 싶어 ...")      -> stage "brief_review" (waits for the artist)
    r.confirm_brief(edited_or_same_brief)      -> rounds, measurement, curator -> stage "choose" (waits again)
    r.choose("form", note="")                  -> stage "done": r.state["realization"], a session proposal
    r.events.since(n, wait=20)                 -> numbered events, for a page that watches (and resumes after a drop)
    Run.load(dir, router, session)             -> the same run after a restart, at the stage it was waiting in

The two waits are where the artist decides; nothing after them runs on its own. Every event and the state are
written under the artist's private data directory (config.data_dir()/cocreate/<id>), never into the repository.
"""
from __future__ import annotations

import concurrent.futures as CF
import contextlib
import json
import secrets
import threading
import time
from pathlib import Path

from worldengine import interpret as IN, works as WK
from worldengine.cocreate import agents as AG, lenses as LZ, measure as MS, production as PR, schema as S

STAGES = ("brief", "brief_review", "round1", "round2", "measure", "curate", "choose", "realize", "done", "error")
WAITING = {"brief_review": "작가가 명세를 확인해야 한다", "choose": "작가가 아이디어를 골라야 한다"}


class EventLog:
    """Numbered events; since(n) gives everything after n, so a phone that dropped its connection resumes exactly."""

    def __init__(self, path: "Path | None"):
        self.path, self.items, self.cv = path, [], threading.Condition()
        if path is not None and path.is_file():
            self.items = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def add(self, kind: str, **data) -> int:
        with self.cv:
            ev = {"seq": len(self.items) + 1, "t": round(time.time(), 3), "kind": kind, **data}
            self.items.append(ev)
            if self.path is not None:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self.cv.notify_all()
            return ev["seq"]

    def since(self, n: int = 0, wait: float = 0.0) -> "list[dict]":
        with self.cv:
            if wait and len(self.items) <= n:
                self.cv.wait_for(lambda: len(self.items) > n, timeout=wait)
            return self.items[n:]


class Run:
    def __init__(self, router, session=None, root=None, run_id: "str | None" = None, session_lock=None):
        self.router, self.session = router, session
        self.slock = session_lock or contextlib.nullcontext()      # the studio's lock: the session is shared with its handlers
        self.id = run_id or time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
        self.dir = Path(root) / self.id if root is not None else None
        if self.dir is not None:
            self.dir.mkdir(parents=True, exist_ok=True)
        self.events = EventLog(self.dir / "events.jsonl" if self.dir is not None else None)
        self.state = {"id": self.id, "stage": "brief", "said": None, "brief": None, "warnings": [], "cards": [], "lane_errors": [],
                      "rebuttals": [], "dropped_rebuttals": [], "measured": None, "curator": None, "choice": None, "realization": None,
                      "providers": router.describe() if router is not None else {}, "usage": []}
        self.lock = threading.Lock()

    # ------------------------------------------------------------ persistence
    def _save(self):
        if self.dir is not None:
            (self.dir / "state.json").write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, d, router, session=None, session_lock=None) -> "Run":
        d = Path(d)
        r = cls(router, session, d.parent, d.name, session_lock)
        r.state = json.loads((d / "state.json").read_text(encoding="utf-8"))
        return r

    def _stage(self, s: str, **extra):
        self.state["stage"] = s
        self._save()
        self.events.add("stage", stage=s, waiting=WAITING.get(s), **extra)

    def _used(self, role: str, meta: dict):
        u = {"role": role, "provider": meta["provider"], "model": meta["model"], **meta["usage"], "attempts": meta["attempts"]}
        self.state["usage"].append(u)
        self.events.add("usage", **u)

    def _fail(self, where: str, e: Exception):
        self.state["error"] = {"where": where, "reason": str(e)[:500]}
        self._stage("error", reason=str(e)[:300])

    # ------------------------------------------------------------ CC-01 brief
    def start(self, said: str) -> dict:
        self.state["said"] = said
        w = IN.copy_risk(said)                                   # CT-04: a warning to the artist, never a block
        self.state["warnings"] = [w] if w else []
        self.events.add("said", text=said, warnings=self.state["warnings"])
        self._stage("brief")
        with self.slock:
            world = self.session.world if self.session is not None else None
        try:
            brief, meta = AG.draft_brief(self.router.of("brief"), said, world)
        except Exception as e:                                   # noqa: BLE001 -- shown to the artist as it is
            self._fail("brief", e); return self.state
        self._used("brief", meta)
        self.state["brief"] = brief
        self.events.add("brief", brief=brief)
        self._stage("brief_review")
        return self.state

    def confirm_brief(self, brief: "dict | None" = None) -> dict:
        if self.state["stage"] != "brief_review":
            raise ValueError("명세를 확인할 단계가 아니다: %s" % self.state["stage"])
        b = S.CreativeBrief.model_validate(brief if brief is not None else self.state["brief"]).data()
        b["intent"]["said"] = self.state["said"] or b["intent"]["said"]
        self.state["brief"] = b
        self.events.add("brief_confirmed", brief=b, edited=brief is not None and brief != self.state.get("brief"))
        try:
            self._round1(b)
            if len(self.state["cards"]) < 2:
                raise RuntimeError("아이디어가 %d개뿐이다 (렌즈 오류: %s)" % (len(self.state["cards"]), "; ".join(e["reason"] for e in self.state["lane_errors"])[:300]))
            self._round2(b)
            self._stage("measure")
            with self.slock:
                hist = [{"n": v["n"], "world": v["world"]} for v in self.session.versions] if self.session is not None else []
            self.state["measured"] = MS.measure(self.state["cards"], b, hist)
            self.events.add("measured", measured=self.state["measured"])
            self._stage("curate")
            rep, meta = AG.curate(self.router.of("curator"), b, self.state["cards"], self.state["rebuttals"], self.state["measured"])
            self._used("curator", meta)
            self.state["curator"] = rep
            self.events.add("curator", report=rep)
        except Exception as e:                                   # noqa: BLE001
            self._fail(self.state["stage"], e); return self.state
        self._stage("choose")
        return self.state

    # ------------------------------------------------------------ CC-03/04 the two rounds
    def _lanes(self, fn, lenses):
        with CF.ThreadPoolExecutor(max_workers=len(LZ.LENSES)) as ex:
            futs = {ex.submit(fn, lz): lz for lz in lenses}
            for f in CF.as_completed(futs):
                f.result()

    def _round1(self, b):
        self._stage("round1")

        def lane(lz):
            self.events.add("lane", round=1, lens=lz, lens_ko=LZ.LENSES[lz]["ko"], status="thinking", sees=list(LZ.LENSES[lz]["sees"]))
            try:
                sysm, prompt = LZ.round1_prompt(lz, b)
                obj, meta = self.router.of(lz).complete(sysm, prompt, S.IdeaDraft)
            except Exception as e:                               # noqa: BLE001
                with self.lock:
                    self.state["lane_errors"].append({"round": 1, "lens": lz, "reason": str(e)[:300]})
                self.events.add("lane", round=1, lens=lz, status="error", reason=str(e)[:300]); return
            card = {"id": lz, "lens": lz, "lens_ko": LZ.LENSES[lz]["ko"], "provider": meta["provider"], "model": meta["model"], **obj.model_dump()}
            with self.lock:
                self.state["cards"].append(card)
                self.state["cards"].sort(key=lambda c: list(LZ.LENSES).index(c["id"]))
            self._used(lz, meta)
            self.events.add("card", round=1, card=card)
        self._lanes(lane, list(LZ.LENSES))
        self._save()

    def _round2(self, b):
        self._stage("round2")
        cards, ids = list(self.state["cards"]), {c["id"] for c in self.state["cards"]}

        def lane(lz):
            self.events.add("lane", round=2, lens=lz, lens_ko=LZ.LENSES[lz]["ko"], status="thinking")
            try:
                sysm, prompt = LZ.round2_prompt(lz, b, cards)
                obj, meta = self.router.of(lz).complete(sysm, prompt, S.RebuttalSet)
            except Exception as e:                               # noqa: BLE001
                with self.lock:
                    self.state["lane_errors"].append({"round": 2, "lens": lz, "reason": str(e)[:300]})
                self.events.add("lane", round=2, lens=lz, status="error", reason=str(e)[:300]); return
            kept, dropped = [], []
            for r in obj.rebuttals:
                row = {"by": lz, **r.model_dump()}
                (dropped if r.target == lz or r.target not in ids else kept).append(row)
            with self.lock:
                self.state["rebuttals"] += kept
                self.state["dropped_rebuttals"] += [{**d, "why": "자기 아이디어" if d["target"] == lz else "없는 아이디어"} for d in dropped]
            self._used(lz, meta)
            self.events.add("rebuttals", round=2, lens=lz, rebuttals=kept, dropped=len(dropped))
        self._lanes(lane, [c["id"] for c in cards])
        self.state["rebuttals"].sort(key=lambda r: (list(LZ.LENSES).index(r["by"]), r["target"]))
        self._save()

    # ------------------------------------------------------------ CC-06 the artist chooses, then realisation
    def choose(self, idea: str, note: str = "") -> dict:
        if self.state["stage"] != "choose":
            raise ValueError("고를 단계가 아니다: %s" % self.state["stage"])
        card = next((c for c in self.state["cards"] if c["id"] == idea), None)
        if card is None:
            raise ValueError("그런 아이디어가 없다: %s" % idea)
        short = [p["idea"] for p in (self.state["curator"] or {}).get("shortlist") or []]
        self.state["choice"] = {"idea": idea, "note": note, "in_shortlist": idea in short, "t": round(time.time(), 3)}
        self.events.add("chosen", **self.state["choice"])
        self._stage("realize")
        b = self.state["brief"]
        try:
            r, meta = AG.realize(self.router.of("realizer"), b, card, MS.sketch_world(card, b))
        except Exception as e:                                   # noqa: BLE001
            self._fail("realize", e); return self.state
        self._used("realizer", meta)
        w = r["world"]
        items = WK.render(w)
        plan = PR.plan(w, r["notes"])
        out = {"world": w, "why": r["why"], "cannot": r["cannot"], "plan": plan, "plan_md": PR.markdown(plan, "제작 지침 — " + w.get("name", "")),
               "works": [{k: it[k] for k in ("title", "medium", "plugin", "ok") if k in it} | ({"reason": it["reason"]} if not it["ok"] else {}) for it in items],
               "proposal": None}
        if self.session is not None:
            why = "공동 창작: %s 렌즈의 '%s' — %s" % (card["lens_ko"], card["title"], r["why"])
            with self.slock:
                p = self.session.propose(w, why[:400], kind="cocreate", extra={"cocreate": self.id, "idea": idea})
            out["proposal"] = p.get("proposal")
            out["understood_as"] = p.get("understood_as")
            if not p.get("ok"):
                out["proposal_error"] = p.get("error")
        if self.dir is not None:
            (self.dir / "world.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
            (self.dir / "production.md").write_text(out["plan_md"], encoding="utf-8")
        self.state["realization"] = out
        self.events.add("realized", proposal=out["proposal"], why=r["why"], cannot=r["cannot"], works=out["works"], plan_md=out["plan_md"])
        self._stage("done")
        return self.state

    def summary(self) -> dict:
        s = dict(self.state)
        if s.get("realization"):
            s["realization"] = {k: v for k, v in s["realization"].items() if k != "world"}
        return s
