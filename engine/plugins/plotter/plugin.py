# -*- coding: utf-8 -*-
"""plotter -- the drawing robot as a generator (the 'Behavior -> Expression' path of SPEC 1-A, row 3).

The artifact is the finished drawing as SVG, inked where the reference FK puts the pen tip at each planned joint
pose (not where the strokes were asked to go), plus the V-16 verdict in notes.

Axis -> parameter translation (G-02, editable):
  density -> n_strokes, rings      form   -> sides (0 = triangles ... 1 = circles)
  motion  -> v_draw (pen m/s)      texture -> wobble (radius noise)     colour -> ink (from palette or grey level)
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from worldengine import draw as D, robot as RB

URDF = Path(__file__).resolve().parents[3] / "kinematics" / "planar_3_dof.urdf"
C, R_MAX, PX = (1.9, 0.0), 0.7, 400            # drawing centre / radius (m, arm frame), SVG pixels per metre
_CHAIN = None


def _chain():
    global _CHAIN
    if _CHAIN is None:
        _CHAIN = RB.load_chain(URDF)
    return _CHAIN


def translate(axes: dict) -> dict:
    a = lambda k, d=0.5: float(axes.get(k, d))
    return {"n_strokes": 1 + int(round(9 * a("density"))), "rings": 1 + int(round(3 * a("density"))),
            "sides": 3 + int(round(37 * a("form"))), "wobble": round(0.15 * a("texture"), 4),
            "v_draw": round(0.05 + 0.45 * a("motion"), 4), "seed": 1}


def _palette(world):
    for c in (world.get("rules") or {}).get("constraints") or []:
        if c["kind"] == "palette" and c.get("enabled", True) is not False:
            return list(c["colours"])
    return None


def _ink(world):
    pal = _palette(world)
    return pal[-1] if pal else "#222222"


def _paper(world):
    """The sheet: the lightest palette colour other than the ink (a world with a palette gets no off-palette paper);
    no palette -> warm white; a one-colour palette -> no sheet drawn."""
    pal = _palette(world)
    if pal is None:
        return "#fffdf7"
    rest = [c for c in pal[:-1] if c.lower() != pal[-1].lower()]
    lum = lambda c: 0.2126 * int(c[1:3], 16) + 0.7152 * int(c[3:5], 16) + 0.0722 * int(c[5:7], 16)
    return max(rest, key=lum) if rest else None


def strokes(params, intent):
    rng = random.Random(int(params["seed"]) * 104729 + int(intent.get("seed", 0)))
    out = []
    for s in range(int(params["n_strokes"])):
        cx, cy = C[0] + (rng.random() - 0.5) * 0.5, C[1] + (rng.random() - 0.5) * 0.5
        r = R_MAX * (0.15 + 0.6 * rng.random()) / max(1, int(params["rings"])) * (1 + s % int(params["rings"]))
        r = min(r, R_MAX * 0.75)
        n, ph = int(params["sides"]), rng.random() * 6.283
        pts = [[cx + r * (1 + params["wobble"] * (rng.random() - 0.5)) * math.cos(ph + 6.283185307 * k / n),
                cy + r * (1 + params["wobble"] * (rng.random() - 0.5)) * math.sin(ph + 6.283185307 * k / n)] for k in range(n)]
        out.append(pts + [pts[0]])
    return out


def generate(world: dict, intent: dict, params: dict) -> dict:
    ch = _chain()
    q0, _ = D.home(ch, [C[0], C[1], 0.0], [-0.6, 0.7, 0.6])
    p = D.plan(ch, strokes(params, intent), {"origin": [0, 0, 0], "u": [1, 0, 0], "v": [0, 1, 0]}, q_home=q0,
               opts={"v_draw": float(params["v_draw"]), "ds": 0.03})
    tr, v = p["trajectory"], p["verify"]
    tips = [RB.tip(ch, q) for q in tr["q"]]
    x0, y0 = C[0] - R_MAX - 0.1, C[1] - R_MAX - 0.1
    W = int(2 * (R_MAX + 0.1) * PX)
    paper = _paper(world)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (W, W, W, W)]
    if paper:
        svg.append('<rect x="0" y="0" width="%d" height="%d" fill="%s"/>' % (W, W, paper))
    run = []
    for i, (t, pen) in enumerate(zip(tips, tr["pen"])):
        if pen:
            run.append("%.1f,%.1f" % ((t[0] - x0) * PX, W - (t[1] - y0) * PX))
        if (not pen or i == len(tips) - 1) and len(run) > 1:
            svg.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2"/>' % (" ".join(run), _ink(world)))
        if not pen:
            run = []
    svg.append("</svg>")
    return {"artifact": "\n".join(svg) + "\n", "media_type": "image/svg+xml",
            "notes": "V-16 %s · stroke err %.4f mm · %d samples · %.1f s" % ("PASS" if v["pass"] else "FAIL", v["stroke_err_max_m"] * 1e3, v["samples"], v["duration_s"]),
            "verify": v}


def self_assess(world: dict, artifact) -> dict:
    p = translate((world.get("rules") or {}).get("axes") or {})
    got = artifact.count("<polyline")
    return {"score": max(0.0, 1 - abs(got - p["n_strokes"]) / p["n_strokes"]), "notes": "inked strokes %d / intended %d" % (got, p["n_strokes"])}


def ports(world: dict, params: dict) -> dict:
    return {"palette": [_ink(world)], "tempo_bpm": round(60 * params["v_draw"] / 0.25, 1), "events": ["pen_down", "pen_up"]}


PLUGIN = {"name": "plotter", "version": "1", "medium": "drawing", "translate": translate, "generate": generate,
          "self_assess": self_assess, "ports": ports}
