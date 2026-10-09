# -*- coding: utf-8 -*-
"""Generator plugin contract (SPEC G-01..G-04) and discovery. Plugins live outside the core, one directory each:

    engine/plugins/<name>/plugin.py   defines  PLUGIN = {
        "name", "version", "medium",                       # e.g. "image", "drawing"
        "translate": (axes: dict) -> params: dict,         # G-02 common axes -> this medium's parameters (pure)
        "generate": (world, intent, params) -> {"artifact": str|bytes, "media_type": str, "notes": str?},   # G-01
        "self_assess": (world, artifact) -> {"score": 0..1, "notes": str},                                   # G-03
        "ports": (world, params) -> {"palette": [...], "tempo_bpm": float|None, "events": [...]},           # G-04
    }

The core wraps generate() so every result carries a recipe (G-01); regenerate(recipe, world) must give the same
bytes (V-05). The core, not the plugin, then measures the result against the world's rules (X-03: complexity
budget, palette, forbidden list -- constraints.output_violations) and refuses it (RuleViolation) unless the artist
switched that rule off (E-03). enforce=False returns the result with the violations, for review screens only.
Adding a plugin means adding a directory -- no core file changes (V-02, tested by hashing).
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
PLUGIN_DIR = ENGINE / "plugins"
REQUIRED = ("name", "version", "medium", "translate", "generate", "self_assess", "ports")


def world_hash(world: dict) -> str:
    return hashlib.sha256(json.dumps(world, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def discover(extra_dirs=()) -> "dict[str, dict]":
    """name -> PLUGIN dict, from engine/plugins/*/plugin.py plus any extra plugin roots. Problems raise, loudly."""
    found = {}
    for root in [PLUGIN_DIR, *map(Path, extra_dirs)]:
        for f in sorted(Path(root).glob("*/plugin.py")):
            spec = importlib.util.spec_from_file_location("we_plugin_" + f.parent.name, f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            P = getattr(mod, "PLUGIN", None)
            if not isinstance(P, dict):
                raise ValueError("%s: no PLUGIN dict" % f)
            missing = [k for k in REQUIRED if k not in P]
            if missing:
                raise ValueError("%s: PLUGIN lacks %s" % (f, ", ".join(missing)))
            if P["name"] in found:
                raise ValueError("plugin name %r defined twice (%s)" % (P["name"], f))
            found[P["name"]] = {**P, "path": str(f)}
    return found


def axes_of(world: dict) -> dict:
    return dict((world.get("rules") or {}).get("axes") or {})


class RuleViolation(ValueError):
    def __init__(self, plugin: str, violations: "list[dict]"):
        self.violations = violations
        super().__init__("%s: the result breaks the world's rules (X-03): %s" % (plugin, "; ".join(
            "%s %s=%s" % (v["kind"], v["field"], v["value"]) for v in violations[:5])))


def generate(plugin: dict, world: dict, intent: "dict | None" = None, params: "dict | None" = None, enforce: bool = True) -> dict:
    """Run a plugin and attach the recipe. params=None -> plugin.translate(world axes); edited params are used as given."""
    intent = dict(intent or {})
    w = copy.deepcopy(world)
    p = plugin["translate"](axes_of(w)) if params is None else copy.deepcopy(params)
    out = plugin["generate"](w, intent, copy.deepcopy(p))
    art = out["artifact"]
    data = art.encode("utf-8") if isinstance(art, str) else art
    from worldengine import constraints as CS
    v = CS.output_violations(world, art, out.get("media_type", ""))
    if v and enforce:
        raise RuleViolation(plugin["name"], v)
    return {**out, "rules": {"ok": not v, "violations": v},
            "recipe": {"plugin": plugin["name"], "plugin_version": plugin["version"], "world": world.get("name"),
                       "world_hash": world_hash(world), "intent": intent, "params": p,
                       "artifact_sha256": hashlib.sha256(data).hexdigest()}}


def regenerate(plugin: dict, recipe: dict, world: dict, enforce: bool = True) -> dict:
    if recipe["world_hash"] != world_hash(world):
        raise ValueError("recipe was made for another version of this world (%s != %s)" % (recipe["world_hash"], world_hash(world)))
    return generate(plugin, world, recipe["intent"], recipe["params"], enforce)
