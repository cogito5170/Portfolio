# -*- coding: utf-8 -*-
"""World rules checked on the Body ingredient (entities). Generic kinds only (P1: no style in code).
engine/runtime/src/rules.js is the JS twin (the editor shows these live); the tests compare both on fixtures.

    dimension_series  every authored size (box size, cylinder/cone height and diameter, sphere diameter, arch
                      width/height/depth/thickness) must be a value of the series (relative tolerance 1e-6)
    max_elements      number of entities (all depths) <= value
    palette           colours named by the world's materials (and inline entity materials) come from the palette
    forbidden (W-01)  type: no entity of that type (or its sub-types "value.*"); colour: no material in that colour;
                      word: not in anything a visitor reads or hears (captions, lines, text, tour captions)

Switches (E-03): a constraint or forbidden item with "enabled": false is not checked; an entity listing a kind in
"ignore_rules" breaks that rule on purpose and is not reported (nor counted, for max_elements).

    violations(world) -> [{"entity", "field", "value", "kind"}]   -- indicators for the artist (C-02), not verdicts
"""
from __future__ import annotations

SIZED = {"box": ("size",), "cylinder": ("height", "radius*2"), "cone": ("height", "radius*2"), "sphere": ("radius*2",),
         "capsule": ("height", "radius*2"), "arch": ("width", "height", "depth", "thickness")}
TEXT_FIELDS = ("caption", "text", "lines")


def _walk(entities):
    for e in entities or []:
        if not isinstance(e, dict):
            continue
        yield e
        yield from _walk(e.get("children"))


def _sizes(e):
    for f in SIZED.get(e.get("type"), ()):
        key, k = (f[:-2], 2.0) if f.endswith("*2") else (f, 1.0)
        if key not in e:
            continue
        for v in (e[key] if isinstance(e[key], list) else [e[key]]):
            yield f, v * k


def _on(rule) -> bool:
    return rule.get("enabled", True) is not False


def _ignores(e, kind) -> bool:
    return kind in (e.get("ignore_rules") or [])


def _colours(world, ents):
    """(entity label, field, colour) for every named colour: world materials, then inline entity materials."""
    for name, m in (world.get("materials") or {}).items():
        for f in ("color", "emissive"):
            if isinstance(m, dict) and isinstance(m.get(f), str):
                yield None, "materials." + name, f, m[f]
    for e in ents:
        m = e.get("material")
        if isinstance(m, dict):
            for f in ("color", "emissive"):
                if isinstance(m.get(f), str):
                    yield e, e.get("id"), "material." + f, m[f]


def _texts(world, ents):
    for e in ents:
        for f in TEXT_FIELDS:
            v = e.get(f)
            for s in (v if isinstance(v, list) else [v]):
                if isinstance(s, str):
                    yield e, e.get("id"), f, s
        for tr in e.get("triggers") or []:
            for a in (tr.get("do") or []) if isinstance(tr, dict) else []:
                if isinstance(a, dict) and isinstance(a.get("text"), str):
                    yield e, e.get("id"), "triggers.text", a["text"]
    for t in world.get("tours") or []:
        for st in (t.get("stops") or []) if isinstance(t, dict) else []:
            if isinstance(st, dict) and isinstance(st.get("caption"), str):
                yield None, "tours." + str(t.get("id")), "caption", st["caption"]       # str(None) == 'None', as rules.js


def violations(world: dict) -> "list[dict]":
    out = []
    ents = list(_walk(world.get("entities")))
    for c in (world.get("rules") or {}).get("constraints") or []:
        if not _on(c):
            continue
        if c["kind"] == "dimension_series":
            series = c["values_m"]
            for e in ents:
                if _ignores(e, "dimension_series"):
                    continue
                for f, v in _sizes(e):
                    if not any(abs(v - s) <= 1e-6 * s for s in series):
                        out.append({"entity": e.get("id"), "field": f, "value": v, "kind": "dimension_series"})
        elif c["kind"] == "max_elements":
            n = sum(1 for e in ents if not _ignores(e, "max_elements"))
            if n > c["value"]:
                out.append({"entity": None, "field": "entities", "value": n, "kind": "max_elements"})
        elif c["kind"] == "palette":
            allowed = {x.lower() for x in c["colours"]}
            for e, label, f, v in _colours(world, ents):
                if v.lower() not in allowed and not (e is not None and _ignores(e, "palette")):
                    out.append({"entity": label, "field": f, "value": v, "kind": "palette"})
    for rule in world.get("forbidden") or []:
        if not _on(rule):
            continue
        kind, val = rule["kind"], rule["value"]
        if kind == "type":
            for e in ents:
                t = e.get("type") or ""
                if (t == val or t.startswith(val + ".")) and not _ignores(e, "forbidden"):
                    out.append({"entity": e.get("id"), "field": "type", "value": t, "kind": "forbidden"})
        elif kind == "colour":
            for e, label, f, v in _colours(world, ents):
                if v.lower() == val.lower() and not (e is not None and _ignores(e, "forbidden")):
                    out.append({"entity": label, "field": f, "value": v, "kind": "forbidden"})
        elif kind == "word":
            for e, label, f, s in _texts(world, ents):
                if val.lower() in s.lower() and not (e is not None and _ignores(e, "forbidden")):
                    out.append({"entity": label, "field": f, "value": val, "kind": "forbidden"})
    return out


def output_violations(world: dict, artifact, media_type: str) -> "list[dict]":
    """X-03 on generator outputs (what a plugin made, measured by the core, not by the plugin): forbidden colours and
    words anywhere in a text artifact; for SVG also the palette (every #rrggbb used) and max_elements (drawn elements).
    Binary artifacts are not inspected (nothing to read without the medium's own decoder): they return no violations."""
    import re
    if isinstance(artifact, bytes):
        try:
            text = artifact.decode("utf-8")
        except UnicodeDecodeError:
            return []
    else:
        text = artifact
    out, low = [], text.lower()
    svg = "svg" in (media_type or "")
    for c in (world.get("rules") or {}).get("constraints") or []:
        if not _on(c) or not svg:
            continue
        if c["kind"] == "palette":
            allowed = {x.lower() for x in c["colours"]}
            for col in sorted(set(m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}\b", text))):
                if col not in allowed:
                    out.append({"entity": "output", "field": "colour", "value": col, "kind": "palette"})
        elif c["kind"] == "max_elements":
            n = len(re.findall(r"<(?:rect|circle|ellipse|line|polyline|polygon|path|text)\b", text))
            if n > c["value"]:
                out.append({"entity": "output", "field": "elements", "value": n, "kind": "max_elements"})
    for rule in world.get("forbidden") or []:
        if not _on(rule):
            continue
        if rule["kind"] in ("colour", "word") and rule["value"].lower() in low:
            out.append({"entity": "output", "field": rule["kind"], "value": rule["value"], "kind": "forbidden"})
    return out
