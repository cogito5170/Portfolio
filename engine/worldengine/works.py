# -*- coding: utf-8 -*-
"""A world's other media, made for the player (T-02): every expression with a generator plugin (image, drawing, ...)
is generated through the core (recipe attached, world rules enforced, X-03). The player shows them beside the 3D
world so image, sound and interaction play as one work.

    items = render(world)  ->  [{"title", "medium", "plugin", "ok", "media_type", "artifact"|"reason", "recipe"}]
A result the world's rules refuse is listed with its reason, not silently dropped.
"""
from __future__ import annotations

from worldengine import plugins as PL

TITLES = {"image": "그림", "drawing": "로봇이 그린 그림", "sound": "소리"}


def render(world: dict, plugins: "dict | None" = None) -> "list[dict]":
    P = plugins if plugins is not None else PL.discover()
    out = []
    for i, ex in enumerate(world.get("expressions") or []):
        name = ex.get("plugin")
        if not name:
            continue                                  # web3d: the world itself
        item = {"title": ex.get("title") or TITLES.get(ex.get("medium"), ex.get("medium")), "medium": ex.get("medium"), "plugin": name, "index": i}
        if name not in P:
            out.append({**item, "ok": False, "reason": "플러그인 '%s' 이 이 기계에 없다" % name}); continue
        try:
            r = PL.generate(P[name], world, ex.get("intent") or {})
        except PL.RuleViolation as e:
            out.append({**item, "ok": False, "reason": "세계 규칙 때문에 만들지 않았다: " + "; ".join("%s %s" % (v["kind"], v["value"]) for v in e.violations[:3])}); continue
        out.append({**item, "ok": True, "media_type": r["media_type"], "artifact": r["artifact"], "recipe": r["recipe"]})
    return out


EXT = {"image/svg+xml": "svg", "image/png": "png", "audio/wav": "wav", "audio/x-wav": "wav"}


def index(items, src_of) -> dict:
    """The player's works list: {"items": [{"title", "medium", "media_type", "src"} | {"title", "reason"}]}.
    src_of(item) gives the URL where the artifact was written (relative to the runtime page)."""
    return {"items": [{"title": it["title"], "medium": it["medium"], "media_type": it["media_type"], "src": src_of(it)} if it["ok"]
                      else {"title": it["title"], "medium": it["medium"], "reason": it["reason"]} for it in items]}
