# -*- coding: utf-8 -*-
"""Scripted stand-ins for the model providers (no network, no key). The ideas below are written by the developer to
exercise the pipeline; they are not model output and say nothing about what a model would propose."""
from __future__ import annotations

import json
import threading

from worldengine.cocreate import schema as S

SAID = "외로움을 표현하고 싶어. 하지만 슬픈 사람을 직접 그리지는 않았으면 좋겠어."

BRIEF = {"schema": "creative_brief/1",
         "artist": {"environment": ["PC", "휴대폰"], "materials": [], "budget": None, "notes": None},
         "intent": {"theme": "외로움", "desired_effect": "관객이 고립감을 느끼게 한다", "said": "(모델이 바꿔 쓴 문장)"},
         "constraints": {"forbidden": [{"text": "슬픈 사람을 직접 묘사", "check": "judged", "kind": None, "value": None,
                                        "flag_types": ["person", "character"], "flag_words": ["슬픈", "우는"]},
                                       {"text": "빨간색은 쓰지 않는다", "check": "machine", "kind": "colour", "value": "#ff0000",
                                        "flag_types": [], "flag_words": []}]},
         "exploration": ["빈 공간", "거리감", "빛과 그림자", "부재의 흔적"],
         "deliverables": ["서로 다른 아이디어", "선정 근거", "시안", "제작 방법"], "uncertainties": ["매체와 재료 미정"]}

AX = dict(density=0.2, colour=0.2, form=0.4, texture=0.2, motion=0.2, sound=0.3, narrative=0.5)


def body(i, t, pos, **kw):
    b = {"id": i, "type": t, "pos": pos, "size": None, "radius": None, "height": None, "color": None, "caption": None, "behaviour": None, "trigger": None}
    b.update(kw)
    return b


def idea(title, premise, bodies, features, axes=None, needs=(), media=("web3d",)):
    return {"title": title, "premise": premise, "departures": ["관객 행동을 더했다"], "audience_experience": "관객이 걷는다",
            "media": list(media), "materials": ["합판"], "selfcheck": [{"constraint": "슬픈 사람을 직접 묘사", "kept": True, "how": "사람이 없다"}],
            "lens_note": "메모", "sketch": {"axes": {**AX, **(axes or {})}, "bounds": [12, 12, 4], "bodies": bodies, "features": list(features), "needs": list(needs)}}


IDEAS = {
    "emotion": idea("늦게 오는 대답", "말하면 방 반대편에서 늦게, 작게 메아리가 돌아온다.",
                    [body("hum", "sound", [10, 10, 1], caption="멀리서 늦게 돌아오는 메아리"), body("orb", "sphere", [10, 10, 1], radius=0.3, color="#c8c8d0", behaviour="react_mic")],
                    ["react_mic", "spatial_sound"], axes={"sound": 0.7}),
    "form": idea("벽을 보는 의자 열두 개", "의자 열두 개가 모두 벽을 향하고 안쪽으로 갈수록 서로 멀어진다.",
                 [body("c%d" % k, "box", [1 + k * 0.8, 1 + k * 0.6, 0], size=[0.45, 0.45, 0.9], color="#b8b0a2") for k in range(12)],
                 ["light"], axes={"density": 0.5, "form": 0.1}),
    "invert": idea("군중 속의 좁은 빛", "관객이 많을수록 각자를 비추는 빛이 좁아져 서로가 보이지 않는다.",
                   [body("lamp", "light", [6, 6, 3.5], color="#fff1dc"), body("floor", "plane", [6, 6, 0], size=[12, 12], color="#222222")],
                   ["light", "presence"], needs=["관객 수에 따라 빛을 바꾸는 기능 (엔진에 없음)"], axes={"colour": 0.1}),
    "audience": idea("혼자일 때만", "혼자 들어왔을 때만 소리가 난다. 다가가면 문장이 나타난다. 사람 모양 하나가 서 있다.",
                     [body("gate", "arch", [6, 1, 0], size=[2, 0.6, 2.4], color="#ff0000", trigger="near", caption="여기서부터 혼자"),
                      body("someone", "person", [6, 6, 0], height=1.7)],
                     ["near"], axes={"narrative": 0.8}),
}

CURATOR = {"notes": [{"idea": k, "strengths": ["분명하다"], "weaknesses": ["아직 거칠다"], "cliche": [], "rebuttals_weighed": [], "feasibility": "된다"} for k in IDEAS],
           "collisions": [{"a": "emotion", "b": "audience", "note": "둘 다 소리에 기댄다"}],
           "shortlist": [{"idea": "form", "reason": "형태만으로 말한다"}, {"idea": "emotion", "reason": "관객이 직접 겪는다"}, {"idea": "nope", "reason": "없는 id"}],
           "message_to_artist": "두 방향이 서로 다릅니다."}


def realization(card_id, world=None, notes=("합판을 먼저 재단한다",)):
    w = world or {"format": "world/1", "name": "실현: " + card_id, "version": "1", "bounds": [12, 12, 4],
                  "rules": {"axes": dict(AX)}, "expressions": [{"medium": "web3d"}, {"medium": "image", "plugin": "image_svg"}],
                  "materials": {"ply": {"color": "#b8b0a2", "roughness": 0.9}},
                  "entities": [{"id": "floor", "type": "plane", "pos": [6, 6, 0], "size": [12, 12], "material": "ply"},
                               {"id": "c1", "type": "box", "pos": [2, 2, 0], "size": [0.45, 0.45, 0.9], "material": "ply"},
                               {"id": "c2", "type": "box", "pos": [9, 8, 0], "size": [0.45, 0.45, 0.9], "material": "ply"},
                               {"id": "hum", "type": "sound", "pos": [10, 10, 1], "recipe": "tone", "freq": 180, "caption": "먼 울림"},
                               {"id": "orb", "type": "sphere", "pos": [10, 10, 1], "radius": 0.3, "material": "ply",
                                "behaviors": [{"type": "react", "input": "mic", "prop": "glow"}]}]}
    return {"world_json": json.dumps(w, ensure_ascii=False), "why": "스케치의 배치를 그대로 두고 소리를 더했다", "production_notes": list(notes),
            "cannot": [{"what": "관객 수에 반응", "why": "엔진에 없다", "alternative": "다가가면 반응"}]}


class Scripted:
    """complete() answers from a script keyed by the requested model; records every call (system, prompt)."""

    def __init__(self, name="anthropic", model="fake-model", script=None, fail=()):
        self.name, self.model, self.script, self.fail = name, model, dict(script or {}), set(fail)
        self.calls, self._lock = [], threading.Lock()

    def complete(self, system, prompt, model_cls):
        with self._lock:
            self.calls.append({"system": system, "prompt": prompt, "model": model_cls.__name__})
        if model_cls.__name__ in self.fail:
            raise RuntimeError("scripted failure: " + model_cls.__name__)
        ans = self.script[model_cls.__name__]
        ans = ans(system, prompt) if callable(ans) else ans
        return S.validate(model_cls, ans), {"provider": self.name, "model": self.model, "usage": {"input_tokens": 10, "output_tokens": 5}, "attempts": 1}


def lens_of(system):
    from worldengine.cocreate import lenses as LZ
    return next(k for k, v in LZ.LENSES.items() if v["role"] in system)


def rebut(system, prompt):
    me = lens_of(system)
    others = [k for k in IDEAS if k != me]
    return {"rebuttals": [{"target": o, "kind": "cliche", "point": "%s 가 본 %s 의 약점" % (me, o)} for o in others] +
            [{"target": me, "kind": "other", "point": "자기 것 (버려져야 한다)"}]}


def script(realize=None):
    return {"CreativeBrief": BRIEF, "IdeaDraft": lambda s, p: IDEAS[lens_of(s)], "RebuttalSet": rebut,
            "CuratorReport": CURATOR, "Realization": realize or (lambda s, p: realization("chosen"))}


def router(**kw):
    from worldengine.cocreate.providers import Router
    a = Scripted("anthropic", "fake-a", script(**kw))
    g = Scripted("gemini", "fake-g", script(**kw))
    by = {"brief": a, "emotion": a, "form": g, "invert": a, "audience": g, "curator": a, "realizer": a}
    return Router(by, a), a, g
