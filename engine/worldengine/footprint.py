# -*- coding: utf-8 -*-
"""Floor plan and area table from a world's bodies (SPEC D-02, D-04): what each body covers seen from above.

    fp = footprints(world)       [{"id", "type", "shape": "rect"|"circle", "cx", "cy", "w", "d", "r", "rot", "area", "material"}]
    t  = area_table(world)       {"by_type": {type: {"count", "area_m2"}}, "sum_m2", "covered_m2", "site_m2", "coverage", "floors_m2"}
    svg = plan_svg(world)        top-down plan, north up, scale bar

Footprints come from each body's own size fields (box/plane size, radius for round bodies, arch width/depth/thickness,
text size, model fit_m, person 0.5 m). Sounds, lights, ground and terrain have none. Children follow their parent's
position, turn (about z) and scale. Planes are floors: listed as floors_m2, not as bodies standing on the site.
"sum" counts overlaps twice; "covered" is the union: a body that touches no other counts exactly; bodies whose
bounding squares overlap are counted together on a grid whose cell is the smaller of 1/200 of their extent and 1/8
of the narrowest one's width, but no finer than ~200k cells per cluster (cell_m reports the coarsest used).
"""
from __future__ import annotations

import html
import math

ROUND = {"cylinder": lambda e: e.get("radius", 0.5), "cone": lambda e: e.get("radius", 0.5), "sphere": lambda e: e.get("radius", 0.5),
         "capsule": lambda e: e.get("radius", 0.3), "torus": lambda e: e.get("radius", 0.5) + e.get("tube", 0.1),
         "person": lambda e: 0.25 * e.get("height", 1.68) / 1.68}
NONE = {"sound", "light", "ground", "terrain", "group", "path", "robot.arm", "retail.store", "character"}


def _rect_of(e):
    t = e.get("type")
    if t in ("box", "plane"):
        s = e.get("size", [1, 1, 1] if t == "box" else [10, 10])
        s = [s, s] if isinstance(s, (int, float)) else s
        return s[0], s[1]
    if t == "arch":
        return e.get("width", 2) + 2 * e.get("thickness", 0.5), e.get("depth", 0.6)
    if t == "text":
        s = e.get("size", [2, 0.5])
        return s[0], 0.05
    if t == "model":
        f = e.get("fit_m", 1)
        return f, f
    return None


def footprints(world: dict) -> "list[dict]":
    out = []

    def walk(es, ox, oy, orot, osc):
        for e in es or []:
            if not isinstance(e, dict):
                continue
            p = e.get("pos") or [0, 0, 0]
            c, s = math.cos(math.radians(orot)), math.sin(math.radians(orot))
            x, y = ox + osc * (p[0] * c - p[1] * s), oy + osc * (p[0] * s + p[1] * c)
            rot = orot + ((e.get("rot") or [0, 0, 0])[2])
            sc = e.get("scale", 1)
            k = osc * (sc if isinstance(sc, (int, float)) else max(sc[0], sc[1]))
            t = e.get("type")
            mat = e.get("material") if isinstance(e.get("material"), str) else None
            if t in ROUND:
                r = ROUND[t](e) * k
                out.append({"id": e.get("id"), "type": t, "shape": "circle", "cx": x, "cy": y, "r": r, "w": 2 * r, "d": 2 * r, "rot": 0.0, "area": math.pi * r * r, "material": mat})
            elif t not in NONE and _rect_of(e):
                w, d = _rect_of(e)
                out.append({"id": e.get("id"), "type": t, "shape": "rect", "cx": x, "cy": y, "w": w * k, "d": d * k, "r": None, "rot": rot % 360, "area": w * d * k * k, "material": mat})
            walk(e.get("children"), x, y, rot, k)
    walk(world.get("entities"), 0.0, 0.0, 0.0, 1.0)
    return out


def _site(world, fps):
    if world.get("bounds"):
        return 0.0, 0.0, float(world["bounds"][0]), float(world["bounds"][1])
    if not fps:
        return 0.0, 0.0, 10.0, 10.0
    xs = [f["cx"] - max(f["w"], f["d"]) for f in fps] + [f["cx"] + max(f["w"], f["d"]) for f in fps]
    ys = [f["cy"] - max(f["w"], f["d"]) for f in fps] + [f["cy"] + max(f["w"], f["d"]) for f in fps]
    return min(xs), min(ys), max(xs), max(ys)


def _inside(f, x, y):
    if f["shape"] == "circle":
        return (x - f["cx"]) ** 2 + (y - f["cy"]) ** 2 <= f["r"] ** 2
    c, s = math.cos(math.radians(-f["rot"])), math.sin(math.radians(-f["rot"]))
    dx, dy = x - f["cx"], y - f["cy"]
    return abs(dx * c - dy * s) <= f["w"] / 2 and abs(dx * s + dy * c) <= f["d"] / 2


def area_table(world: dict) -> dict:
    allf = footprints(world)
    x0, y0, x1, y1 = _site(world, allf)
    fps = [f for f in allf if f["type"] != "plane"]
    by = {}
    for f in fps:
        b = by.setdefault(f["type"], {"count": 0, "area_m2": 0.0})
        b["count"] += 1; b["area_m2"] += f["area"]
    box = lambda f: (f["cx"] - max(f["w"], f["d"]) * 0.7072, f["cy"] - max(f["w"], f["d"]) * 0.7072,  # noqa: E731
                     f["cx"] + max(f["w"], f["d"]) * 0.7072, f["cy"] + max(f["w"], f["d"]) * 0.7072)
    B = [box(f) for f in fps]
    parent = list(range(len(fps)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            if B[i][0] < B[j][2] and B[j][0] < B[i][2] and B[i][1] < B[j][3] and B[j][1] < B[i][3]:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(fps)):
        groups.setdefault(find(i), []).append(i)
    covered, cells = 0.0, []
    for g in groups.values():
        if len(g) == 1:
            covered += fps[g[0]]["area"]; continue
        gx0, gy0 = min(B[i][0] for i in g), min(B[i][1] for i in g)
        gx1, gy1 = max(B[i][2] for i in g), max(B[i][3] for i in g)
        cell = max(min(max(gx1 - gx0, gy1 - gy0) / 200, min(min(fps[i]["w"], fps[i]["d"]) for i in g) / 8),
                   math.sqrt((gx1 - gx0) * (gy1 - gy0) / 2e5), 2e-3)                 # at most ~200k cells per cluster
        cells.append(cell)
        hit = set()
        for i in g:
            f, b = fps[i], B[i]
            for a in range(int((b[0] - gx0) / cell), int((b[2] - gx0) / cell) + 1):
                for c in range(int((b[1] - gy0) / cell), int((b[3] - gy0) / cell) + 1):
                    if (a, c) not in hit and _inside(f, gx0 + (a + 0.5) * cell, gy0 + (c + 0.5) * cell):
                        hit.add((a, c))
        covered += len(hit) * cell * cell
    site = (x1 - x0) * (y1 - y0)
    return {"by_type": {k: {"count": v["count"], "area_m2": round(v["area_m2"], 3)} for k, v in sorted(by.items())},
            "sum_m2": round(sum(f["area"] for f in fps), 3), "covered_m2": round(covered, 3), "site_m2": round(site, 3),
            "coverage": round(covered / site, 4) if site else None, "cell_m": round(max(cells), 4) if cells else None,
            "floors_m2": round(sum(f["area"] for f in allf if f["type"] == "plane"), 3)}


def plan_svg(world: dict, px: int = 480) -> str:
    fps = footprints(world)
    x0, y0, x1, y1 = _site(world, fps)
    W, D = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    k = (px - 40) / max(W, D)
    X = lambda x: 20 + (x - x0) * k            # noqa: E731
    Y = lambda y: 20 + (y1 - y) * k            # noqa: E731  north up
    mats = world.get("materials") or {}
    col = lambda f: (mats.get(f["material"]) or {}).get("color") if isinstance((mats.get(f["material"]) or {}).get("color"), str) else "#cfcac2"  # noqa: E731
    h = int(40 + D * k)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" font-family="sans-serif" font-size="11">' % (px, h, px, h),
           '<rect x="20" y="20" width="%.1f" height="%.1f" fill="#fbfaf7" stroke="#999" stroke-dasharray="4 3"/>' % (W * k, D * k)]
    for f in fps:
        if f["shape"] == "circle":
            out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity="0.8" stroke="#333" stroke-width="0.8"/>' % (X(f["cx"]), Y(f["cy"]), f["r"] * k, col(f)))
        else:
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" fill-opacity="0.8" stroke="#333" stroke-width="0.8" transform="rotate(%.1f %.1f %.1f)"/>' % (
                X(f["cx"]) - f["w"] * k / 2, Y(f["cy"]) - f["d"] * k / 2, f["w"] * k, f["d"] * k, col(f), -f["rot"], X(f["cx"]), Y(f["cy"])))
    for f in fps:
        if f["id"] and len(fps) <= 40:
            out.append('<text x="%.1f" y="%.1f" text-anchor="middle" fill="#111">%s</text>' % (X(f["cx"]), Y(f["cy"]) + 4, html.escape(str(f["id"]))))
    bar = 10 ** math.floor(math.log10(max(W, D) / 3))
    out.append('<line x1="20" y1="%d" x2="%.1f" y2="%d" stroke="#111" stroke-width="2"/><text x="20" y="%d">%g m</text>' % (h - 8, 20 + bar * k, h - 8, h - 12, bar))
    out.append('<text x="%d" y="16" text-anchor="end">N ↑</text></svg>' % (px - 4))
    return "\n".join(out)
