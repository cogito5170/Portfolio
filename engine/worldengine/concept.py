# -*- coding: utf-8 -*-
"""Concept rules -> planner settings. A concept card (world["concepts"]) says what idea a work follows; its
rules are the part a machine can act on. Each rule either changes the plan or is reported as not applied with
the reason -- never silently dropped.

    effects, opts, strokes = apply(concepts, "arm", strokes)
    effects == [{"concept", "param", "value", "applied": bool, "note"}]
"""
from __future__ import annotations


def _pen_lifts(v, opts, strokes):
    if v != 0:
        return False, "pen.lifts 는 0 만 지원한다 (한 번도 떼지 않는 선)"
    opts["continuous"] = True
    return True, "획 사이 이동도 펜을 내린 채 그린다 — 선 하나로 이어진다"


def _v_draw(v, opts, strokes):
    if not isinstance(v, (int, float)) or not 0.01 <= v <= 1.0:
        return False, "draw.v_draw 는 0.01~1.0 m/s"
    opts["v_draw"] = float(v)
    return True, "펜 속도 %.2f m/s" % v


def _max_strokes(v, opts, strokes):
    if not isinstance(v, int) or v < 1:
        return False, "draw.max_strokes 는 1 이상의 정수"
    del strokes[v:]
    return True, "획을 앞에서부터 %d개만 남긴다" % v


RULES = {"pen.lifts": _pen_lifts, "draw.v_draw": _v_draw, "draw.max_strokes": _max_strokes}


def apply(concepts, target_id: str, strokes, opts=None):
    opts, strokes, effects = dict(opts or {}), [list(s) for s in strokes], []
    for c in concepts or []:
        if c.get("drives") and target_id not in c["drives"]:
            continue
        for r in c.get("rules") or []:
            fn = RULES.get(r["param"])
            if fn is None:
                ok, note = False, "이 런타임은 아직 이 규칙을 모른다 (요구 기록부 대상)"
            else:
                ok, note = fn(r["value"], opts, strokes)
            effects.append({"concept": c["id"], "param": r["param"], "value": r["value"], "applied": ok, "note": note})
    return effects, opts, strokes


MEASURES = {   # param -> (measurement key in draw.verify, does the measured value obey the rule?)
    "pen.lifts": ("pen_lifts", lambda m, v: m == v),
    "draw.v_draw": ("pen_speed_max_mps", lambda m, v: m <= v * (1 + 1e-6)),
    "draw.max_strokes": (None, None),
}


def measure(effects, verify: dict):
    """Check each applied rule on the finished plan (not just that a setting was passed). Adds measured/met."""
    for e in effects:
        key, ok = MEASURES.get(e["param"], (None, None))
        if e["applied"] and key:
            e["measured"] = verify[key]; e["met"] = bool(ok(verify[key], e["value"]))
        else:
            e["measured"] = None; e["met"] = None if not e["applied"] else True
    return all(e["met"] is not False for e in effects)


# The demo concept. A well-known paraphrase, marked as such -- not a quote, and not an artist's own statement.
KLEE_WALK = {
    "id": "line_walk",
    "title": "산책하는 선",
    "statement": "선은 점이 산책을 나간 것이다. 그러니 이 선은 한 번 출발하면 끝날 때까지 종이에서 떨어지지 않고, 서두르지 않는다.",
    "sources": [{"who": "Paul Klee", "kind": "paraphrase",
                 "where": "Pädagogisches Skizzenbuch (Bauhausbücher 2, 1925) — 영어권에 널리 퍼진 의역 'a line is a dot that went for a walk'",
                 "note": "원문 인용이 아니라 의역. 해석과 규칙은 World Platform 데모가 정했다."},
                {"who": "World Platform 데모", "kind": "own", "note": "규칙 두 개(펜 떼지 않기, 천천히)는 데모의 번역이다"}],
    "rules": [{"param": "pen.lifts", "value": 0, "why": "산책은 끊기지 않는다"},
              {"param": "draw.v_draw", "value": 0.15, "why": "산책은 서두르지 않는다"}],
    "drives": ["arm"],
}
