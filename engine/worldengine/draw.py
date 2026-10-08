# -*- coding: utf-8 -*-
"""Drawing robot planner: strokes on a plane -> joint trajectory with pen up/down, verified against V-16.

    plan = draw.plan(chain, strokes, plane)          # strokes: [[[u, v], ...], ...] metres in the drawing plane
    plan["verify"] -> {"stroke_err_max_m", "chord_err_max_m", "unreachable", "limit_violations", "self_collisions", ...}

- IK: damped least squares on position, seeded from the previous pose, so consecutive samples stay on one
  branch (the reference planar IK returns the first feasible branch per point, which can jump between samples).
  The reference FK is the model. Joint limits are enforced by projection.
- Pen lift is a tool action, not a joint: the trajectory carries pen = 0|1 next to q, and the targets stay on
  the plane (a planar arm cannot leave it). An arm that should lift its wrist instead sets opts pen_lift_ik (m).
- opts enforce_limits=False plans without projecting onto the joint limits -- used to prove that the
  verifier catches violations (V-16: "일부러 한계를 넘는 그림을 넣어 검출 확인").
- Time: each step is as slow as the slower of tip speed (draw/travel) and joint speed limit.
- Verification uses the reference FK and the reference limit check (kinematics.check_trajectory); the chord
  check probes the joint-space interpolation between samples, which the IK never sees.

No numpy: CI runs without it.
"""
from __future__ import annotations

import math
import re

from worldengine import robot as RB

DEFAULTS = {"ds": 0.02, "v_draw": 0.25, "v_travel": 0.6, "qd_max": 1.5, "tol": 1e-5, "chord_tol": 0.002,
            "lam": 0.02, "iters": 60, "link_clearance": 0.04,
            "pen_lift_ik": 0.0, "enforce_limits": True, "continuous": False}


# ---------------------------------------------------------------- strokes
def svg_path(d: str) -> "list[list[list[float]]]":
    """Minimal SVG path subset: M/L/H/V/Z (absolute and relative). Curves are not supported -- they raise."""
    toks = re.findall(r"[A-DF-Za-df-z]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", d)   # every command letter, so unsupported ones are seen
    strokes, cur, x, y, cmd, i = [], [], 0.0, 0.0, None, 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t; i += 1
            if cmd in "Zz" and cur:
                first = list(cur[0]); cur.append(first); strokes.append(cur); cur = []
                x, y = first
            continue
        if cmd is None or cmd in "Zz":
            raise ValueError("number without a command in path")
        if cmd in "CcSsQqTtAa":
            raise ValueError("curves are not supported yet: " + cmd)
        if cmd in "Hh":
            x = float(t) + (x if cmd == "h" else 0); i += 1
        elif cmd in "Vv":
            y = float(t) + (y if cmd == "v" else 0); i += 1
        else:
            nx, ny = float(t), float(toks[i + 1]); i += 2
            x, y = (x + nx, y + ny) if cmd.islower() else (nx, ny)
        if cmd in "Mm":
            if len(cur) > 1:
                strokes.append(cur)
            cur = [[x, y]]; cmd = "l" if cmd == "m" else "L"
        else:
            cur.append([x, y])
    if len(cur) > 1:
        strokes.append(cur)
    return strokes


def star(cx, cy, r_out, r_in, n=5, rot=math.pi / 2):
    pts = [[cx + (r_out if k % 2 == 0 else r_in) * math.cos(rot + k * math.pi / n), cy + (r_out if k % 2 == 0 else r_in) * math.sin(rot + k * math.pi / n)] for k in range(2 * n)]
    return pts + [pts[0]]


def circle(cx, cy, r, n=72):
    return [[cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)] for k in range(n + 1)]


def spiral(cx, cy, r0, r1, turns=3, n=240):
    return [[cx + (r0 + (r1 - r0) * k / n) * math.cos(2 * math.pi * turns * k / n), cy + (r0 + (r1 - r0) * k / n) * math.sin(2 * math.pi * turns * k / n)] for k in range(n + 1)]


def resample(poly, ds):
    out = [list(poly[0])]
    for a, b in zip(poly, poly[1:]):
        L = math.dist(a, b); n = max(1, math.ceil(L / ds))
        out += [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n] for k in range(1, n + 1)]
    return out


def home(chain: dict, target, seed, opts=None):
    """A rest pose that puts the tip on target, found from a hand-picked comfortable seed (not the first IK branch)."""
    o = {**DEFAULTS, **(opts or {}), "iters": 400}
    rb, act = RB.to_robot(chain), RB.active(chain)
    q, err = ik(rb, [(j["lower"], j["upper"]) for j in act], target, seed, o, list(seed))
    return q, err


# ---------------------------------------------------------------- plane
def to3(plane, uv, lift=0.0):
    o, u, v, n = plane["origin"], plane["u"], plane["v"], _cross(plane["u"], plane["v"])
    return [o[k] + uv[0] * u[k] + uv[1] * v[k] + lift * n[k] for k in range(3)]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


# ---------------------------------------------------------------- IK (damped least squares, position only)
def _solve3(A, b):
    """3x3 linear solve by Gaussian elimination with partial pivoting."""
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(3):
        p = max(range(c, 3), key=lambda r: abs(M[r][c])); M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-15:
            return [0.0, 0.0, 0.0]
        for r in range(3):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [M[r][k] - f * M[c][k] for k in range(4)]
    return [M[i][3] / M[i][i] for i in range(3)]


def ik(rb, lims, target, q0, o=DEFAULTS, q_rest=None):
    """DLS step dq = J^T (J J^T + lam^2 I)^-1 e, plus a null-space pull toward q_rest (redundant arms):
    dq += (I - J+ J) k (q_rest - q). The pull keeps a 3-joint arm drawing in 2D from drifting into folds."""
    q = list(q0)
    k_rest = o.get("k_rest", 0.1)
    for _ in range(o["iters"]):
        p = RB.K.forward_kinematics(rb, q)
        e = [target[k] - p[k] for k in range(3)]
        if math.sqrt(sum(x * x for x in e)) < o["tol"]:
            break
        h = 1e-6
        J = []                                            # columns d p / d q_j (finite differences on the reference FK)
        for j in range(len(q)):
            qq = list(q); qq[j] += h; pj = RB.K.forward_kinematics(rb, qq)
            J.append([(pj[k] - p[k]) / h for k in range(3)])
        n = len(q)
        A = [[sum(J[j][r] * J[j][c] for j in range(n)) + (o["lam"] ** 2 if r == c else 0.0) for c in range(3)] for r in range(3)]
        y = _solve3(A, e)
        dq = [sum(J[j][k] * y[k] for k in range(3)) for j in range(n)]
        if q_rest is not None and math.sqrt(sum(x * x for x in e)) > 1e-3:   # near the target: pure DLS, so it converges
            z = [k_rest * (q_rest[j] - q[j]) for j in range(n)]
            Jz = [sum(J[j][r] * z[j] for j in range(n)) for r in range(3)]             # J z
            w = _solve3(A, Jz)                                                          # (J J^T + lam^2)^-1 J z
            dq = [dq[j] + z[j] - sum(J[j][k] * w[k] for k in range(3)) for j in range(n)]
        q = [q[j] + dq[j] for j in range(n)]
        if o["enforce_limits"]:
            q = [min(lims[j][1], max(lims[j][0], q[j])) for j in range(len(q))]
    p = RB.K.forward_kinematics(rb, q)
    return q, math.dist(p, target)


def home(chain: dict, target, seed, opts=None):
    """A rest pose that puts the tip on target, found from a hand-picked comfortable seed (not the first IK branch)."""
    o = {**DEFAULTS, **(opts or {}), "iters": 400}
    rb, act = RB.to_robot(chain), RB.active(chain)
    q, err = ik(rb, [(j["lower"], j["upper"]) for j in act], target, seed, o, list(seed))
    return q, err


# ---------------------------------------------------------------- plan
def plan(chain: dict, strokes, plane: dict, q_home=None, opts=None) -> dict:
    o = {**DEFAULTS, **(opts or {})}
    rb, act = RB.to_robot(chain), RB.active(chain)
    lims = [(j["lower"], j["upper"]) for j in act]
    q = list(q_home) if q_home is not None else [0.0] * len(act)
    q_rest = list(o.get("q_rest") or q)
    lift = o["pen_lift_ik"]
    T, Q, PEN, TARGET, STROKE = [0.0], [list(q)], [0], [RB.K.forward_kinematics(rb, q)], [-1]
    worst = 0.0
    unreachable = []

    def go(p3, pen, sid, v):
        nonlocal q, worst
        qn, err = ik(rb, lims, p3, q, o, q_rest)
        if err > 1e3 * o["tol"]:
            unreachable.append({"stroke": sid, "target": p3, "residual_m": err})
        dist = math.dist(RB.K.forward_kinematics(rb, q), RB.K.forward_kinematics(rb, qn))
        dq = max(abs(a - b) for a, b in zip(qn, q)) if qn else 0.0
        dt = max(dist / v, dq / o["qd_max"], 1e-3)
        T.append(T[-1] + dt); Q.append(qn); PEN.append(pen); TARGET.append(p3); STROKE.append(sid)
        q = qn

    cont = o["continuous"]                                   # one unbroken line: travel between strokes is drawn too
    for sid, poly in enumerate(strokes):
        pts = resample(poly, o["ds"])
        first, last = sid == 0, sid == len(strokes) - 1
        drawn_travel = cont and not first
        start = to3(plane, pts[0], 0.0 if drawn_travel else lift)
        prev = TARGET[-1]
        n_tr = max(2, math.ceil(math.dist(prev, start) / ((1 if drawn_travel else 4) * o["ds"])))
        for k in range(1, n_tr + 1):                          # travel: pen up, or pen down when continuous
            a = k / n_tr
            go([prev[i] + (start[i] - prev[i]) * a for i in range(3)], 1 if drawn_travel else 0, sid, o["v_draw"] if drawn_travel else o["v_travel"])
        if not drawn_travel:
            go(to3(plane, pts[0]), 1, sid, o["v_draw"] / 4)                                         # pen down
        for uv in pts[1:]:
            go(to3(plane, uv), 1, sid, o["v_draw"])
        if not cont or last:
            go(to3(plane, pts[-1], lift), 0, sid, o["v_draw"] / 4)                                  # pen up
    traj = {"t": T, "q": Q, "pen": PEN, "target": TARGET, "stroke": STROKE}
    return {"chain": chain, "plane": plane, "strokes": strokes, "opts": o, "trajectory": traj,
            "verify": verify(chain, traj, o, unreachable)}


# ---------------------------------------------------------------- verification (V-16)
def _seg_dist(p, q, r, s):
    """Minimum distance between 3D segments pq and rs (clamped closest points)."""
    d1, d2, w = [q[i] - p[i] for i in range(3)], [s[i] - r[i] for i in range(3)], [p[i] - r[i] for i in range(3)]
    a, e, f = sum(x * x for x in d1), sum(x * x for x in d2), sum(d2[i] * w[i] for i in range(3))
    if a < 1e-15 and e < 1e-15:
        return math.dist(p, r)
    if a < 1e-15:
        sc, tc = 0.0, min(1, max(0, f / e))
    else:
        c = sum(d1[i] * w[i] for i in range(3))
        if e < 1e-15:
            sc, tc = min(1, max(0, -c / a)), 0.0
        else:
            b = sum(d1[i] * d2[i] for i in range(3)); den = a * e - b * b
            sc = min(1, max(0, (b * f - c * e) / den)) if den > 1e-15 else 0.0
            tc = (b * sc + f) / e
            if tc < 0:
                tc, sc = 0.0, min(1, max(0, -c / a))
            elif tc > 1:
                tc, sc = 1.0, min(1, max(0, (b - c) / a))
    return math.dist([p[i] + d1[i] * sc for i in range(3)], [r[i] + d2[i] * tc for i in range(3)])


def _links(chain, q):
    pts = RB.frames(chain, q)
    segs = []
    for a, b in zip(pts, pts[1:]):
        if math.dist(a, b) > 1e-9:
            segs.append((a, b))
    return segs


def verify(chain: dict, traj: dict, o=DEFAULTS, unreachable=None) -> dict:
    rb = RB.to_robot(chain)
    Q, PEN, TGT = traj["q"], traj["pen"], traj["target"]
    stroke_err = max((math.dist(RB.K.forward_kinematics(rb, q), t) for q, p, t in zip(Q, PEN, TGT) if p), default=0.0)
    chord = 0.0
    for i in range(1, len(Q)):
        if PEN[i] and PEN[i - 1]:
            qm = [(a + b) / 2 for a, b in zip(Q[i - 1], Q[i])]
            mid = [(a + b) / 2 for a, b in zip(TGT[i - 1], TGT[i])]
            chord = max(chord, math.dist(RB.K.forward_kinematics(rb, qm), mid))
    viol = RB.K.check_trajectory(rb, Q)
    v_pen = max((math.dist(RB.K.forward_kinematics(rb, Q[i]), RB.K.forward_kinematics(rb, Q[i - 1])) / (traj["t"][i] - traj["t"][i - 1])
                 for i in range(1, len(Q)) if PEN[i] and PEN[i - 1]), default=0.0)
    qd = max((max(abs(a - b) for a, b in zip(Q[i], Q[i - 1])) / (traj["t"][i] - traj["t"][i - 1]) for i in range(1, len(Q))), default=0.0)
    coll, min_gap = [], float("inf")
    for i, q in enumerate(Q):                                          # every sample; links that are not neighbours
        segs = _links(chain, q)
        for a in range(len(segs)):
            for b in range(a + 2, len(segs)):
                d = _seg_dist(*segs[a], *segs[b]); min_gap = min(min_gap, d)
                if d < o["link_clearance"]:
                    coll.append({"step": i, "links": [a, b], "gap_m": d})
    return {
        "samples": len(Q), "pen_down_samples": sum(PEN), "duration_s": traj["t"][-1],
        "pen_lifts": sum(1 for i in range(1, len(PEN)) if PEN[i - 1] and not PEN[i] and any(PEN[i:])),   # interruptions only
        "stroke_err_max_m": stroke_err, "chord_err_max_m": chord, "chord_tol_m": o["chord_tol"],
        "unreachable": len(unreachable or []), "unreachable_first": (unreachable or [None])[0],
        "limit_violations": len(viol), "limit_violation_first": list(viol[0]) if viol else None,
        "qd_max_measured": qd, "qd_max_allowed": o["qd_max"], "pen_speed_max_mps": v_pen,
        "self_collisions": len(coll), "min_link_gap_m": None if min_gap == float("inf") else min_gap,
        "pass": stroke_err <= 1e-3 and chord <= o["chord_tol"] and not unreachable and not viol and not coll and qd <= o["qd_max"] * (1 + 1e-9),
    }


# ---------------------------------------------------------------- world + report
def _r(v, nd=7):
    return [_r(x, nd) for x in v] if isinstance(v, list) else round(v, nd)


def world(p: dict, name: str = "그림 그리는 로봇 (데모)", at=(6.0, 6.0), table_h: float = 0.4, concepts=None, effects=None) -> dict:
    """A gallery world with the arm on a low platform over a sheet of paper. The plan's verification travels with it."""
    tr = p["trajectory"]
    xs = [t[0] for t in tr["target"]] + [0.0]
    ys = [t[1] for t in tr["target"]] + [0.0]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    R = RB.reach(p["chain"])
    px0, px1, py0, py1 = -0.6, max(x1, R * 0.95) + 0.3, min(y0, -R * 0.5) - 0.3, max(y1, R * 0.5) + 0.3
    ax, ay = at
    sx0, sx1, sy0, sy1 = min(t[0] for t in tr["target"] if t), max(t[0] for t in tr["target"]), min(t[1] for t in tr["target"]), max(t[1] for t in tr["target"])
    pad = 0.15
    return {
        "format": "world/1", "name": name,
        "about": "Planned in Python (worldengine.draw, reference FK from kinematics/), played and inked by the runtime's own FK.",
        "bounds": [ax + px1 + 4, ay + py1 + 4, 5],
        "environment": {"background": "#eceae6", "exposure": 0.95, "ambient": 0.8},
        "materials": {"floor": {"color": "#ffffff", "roughness": 0.6, "texture": {"kind": "speckle", "colors": ["#cfcbc4", "#bdb8af", "#e0dcd5"], "size_m": 3}},
                      "plinth": {"color": "#f4f2ee", "roughness": 0.7}, "paper": {"color": "#fffdf7", "roughness": 0.95}},
        "entities": [
            {"id": "floor", "type": "plane", "pos": [(ax + px1 + 4) / 2, (ay + py1 + 4) / 2, 0], "size": [ax + px1 + 4, ay + py1 + 4], "material": "floor"},
            {"id": "platform", "type": "box", "pos": [ax + (px0 + px1) / 2, ay + (py0 + py1) / 2, 0], "size": [px1 - px0, py1 - py0, table_h], "material": "plinth", "solid": True},
            {"id": "paper", "type": "plane", "pos": [ax + (sx0 + sx1) / 2, ay + (sy0 + sy1) / 2, table_h + 0.001], "size": [sx1 - sx0 + 2 * pad, sy1 - sy0 + 2 * pad], "material": "paper"},
            {"id": "arm", "type": "robot.arm", "pos": [ax, ay, table_h], "chain": p["chain"], "speed": 1, "loop": True,
             "trajectory": {"t": _r(tr["t"], 4), "q": _r(tr["q"]), "pen": tr["pen"], "target": _r(tr["target"])}},
            {"id": "lamp", "type": "light", "pos": [ax + 1.9, ay, 3.2], "kind": "spot", "target": [ax + 1.9, ay, table_h], "intensity": 40, "angle_deg": 35},
        ],
        "views": {
            "aerial": {"pos": [ax - 2.5, ay - 4.5, 4.5], "target": [ax + 1.6, ay, table_h], "fov": 45},
            "top": {"pos": [ax + (sx0 + sx1) / 2, ay + (sy0 + sy1) / 2 - 0.01, table_h + 3.2], "target": [ax + (sx0 + sx1) / 2, ay + (sy0 + sy1) / 2, table_h], "fov": 40},
            "eye": {"pos": [ax + 1.9, ay - 3.2, 1.7], "target": [ax + 1.9, ay, table_h + 0.2], "fov": 55},
        },
        "player": {"spawn": [ax + 1.9, ay - 3.5], "yaw_deg": 90, "eye": "adult"},
        "controls": {"default": "orbit"},
        "concepts": concepts or [],
        "verify": {"V-16": p["verify"], "planner": {k: v for k, v in p["opts"].items() if k != "q_rest"},
                   "concept_effects": effects or []},
    }


def report_md(p: dict, title: str, effects=None) -> str:
    v = p["verify"]
    rows = [("의도한 획 ↔ 시뮬레이션 손끝 최대 오차 (표본점)", "%.4f mm" % (v["stroke_err_max_m"] * 1e3), "≤ 1 mm"),
            ("표본 사이 관절 보간 중점 오차 (chord)", "%.4f mm" % (v["chord_err_max_m"] * 1e3), "≤ %.1f mm" % (v["chord_tol_m"] * 1e3)),
            ("도달 못 한 점", str(v["unreachable"]), "0"),
            ("관절 한계 위반 (reference check_trajectory)", str(v["limit_violations"]), "0"),
            ("자기 충돌 (이웃 아닌 링크 간격 < %.0f mm)" % (p["opts"]["link_clearance"] * 1e3), str(v["self_collisions"]), "0"),
            ("최대 관절 속도", "%.3f rad/s" % v["qd_max_measured"], "≤ %.1f rad/s" % v["qd_max_allowed"]),
            ("그리는 도중 펜 떼기", str(v["pen_lifts"]), "(개념이 정하면 그 값)")]
    L = ["# V-16 " + title, "", "- 로봇: `%s` (%s), 관절 %d개 · 표본 %d · 펜 내림 %d · 재생 %.1f s" % (
        p["chain"]["name"], p["chain"].get("source", ""), len(RB.active(p["chain"])), v["samples"], v["pen_down_samples"], v["duration_s"]),
         "- 판정: **%s**" % ("PASS" if v["pass"] else "FAIL"), "", "| 항목 | 측정 | 기준 |", "|---|---|---|"]
    L += ["| %s | %s | %s |" % r for r in rows]
    if v["unreachable_first"]:
        L.append("\n첫 도달 실패: %s" % v["unreachable_first"])
    if v["limit_violation_first"]:
        L.append("\n첫 한계 위반: %s" % v["limit_violation_first"])
    if effects:
        L += ["", "## 개념 규칙: 적용과 측정", "", "| 개념 | 규칙 | 값 | 적용 | 측정 | 지킴 | 설명 |", "|---|---|---|---|---|---|---|"]
        fmt = lambda m: "—" if m is None else ("%.4g" % m if isinstance(m, float) else str(m))
        L += ["| %s | `%s` | %s | %s | %s | %s | %s |" % (e["concept"], e["param"], e["value"], "예" if e["applied"] else "**아니오**", fmt(e.get("measured")),
              {True: "예", False: "**아니오**", None: "—"}[e.get("met")], e["note"]) for e in effects]
    L += ["", "측정 모델 = kinematics/ 의 reference FK. 브라우저 쪽 FK(robot/kinematics.js)는 같은 test_vectors 600개에서 1e-9 m 이내로 일치하는지 따로 검사한다.",
          "펜 들기는 관절이 아니라 도구 동작이다 (평면 팔은 평면을 벗어날 수 없다)."]
    return "\n".join(L) + "\n"


def demo_strokes(center=(1.9, 0.0)):
    c = center
    return [star(*c, 0.6, 0.25), circle(*c, 0.75), spiral(*c, 0.05, 0.35, turns=3)]
