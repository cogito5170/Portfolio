# -*- coding: utf-8 -*-
"""Device bridge (SPEC RB-06), with a SIMULATED device. No real hardware is driven from this repository.

Two independent guards, by design:
  host side   -- only trajectories that passed the simulation checks (guard.check, V-16) are sent, and only by the
                 approval executor (A-06 drive_device). Each packet carries the hash of the approved trajectory.
  device side -- SimFirmware runs in its own process (a stand-in for the microcontroller) and enforces ITS OWN
                 limits from its own config, whatever the host says: joint range, joint speed, acceleration (a
                 force proxy), approved-trajectory hash, packet order, a watchdog (stream gap -> stop), and an
                 emergency stop that latches until an explicit reset. Agent-written code has no path to it: the
                 sandbox has no network, and the bridge is reachable only through the approval executor.

Protocol: JSON lines over the child's stdin/stdout.
  host -> {"op": "arm", "traj_sha": hex, "n": count}  {"op": "point", "i": k, "t": s, "q": [...]}  {"op": "estop"}  {"op": "reset"}  {"op": "status"}
  dev  -> {"ok": bool, "state": "idle|armed|moving|done|stopped", "reason"?, "q"?, "accepted"?}
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from worldengine import guard as GD, robot as RB

FIRMWARE_SRC = r'''
import json, math, sys, time
cfg = json.loads(sys.argv[1])
lo, hi = cfg["lower"], cfg["upper"]
state, armed_sha, expect_n, nxt, q, qd, last_t, last_rx, reason = "idle", None, 0, 0, None, None, None, None, ""
def out(ok, **kw):
    sys.stdout.write(json.dumps({"ok": ok, "state": state, **kw}) + "\n"); sys.stdout.flush()
def stop(why):
    global state, reason
    state, reason = "stopped", why
    out(False, reason=why)
for line in sys.stdin:
    now = time.monotonic()
    try:
        m = json.loads(line)
    except ValueError:
        stop("malformed packet"); continue
    op = m.get("op")
    if state in ("moving", "armed") and last_rx is not None and now - last_rx > cfg["watchdog_s"] and op not in ("estop", "reset", "status"):
        stop("watchdog: stream gap %.2f s" % (now - last_rx)); continue
    last_rx = now
    if op == "status":
        out(True, q=q, reason=reason); continue
    if op == "estop":
        stop("emergency stop"); continue
    if op == "reset":
        state, armed_sha, nxt, q, qd, last_t, reason = "idle", None, 0, None, None, None, ""
        out(True); continue
    if state == "stopped":
        out(False, reason="stopped (%s) -- reset required" % reason); continue
    if op == "arm":
        if not isinstance(m.get("traj_sha"), str) or len(m["traj_sha"]) != 64:
            stop("arm without an approved trajectory hash"); continue
        state, armed_sha, expect_n, nxt = "armed", m["traj_sha"], int(m["n"]), 0
        out(True); continue
    if op == "point":
        if state not in ("armed", "moving"):
            stop("point before arm"); continue
        if m.get("sha") != armed_sha:
            stop("point from another trajectory"); continue
        if m.get("i") != nxt:
            stop("out-of-order point %s (expected %d)" % (m.get("i"), nxt)); continue
        p, t = m.get("q"), m.get("t")
        if not (isinstance(p, list) and len(p) == len(lo) and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p)):
            stop("bad joint vector"); continue
        bad = [j for j, v in enumerate(p) if not lo[j] <= v <= hi[j]]
        if bad:
            stop("joint %d outside firmware range" % bad[0]); continue
        if q is not None:
            dt = t - last_t
            if not dt > 0:
                stop("time does not increase"); continue
            v = [(a - b) / dt for a, b in zip(p, q)]
            if max(abs(x) for x in v) > cfg["qd_max"]:
                stop("joint speed %.2f rad/s over firmware limit %.2f" % (max(abs(x) for x in v), cfg["qd_max"])); continue
            if qd is not None and max(abs(a - b) / dt for a, b in zip(v, qd)) > cfg["qdd_max"]:
                stop("acceleration over firmware limit %.1f rad/s2" % cfg["qdd_max"]); continue
            qd = v
        q, last_t, nxt, state = p, t, nxt + 1, "moving"
        if nxt == expect_n:
            state = "done"
        out(True, accepted=nxt); continue
    stop("unknown op %r" % op)
'''


def traj_sha(traj: dict) -> str:
    return hashlib.sha256(json.dumps({"t": traj["t"], "q": traj["q"]}, separators=(",", ":")).encode()).hexdigest()


class SimDevice:
    """The simulated device: a separate process running FIRMWARE_SRC with its own limits."""
    def __init__(self, chain: dict, qd_max: float = 1.5, qdd_max: float = 30.0, watchdog_s: float = 0.5):
        act = RB.active(chain)
        self.cfg = {"lower": [j["lower"] for j in act], "upper": [j["upper"] for j in act], "qd_max": qd_max, "qdd_max": qdd_max, "watchdog_s": watchdog_s}
        self.p = subprocess.Popen([sys.executable, "-I", "-c", FIRMWARE_SRC, json.dumps(self.cfg)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def send(self, msg: dict) -> dict:
        self.p.stdin.write(json.dumps(msg) + "\n"); self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def close(self):
        try:
            self.p.stdin.close(); self.p.wait(timeout=5)
        except Exception:                                   # noqa: BLE001
            self.p.kill()
        self.p.stdout.close()


class Bridge:
    """Host side. drive() is what the drive_device approval executor calls; nothing else should."""
    def __init__(self, chain: dict, device):
        self.chain, self.device = chain, device

    def drive(self, traj: dict, qd_max: float = 1.5, pace=None) -> dict:
        g = GD.check(self.chain, traj, qd_max)                # host guard first: never send what failed simulation
        if not g["ok"]:
            return {"sent": 0, "ok": False, "blocked_by": "host guard", "violations": g["violations"][:5]}
        sha = traj_sha(traj)
        r = self.device.send({"op": "arm", "traj_sha": sha, "n": len(traj["q"])})
        if not r["ok"]:
            return {"sent": 0, "ok": False, "blocked_by": "device", "reason": r.get("reason")}
        for i, (t, q) in enumerate(zip(traj["t"], traj["q"])):
            if pace:
                pace(i)
            r = self.device.send({"op": "point", "i": i, "t": t, "q": q, "sha": sha})
            if not r["ok"]:
                return {"sent": i, "ok": False, "blocked_by": "device", "reason": r.get("reason")}
        return {"sent": len(traj["q"]), "ok": r["state"] == "done", "state": r["state"]}
