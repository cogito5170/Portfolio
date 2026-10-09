# -*- coding: utf-8 -*-
"""What the curator is GIVEN, measured by code (CC-05). Indicators, not verdicts: the curator writes reasons from
them and the artist decides. No number here claims to measure originality or artistic value.

    w = sketch_world(card, brief)          the idea's sketch as a world/1 (checked by the core)
    m = measure(cards, brief, history=())  per idea: world errors, missing features, machine-forbidden violations,
                                           judged flags, brief echo, nearest earlier version; pairwise distances
"""
from __future__ import annotations

import itertools

from worldengine import constraints as CS, footprint as FP, world as WD

AXES = ("density", "colour", "form", "texture", "motion", "sound", "narrative")


def machine_forbidden(brief: dict) -> "list[dict]":
    return [{"kind": f["kind"], "value": f["value"]} for f in brief["constraints"]["forbidden"] if f["check"] == "machine"]


def _entity(b: dict) -> dict:
    e = {"id": b["id"], "type": b["type"], "pos": list(b["pos"])}
    t = b["type"]
    if t in ("box", "plane", "text") and b.get("size"):
        e["size"] = list(b["size"][:3 if t == "box" else 2])
    if t in ("cylinder", "cone", "sphere", "capsule", "torus") and b.get("radius") is not None:
        e["radius"] = b["radius"]
    if t in ("cylinder", "cone", "capsule", "person") and b.get("height") is not None:
        e["height"] = b["height"]
    if t == "arch":
        e.update({"width": (b.get("size") or [2])[0], "height": b.get("height") or 2.4})
    if b.get("color") and t not in ("sound", "light", "person"):
        e["material"] = {"color": b["color"]}
    if t == "light":
        e.update({"kind": "point", "color": b.get("color") or "#ffffff", "intensity": 20})
    if t == "sound":
        e.update({"recipe": "tone", "freq": 220, "caption": b.get("caption") or "(자막 없음)"})
    if t == "text":
        e["text"] = b.get("caption") or ""
    elif b.get("caption") and t != "sound":
        e["caption"] = b["caption"]
    beh = b.get("behaviour")
    if beh in ("spin", "bob", "fall", "orbit"):
        e["behaviors"] = [{"type": beh}]
    elif beh in ("react_mic", "react_camera"):
        e["behaviors"] = [{"type": "react", "input": beh[6:], "prop": "glow"}]
    if b.get("trigger"):
        e["triggers"] = [{"on": b["trigger"], **({"radius": 2.0} if b["trigger"] == "near" else {}),
                          "do": [{"action": "caption", "text": b.get("caption") or b["id"]}]}]
    return e


def sketch_world(card: dict, brief: dict) -> dict:
    sk = card["sketch"]
    w = {"format": WD.FORMAT, "name": card["title"][:80] or card["id"], "version": "sketch",
         "about": "공동 창작 시안 (%s 렌즈) — 스케치일 뿐 완성 작품이 아니다" % card.get("lens_ko", card["id"]),
         "rules": {"axes": {k: sk["axes"][k] for k in AXES}}, "expressions": [{"medium": "web3d"}],
         "entities": [_entity(b) for b in sk["bodies"]]}
    if sk.get("bounds") and len(sk["bounds"]) == 3 and all(v > 0 for v in sk["bounds"]):
        w["bounds"] = list(sk["bounds"])
    fb = machine_forbidden(brief)
    if fb:
        w["forbidden"] = fb
    return w


def _dist_axes(a: dict, b: dict) -> float:
    return sum(abs(a[k] - b.get(k, 0.5)) for k in AXES) / len(AXES)


def _types(w: dict) -> set:
    return {e.get("type") for e in w.get("entities") or []}


def _jaccard_dist(a: set, b: set) -> float:
    return 1.0 - (len(a & b) / len(a | b)) if (a | b) else 0.0


def measure(cards: "list[dict]", brief: dict, history: "list[dict]" = ()) -> dict:
    ex = [w for w in brief.get("exploration") or [] if w.strip()]
    judged = [f for f in brief["constraints"]["forbidden"] if f["check"] == "judged"]
    per, worlds = {}, {}
    for c in cards:
        w = sketch_world(c, brief)
        worlds[c["id"]] = w
        text = " ".join([c["title"], c["premise"], c["audience_experience"]] + [b.get("caption") or "" for b in c["sketch"]["bodies"]])
        flags = []
        for f in judged:
            hit_t = sorted({b["type"] for b in c["sketch"]["bodies"] if b["type"] in (f.get("flag_types") or [])})
            hit_w = sorted({x for x in (f.get("flag_words") or []) if x and x in text})
            if hit_t or hit_w:
                flags.append({"constraint": f["text"], "types": hit_t, "words": hit_w, "note": "사람이 판단할 금지 조건에 걸릴 수 있다 — 막지 않고 표시만 한다"})
        area = FP.area_table(w)
        near = None
        for v in history:
            ax = (v.get("world", {}).get("rules") or {}).get("axes")
            if isinstance(ax, dict):
                d = round(_dist_axes(w["rules"]["axes"], ax), 3)
                if near is None or d < near["axes_distance"]:
                    near = {"version": v.get("n"), "axes_distance": d, "types_distance": round(_jaccard_dist(_types(w), _types(v["world"])), 3)}
        per[c["id"]] = {"world_errors": WD.check(w), "needs": list(c["sketch"]["needs"]),
                        "machine_forbidden": [v for v in CS.violations(w) if v["kind"] == "forbidden"],
                        "judged_flags": flags, "echo": [x for x in ex if x in c["title"] + c["premise"]],
                        "bodies": len(c["sketch"]["bodies"]), "covered_m2": area["covered_m2"], "nearest_version": near}
    pairs = []
    for a, b in itertools.combinations(cards, 2):
        wa, wb = worlds[a["id"]], worlds[b["id"]]
        pairs.append({"a": a["id"], "b": b["id"], "axes_distance": round(_dist_axes(wa["rules"]["axes"], wb["rules"]["axes"]), 3),
                      "types_distance": round(_jaccard_dist(_types(wa), _types(wb)), 3),
                      "shared_features": sorted(set(a["sketch"]["features"]) & set(b["sketch"]["features"]))})
    closest = min(pairs, key=lambda p: p["axes_distance"] + p["types_distance"]) if pairs else None
    return {"ideas": per, "pairs": pairs, "closest_pair": closest,
            "method": "axes_distance = 7축 차이의 평균(0~1), types_distance = 몸 종류 집합의 자카드 거리(0~1). "
                      "echo = 명세의 탐구 단어를 제목·전제에 그대로 쓴 것. 독창성 점수가 아니다."}
