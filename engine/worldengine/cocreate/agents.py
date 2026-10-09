# -*- coding: utf-8 -*-
"""The non-lens agents (CC-01, CC-05, CC-06): brief writer, curator, realizer. Each is one structured call through a
provider; none of them can apply anything (the session's proposal/apply split stays the only way in, A-02).

    brief = draft_brief(provider, said, world=None)        -> creative_brief/1 dict (the artist confirms or edits it)
    report = curate(provider, brief, cards, rebuttals, measured)   -> CuratorReport dict (no numbers, CC-05)
    r = realize(provider, brief, card, measured_idea)       -> {"world", "why", "notes", "cannot", "attempts"} | raises
"""
from __future__ import annotations

import json

from worldengine import constraints as CS, world as WD
from worldengine.cocreate import schema as S
from worldengine.cocreate.providers import ProviderError

BRIEF_SYSTEM = """너는 예술가의 말을 creative_brief/1 명세로 옮긴다. 해석하지 말고 옮긴다.
- intent.said 에는 예술가의 말을 한 글자도 바꾸지 않고 넣는다.
- 금지 조건(constraints.forbidden): 엔진이 확실히 막을 수 있는 것(몸 종류 type, 색 colour #rrggbb, 관객이 읽거나 듣는 단어 word)만 check=machine 으로,
  나머지(예: "슬픈 사람을 직접 묘사")는 check=judged 로 두고 나오면 표시할 몸 종류(flag_types: 예 person, character)와 단어(flag_words)를 적는다.
  사람을 모두 금지한 것이 아니면 person 을 machine 으로 막지 않는다.
- 예술가가 말하지 않은 것은 채우지 말고 uncertainties 에 쓴다. 예술가가 말한 탐구 방향만 exploration 에 쓴다.
- deliverables 의 기본값: 서로 다른 아이디어, 선정 근거, 시안, 제작 방법.
- 한국어로 쓴다."""

CURATOR_SYSTEM = """너는 큐레이터다. 아이디어를 쓰거나 고치지 않는다. 비교하고, 근거를 쓰고, 2~3개를 추천한다.
- 측정값(measured)은 코드가 잰 지표다. 근거로 쓰되 그것만으로 판정하지 않는다. 독창성이나 예술적 가치에 점수를 매기지 않는다.
- 진부함(cliche): 이 주제에서 흔히 떠올리는 장치를 그대로 쓴 곳을 구체적으로 짚는다.
- 충돌(collisions): 서로 너무 비슷하거나, 같은 장치에 기대는 아이디어 쌍.
- 반박(rebuttals)을 읽고, 맞다고 본 것과 아니라고 본 것을 rebuttals_weighed 에 쓴다.
- 금지 조건 위반(machine_forbidden)이 있는 아이디어는 그 사실을 먼저 쓴다. judged_flags 는 작가가 판단할 일이라고 쓴다.
- shortlist 는 서로 다른 방향 2~3개. 고르는 것은 예술가다. message_to_artist 는 두세 문장.
- 한국어로 쓴다."""

REALIZER_SYSTEM = """너는 예술가가 고른 아이디어 하나를 world/1 세계 전체로 옮긴다. 아이디어를 바꾸지 않는다.
- 스케치(sketch)를 출발점으로 쓰고, 아이디어의 전제와 관객 경험이 실제로 일어나게 몸·행동·소리·빛·투어를 채운다.
- 엔진에 없는 것은 지어내지 말고 cannot 에 무엇이, 왜, 대신 무엇을 했는지 쓴다.
- 금지 조건(forbidden)은 세계에 그대로 넣고 어기지 않는다. 소리 몸(sound)마다 caption(자막)이 있어야 한다.
- world_json 은 아래 참고 세계와 같은 형식의 JSON 문자열이다. 쓰는 필드는 참고 세계에 있는 것만.
- production_notes 에는 실제로 만들 때의 순서와 주의점을 쓴다 (측정값이 아니라 메모로 표시된다).
- 한국어로 쓴다."""

REFERENCE = {   # every field the realizer may use, in a world the core accepts (tested: WD.check == [])
    "format": "world/1", "name": "참고", "version": "1", "bounds": [12, 12, 4],
    "rules": {"axes": {"density": 0.2, "colour": 0.3, "form": 0.5, "texture": 0.2, "motion": 0.3, "sound": 0.4, "narrative": 0.5},
              "physics": {"gravity_mps2": 9.81, "time_scale": 1.0}},
    "expressions": [{"medium": "web3d"}],
    "environment": {"background": "#e9e6df", "exposure": 1.0, "ambient": 0.6, "bloom": {"strength": 0.6, "radius": 0.4, "threshold": 0.8}},
    "materials": {"wall": {"color": "#d9d4ca", "roughness": 0.9}, "glow": {"color": "#111111", "emissive": "#ffd36e", "emissive_intensity": 2.0}},
    "entities": [
        {"id": "floor", "type": "plane", "pos": [6, 6, 0], "size": [12, 12], "material": "wall"},
        {"id": "block", "type": "box", "pos": [3, 3, 0], "size": [1, 1, 2], "material": "wall", "rot": [0, 0, 15]},
        {"id": "pillar", "type": "cylinder", "pos": [8, 3, 0], "radius": 0.3, "height": 3, "material": "wall"},
        {"id": "orb", "type": "sphere", "pos": [6, 8, 1], "radius": 0.4, "material": "glow",
         "behaviors": [{"type": "react", "input": "mic", "prop": "glow", "amount": 1}, {"type": "bob", "amp": 0.1, "hz": 0.3}],
         "triggers": [{"on": "tap", "do": [{"action": "play", "target": "hum"}, {"action": "caption", "text": "낮게 울린다"}]}]},
        {"id": "gate", "type": "arch", "pos": [6, 1, 0], "width": 2, "height": 2.4, "depth": 0.5, "thickness": 0.4, "material": "wall",
         "triggers": [{"on": "near", "radius": 2.0, "do": [{"action": "caption", "text": "들어오면 조용해진다"}]}]},
        {"id": "hum", "type": "sound", "pos": [6, 8, 1.5], "recipe": "chord", "freqs": [110, 165], "wave": "sine", "caption": "낮은 화음"},
        {"id": "sign", "type": "text", "pos": [6, 11, 1.5], "size": [3, 0.4], "text": "여기"},
        {"id": "lamp", "type": "light", "pos": [6, 6, 3.5], "kind": "point", "color": "#fff1dc", "intensity": 20, "distance": 12},
    ],
    "tours": [{"id": "walk", "title": "한 바퀴", "stops": [{"pos": [6, 0, 1.6], "target": [6, 6, 1], "dwell_s": 3, "caption": "입구"}]}],
}


def draft_brief(provider, said: str, world: "dict | None" = None) -> "tuple[dict, dict]":
    ctx = ""
    if world:
        ctx = "\n\n지금 열려 있는 세계 (참고만, 명세에 억지로 넣지 않는다): %s, 금지 목록 %s" % (world.get("name"), json.dumps(world.get("forbidden") or [], ensure_ascii=False))
    obj, meta = provider.complete(BRIEF_SYSTEM, "예술가의 말:\n" + said + ctx, S.CreativeBrief)
    b = obj.data()
    b["intent"]["said"] = said                       # verbatim, whatever the model wrote there
    return b, meta


def curate(provider, brief: dict, cards: "list[dict]", rebuttals: "list[dict]", measured: dict) -> "tuple[dict, dict]":
    shown = [{k: c[k] for k in ("id", "lens_ko", "title", "premise", "departures", "audience_experience", "media", "materials", "selfcheck", "lens_note", "sketch")} for c in cards]
    obj, meta = provider.complete(CURATOR_SYSTEM, json.dumps({"brief": brief, "ideas": shown, "rebuttals": rebuttals, "measured": measured}, ensure_ascii=False, indent=1),
                                  S.CuratorReport)
    rep = obj.model_dump()
    ids = {c["id"] for c in cards}
    rep["shortlist"] = [p for p in rep["shortlist"] if p["idea"] in ids][:3]
    rep["notes"] = [n for n in rep["notes"] if n["idea"] in ids]
    if len(cards) >= 2 and len(rep["shortlist"]) < 2:      # the artist chooses anyway; say that the curator fell short
        rep["shortlist_note"] = "큐레이터가 있는 아이디어 중 %d개만 추천했다 (2~3개를 요청함)" % len(rep["shortlist"])
    return rep, meta


def realize(provider, brief: dict, card: dict, sketch_world: dict) -> "tuple[dict, dict]":
    fb = [{"kind": f["kind"], "value": f["value"]} for f in brief["constraints"]["forbidden"] if f["check"] == "machine"]
    judged = [f["text"] for f in brief["constraints"]["forbidden"] if f["check"] == "judged"]
    prompt = json.dumps({"brief": brief, "idea": {k: v for k, v in card.items() if k not in ("provider", "model", "usage")},
                         "sketch_world": sketch_world, "forbidden_machine": fb, "forbidden_judged": judged,
                         "reference_world": REFERENCE}, ensure_ascii=False, indent=1)
    errs, total = None, {"input_tokens": 0, "output_tokens": 0}
    for attempt in (1, 2):
        p = prompt if errs is None else prompt + "\n\n앞의 world_json 이 엔진 검사에서 떨어졌다. 고칠 것:\n" + "\n".join(errs[:12])
        obj, meta = provider.complete(REALIZER_SYSTEM, p, S.Realization)
        total = {k: total[k] + meta["usage"][k] for k in total}
        try:
            w = json.loads(obj.world_json)
        except ValueError as e:
            errs = ["world_json 이 JSON 이 아니다: %s" % e]; continue
        if isinstance(w, dict):
            w["forbidden"] = (w.get("forbidden") or []) + [f for f in fb if f not in (w.get("forbidden") or [])]
        errs = WD.check(w) + ["%s %s=%s (%s)" % (v["kind"], v["field"], v["value"], v["entity"]) for v in (CS.violations(w) if isinstance(w, dict) and not WD.check(w) else [])
                              if v["kind"] == "forbidden"]
        if not errs:
            return {"world": w, "why": obj.why, "notes": list(obj.production_notes), "cannot": [c.model_dump() for c in obj.cannot]}, \
                {**meta, "usage": total, "attempts": attempt}
    raise ProviderError("구현 결과가 엔진 검사를 두 번 다 통과하지 못했다: " + "; ".join(errs[:5]))
