# -*- coding: utf-8 -*-
"""Contradiction synthesis (SPEC K-01..K-06): two worlds -> one, with a mode per attribute, never averaging by default.

    C = combine(A, B, modes={"bodies": "juxtapose", "materials": "keep", "axes": "viewpoint", ...}, name=...)
    recognisability(C, A, B) -> {"A": 0..1, "B": 0..1, "verdict": "both kept"|"absorbed by A/B"|"blurred"}

bodies modes:  juxtapose (B placed beside A), layer (B over A in the same place), seam (A keeps x < mid, B x >= mid),
               viewpoint (A shown at the adult eye height, B at the child eye height: entity field eye_only, K-04)
axes modes:    per_region (A's axes where A's bodies are, B's where B's are: rules.axes_by_region) | viewpoint (both
               kept: rules.axes_by_eye) | time (rules.axes_path from A to B over period_s, K-05) | keep_a | keep_b |
               per_axis {axis: "a"|"b"} | average (allowed when asked, never a default)
Default axes mode follows the bodies mode: juxtapose/seam -> per_region, viewpoint -> viewpoint, layer -> time.
Lineage (K-01): C["combined_from"] = [{name, version, hash}, ...] and C["combination"] = the modes used.
Opposite pairs (K-03): C["opposites"] = [{"a": "아이", "b": "어른", "mode": "viewpoint"}, ...] recorded as given.
"""
from __future__ import annotations

import copy

from worldengine import plugins as PL, world as WD


def _ids(es, prefix, out=None):
    out = [] if out is None else out
    for e in es:
        e = copy.deepcopy(e)
        if e.get("id"):
            e["id"] = prefix + e["id"]
        if e.get("material") and isinstance(e["material"], str):
            e["material"] = prefix + e["material"]
        if e.get("children"):
            e["children"] = _ids(e["children"], prefix)
        for tr in e.get("triggers") or []:
            for a in tr.get("do") or []:
                if a.get("target"):
                    a["target"] = prefix + a["target"]
                if a.get("tour"):
                    a["tour"] = prefix + a["tour"]
        out.append(e)
    return out


def _bounds(w):
    return w.get("bounds") or [20, 20, 6]


def combine(A: dict, B: dict, modes: "dict | None" = None, name: "str | None" = None, opposites=None) -> dict:
    bm0 = (modes or {}).get("bodies", "juxtapose")
    m = {"bodies": bm0, "axes": {"juxtapose": "per_region", "seam": "per_region", "viewpoint": "viewpoint", "layer": "time"}.get(bm0, "per_region"), **(modes or {})}
    ea, eb = _ids(A.get("entities") or [], "a_"), _ids(B.get("entities") or [], "b_")
    WA, DA, HA = _bounds(A); WB, DB, HB = _bounds(B)
    bm = m["bodies"]
    if bm == "juxtapose":
        gap = 4.0
        for e in eb:
            p = e.get("pos") or [0, 0, 0]; e["pos"] = [p[0] + WA + gap, p[1], p[2]]
        bounds = [WA + gap + WB, max(DA, DB), max(HA, HB)]
    elif bm in ("layer", "viewpoint"):
        bounds = [max(WA, WB), max(DA, DB), max(HA, HB)]
        if bm == "viewpoint":
            for e in ea:
                e["eye_only"] = "adult"
            for e in eb:
                e["eye_only"] = "child"
    elif bm == "seam":
        mid = max(WA, WB) / 2
        ea = [e for e in ea if (e.get("pos") or [0])[0] < mid or e.get("type") in ("light",)]
        eb = [e for e in eb if (e.get("pos") or [0])[0] >= mid or e.get("type") in ("light",)]
        bounds = [max(WA, WB), max(DA, DB), max(HA, HB)]
    else:
        raise ValueError("unknown bodies mode %r" % bm)
    axa, axb = (A.get("rules") or {}).get("axes") or {}, (B.get("rules") or {}).get("axes") or {}
    am, rules = m["axes"], {}
    if am == "per_region":
        rules["axes"] = dict(axa)
        rules["axes_by_region"] = {"a": dict(axa), "b": dict(axb)}
    elif am == "keep_a":
        rules["axes"] = dict(axa)
    elif am == "keep_b":
        rules["axes"] = dict(axb)
    elif am == "average":
        rules["axes"] = {k: (axa.get(k, 0.5) + axb.get(k, 0.5)) / 2 for k in set(axa) | set(axb)}
    elif am in ("viewpoint", "time"):
        rules["axes"] = dict(axa)
        if am == "viewpoint":
            rules["axes_by_eye"] = {"adult": dict(axa), "child": dict(axb)}
        else:
            rules["axes_path"] = {"from": dict(axa), "to": dict(axb), "period_s": float(m.get("period_s", 60))}
    elif isinstance(am, dict):
        rules["axes"] = {k: (axa if am.get(k, "a") == "a" else axb).get(k) for k in set(axa) | set(axb) if (axa if am.get(k, "a") == "a" else axb).get(k) is not None}
        m["axes"] = {"per_axis": am}
    else:
        raise ValueError("unknown axes mode %r" % am)
    mats = {"a_" + k: v for k, v in (A.get("materials") or {}).items()}
    mats.update({"b_" + k: v for k, v in (B.get("materials") or {}).items()})
    concepts = _ids_concepts(A, "a_") + _ids_concepts(B, "b_")
    C = {"format": WD.FORMAT, "name": name or "%s × %s" % (A["name"], B["name"]), "version": "1.0",
         "about": "결합 세계: %s 와 %s. 방식: %s" % (A["name"], B["name"], m),
         "bounds": bounds, "rules": rules, "materials": mats, "entities": ea + eb, "concepts": concepts,
         "expressions": [{"medium": "web3d"}],
         "combined_from": [{"name": W["name"], "version": W.get("version"), "hash": PL.world_hash(W)} for W in (A, B)],
         "combination": m, "opposites": list(opposites or []),
         "environment": copy.deepcopy(A.get("environment") or {}), "controls": {"default": "orbit"}}
    if bm == "viewpoint":
        C["player"] = {"eye": "adult", "eye_heights": {"child": 1.1, "adult": 1.7}}
    return C


def _ids_concepts(W, prefix):
    out = []
    for c in W.get("concepts") or []:
        c = copy.deepcopy(c); c["id"] = prefix + c["id"]
        c["drives"] = [prefix + d for d in c.get("drives") or []]
        out.append(c)
    return out


def recognisability(C: dict, A: dict, B: dict) -> dict:
    """K-06 / V-09 first measurement. For each source X, the MINIMUM of three preservation scores (a world blurred in
    any one channel is not recognisable, however well the others survive):
      bodies    -- share of X's entity types (multiset) still present in C under X's prefix
      materials -- share of X's material definitions still present unchanged
      axes      -- 1 - mean |axis_C - axis_X| over X's axes, where axis_C is what a visitor meets for X:
                   the eye-specific axes for viewpoint, the path end for time, its region for per_region, else C's axes
    Verdict: both >= 0.8 'both kept'; one >= 0.8 and the other < 0.5 'absorbed by'; otherwise 'blurred'."""
    def walk(es):
        for e in es or []:
            yield e; yield from walk(e.get("children"))
    ec = list(walk(C["entities"]))
    out = {}
    for tag, X, eye, end in (("A", A, "adult", "from"), ("B", B, "child", "to")):
        p = "a_" if tag == "A" else "b_"
        types_x = [e["type"] for e in walk(X.get("entities"))]
        have = [e["type"] for e in ec if (e.get("id") or "").startswith(p)] + [e["type"] for e in ec if not e.get("id")]
        pool, kept = list(have), 0
        for t in types_x:
            if t in pool:
                pool.remove(t); kept += 1
        bodies = kept / len(types_x) if types_x else 1.0
        mx = X.get("materials") or {}
        materials = sum(1 for k, v in mx.items() if C["materials"].get(p + k) == v) / len(mx) if mx else 1.0
        r = C.get("rules") or {}
        axc = ((r.get("axes_by_eye") or {}).get(eye) or (r.get("axes_path") or {}).get(end)
               or (r.get("axes_by_region") or {}).get(tag.lower()) or r.get("axes") or {})
        axx = (X.get("rules") or {}).get("axes") or {}
        axes = 1 - sum(abs(axc.get(k, 0.5) - v) for k, v in axx.items()) / len(axx) if axx else 1.0
        out[tag] = round(min(bodies, materials, axes), 4)          # recognisable only if every channel survives
        out[tag + "_parts"] = {"bodies": round(bodies, 4), "materials": round(materials, 4), "axes": round(axes, 4)}
    a, b = out["A"], out["B"]
    out["verdict"] = "both kept" if a >= 0.8 and b >= 0.8 else ("absorbed by A" if a >= 0.8 and b < 0.5 else ("absorbed by B" if b >= 0.8 and a < 0.5 else "blurred"))
    return out
