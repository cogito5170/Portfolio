# -*- coding: utf-8 -*-
"""Conformance kit (SPEC G-05): does a generator plugin keep G-01..G-04? Run on every reference world.

    rows = run(plugin, worlds)   # [{"plugin", "world", "clause", "ok", "detail"}]

G-01 result + recipe, recipe JSON-serialisable; V-05 regenerate(recipe) is byte-identical; the world is not mutated
G-02 translate is pure, every param it returns is in the recipe, and editing one param changes the artifact
     (judged only when the plugin repeats itself -- otherwise any 'change' is noise)
G-03 self_assess returns a score in [0,1] and notes
G-04 ports expose at least one of palette/tempo/events; palette entries are "#rrggbb"
"""
from __future__ import annotations

import copy
import json
import re

from worldengine import plugins as PL


def _edits(params: dict):
    """Candidate single-parameter edits: numbers scaled/shifted, booleans flipped."""
    for k, v in params.items():
        if isinstance(v, bool):
            yield k, not v
        elif isinstance(v, int):
            yield k, v + max(1, abs(v) // 2)
        elif isinstance(v, float):
            yield k, v * 1.5 + 0.1


def run(plugin: dict, worlds: "list[dict]") -> "list[dict]":
    rows = []
    add = lambda w, c, ok, d="": rows.append({"plugin": plugin["name"], "world": w.get("name"), "clause": c, "ok": bool(ok), "detail": d})
    for w in worlds:
        before = copy.deepcopy(w)
        try:
            r1 = PL.generate(plugin, w)
        except Exception as e:                                    # noqa: BLE001 -- a crashing plugin fails conformance
            add(w, "G-01", False, "generate raised %s: %s" % (type(e).__name__, e)); continue
        ok = "artifact" in r1 and "media_type" in r1
        try:
            json.dumps(r1["recipe"]); ser = True
        except TypeError:
            ser = False
        add(w, "G-01", ok and ser and w == before, "artifact+media_type, JSON recipe, world untouched")
        def clause(name, fn):                                       # a clause that raises fails that clause, not the kit
            try:
                fn()
            except Exception as e:                                  # noqa: BLE001
                add(w, name, False, "%s: %s" % (type(e).__name__, str(e).splitlines()[-1][:200] if str(e) else ""))

        state = {}

        def v05():
            state["r2"] = PL.regenerate(plugin, r1["recipe"], w)
            add(w, "V-05", state["r2"]["artifact"] == r1["artifact"], "regenerate from recipe: %s" % ("identical" if state["r2"]["artifact"] == r1["artifact"] else "DIFFERENT"))

        def g02():
            a = PL.axes_of(w)
            p1, p2 = plugin["translate"](dict(a)), plugin["translate"](dict(a))
            state["p1"] = p1
            changed = None
            for k, v in _edits(p1):
                q = dict(p1); q[k] = v
                if PL.generate(plugin, w, params=q)["artifact"] != r1["artifact"]:
                    changed = k; break
            repeatable = "r2" in state and state["r2"]["artifact"] == r1["artifact"]   # an unrepeatable plugin 'changes' on every call
            add(w, "G-02", repeatable and p1 == p2 and p1 == r1["recipe"]["params"] and changed is not None,
                ("translate pure, params in recipe, edit of %r changes output" % changed if changed else "no single-param edit changed the output")
                if repeatable else "output not repeatable, so an edit's effect cannot be shown")

        def g03():
            sa = plugin["self_assess"](w, r1["artifact"])
            add(w, "G-03", isinstance(sa, dict) and isinstance(sa.get("score"), (int, float)) and 0 <= sa["score"] <= 1 and isinstance(sa.get("notes"), str),
                "score %s" % sa.get("score") if isinstance(sa, dict) else repr(sa))

        def g04():
            po = plugin["ports"](w, state.get("p1") or plugin["translate"](PL.axes_of(w)))
            pal = po.get("palette") or []
            add(w, "G-04", isinstance(po, dict) and (pal or po.get("tempo_bpm") or po.get("events")) and all(isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in pal),
                "ports: %s" % ", ".join(k for k in ("palette", "tempo_bpm", "events") if po.get(k)))
        for name, fn in (("V-05", v05), ("G-02", g02), ("G-03", g03), ("G-04", g04)):
            clause(name, fn)
    return rows
