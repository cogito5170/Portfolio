# -*- coding: utf-8 -*-
"""Independent style measurer for V-04 (SPEC 5절). Reads an SVG artifact and estimates the style axes from what is
drawn -- it never imports or calls the plugin that made it, and plugins never call it.

Method (fixed before any V-04 numbers were looked at; constants are part of the method):
  marks    = shapes (circle/ellipse/rect/line/path/polygon) + polyline ink length / (W/10)   (background rect excluded:
             a rect covering the whole viewBox)
  density  = log(1 + marks) / log(1 + 400)                                          clipped to [0,1]
  colour   = 0.5 * min(1, (distinct ink colours - 1) / 7) + 0.5 * mean HSL saturation of ink colours
  form     = curved marks / all marks; circle, ellipse, path with Q/C/S/T/A are curved; rect, line, polygon are
             straight; for polylines each vertex counts, curved if its turning angle is 1..30 deg
  texture  = coefficient of variation of stroke widths (0 if fewer than 2 stroked marks), clipped to [0,1]
  motion   = population std of rotate() angles / 90 deg, clipped to [0,1]
Axes the measurer cannot see (sound, narrative) are not reported.
"""
from __future__ import annotations

import colorsys
import math
import re
import xml.etree.ElementTree as ET

MEASURED = ("density", "colour", "form", "texture", "motion")
_SHAPES = {"circle", "ellipse", "rect", "line", "path", "polygon", "polyline"}


def _hex(c):
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", (c or "").strip())
    return m and "#" + m.group(1).lower()


def axes(svg: str) -> dict:
    root = ET.fromstring(svg)
    vb = [float(x) for x in (root.get("viewBox") or "0 0 100 100").split()]
    W, H = vb[2], vb[3]
    marks, curved, colours, widths, rots, ink_len = 0.0, 0.0, set(), [], [], 0.0
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in _SHAPES:
            continue
        if tag == "rect" and float(el.get("width", 0)) >= W and float(el.get("height", 0)) >= H:
            continue                                                     # background
        for k in ("fill", "stroke"):
            h = _hex(el.get(k))
            if h:
                colours.add(h)
        if el.get("stroke-width"):
            widths.append(float(el.get("stroke-width")))
        m = re.search(r"rotate\(\s*(-?[\d.]+)", el.get("transform", ""))
        if m:
            rots.append(float(m.group(1)))
        if tag == "polyline":
            pts = [tuple(map(float, p.split(","))) for p in el.get("points", "").split()]
            ink_len += sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
            for a, b, c in zip(pts, pts[1:], pts[2:]):
                v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
                n1, n2 = math.hypot(*v1), math.hypot(*v2)
                if n1 > 0 and n2 > 0:
                    ang = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))
                    curved += (1 <= ang <= 30) / max(1, len(pts) - 2)
            marks += 0                                                   # counted through ink length below
            continue
        marks += 1
        if tag in ("circle", "ellipse") or (tag == "path" and re.search(r"[QCSTAqcsta]", el.get("d", ""))):
            curved += 1
    n_poly = sum(1 for el in root.iter() if el.tag.split("}")[-1] == "polyline")
    total = marks + n_poly
    marks += ink_len / (W / 10)
    sats = [colorsys.rgb_to_hls(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)))[2] for c in colours]
    mean_w = sum(widths) / len(widths) if widths else 0
    cv = (math.sqrt(sum((x - mean_w) ** 2 for x in widths) / len(widths)) / mean_w) if len(widths) > 1 and mean_w > 0 else 0.0
    mr = sum(rots) / len(rots) if rots else 0.0
    sd = math.sqrt(sum((x - mr) ** 2 for x in rots) / len(rots)) if rots else 0.0
    cl = lambda x: max(0.0, min(1.0, x))
    return {"density": cl(math.log1p(marks) / math.log1p(400)),
            "colour": cl(0.5 * min(1, (len(colours) - 1) / 7) + 0.5 * (sum(sats) / len(sats) if sats else 0)),
            "form": cl(curved / total) if total else 0.0,
            "texture": cl(cv), "motion": cl(sd / 90)}


def distance(measured: dict, world_axes: dict) -> "float | None":
    keys = [k for k in MEASURED if k in measured and k in world_axes]
    if not keys:
        return None
    return math.sqrt(sum((measured[k] - world_axes[k]) ** 2 for k in keys) / len(keys))


def distinctness(results: "list[dict]", worlds: "dict[str, dict]") -> "list[dict]":
    """results: [{"plugin", "world", "svg"}]. For each: measured axes, distance to every world's axes, own rank."""
    rows = []
    for r in results:
        m = axes(r["svg"])
        d = {name: distance(m, (w.get("rules") or {}).get("axes") or {}) for name, w in worlds.items()}
        ranked = sorted(d, key=lambda k: d[k])
        rows.append({"plugin": r["plugin"], "world": r["world"], "measured": m, "distance": d,
                     "nearest": ranked[0], "own_rank": ranked.index(r["world"]) + 1})
    return rows
