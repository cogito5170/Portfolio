# -*- coding: utf-8 -*-
"""image_svg -- procedural 2D image (SPEC M-01, procedural half). Deterministic SVG; no dependencies.

Axis -> parameter translation (G-02, editable):
  density  -> n (number of marks), margin (empty border)       texture -> width_var (stroke-width variation)
  colour   -> n_colours, saturation                            motion  -> rot_max (degrees of rotation spread)
  form     -> curve (share of curved marks)
World constraints honoured: palette (colours used as given), max_elements (caps n), dimension_series (mark sizes
snap to the series, scaled so its largest value spans half the canvas).
"""
from __future__ import annotations

import colorsys
import random
import re

SIZE = 800


def _f(x):
    return ("%.2f" % x).rstrip("0").rstrip(".")


def translate(axes: dict) -> dict:
    a = lambda k, d=0.5: float(axes.get(k, d))
    return {"n": int(round(3 + 397 * a("density") ** 2)), "margin": round(0.05 + 0.3 * (1 - a("density")), 4),
            "n_colours": 1 + int(round(7 * a("colour"))), "saturation": round(0.05 + 0.9 * a("colour"), 4),
            "curve": round(a("form"), 4), "width_var": round(a("texture"), 4), "rot_max": round(180 * a("motion"), 2),
            "seed": 1}


def _constraints(world):
    out = {}
    for c in (world.get("rules") or {}).get("constraints") or []:
        if c.get("enabled", True) is not False:          # E-03: a rule the artist switched off is not honoured
            out[c["kind"]] = c
    return out


def _palette(params, cons, rng):
    if "palette" in cons:
        return list(cons["palette"]["colours"])
    base = rng.random()
    cols = []
    for i in range(max(1, params["n_colours"])):
        h = (base + i / max(1, params["n_colours"])) % 1.0
        r, g, b = colorsys.hls_to_rgb(h, 0.5 if params["saturation"] > 0.2 else 0.15, params["saturation"])
        cols.append("#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255)))
    return cols


def generate(world: dict, intent: dict, params: dict) -> dict:
    cons, rng = _constraints(world), random.Random(int(params.get("seed", 1)) * 7919 + int(intent.get("seed", 0)))
    n = int(params["n"])
    if "max_elements" in cons:
        n = min(n, cons["max_elements"]["value"])
    pal = _palette(params, cons, rng)
    bg, ink = ("#f7f5f0", pal) if len(pal) < 2 or "palette" not in cons else (pal[0], pal[1:])
    series = sorted(cons["dimension_series"]["values_m"]) if "dimension_series" in cons else None
    m = params["margin"] * SIZE
    lo, hi = m, SIZE - m
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (SIZE, SIZE, SIZE, SIZE),
           '<rect x="0" y="0" width="%d" height="%d" fill="%s"/>' % (SIZE, SIZE, bg)]
    for i in range(n):
        if series:
            s = series[rng.randrange(len(series))] / series[-1] * SIZE * 0.5
        else:
            s = (hi - lo) * (0.02 + 0.3 * rng.random() ** 2)
        x, y = lo + rng.random() * (hi - lo), lo + rng.random() * (hi - lo)
        col = ink[i % len(ink)]
        sw = 2.0 * (1 + params["width_var"] * (4 * rng.random() - 1))
        rot = (rng.random() * 2 - 1) * params["rot_max"]
        tr = ' transform="rotate(%s %s %s)"' % (_f(rot), _f(x), _f(y)) if params["rot_max"] > 0 else ""
        curved = rng.random() < params["curve"]
        kind = rng.randrange(2)
        if curved and kind == 0:
            out.append('<circle cx="%s" cy="%s" r="%s" fill="%s" fill-opacity="0.85"/>' % (_f(x), _f(y), _f(s / 2), col))
        elif curved:
            out.append('<path d="M%s %s Q%s %s %s %s" fill="none" stroke="%s" stroke-width="%s"%s/>' % (
                _f(x - s / 2), _f(y), _f(x), _f(y - s), _f(x + s / 2), _f(y), col, _f(sw), tr))
        elif kind == 0:
            w = s if series is None else series[rng.randrange(len(series))] / series[-1] * SIZE * 0.5
            out.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"%s/>' % (_f(x - w / 2), _f(y - s / 2), _f(w), _f(s), col, tr))
        else:
            out.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="%s"%s/>' % (_f(x - s / 2), _f(y), _f(x + s / 2), _f(y), col, _f(sw), tr))
    out.append("</svg>")
    return {"artifact": "\n".join(out) + "\n", "media_type": "image/svg+xml", "notes": "%d marks, %d colours" % (n, len(ink))}


def self_assess(world: dict, artifact) -> dict:
    """The plugin's own check: did it place the number of marks its translation asked for (after constraints)?"""
    p = translate((world.get("rules") or {}).get("axes") or {})
    cons = _constraints(world)
    want = min(p["n"], cons["max_elements"]["value"]) if "max_elements" in cons else p["n"]
    got = len(re.findall(r"<(?:circle|path|rect|line)\b", artifact)) - 1          # minus the background
    return {"score": max(0.0, 1 - abs(got - want) / max(1, want)), "notes": "marks %d / intended %d" % (got, want)}


def ports(world: dict, params: dict) -> dict:
    cons = _constraints(world)
    pal = list(cons["palette"]["colours"]) if "palette" in cons else _palette(params, cons, random.Random(int(params.get("seed", 1)) * 7919))
    return {"palette": pal, "tempo_bpm": round(40 + 140 * params["rot_max"] / 180, 1), "events": []}


PLUGIN = {"name": "image_svg", "version": "1", "medium": "image", "procedural": True, "translate": translate, "generate": generate,
          "self_assess": self_assess, "ports": ports}
