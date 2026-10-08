# -*- coding: utf-8 -*-
"""World-rule constraints checked on the Body ingredient (entities). Generic kinds only (P1: no style in code):

    dimension_series  every authored size (box size, cylinder/cone height and diameter, sphere diameter, arch
                      width/height/depth/thickness) must be a value of the series (relative tolerance 1e-6)
    max_elements      number of entities (all depths) <= value
    palette           colours named by the world's own materials must come from the palette

    violations(world) -> [{"entity", "field", "value", "kind"}]
"""
from __future__ import annotations

SIZED = {"box": ("size",), "cylinder": ("height", "radius*2"), "cone": ("height", "radius*2"), "sphere": ("radius*2",),
         "capsule": ("height", "radius*2"), "arch": ("width", "height", "depth", "thickness")}


def _walk(entities):
    for e in entities or []:
        yield e
        yield from _walk(e.get("children"))


def _sizes(e):
    for f in SIZED.get(e.get("type"), ()):
        key, k = (f[:-2], 2.0) if f.endswith("*2") else (f, 1.0)
        if key not in e:
            continue
        for v in (e[key] if isinstance(e[key], list) else [e[key]]):
            yield f, v * k


def violations(world: dict) -> "list[dict]":
    out = []
    ents = list(_walk(world.get("entities")))
    for c in (world.get("rules") or {}).get("constraints") or []:
        if c["kind"] == "dimension_series":
            series = c["values_m"]
            for e in ents:
                for f, v in _sizes(e):
                    if not any(abs(v - s) <= 1e-6 * s for s in series):
                        out.append({"entity": e.get("id"), "field": f, "value": v, "kind": "dimension_series"})
        elif c["kind"] == "max_elements" and len(ents) > c["value"]:
            out.append({"entity": None, "field": "entities", "value": len(ents), "kind": "max_elements"})
        elif c["kind"] == "palette":
            allowed = {x.lower() for x in c["colours"]}
            for name, m in (world.get("materials") or {}).items():
                for f in ("color", "emissive"):
                    if isinstance(m.get(f), str) and m[f].lower() not in allowed:
                        out.append({"entity": "materials." + name, "field": f, "value": m[f], "kind": "palette"})
    return out
