# -*- coding: utf-8 -*-
"""SDK tools the agent calls. Strict JSON schemas (additionalProperties: false). None of them applies a change:
they describe, propose, generate previews, or queue an approval.

    TOOLS               -> list for messages.create(tools=...)
    run(session, name, input) -> dict (JSON-able tool result)
"""
from __future__ import annotations

import copy
import json

from pathlib import Path

from worldengine import combine as KB, concept as CP, constraints as CS, interpret as IN, plugins as PL, promote as PR, sandbox as SB, world as WD
from worldengine.studio import session as SS

AXES = list(WD.AXES)
ENTITY_TYPES = ["group", "box", "cylinder", "cone", "sphere", "capsule", "torus", "plane", "ground", "text", "light", "terrain", "path", "person", "arch"]


def _obj(props: dict, required: "list[str]") -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


_NUM3 = {"type": "array", "items": {"type": "number"}}
ENTITY = _obj({"id": {"type": "string"}, "type": {"type": "string", "enum": ENTITY_TYPES},
               "pos": _NUM3, "rot": _NUM3, "size": _NUM3, "radius": {"type": "number"}, "height": {"type": "number"},
               "material": {"type": "string"}, "text": {"type": "string"},
               "behavior": {"type": "string", "enum": ["none", "spin", "bob", "orbit"]}},
              ["id", "type", "pos"])

TOOLS = [
    {"name": "describe_world", "description": "현재 세계의 요약: 이름, 판, 스타일 축, 규칙(제약), 개념, 몸(엔티티) 수와 id, 표현. 무엇이든 바꾸기 전에 먼저 부른다.",
     "input_schema": _obj({}, [])},
    {"name": "propose_axes", "description": "스타일 축 값을 바꾸자고 제안한다(0~1). 적용은 작가가 한다. why 에 작가의 말을 어떻게 이해했는지 쓴다.",
     "input_schema": _obj({"changes": _obj({a: {"type": "number"} for a in AXES}, []), "why": {"type": "string"}}, ["changes", "why"])},
    {"name": "propose_entities", "description": "몸(엔티티)을 더하거나 고치거나 빼자고 제안한다. 위치는 미터, z 위. 적용은 작가가 한다.",
     "input_schema": _obj({"add": {"type": "array", "items": ENTITY},
                           "edit": {"type": "array", "items": _obj({"id": {"type": "string"}, "pos": _NUM3, "rot": _NUM3, "size": _NUM3,
                                                                     "radius": {"type": "number"}, "height": {"type": "number"}, "material": {"type": "string"}}, ["id"])},
                           "remove": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}}, ["add", "edit", "remove", "why"])},
    {"name": "propose_concept", "description": "개념 카드를 더하자고 제안한다. 출처를 반드시 밝힌다: 직접 인용(quote)이면 where 필수, 널리 알려진 말은 paraphrase, 작가 자신의 말은 interview, 우리가 정한 것은 own.",
     "input_schema": _obj({"id": {"type": "string"}, "title": {"type": "string"}, "statement": {"type": "string"},
                           "sources": {"type": "array", "items": _obj({"who": {"type": "string"}, "kind": {"type": "string", "enum": ["quote", "paraphrase", "own", "interview"]},
                                                                        "where": {"type": "string"}}, ["who", "kind", "where"])},
                           "why": {"type": "string"}}, ["id", "title", "statement", "sources", "why"])},
    {"name": "propose_variants", "description": "요청이 여러 뜻으로 읽힐 때, 질문 대신 해석이 서로 다른 시안 2~3개를 만든다. 각 시안은 축 변화로 표현한다.",
     "input_schema": _obj({"variants": {"type": "array", "items": _obj({"label": {"type": "string"}, "interpretation": {"type": "string"},
                                                                         "axes": _obj({a: {"type": "number"} for a in AXES}, [])}, ["label", "interpretation", "axes"])},
                           "why": {"type": "string"}}, ["variants", "why"])},
    {"name": "propose_revert", "description": "'아까가 나았어' 같은 말에: 이전 판으로 되돌리자고 제안한다(새 판으로 남는다, 기록은 지워지지 않는다).",
     "input_schema": _obj({"to_version": {"type": "integer"}, "why": {"type": "string"}}, ["to_version", "why"])},
    {"name": "history", "description": "판 목록과 각 판에서 바뀐 것.", "input_schema": _obj({}, [])},
    {"name": "preview", "description": "현재 세계로 생성기 플러그인 하나를 돌려 미리보기를 만든다(싸고 되돌릴 필요 없음). plugin: image_svg 또는 plotter.",
     "input_schema": _obj({"plugin": {"type": "string", "enum": ["image_svg", "plotter"]}}, ["plugin"])},
    {"name": "request_action", "description": "비용이 크거나 되돌리기 어려운 작업을 요청한다: render_highres, delete_work, publish, drive_device. 실행하지 않고 작가 승인 대기열에 넣는다.",
     "input_schema": _obj({"kind": {"type": "string", "enum": sorted(SS.NEEDS_APPROVAL)}, "why": {"type": "string"}}, ["kind", "why"])},
    {"name": "cannot_do", "description": "할 수 없는 요청일 때 부른다. 비슷한 다른 것으로 바꿔치기하지 말고, 못 하는 이유와 대안을 적는다. kind 는 못 하는 이유의 종류.",
     "input_schema": _obj({"request": {"type": "string"}, "reason": {"type": "string"}, "alternatives": {"type": "array", "items": {"type": "string"}},
                           "kind": {"type": "string", "enum": ["medium_missing", "hardware_missing", "capability_missing", "policy", "other"]}},
                          ["request", "reason", "alternatives", "kind"])},
    {"name": "propose_interpretations", "description": "철학·건축·작가의 개념을 실행 가능한 규칙으로 옮기는 해석 카드 2~3개를 시안으로 낸다. 각 해석은 근거(basis)와 규칙(축 값, 선택: 움직일 몸 id 와 행동)을 가진다. 출처를 정직하게.",
     "input_schema": _obj({"concept": _obj({"id": {"type": "string"}, "title": {"type": "string"}, "statement": {"type": "string"},
                                            "sources": {"type": "array", "items": _obj({"who": {"type": "string"}, "kind": {"type": "string", "enum": ["quote", "paraphrase", "own", "interview"]},
                                                                                         "where": {"type": "string"}}, ["who", "kind", "where"])}}, ["id", "title", "statement", "sources"]),
                           "readings": {"type": "array", "items": _obj({"label": {"type": "string"}, "reading": {"type": "string"}, "basis": {"type": "string"},
                                                                         "axes": _obj({a: {"type": "number"} for a in AXES}, []),
                                                                         "behavior": {"type": "string", "enum": ["none", "spin", "bob", "orbit"]},
                                                                         "drives": {"type": "array", "items": {"type": "string"}}}, ["label", "reading", "basis", "axes"])},
                           "why": {"type": "string"}}, ["concept", "readings", "why"])},
    {"name": "propose_combination", "description": "지금 세계와 다른 세계를 결합하자고 제안한다(평균 내지 않는다). bodies: juxtapose(나란히)·layer(겹침)·seam(경계)·viewpoint(아이 눈높이엔 B, 어른엔 A). other: 저장소의 세계 파일 이름(예: ref_festival_baroque).",
     "input_schema": _obj({"other": {"type": "string"}, "bodies": {"type": "string", "enum": ["juxtapose", "layer", "seam", "viewpoint"]},
                           "opposites": {"type": "array", "items": _obj({"a": {"type": "string"}, "b": {"type": "string"}}, ["a", "b"])},
                           "why": {"type": "string"}}, ["other", "bodies", "opposites", "why"])},
    {"name": "run_code", "description": "기존 도구로 안 되는 것을 표준 라이브러리 Python 코드로 시험한다. 네트워크 없음·임시 폴더만 쓰기·시간과 메모리 제한이 걸린 샌드박스에서 돈다. 입력은 input.json 의 world, 마지막 줄에 JSON 을 출력한다. 세계는 바뀌지 않는다.",
     "input_schema": _obj({"code": {"type": "string"}, "purpose": {"type": "string"}}, ["code", "purpose"])},
    {"name": "propose_plugin", "description": "run_code 로 시험한 생성기 코드를 작가의 플러그인으로 등록하자고 제안한다. 코드는 translate/generate/self_assess/ports 네 함수를 정의한다. 적합성 시험을 통과해야 승인 대기열에 들어간다.",
     "input_schema": _obj({"name": {"type": "string"}, "code": {"type": "string"}, "why": {"type": "string"}}, ["name", "code", "why"])},
]
for t in TOOLS:
    t["strict"] = True


def _describe(w):
    def walk(es):
        for e in es or []:
            yield e; yield from walk(e.get("children"))
    ents = list(walk(w.get("entities")))
    by = {}
    for e in ents:
        by[e["type"]] = by.get(e["type"], 0) + 1
    return {"name": w["name"], "version": w.get("version"), "axes": (w.get("rules") or {}).get("axes", {}),
            "constraints": (w.get("rules") or {}).get("constraints", []), "concepts": [{"id": c["id"], "title": c["title"]} for c in w.get("concepts") or []],
            "entities": {"count": len(ents), "by_type": by, "ids": [e.get("id") for e in ents if e.get("id")][:80]},
            "materials": sorted(w.get("materials") or {}), "expressions": w.get("expressions", [])}


def _axes_world(w, changes):
    w = copy.deepcopy(w)
    r = w.setdefault("rules", {}); ax = r.setdefault("axes", {})
    for k, v in changes.items():
        ax[k] = max(0.0, min(1.0, float(v)))
    return w


def _behaviour(name):
    return {"spin": [{"type": "spin", "axis": "z", "deg_per_s": 30}], "bob": [{"type": "bob", "amp": 0.1, "hz": 0.5}],
            "orbit": [{"type": "orbit", "radius": 1.5, "period_s": 8}]}.get(name, [])


def run(s: SS.Session, name: str, inp: dict) -> dict:
    w = s.world
    if name == "describe_world":
        return _describe(w)
    if name == "history":
        return {"versions": s.history()}
    if name == "propose_axes":
        return s.propose(_axes_world(w, inp["changes"]), inp["why"], "axes")
    if name == "propose_entities":
        ids = {e.get("id") for e in CS._walk(w.get("entities"))}
        for e in inp["add"]:
            if e["id"] in ids:
                return {"ok": False, "error": "id %r 는 이미 있다" % e["id"]}
            if e.get("material") and e["material"] not in (w.get("materials") or {}):
                return {"ok": False, "error": "재질 %r 이 이 세계에 없다. 있는 재질: %s" % (e["material"], ", ".join(sorted(w.get("materials") or {})))}
        missing = [x for x in [*(e["id"] for e in inp["edit"]), *inp["remove"]] if x not in ids]
        if missing:
            return {"ok": False, "error": "없는 id: " + ", ".join(missing)}
        new = copy.deepcopy(w)
        for e in inp["add"]:
            b = e.get("behavior", "none")
            ent = {k: v for k, v in e.items() if k != "behavior"}
            if _behaviour(b):
                ent["behaviors"] = _behaviour(b)
            new["entities"].append(ent)

        def patch(es):
            out = []
            for e in es:
                if e.get("id") in inp["remove"]:
                    continue
                ed = next((x for x in inp["edit"] if x["id"] == e.get("id")), None)
                if ed:
                    e = {**e, **{k: v for k, v in ed.items() if k != "id"}}
                if e.get("children"):
                    e = {**e, "children": patch(e["children"])}
                out.append(e)
            return out
        new["entities"] = patch(new["entities"])
        r = s.propose(new, inp["why"], "entities")
        v = CS.violations(new)
        if r.get("ok") and v:
            r["rule_warnings"] = ["%s.%s=%s 가 세계 규칙(%s)에 어긋난다" % (x["entity"], x["field"], x["value"], x["kind"]) for x in v[:5]]
        return r
    if name == "propose_concept":
        new = copy.deepcopy(w)
        card = {k: inp[k] for k in ("id", "title", "statement")}
        card["sources"] = [{k: v for k, v in so.items() if v} for so in inp["sources"]]
        new.setdefault("concepts", []).append(card)
        return s.propose(new, inp["why"], "concept")
    if name == "propose_variants":
        vs = inp["variants"]
        if not 2 <= len(vs) <= 3:
            return {"ok": False, "error": "시안은 2~3개 (A-03)"}
        set_id = "v%d" % (len(s.variant_sets) + 1)
        out = []
        for v in vs:
            r = s.propose(_axes_world(w, v["axes"]), v["interpretation"], "variant", {"variant_set": set_id, "label": v["label"]})
            out.append({"label": v["label"], **r})
        s.variant_sets.append({"id": set_id, "why": inp["why"], "proposals": [o["proposal"] for o in out if o.get("ok")], "base": s.versions[-1]["n"]})
        return {"ok": True, "variant_set": set_id, "variants": out, "note": "작가가 하나를 고르거나 고쳐서 적용한다"}
    if name == "propose_revert":
        n = inp["to_version"]
        if not 0 <= n < len(s.versions):
            return {"ok": False, "error": "판 %d 은 없다 (0~%d)" % (n, len(s.versions) - 1)}
        return s.propose(copy.deepcopy(s.versions[n]["world"]), inp["why"], "revert", {"to_version": n})
    if name == "preview":
        p = PL.discover()[inp["plugin"]]
        r = PL.generate(p, w)
        s.log.append(("preview", inp["plugin"], r["recipe"]["artifact_sha256"]))
        s.previews = getattr(s, "previews", []) + [{"plugin": inp["plugin"], "artifact": r["artifact"], "recipe": r["recipe"], "notes": r.get("notes", "")}]
        return {"ok": True, "plugin": inp["plugin"], "media_type": r["media_type"], "notes": r.get("notes", ""), "recipe": r["recipe"]}
    if name == "request_action":
        return s.request(inp["kind"], {}, inp["why"])
    if name == "cannot_do":
        s.log.append(("cannot_do", inp["request"]))
        if s.ledger is not None:
            s.ledger.record(s.last_request or inp["request"], "N5", inp.get("kind", "other"), inp["reason"], inp["alternatives"])
        return {"ok": True, "recorded": True, "shown_to_artist": {"request": inp["request"], "reason": inp["reason"], "alternatives": inp["alternatives"]}}
    if name == "propose_interpretations":
        rs = inp["readings"]
        if not 2 <= len(rs) <= 3:
            return {"ok": False, "error": "해석은 2~3개 (CT-02)"}
        set_id = "v%d" % (len(s.variant_sets) + 1)
        out = []
        for rd in rs:
            r = s.propose(IN.apply_reading(w, inp["concept"], rd), "%s — %s (근거: %s)" % (rd["label"], rd["reading"], rd["basis"]), "variant",
                          {"variant_set": set_id, "label": rd["label"], "interpretation": rd})
            out.append({"label": rd["label"], **r})
        s.variant_sets.append({"id": set_id, "why": inp["why"], "proposals": [o["proposal"] for o in out if o.get("ok")], "base": s.versions[-1]["n"]})
        return {"ok": True, "variant_set": set_id, "variants": out, "note": "해석 카드: 작가가 하나를 고르거나 고친다"}
    if name == "propose_combination":
        f = Path(__file__).resolve().parents[2] / "worlds" / (Path(inp["other"]).name.replace(".world.json", "") + ".world.json")
        if not f.exists():
            return {"ok": False, "error": "세계 %r 가 없다" % inp["other"]}
        other = WD.load(f)
        C = KB.combine(w, other, {"bodies": inp["bodies"]}, opposites=inp["opposites"])
        rec = KB.recognisability(C, w, other)
        r = s.propose(C, inp["why"], "combination")
        if r.get("ok"):
            r["recognisability"] = rec
        return r
    if name == "run_code":
        res = SB.run(inp["code"], inputs={"world": w})
        s.log.append(("run_code", inp["purpose"], res.get("ran")))
        keep = {k: res.get(k) for k in ("ran", "exit", "killed", "result", "reason")}
        keep["stdout_tail"], keep["stderr_tail"] = (res.get("stdout") or "")[-1500:], (res.get("stderr") or "")[-1500:]
        return {"ok": bool(res.get("ran")), **keep}
    if name == "propose_plugin":
        refs = [WD.load(Path(__file__).resolve().parents[2] / "worlds" / (n + ".world.json")) for n in ("ref_yeobaek", "ref_festival_baroque", "ref_modulor")]
        try:
            chk = PR.check(inp["code"], inp["name"], refs)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if not chk["ok"]:
            return {"ok": False, "error": chk["reason"], "conformance": [{k: x[k] for k in ("world", "clause", "ok", "detail")} for x in chk["rows"]]}
        r = s.request("promote_plugin", {"name": inp["name"], "code": inp["code"], "rows": [{k: x[k] for k in ("world", "clause", "ok")} for x in chk["rows"]]}, inp["why"])
        r["conformance"] = "%d/%d 통과" % (len(chk["rows"]), len(chk["rows"]))
        return r
    return {"ok": False, "error": "모르는 도구: %s" % name}


def run_json(s, name, inp) -> str:
    try:
        return json.dumps(run(s, name, inp), ensure_ascii=False)
    except Exception as e:                              # noqa: BLE001 -- the model sees the error and can correct itself
        return json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, ensure_ascii=False)
