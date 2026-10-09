# -*- coding: utf-8 -*-
"""Physical-limit guard (V-14, RB-04): checks a joint trajectory before it may drive anything (simulation playback
of agent-written code, or a device after A-06 approval). Independent of whoever produced the trajectory.

    check(chain, traj, qd_max=1.5) -> {"ok", "violations": [...]}   traj = {"t": [...], "q": [[...]]}
Blocks: joint-limit violations (reference check_trajectory), joint speed above qd_max, non-increasing time,
non-finite numbers, wrong number of joints.
"""
from __future__ import annotations

import math

from worldengine import robot as RB


def check(chain: dict, traj: dict, qd_max: float = 1.5) -> dict:
    v = []
    n = len(RB.active(chain))
    T, Q = traj.get("t") or [], traj.get("q") or []
    if len(T) != len(Q) or not Q:
        return {"ok": False, "violations": [{"kind": "shape", "detail": "t and q must be non-empty and the same length"}]}
    for i, q in enumerate(Q):
        if len(q) != n:
            v.append({"kind": "joints", "step": i, "detail": "%d angles for %d joints" % (len(q), n)})
        elif not all(isinstance(x, (int, float)) and math.isfinite(x) for x in q):
            v.append({"kind": "nan", "step": i})
    if v:
        return {"ok": False, "violations": v[:20]}
    for i in range(1, len(T)):
        dt = T[i] - T[i - 1]
        if not dt > 0:
            v.append({"kind": "time", "step": i, "detail": "time does not increase"}); continue
        sp = max(abs(a - b) for a, b in zip(Q[i], Q[i - 1])) / dt
        if sp > qd_max * (1 + 1e-9):
            v.append({"kind": "speed", "step": i, "rad_s": sp, "limit": qd_max})
    for s, name, ang, lo, hi in RB.K.check_trajectory(RB.to_robot(chain), Q):
        v.append({"kind": "limit", "step": s, "joint": name, "angle": ang, "range": [lo, hi]})
    return {"ok": not v, "violations": v[:50], "count": len(v)}
