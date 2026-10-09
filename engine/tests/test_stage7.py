# -*- coding: utf-8 -*-
"""Stage 7 buildables (SPEC 6절 7단계): glTF export (XR-10), multi-visitor presence (XR-09), WebXR smoke (XR-08),
device bridge to a SIMULATED device with its own firmware limits (RB-06). A real headset and a real device are
not in this repository; those checks are the artist's / owner's tasks. Run from engine/."""
from __future__ import annotations

import base64
import copy
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from worldengine import device as DV, exhibit as EX, gltf, guard as GD, headless, presence as PR, world as WD  # noqa: E402

BROWSER, BROWSER_WHY = headless.available()
GARDEN = WD.load(ENGINE / "worlds" / "talking_garden.world.json")
ROBOT = WD.load(ENGINE / "worlds" / "drawing_robot.world.json")
ARM = next(e for e in ROBOT["entities"] if e.get("type") == "robot.arm" and e.get("trajectory"))


def masked(payload: bytes, opcode: int = 1) -> bytes:
    """A client frame (clients must mask, RFC 6455 5.3)."""
    m = os.urandom(4)
    n = len(payload)
    head = bytes([0x80 | opcode]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + n.to_bytes(2, "big"))
    return head + m + bytes(b ^ m[i % 4] for i, b in enumerate(payload))


class Visitor:
    """A minimal WebSocket client for the tests."""
    def __init__(self, port: int):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(("GET /ws HTTP/1.1\r\nHost: t\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % key).encode())
        r = b""
        while b"\r\n\r\n" not in r:
            c = self.s.recv(1)
            if not c:
                break
            r += c
        self.head = r.decode("latin-1")
        self.key = key

    def send(self, obj) -> None:
        self.s.sendall(masked(obj if isinstance(obj, bytes) else json.dumps(obj).encode()))

    def next(self, kind: str, timeout: float = 5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            fr = PR.read_frame(self.s, 1 << 20)
            if fr is None:
                return None
            if fr[0] == 1:
                m = json.loads(fr[1])
                if m.get("type") == kind:
                    return m
        return None

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


class Server:
    def __init__(self, world):
        self.room = PR.Room(world.get("bounds"))
        self.srv = EX.http.server.ThreadingHTTPServer(("127.0.0.1", 0), EX.make_handler(world, None, self.room))
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


class GltfTests(unittest.TestCase):
    def test_validator_catches_broken_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.glb"
            p.write_bytes(b"not a glb at all, just text")
            self.assertFalse(gltf.validate(p)["ok"])
            js = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"byteLength": 36}],
                             "bufferViews": [{"buffer": 0, "byteLength": 36}],
                             "accessors": [{"bufferView": 0, "count": 3, "type": "VEC3", "componentType": 5126}],
                             "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]}).encode()
            js += b" " * (-len(js) % 4)
            body = (len(js).to_bytes(4, "little") + b"JSON" + js + (36).to_bytes(4, "little") + b"BIN\x00" + bytes(36))
            good = b"glTF" + (2).to_bytes(4, "little") + (12 + len(body)).to_bytes(4, "little") + body
            p.write_bytes(good)
            v = gltf.validate(p)
            self.assertTrue(v["ok"], v["problems"])
            self.assertEqual(v["triangles"], 1)
            p.write_bytes(good[:-4])                                     # truncated: header length and BIN disagree
            self.assertFalse(gltf.validate(p)["ok"])

    @unittest.skipUnless(BROWSER, "no browser: " + BROWSER_WHY)
    def test_export_world_to_valid_glb(self):
        with tempfile.TemporaryDirectory() as d:
            r = gltf.export(ENGINE / "worlds" / "ref_yeobaek.world.json", Path(d) / "yeobaek.glb")
            self.assertTrue(r["ok"], r)
            s = r["summary"]
            print("\nGLTF ref_yeobaek: %d bytes, %d meshes in scene, glb nodes %d meshes %d materials %d triangles %d lights %d"
                  % (r["bytes"], r["scene_meshes"], s["nodes"], s["meshes"], s["materials"], s["triangles"], s["lights"]), file=sys.stderr)
            self.assertGreater(s["meshes"], 0)
            self.assertGreater(s["triangles"], 0)
            self.assertEqual(s["problems"], [])


class PresenceTests(unittest.TestCase):
    def setUp(self):
        self.server = Server(GARDEN)
        self.open = []

    def tearDown(self):
        for v in self.open:
            v.close()
        self.server.close()

    def visitor(self):
        v = Visitor(self.server.port); self.open.append(v)
        return v

    def test_accept_key_rfc6455_example(self):
        self.assertEqual(PR.accept_key("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def test_two_visitors_see_each_other_anonymously(self):
        a, b = self.visitor(), self.visitor()
        self.assertIn("101", a.head.split("\r\n")[0])
        self.assertIn(PR.accept_key(a.key), a.head)
        ha, hb = a.next("hello"), b.next("hello")
        self.assertNotEqual(ha["id"], hb["id"])
        a.send({"pos": [1, 2, 1.7], "yaw": 0.5, "eye": "adult"})
        b.send({"pos": [3, 4, 1.1], "yaw": 0, "eye": "child"})
        seen = None
        for _ in range(30):
            m = b.next("room")
            if m and m["others"]:
                seen = m; break
        self.assertIsNotNone(seen)
        o = seen["others"][0]
        self.assertEqual(o["id"], ha["id"])
        self.assertEqual(o["pos"], [1.0, 2.0, 1.7])
        self.assertEqual(set(o), {"id", "colour", "pos", "yaw", "eye"})             # nothing else: no address, no name
        self.assertNotIn("127.0.0.1", json.dumps(seen))

    def test_bad_states_are_dropped(self):
        a, b = self.visitor(), self.visitor()
        a.next("hello"); b.next("hello")
        for bad in ({"pos": [1e9, 0, 0]}, {"pos": [float("nan"), 0, 0]}, {"pos": "here"}, {"pos": [1, 2]}, b"\xff\xfe not json"):
            a.send(bad if isinstance(bad, bytes) else json.dumps(bad, allow_nan=True).encode()); time.sleep(0.06)
        a.send(b"x" * (PR.MAX_MSG + 10)); time.sleep(0.06)
        time.sleep(0.3)
        m = b.next("room")
        self.assertEqual(m["others"], [])                                          # a is connected but has no valid state
        self.assertGreaterEqual(self.server.room.stats["dropped"], 6)

    def test_room_is_capped(self):
        old = PR.MAX_CLIENTS
        PR.MAX_CLIENTS = 2
        try:
            self.visitor().next("hello"); self.visitor().next("hello")
            third = self.visitor()
            self.assertIsNotNone(third.next("full"))
        finally:
            PR.MAX_CLIENTS = old

    def test_nothing_written_to_disk(self):
        before = {p: p.stat().st_mtime for p in ENGINE.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        a, b = self.visitor(), self.visitor()
        a.send({"pos": [1, 1, 1.7]}); b.next("room")
        after = {p: p.stat().st_mtime for p in ENGINE.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        self.assertEqual(before, after)

    @unittest.skipUnless(BROWSER, "no browser: " + BROWSER_WHY)
    def test_browser_sees_a_python_visitor(self):
        py = self.visitor(); hello = py.next("hello")
        stop = threading.Event()

        def keep_sending():
            while not stop.is_set():
                try:
                    py.send({"pos": [2, 3, 1.7], "yaw": 0, "eye": "adult"})
                except OSError:
                    return
                time.sleep(0.2)
        threading.Thread(target=keep_sending, daemon=True).start()
        try:
            url = ("http://127.0.0.1:%d/runtime/index.html?world=/world.json&presence=/ws&headless=1&selftest=presence&w=320&h=200"
                   % self.server.port)
            with tempfile.TemporaryDirectory() as d:
                r = headless.render_url(url, Path(d) / "p.png", 320, 200, timeout_s=120, real_time_s=12)
        finally:
            stop.set()
        self.assertTrue(r["ok"], r.get("reason"))
        res = r["result"]
        print("\nPRESENCE browser: %s" % json.dumps({k: res[k] for k in ("connected", "count", "avatars", "in_scene", "received")}), file=sys.stderr)
        self.assertTrue(res["connected"])
        self.assertIn(hello["id"], res["avatar_ids"])
        self.assertGreaterEqual(res["in_scene"], 1)


@unittest.skipUnless(BROWSER, "no browser: " + BROWSER_WHY)
class XRSmokeTests(unittest.TestCase):
    def test_vr_offered_only_when_supported(self):
        # Wall clock, not Chromium's virtual time: isSessionSupported answers through the browser process, and under
        # a virtual-time budget the page often finished before the answer came (4 of 6 runs here). Real browsers
        # always run on the wall clock.
        srv = EX.http.server.ThreadingHTTPServer(("127.0.0.1", 0), EX.make_handler(GARDEN, None, None))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = "http://127.0.0.1:%d/runtime/index.html?world=/world.json&headless=1&selftest=xr&w=320&h=200" % srv.server_address[1]
            with tempfile.TemporaryDirectory() as d:
                r = headless.render_url(url, Path(d) / "x.png", 320, 200, timeout_s=120, real_time_s=6)
        finally:
            srv.shutdown(); srv.server_close()
        self.assertTrue(r["ok"], r.get("reason"))
        res = r["result"]
        print("\nXR smoke: %s" % json.dumps(res), file=sys.stderr)
        self.assertTrue(res["agree"])
        self.assertEqual(res["button"], res["vr"])                                  # no VR here -> no button, renderer untouched
        self.assertEqual(res["renderer_xr"], res["vr"])


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.dev = DV.SimDevice(ARM["chain"])

    def tearDown(self):
        self.dev.close()

    def test_approved_demo_trajectory_runs_to_done(self):
        traj = ARM["trajectory"]
        self.assertTrue(GD.check(ARM["chain"], traj)["ok"])
        r = DV.Bridge(ARM["chain"], self.dev).drive(traj)
        self.assertEqual((r["ok"], r["state"], r["sent"]), (True, "done", len(traj["q"])))

    def test_host_guard_blocks_before_anything_is_sent(self):
        fast = copy.deepcopy(ARM["trajectory"])
        fast["t"] = [t / 10 for t in fast["t"]]
        r = DV.Bridge(ARM["chain"], self.dev).drive(fast)
        self.assertEqual((r["ok"], r["sent"], r["blocked_by"]), (False, 0, "host guard"))
        self.assertEqual(self.dev.send({"op": "status"})["state"], "idle")

    def arm(self, n=10):
        sha = "a" * 64
        self.assertTrue(self.dev.send({"op": "arm", "traj_sha": sha, "n": n})["ok"])
        return sha

    def q0(self):
        return list(ARM["trajectory"]["q"][0])

    def test_firmware_refuses_unarmed_and_unhashed(self):
        self.assertIn("before arm", self.dev.send({"op": "point", "i": 0, "t": 0, "q": self.q0(), "sha": "a" * 64})["reason"])
        self.dev.send({"op": "reset"})
        self.assertFalse(self.dev.send({"op": "arm", "traj_sha": "short", "n": 3})["ok"])
        self.dev.send({"op": "reset"})
        self.arm()
        self.assertIn("another trajectory", self.dev.send({"op": "point", "i": 0, "t": 0, "q": self.q0(), "sha": "b" * 64})["reason"])

    def test_firmware_own_limits(self):
        lo, hi = self.dev.cfg["lower"], self.dev.cfg["upper"]
        cases = []
        sha = self.arm(); q = self.q0()
        self.dev.send({"op": "point", "i": 0, "t": 0.0, "q": q, "sha": sha})
        cases.append(self.dev.send({"op": "point", "i": 1, "t": 0.01, "q": [v + 0.1 for v in q], "sha": sha}))     # 10 rad/s
        self.dev.send({"op": "reset"}); sha = self.arm()
        cases.append(self.dev.send({"op": "point", "i": 0, "t": 0.0, "q": [hi[0] + 0.5] + q[1:], "sha": sha}))     # range
        self.dev.send({"op": "reset"}); sha = self.arm()
        self.dev.send({"op": "point", "i": 0, "t": 0.0, "q": q, "sha": sha})
        cases.append(self.dev.send({"op": "point", "i": 2, "t": 0.1, "q": q, "sha": sha}))                           # order
        self.dev.send({"op": "reset"}); sha = self.arm()
        self.dev.send({"op": "point", "i": 0, "t": 0.0, "q": q, "sha": sha})
        self.dev.send({"op": "point", "i": 1, "t": 0.1, "q": q, "sha": sha})
        cases.append(self.dev.send({"op": "point", "i": 2, "t": 0.11, "q": [q[0] + 0.014] + q[1:], "sha": sha}))     # 1.4 rad/s reached in 10 ms
        self.dev.send({"op": "reset"}); sha = self.arm()
        cases.append(self.dev.send({"op": "point", "i": 0, "t": 0.0, "q": [float("nan")] + q[1:], "sha": sha}))      # NaN never reaches a joint
        reasons = [c["reason"] for c in cases]
        self.assertTrue(all(not c["ok"] and c["state"] == "stopped" for c in cases), reasons)
        for want, got in zip(("joint speed", "outside firmware range", "out-of-order", "acceleration", "bad joint vector"), reasons):
            self.assertIn(want, got)
        self.assertTrue(lo[0] < q[0] < hi[0])

    def test_watchdog_stop_latches_until_reset(self):
        sha = self.arm(); q = self.q0()
        self.dev.send({"op": "point", "i": 0, "t": 0.0, "q": q, "sha": sha})
        time.sleep(0.7)
        r = self.dev.send({"op": "point", "i": 1, "t": 0.1, "q": q, "sha": sha})
        self.assertIn("watchdog", r["reason"])
        self.assertIn("reset required", self.dev.send({"op": "point", "i": 1, "t": 0.1, "q": q, "sha": sha})["reason"])
        self.assertTrue(self.dev.send({"op": "reset"})["ok"])

    def test_estop_mid_run(self):
        traj = ARM["trajectory"]

        def pace(i):
            if i == 50:
                self.dev.send({"op": "estop"})
        r = DV.Bridge(ARM["chain"], self.dev).drive(traj, pace=pace)
        self.assertEqual((r["ok"], r["sent"], r["blocked_by"]), (False, 50, "device"))
        self.assertIn("emergency stop", r["reason"])
        self.assertEqual(self.dev.send({"op": "status"})["state"], "stopped")
        self.dev.send({"op": "reset"})
        self.assertTrue(DV.Bridge(ARM["chain"], self.dev).drive(traj)["ok"])           # after an explicit reset it runs again


if __name__ == "__main__":
    unittest.main()
