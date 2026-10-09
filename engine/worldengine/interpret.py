# -*- coding: utf-8 -*-
"""Concept translator (SPEC CT-01..04).

CT-01 interpretation card: a concept (with its sources, CT-03) and 2-3 readings, each turned into executable rules
      -- axes, constraints, behaviours -- with its basis written next to it.
CT-02 the readings go to the studio as a variant set; the artist picks or corrects one.
CT-03 sources stay on the concept card in the world (shown on the HUD card and the landing page when published).
CT-04 copy_risk(): a request that asks to reproduce a specific named work or a named artist's signature style closely
      gets a WARNING. It never blocks: the artist decides, and the platform makes no legal judgement.
"""
from __future__ import annotations

import copy
import re

_COPY_VERBS = r"(그대로|똑같이|똑같은|베껴|베끼|복제|카피|따라\s*그려|모작|exactly\s+like|copy|replicate|same\s+as)"
_NAMED = r"(「[^」]+」|『[^』]+』|\"[^\"]+\"|'[^']+'|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+|[가-힣]{2,}\s*의\s*(작품|그림|화풍|스타일|조각|건물|영화))"


def copy_risk(text: str) -> "dict | None":
    """Warning only (CT-04). Returns None when there is nothing to warn about."""
    if re.search(_COPY_VERBS, text or "", re.I) and re.search(_NAMED, text or ""):
        return {"level": "warning", "blocks": False,
                "message": "특정 작품이나 작가의 고유한 화풍을 거의 그대로 따라 하려는 요청으로 보여요. 계속할지는 작가가 정해요. "
                           "플랫폼은 법적 판단을 하지 않아요. 영감을 받은 요소(구도·색·개념)를 골라 바꿔 쓰는 방법도 있어요."}
    return None


def apply_reading(world: dict, concept: dict, reading: dict) -> dict:
    """One reading -> a new world: the concept card (with this reading recorded) + its rules applied."""
    w = copy.deepcopy(world)
    card = {k: concept[k] for k in ("id", "title", "statement", "sources")}
    card["interpretation"] = {"label": reading["label"], "reading": reading["reading"], "basis": reading["basis"]}
    w["concepts"] = [c for c in w.get("concepts") or [] if c["id"] != card["id"]] + [card]
    rules = w.setdefault("rules", {})
    ax = rules.setdefault("axes", {})
    for k, v in (reading.get("axes") or {}).items():
        ax[k] = max(0.0, min(1.0, float(v)))
    if reading.get("constraints"):
        rules["constraints"] = [c for c in rules.get("constraints") or [] if c["kind"] not in {x["kind"] for x in reading["constraints"]}] + reading["constraints"]
    if reading.get("behavior") and reading.get("drives"):
        b = {"spin": {"type": "spin", "axis": "z", "deg_per_s": 20}, "bob": {"type": "bob", "amp": 0.1, "hz": 0.4},
             "orbit": {"type": "orbit", "radius": 1.5, "period_s": 10}}.get(reading["behavior"])

        def walk(es):
            for e in es or []:
                if e.get("id") in reading["drives"] and b:
                    e["behaviors"] = (e.get("behaviors") or []) + [dict(b)]
                walk(e.get("children"))
        walk(w.get("entities"))
        card["drives"] = list(reading["drives"])
    return w
