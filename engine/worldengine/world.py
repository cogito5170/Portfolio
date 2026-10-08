# -*- coding: utf-8 -*-
"""World format "world/1" (Python side). The runtime reads it; engine/runtime/src/world.js is the JS twin of check().

Both check() functions are run on the same fixtures by the tests, so the two sides cannot drift apart silently.
Unknown fields are kept (open data). check() reports, it never fixes.
"""
from __future__ import annotations

import json
import math


def _js(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))   # JSON.stringify spelling, so messages match world.js
from pathlib import Path

FORMAT = "world/1"
EYE_HEIGHTS = {"child": 1.1, "adult": 1.7}


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _vec(v, n) -> bool:
    return isinstance(v, list) and len(v) == n and all(_num(x) for x in v)


def check(w, known_types=None) -> "list[str]":
    if not isinstance(w, dict):
        return ["world must be an object"]
    bad = []
    if w.get("format") != FORMAT:
        bad.append('format must be "%s": %s' % (FORMAT, _js(w.get("format"))))
    if not isinstance(w.get("name"), str) or not w.get("name"):
        bad.append("name must be a non-empty string")
    if "bounds" in w and not (_vec(w["bounds"], 3) and all(v > 0 for v in w["bounds"])):
        bad.append("bounds must be three positive numbers: %s" % _js(w["bounds"]))
    if not isinstance(w.get("entities"), list):
        bad.append("entities must be a list")
    ids = set()
    mats = w.get("materials") or {}

    def walk(lst, path):
        for i, e in enumerate(lst or []):
            p = "%s[%d]" % (path, i)
            if not isinstance(e, dict):
                bad.append("%s must be an object" % p); continue
            t = e.get("type")
            if not isinstance(t, str):
                bad.append("%s.type must be a string" % p)
            elif known_types is not None and t not in known_types:
                bad.append('%s.type unknown: "%s"' % (p, t))
            if "id" in e:
                if e["id"] in ids:
                    bad.append('%s.id duplicated: "%s"' % (p, e["id"]))
                ids.add(e["id"])
            if "pos" in e and not _vec(e["pos"], 3):
                bad.append("%s.pos must be [x,y,z]" % p)
            if "rot" in e and not _vec(e["rot"], 3):
                bad.append("%s.rot must be [rx,ry,rz] degrees" % p)
            if "scale" in e and not (_num(e["scale"]) or _vec(e["scale"], 3)):
                bad.append("%s.scale must be a number or [sx,sy,sz]" % p)
            m = e.get("material")
            if isinstance(m, str) and m not in mats and "." not in m:
                bad.append('%s.material "%s" is not in materials' % (p, m))
            if "children" in e:
                if not isinstance(e["children"], list):
                    bad.append("%s.children must be a list" % p)
                else:
                    walk(e["children"], p + ".children")

    if isinstance(w.get("entities"), list):
        walk(w["entities"], "entities")
    for k, v in (w.get("views") or {}).items():
        if not (isinstance(v, dict) and _vec(v.get("pos"), 3) and _vec(v.get("target"), 3) and _num(v.get("fov")) and 0 < v["fov"] < 180):
            bad.append("views.%s needs pos, target, fov (0..180)" % k)
    pl = w.get("player")
    if pl is not None:
        if "spawn" in pl and not _vec(pl["spawn"], 2):
            bad.append("player.spawn must be [x,y]")
        if "eye" in pl and pl["eye"] not in {**EYE_HEIGHTS, **(pl.get("eye_heights") or {})}:
            bad.append('player.eye unknown: "%s"' % pl["eye"])
    _check_concepts(w, ids, bad)
    mode = (w.get("controls") or {}).get("default")
    if mode is not None and mode not in ("orbit", "walk"):
        bad.append('controls.default must be orbit|walk: "%s"' % mode)
    return bad


SOURCE_KINDS = ("quote", "paraphrase", "own", "interview")


def _check_concepts(w, ids, bad):
    """Concept cards (the Concept ingredient). Every claim names its source and how it was used; rules say what
    they change; drives must point at entities that exist."""
    cs = w.get("concepts")
    if cs is None:
        return
    if not isinstance(cs, list):
        bad.append("concepts must be a list"); return
    seen = set()
    for i, c in enumerate(cs):
        p = "concepts[%d]" % i
        if not isinstance(c, dict):
            bad.append("%s must be an object" % p); continue
        if not isinstance(c.get("id"), str) or not c.get("id"):
            bad.append("%s.id must be a non-empty string" % p)
        elif c["id"] in seen:
            bad.append('%s.id duplicated: "%s"' % (p, c["id"]))
        else:
            seen.add(c["id"])
        for k in ("title", "statement"):
            if not isinstance(c.get(k), str) or not c.get(k):
                bad.append("%s.%s must be a non-empty string" % (p, k))
        src = c.get("sources")
        if not isinstance(src, list) or not src:
            bad.append("%s.sources must be a non-empty list (say where the idea comes from, even if it is your own)" % p)
        else:
            for j, so in enumerate(src):
                if not isinstance(so, dict) or not so.get("who"):
                    bad.append("%s.sources[%d].who is required" % (p, j))
                elif so.get("kind") not in SOURCE_KINDS:
                    bad.append('%s.sources[%d].kind must be one of %s: %s' % (p, j, "|".join(SOURCE_KINDS), _js(so.get("kind"))))
                elif so.get("kind") == "quote" and not so.get("where"):
                    bad.append("%s.sources[%d] is a quote: where (book/page/url) is required" % (p, j))
        for j, r in enumerate(c.get("rules") or []):
            if not isinstance(r, dict) or not isinstance(r.get("param"), str) or "value" not in r:
                bad.append("%s.rules[%d] needs param and value" % (p, j))
        for d in c.get("drives") or []:
            if d not in ids:
                bad.append('%s.drives "%s" is not an entity id' % (p, d))


def from_scene(sc: dict) -> dict:
    """A render3d scene (layout.to_scene) -> a world with one retail.store entity. Views and bounds carry over."""
    keep = {k: sc[k] for k in ("name", "y_axis", "bounds", "shell", "boxes", "columns", "signs", "people", "views") if k in sc}
    W, D, _H = sc["bounds"]
    return {
        "format": FORMAT, "name": sc["name"], "bounds": list(sc["bounds"]),
        "provenance": {"from": "render3d scene", "fidelity": sc.get("fidelity", "미표기")},
        "entities": [{"id": "store", "type": "retail.store", "scene": keep}],
        "views": sc.get("views", {}),
        "player": {"spawn": [W / 2, 1.0], "yaw_deg": 90},
        "controls": {"default": "orbit"},
    }


def load(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(w: dict, path) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path)
