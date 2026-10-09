# -*- coding: utf-8 -*-
"""A working session on one world.

- versions: every applied change is a new version (full world copy + why + diff). Going back is itself a new
  version ("아까가 나았어" never destroys history) -- A-05.
- proposals: the agent only proposes. A proposal carries the changed world and the "이렇게 이해했다" summary; the
  artist applies it (optionally after editing it) or rejects it -- A-02. The agent has no tool that applies.
- approvals: costly or irreversible actions are queued, never run by the agent -- A-06. Only approve() runs one,
  and only the studio server calls approve(), on the artist's click.
"""
from __future__ import annotations

import copy
import itertools
import time

from worldengine import world as WD
from worldengine.studio import diff as DF

NEEDS_APPROVAL = {
    "render_highres": "고해상도 렌더 — 시간이 오래 걸린다",
    "delete_work": "작품(모든 판) 삭제 — 되돌릴 수 없다",
    "publish": "외부 공개 — 링크를 받은 누구나 본다",
    "drive_device": "실제 장치 구동 — 물리적으로 움직인다",
    "promote_plugin": "새 플러그인 등록 — 샌드박스·적합성 시험을 통과한 코드를 작가의 플러그인으로 남긴다",
}


class Session:
    def __init__(self, world: dict, executors: "dict | None" = None, ledger=None):
        bad = WD.check(world)
        if bad:
            raise ValueError("invalid world: " + "; ".join(bad[:3]))
        self.versions = [{"n": 0, "world": copy.deepcopy(world), "why": "시작", "diff": None, "t": time.time()}]
        self.proposals, self.approvals, self.variant_sets = {}, {}, []
        self._ids = itertools.count(1)
        self.executors = executors or {}          # kind -> callable(session, args) ; run only by approve()
        self.log = []                             # what ran, for tests and the artist
        self.ledger = ledger                      # N-05: unmet requests (private)
        self.last_request = ""

    # ---------------------------------------------------------------- versions
    @property
    def world(self) -> dict:
        return copy.deepcopy(self.versions[-1]["world"])

    def history(self) -> "list[dict]":
        return [{"n": v["n"], "why": v["why"], "summary": DF.summary_ko(v["diff"]) if v["diff"] else []} for v in self.versions]

    # ---------------------------------------------------------------- proposals (A-02)
    def propose(self, new_world: dict, why: str, kind: str = "change", extra: "dict | None" = None) -> dict:
        bad = WD.check(new_world)
        if bad:
            return {"ok": False, "error": "이 변경은 세계 형식을 깨뜨린다: " + "; ".join(bad[:3])}
        pid = "p%d" % next(self._ids)
        d = DF.diff(self.versions[-1]["world"], new_world)
        self.proposals[pid] = {"id": pid, "kind": kind, "world": copy.deepcopy(new_world), "why": why, "diff": d,
                               "base": self.versions[-1]["n"], "status": "pending", **(extra or {})}
        return {"ok": True, "proposal": pid, "understood_as": DF.summary_ko(d), "why": why, "applied": False,
                "note": "작가가 적용하기 전까지 아무것도 바뀌지 않았다"}

    def apply(self, pid: str, edited_world: "dict | None" = None) -> dict:
        """Artist action. edited_world: the artist corrected the proposal (e.g. moved a slider) before applying."""
        p = self.proposals[pid]
        if p["status"] != "pending":
            raise ValueError("proposal %s is %s" % (pid, p["status"]))
        w = copy.deepcopy(edited_world if edited_world is not None else p["world"])
        bad = WD.check(w)
        if bad:
            raise ValueError("invalid world: " + "; ".join(bad[:3]))
        d = DF.diff(self.versions[-1]["world"], w)
        self.versions.append({"n": len(self.versions), "world": w, "why": p["why"] + (" (작가가 고쳐서 적용)" if edited_world is not None else ""), "diff": d, "t": time.time()})
        p["status"] = "applied"
        return {"version": self.versions[-1]["n"], "summary": DF.summary_ko(d)}

    def edit(self, new_world: dict, why: str = "") -> dict:
        """Artist action (E-01): the artist changed the world directly in the editor. It becomes a new version like any
        applied change, so it can be compared, previewed and reverted; nothing is proposed or approved on their behalf."""
        bad = WD.check(new_world)
        if bad:
            raise ValueError("invalid world: " + "; ".join(bad[:3]))
        d = DF.diff(self.versions[-1]["world"], new_world)
        if not d or not any(d.values()):
            return {"version": self.versions[-1]["n"], "summary": [], "unchanged": True}
        self.versions.append({"n": len(self.versions), "world": copy.deepcopy(new_world), "why": "작가가 직접 고침" + (": " + why if why else ""),
                              "diff": d, "t": time.time()})
        return {"version": self.versions[-1]["n"], "summary": DF.summary_ko(d)}

    def reject(self, pid: str, note: str = "") -> None:
        self.proposals[pid]["status"] = "rejected"
        self.proposals[pid]["artist_note"] = note

    # ---------------------------------------------------------------- approvals (A-06)
    def request(self, kind: str, args: dict, why: str) -> dict:
        if kind not in NEEDS_APPROVAL:
            return {"ok": False, "error": "모르는 작업: %s" % kind}
        aid = "a%d" % next(self._ids)
        self.approvals[aid] = {"id": aid, "kind": kind, "args": args, "why": why, "status": "waiting"}
        return {"ok": True, "approval": aid, "status": "needs_approval", "ran": False,
                "message": "%s. 작가가 승인하기 전에는 실행하지 않는다." % NEEDS_APPROVAL[kind]}

    def approve(self, aid: str) -> dict:
        a = self.approvals[aid]
        if a["status"] != "waiting":
            raise ValueError("approval %s is %s" % (aid, a["status"]))
        fn = self.executors.get(a["kind"])
        a["status"] = "approved"
        if fn is None:
            a["result"] = {"ran": False, "reason": "이 스튜디오에는 '%s' 실행기가 연결돼 있지 않다" % a["kind"]}
        else:
            a["result"] = {"ran": True, **(fn(self, a["args"]) or {})}
            self.log.append(("ran", a["kind"], a["args"]))
        return a["result"]

    def decline(self, aid: str) -> None:
        self.approvals[aid]["status"] = "declined"
