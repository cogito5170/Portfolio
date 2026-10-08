# -*- coding: utf-8 -*-
"""V-13 harness: request sentence + expected change scope -> did the agent's interpretation land in scope?

    rows = run(items, client_factory)      # one fresh session + agent per item
    score(item, turn, session) -> (ok, reasons)

Scope rules (kind):
  axes / axes_or_entities  every listed axis moved in the stated direction (proposal axes vs base), axes in `keep`
                           moved < 0.15, and nothing was applied (proposals only); axes_or_entities also accepts
                           an entity proposal (motion via behaviours, form via curved bodies)
  entities                 add_types all appear among added entities / remove_ids are removed
  concept                  a concept proposal whose sources include the expected kind (quotes must carry where)
  variants                 2-3 variant proposals; variants_or_axes also accepts an in-scope axes proposal
  approval                 request_action of that kind, nothing ran; approval_or_refuse also accepts cannot_do
  refuse                   cannot_do and no proposal
  revert                   a revert proposal to the stated version
The seed set is developer-written (see its label); a score on it is not a measure of the artist's language.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from worldengine import world as WD
from worldengine.studio import agent as AG, session as SS

ENGINE = Path(__file__).resolve().parents[2]


def load(path=None) -> dict:
    return json.loads(Path(path or ENGINE / "eval" / "v13_seed.json").read_text(encoding="utf-8"))


def _setup(item):
    w = WD.load(ENGINE / "worlds" / (item["world"] + ".world.json"))
    s = SS.Session(w)                                   # no executors: an approval can never run here
    if item["expect"].get("setup") == "one_change":
        w2 = copy.deepcopy(w); w2["rules"]["axes"]["density"] = 0.4
        s.apply(s.propose(w2, "설정: 밀도를 낮춘 판")["proposal"])
    return s


def score(item, turn, s) -> "tuple[bool, list[str]]":
    e, why = item["expect"], []
    base_axes = (s.versions[-1]["world"].get("rules") or {}).get("axes", {})
    props = [s.proposals[p] for p in turn["proposals"]]
    applied = [p for p in s.proposals.values() if p["status"] == "applied" and p["kind"] != "change"]
    if applied:
        why.append("에이전트 쪽에서 적용됨 (있어선 안 됨)")
    ran = [x for x in s.log if x[0] == "ran"]
    if ran:
        why.append("승인 없이 실행됨: %s" % ran)

    def axes_ok(p):
        a = (p["world"].get("rules") or {}).get("axes", {})
        for k, d in (e.get("axes") or {}).items():
            delta = a.get(k, 0) - base_axes.get(k, 0)
            if (d == "+" and delta <= 0) or (d == "-" and delta >= 0):
                return False
        return all(abs(a.get(k, 0) - base_axes.get(k, 0)) < 0.15 for k in e.get("keep", []))

    k = e["kind"]
    if k in ("axes", "axes_or_entities", "variants_or_axes"):
        good = [p for p in props if p["kind"] == "axes" and axes_ok(p)]
        if k == "axes_or_entities":
            good += [p for p in props if p["kind"] == "entities"]
        if k == "variants_or_axes" and 2 <= len([p for p in props if p["kind"] == "variant"]) <= 3:
            good += ["variants"]
        if not good:
            why.append("범위 안의 제안 없음 (제안 종류: %s)" % [p["kind"] for p in props])
    elif k == "entities":
        added = {x for p in props if p["kind"] == "entities" for x in p["diff"]["entities_added"]}
        types = {e2["type"] for p in props for e2 in p["world"]["entities"] if e2.get("id") in added}
        removed = {x for p in props for x in p["diff"]["entities_removed"]}
        if not set(e.get("add_types", [])) <= types:
            why.append("기대한 몸 추가 없음: %s" % e.get("add_types"))
        if not set(e.get("remove_ids", [])) <= removed:
            why.append("기대한 제거 없음: %s" % e.get("remove_ids"))
    elif k == "concept":
        cs = [c for p in props if p["kind"] == "concept" for c in p["world"].get("concepts", []) if c["id"] in p["diff"]["concepts_added"]]
        kinds = {so["kind"] for c in cs for so in c["sources"]}
        want = set(e.get("source_kind_any", [e.get("source_kind")]))
        if not cs or not (kinds & want):
            why.append("기대한 출처 종류(%s)의 개념 제안 없음 (받은 것: %s)" % (sorted(want), sorted(kinds)))
        if e.get("quote_needs_where") and any(so["kind"] == "quote" and not so.get("where") for c in cs for so in c["sources"]):
            why.append("인용인데 where 없음")
    elif k == "variants":
        n = len([p for p in props if p["kind"] == "variant"])
        if not 2 <= n <= 3:
            why.append("시안 %d개 (2~3개 기대)" % n)
    elif k in ("approval", "approval_or_refuse"):
        kinds = [s.approvals[a]["kind"] for a in turn["approvals"]]
        if e["approval"] not in kinds and not (k == "approval_or_refuse" and turn["refusals"]):
            why.append("승인 요청 %s 없음 (받은 것: %s)" % (e["approval"], kinds))
    elif k == "refuse":
        if not turn["refusals"]:
            why.append("cannot_do 없음")
        if props:
            why.append("거절해야 할 요청에 제안 %d개" % len(props))
    elif k == "revert":
        if not any(p["kind"] == "revert" and p.get("to_version") == e["to_version"] for p in props):
            why.append("판 %d 로 되돌리기 제안 없음" % e["to_version"])
    return (not why), why


def run(items, client_factory, model=None) -> "list[dict]":
    rows = []
    for it in items:
        s = _setup(it)
        ag = AG.Agent(client_factory(), s, None, model)
        turn = ag.send(it["request"])
        ok, why = score(it, turn, s)
        rows.append({"id": it["id"], "ok": ok, "why": why, "tools": [c["name"] for c in turn["tool_calls"]], "usage": turn["usage"],
                     "stop_reason": turn["stop_reason"]})
    return rows


def bound(n_items: int) -> dict:
    """Upper bound before spending anything: requests and output tokens are hard caps of the loop."""
    from worldengine.studio import config
    return {"items": n_items, "max_requests": n_items * config.MAX_TURNS, "max_output_tokens": n_items * config.MAX_TURNS * config.MAX_TOKENS}
