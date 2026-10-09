# -*- coding: utf-8 -*-
"""The four lenses (CC-03). They differ in what they are SHOWN, not only in what they are told: each lens gets its
own view of the brief, built here in code, so "think differently" does not rest on a prompt alone.

    view(lens, brief)            -> the part of creative_brief/1 this lens may read
    round1_prompt(lens, brief)   -> (system, prompt)        round 1: alone, without the other lenses (CC-04)
    round2_prompt(lens, brief, cards) -> (system, prompt)   round 2: reads every card, objects to the others' ideas
"""
from __future__ import annotations

import json

from worldengine.cocreate import schema as S

LENSES = {
    "emotion": {"ko": "감정", "sees": ("intent", "exploration", "forbidden", "uncertainties"),
                "role": "너는 감정에서 출발한다. 관객이 거칠 감정의 순서(처음 → 전환 → 끝)를 먼저 정하고, 그 순서를 만드는 장치를 찾는다. "
                        "재료와 매체는 감정이 정한 뒤에 따라온다. lens_note 에 감정의 순서를 쓴다."},
    "form": {"ko": "형태·재료", "sees": ("theme", "exploration", "artist", "forbidden", "deliverables"),
             "role": "너는 형태와 재료, 구조에서 출발한다. 치수, 배치, 재료의 성질(무게, 빛을 받는 방식, 소리)로만 말한다. "
                     "premise 와 title 에 감정을 가리키는 단어를 쓰지 않는다. lens_note 에 핵심 치수와 구조를 쓴다."},
    "invert": {"ko": "발상 전환", "sees": ("all",),
               "role": "너는 이 주제에 대해 사람들이 당연하게 여기는 전제를 하나 골라 뒤집는다. 낯선 연결과 역설을 찾는다. "
                       "lens_note 에 '뒤집은 전제: …' 를 한 줄로 쓴다. 뒤집은 결과가 단지 반대말이면 실패다."},
    "audience": {"ko": "관객", "sees": ("intent", "environment", "forbidden"),
                 "role": "너는 관객의 몸과 행동에서 출발한다. 관객이 무엇을 하고(걷기, 말하기, 누르기, 기다리기, 혼자/여럿), 그때 작품에서 무엇이 일어나는지 쓴다. "
                         "작가의 설명이 없어도 관객이 겪을 수 있어야 한다. lens_note 에 관객 행동 → 작품 반응을 차례로 쓴다."},
}

COMMON = """너는 예술가와 함께 작업하는 공동 창작자다. 예술가의 명세(creative_brief/1)의 일부를 받고, 작품 아이디어 하나를 낸다.
지킬 것:
1. 예술가의 말을 벗어나도 된다. 그러나 벗어난 것(예술가가 말하지 않았는데 네가 더한 것)은 departures 에 빠짐없이 쓴다.
2. 금지 조건은 selfcheck 에 하나씩 지켰는지와 어떻게 지켰는지 쓴다.
3. 평균적인 취향으로 가지 않는다. 무난한 것보다 분명한 것을 낸다.
4. sketch 는 엔진이 그릴 수 있는 것만 쓴다: 몸 종류 {types}; 기능 {features}.
   엔진에 없는 것이 필요하면 지어내지 말고 sketch.needs 에 쓴다.
5. sketch 의 axes 는 0~1 (밀도·색·형태(곡선)·질감·움직임·소리·서사). 몸은 30개 이하. 단위는 미터, z 가 위.
6. 소리 몸(sound)에는 caption(자막)을 꼭 쓴다. 들을 수 없는 관객도 작품을 겪어야 한다.
7. 특정 작가의 화풍을 그대로 따라 하지 않는다.
8. 한국어로 쓴다.
{role}"""


def view(lens: str, brief: dict) -> dict:
    sees = LENSES[lens]["sees"]
    if "all" in sees:
        return json.loads(json.dumps(brief))
    out = {"schema": brief["schema"]}
    for k in sees:
        if k == "theme":
            out["intent"] = {"theme": brief["intent"]["theme"]}
        elif k == "forbidden":
            out["forbidden"] = [f["text"] for f in brief["constraints"]["forbidden"]]
        elif k == "environment":
            out["environment"] = list(brief["artist"]["environment"])
        else:
            out[k] = json.loads(json.dumps(brief[k]))
    return out


def system(lens: str) -> str:
    return COMMON.format(types=", ".join(S.BODY_TYPES), features=", ".join("%s(%s)" % kv for kv in S.FEATURES.items()),
                         role=LENSES[lens]["role"])


def round1_prompt(lens: str, brief: dict) -> "tuple[str, str]":
    return system(lens), ("예술가의 명세 (네 렌즈가 볼 수 있는 부분):\n" + json.dumps(view(lens, brief), ensure_ascii=False, indent=1) +
                          "\n\n다른 렌즈의 생각은 보지 않는다. 너의 아이디어 하나를 낸다.")


REBUT = """
지금은 2라운드다. 모든 렌즈의 아이디어(네 것 포함)를 읽고, 다른 렌즈의 아이디어를 반박한다.
- 다른 아이디어마다 가장 약한 곳 하나 이상: 진부함(cliche), 명세 위반(breaks_brief), 만들 수 없음(not_feasible), 효과가 약함(weak_effect), 내적 모순(contradiction), 기타(other).
- target 에는 아이디어 id 를 쓴다. 네 아이디어(id: {own})는 반박하지 않는다.
- 같이 동의하는 척하지 않는다. 근거 없는 칭찬은 쓰지 않는다. 네 렌즈의 관점에서 반박한다."""


def round2_prompt(lens: str, brief: dict, cards: "list[dict]") -> "tuple[str, str]":
    shown = [{k: c[k] for k in ("id", "lens_ko", "title", "premise", "departures", "audience_experience", "media", "materials", "lens_note", "sketch")} for c in cards]
    return system(lens) + REBUT.format(own=lens), ("예술가의 명세 (네 렌즈가 볼 수 있는 부분):\n" + json.dumps(view(lens, brief), ensure_ascii=False, indent=1) +
                                                   "\n\n1라운드 아이디어들:\n" + json.dumps(shown, ensure_ascii=False, indent=1))
