# -*- coding: utf-8 -*-
"""Runtime Musts: glow (XR-01 bloom), level of detail (XR-01 LOD), flying (XR-02), the exhibition player (T-02),
imported files (E-02, local to the artist unless an approved publish takes the ones a work uses) and opt-in live
camera/microphone input (M-03, nothing leaves the device). Run from engine/.

Live inputs and recordings run on the wall clock (headless.run_live): in Chromium's --timeout mode the page's
timers stop once a camera, microphone or audio stream starts, and virtual time never finishes decoding audio."""
from __future__ import annotations

import base64
import copy
import io
import json
import math
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave
import zlib
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
REPO = ENGINE.parent
sys.path.insert(0, str(ENGINE))

from worldengine import assets as AS, exhibit as EX, headless, site, works as WK, world as WD  # noqa: E402
from worldengine.studio import server as SV, session as SS  # noqa: E402

BROWSER, WHY = headless.available()
YEOBAEK = WD.load(ENGINE / "worlds" / "ref_yeobaek.world.json")


def glb_box(sx=1.0, sy=2.0, sz=0.5) -> bytes:
    """A box sx * sy (up, glTF y) * sz as binary glTF."""
    xs, ys, zs = (-sx / 2, sx / 2), (0.0, sy), (-sz / 2, sz / 2)
    V = [(x, y, z) for x in xs for y in ys for z in zs]
    F = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    pos = b"".join(struct.pack("<3f", *v) for v in V)
    idx = b"".join(struct.pack("<3H", *f) for f in F)
    idx += b"\0" * (-len(idx) % 4)
    binc = pos + idx
    g = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}], "buffers": [{"byteLength": len(binc)}],
         "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos)}, {"buffer": 0, "byteOffset": len(pos), "byteLength": 72}],
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": [min(xs), 0, min(zs)], "max": [max(xs), sy, max(zs)]},
                       {"bufferView": 1, "componentType": 5123, "count": 36, "type": "SCALAR"}]}
    js = json.dumps(g).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<I", len(js)) + b"JSON" + js + struct.pack("<I", len(binc)) + b"BIN\0" + binc
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def png(w=8, h=4, rgb=(200, 30, 60)) -> bytes:
    raw = b"".join(b"\0" + bytes(rgb) * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


def wav(seconds=0.5, hz=440, rate=22050) -> bytes:
    b = io.BytesIO()
    f = wave.open(b, "wb"); f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
    f.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / rate))) for i in range(int(seconds * rate))))
    f.close()
    return b.getvalue()


FILES = {"box.glb": glb_box(), "그림 1.png": png(), "tone.wav": wav()}
IMPORTED = {"format": "world/1", "name": "imp", "bounds": [10, 10, 4], "environment": {"env_map": None},
            "materials": {"pic": {"image": "asset:그림 1.png"}},
            "entities": [{"id": "model", "type": "model", "src": "asset:box.glb", "pos": [3, 3, 0], "fit_m": 4},
                         {"id": "wall", "type": "box", "size": [2, 0.2, 2], "pos": [7, 5, 0], "material": "pic"},
                         {"id": "rec", "type": "sound", "src": "asset:tone.wav", "caption": "녹음한 소리", "pos": [5, 5, 1]}]}


def repo_files():
    return {p: p.stat().st_mtime for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}


class SchemaTests(unittest.TestCase):
    def test_imported_files_are_named_never_linked(self):
        for bad in ("https://x/y.glb", "file:///etc/passwd", "asset:../up", "asset:", "y.glb"):
            w = copy.deepcopy(IMPORTED); w["entities"][0]["src"] = bad
            self.assertTrue(any(".src must be" in m for m in WD.check(w)), bad)
        self.assertEqual(WD.check(IMPORTED), [])
        self.assertEqual(AS.refs(IMPORTED), {"box.glb", "그림 1.png", "tone.wav"})


class AssetStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.st = AS.Store(self.tmp)

    def test_kind_comes_from_the_bytes_and_names_are_checked(self):
        r = self.st.put("의자 (2).glb", FILES["box.glb"])
        self.assertEqual((r["ref"], r["media_type"]), ("asset:의자 (2).glb", "model/gltf-binary"))
        self.assertEqual(self.st.get("의자 (2).glb"), (FILES["box.glb"], "model/gltf-binary"))
        for name, data in (("x.glb", b"MZ\x90\x00 not a model"), ("../evil.png", png()), ("a/b.png", png()), ("", png())):
            with self.assertRaises(ValueError):
                self.st.put(name, data)
        self.assertEqual(AS.sniff(png()), "image/png"); self.assertEqual(AS.sniff(wav()), "audio/wav")
        self.assertTrue(all(p.is_relative_to(self.tmp) for p in self.tmp.rglob("*")))

    def test_publish_copies_only_what_the_work_uses(self):
        for n, b in FILES.items():
            self.st.put(n, b)
        self.st.put("unused.png", png(2, 2))
        out = self.tmp / "site"
        w = self.tmp / "imp.world.json"; w.write_text(json.dumps(IMPORTED, ensure_ascii=False), encoding="utf-8")
        b = site.build(out, world_files=[w], assets=self.st)
        self.assertEqual(sorted(p.name for p in (out / "assets").iterdir()), sorted(FILES))
        self.assertIn("&assets=", b["worlds"][0]["url"])
        self.assertFalse((site.build(self.tmp / "site2", world_files=[w]).get("out") and (self.tmp / "site2" / "assets").exists()))   # no store: none


class StudioAssetTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.st = SV.Studio(IMPORTED, "t", None, data=self.d)
        self.srv = SV.http.server.ThreadingHTTPServer(("127.0.0.1", 0), SV.make_handler(self.st))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()

    def post(self, path, body, token=True):
        url = self.base + path + ("?t=" + self.st.token if token else "")
        return json.loads(urllib.request.urlopen(urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})).read())

    def test_import_needs_the_token_and_stays_in_the_private_folder(self):
        before = repo_files()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post("/api/asset", {"name": "box.glb", "data": base64.b64encode(FILES["box.glb"]).decode()}, token=False)
        self.assertEqual(cm.exception.code, 403)
        r = self.post("/api/asset", {"name": "box.glb", "data": base64.b64encode(FILES["box.glb"]).decode()})
        self.assertEqual(r["ref"], "asset:box.glb")
        self.assertTrue(any(Path(self.d, "assets").glob("*.glb")))
        self.assertFalse(Path(self.d).resolve().is_relative_to(REPO.resolve()))
        got = urllib.request.urlopen(self.base + "/api/asset/box.glb?t=" + self.st.token).read()
        self.assertEqual(got, FILES["box.glb"])
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(self.base + "/api/asset/box.glb")
        self.assertEqual(cm.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post("/api/asset", {"name": "x.glb", "data": base64.b64encode(b"#!/bin/sh\nrm -rf /").decode()})
        self.assertEqual(cm.exception.code, 400)
        self.assertEqual(repo_files(), before)                                      # nothing written into the repository

    def test_publish_needs_approval_and_takes_only_this_works_files(self):
        for n, b in FILES.items():
            self.post("/api/asset", {"name": n, "data": base64.b64encode(b).decode()})
        self.post("/api/asset", {"name": "other.png", "data": base64.b64encode(png(2, 2)).decode()})
        s = self.st.session
        a = s.request("publish", {}, "공개")
        pub = Path(self.d) / "out" / "publish"
        self.assertFalse(pub.exists())                                              # nothing before the artist approves
        s.approve(a["approval"])
        self.assertEqual(sorted(p.name for p in (pub / "assets").iterdir()), sorted(FILES))


class ExhibitTests(unittest.TestCase):
    def test_visitors_get_works_but_never_imported_files(self):
        srv = EX.http.server.ThreadingHTTPServer(("127.0.0.1", 0), EX.make_handler(YEOBAEK, None, None))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        try:
            idx = json.loads(urllib.request.urlopen(base + "/works.json").read())
            self.assertEqual([i["title"] for i in idx["items"]], ["그림", "로봇이 그린 그림"])
            self.assertTrue(urllib.request.urlopen(base + idx["items"][0]["src"]).read().startswith(b"<svg"))
            for path in ("/api/asset/box.glb", "/assets/box.glb", "/api/assets"):
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(base + path)
                self.assertEqual(cm.exception.code, 404, path)
        finally:
            srv.shutdown(); srv.server_close()

    def test_works_refused_by_the_rules_are_listed_with_the_reason(self):
        w = copy.deepcopy(YEOBAEK); w["forbidden"] = [{"kind": "word", "value": "polyline"}]
        items = WK.render(w)
        self.assertEqual([i["ok"] for i in items], [True, False])
        self.assertIn("세계 규칙", items[1]["reason"])
        self.assertNotIn("src", WK.index(items, lambda it: "x")["items"][1])


@unittest.skipUnless(BROWSER, "no browser: " + WHY)
class RuntimeMustsBrowserTests(unittest.TestCase):
    def selftest(self, world, name, w=480, h=320, **kw):
        with tempfile.TemporaryDirectory() as d:
            r = headless.render_world(world, Path(d) / "x.png", w=w, h=h, selftest=name, timeout_s=180, **kw)
        self.assertTrue(r["ok"], r.get("reason"))
        return r["result"]

    GLOW = {"format": "world/1", "name": "glow", "bounds": [10, 10, 4],
            "environment": {"background": "#05060a", "env_map": None, "ambient": 0.05, "sun": {"intensity": 0.2, "shadows": False},
                            "bloom": {"strength": 1.6, "radius": 0.5, "threshold": 0.2}},
            "materials": {"hot": {"color": "#ffffff", "emissive": "#ffd27a", "emissive_intensity": 4}},
            "entities": [{"id": "glow", "type": "sphere", "pos": [5, 5, 1], "radius": 0.6, "material": "hot"}],
            "views": {"v": {"pos": [5, -3, 2], "target": [5, 5, 1.6], "fov": 40}}}

    def test_bloom_glows_and_low_spec_drops_it(self):
        on = self.selftest(self.GLOW, "bloom")
        print("\nBLOOM ring luminance off %.2f on %.2f low-spec %.2f (radius %.1f px)" % (on["ring_off"], on["ring_on"], on["ring_lowspec"], on["px_radius"]), file=sys.stderr)
        self.assertTrue(on["has_post"])
        self.assertGreater(on["ring_on"], 5 * on["ring_off"] + 10)
        self.assertEqual(on["ring_lowspec"], on["ring_off"])
        plain = copy.deepcopy(self.GLOW); del plain["environment"]["bloom"]
        off = self.selftest(plain, "bloom")
        self.assertFalse(off["has_post"])
        self.assertEqual(off["ring_on"], off["ring_off"])

    def test_lod_draws_far_bodies_coarser(self):
        grid = {"format": "world/1", "name": "grid", "environment": {"env_map": None},
                "entities": [{"type": "sphere", "pos": [2 * i, 2 * j, 0], "radius": 0.4} for i in range(10) for j in range(10)]}
        on = self.selftest(grid, "lod")
        off_w = copy.deepcopy(grid); off_w["environment"]["lod"] = False
        off = self.selftest(off_w, "lod")
        print("\nLOD triangles near %d / far %d (on, %d LOD bodies, switch at %g m) vs near %d / far %d (off)" % (
            on["near"], on["far"], on["lod_objects"], on["distance"], off["near"], off["far"]), file=sys.stderr)
        self.assertEqual((on["lod_objects"], off["lod_objects"]), (100, 0))
        self.assertLess(on["far"] * 10, off["far"])
        self.assertLess(on["near"], off["near"])

    def test_fly(self):
        r = self.selftest(WD.load(ENGINE / "worlds" / "contradiction_garden.world.json"), "fly")
        self.assertEqual((r["forward_m"], r["forward_dz"], r["up_m"], r["floor_m"]), (4, 0, 4, 0.3))
        self.assertEqual(r["walk_eye_after"], r["eye_height"])                      # landing puts the eye back at walking height

    def test_player(self):
        w = copy.deepcopy(YEOBAEK)
        w["tours"] = [{"id": "t", "stops": [{"pos": [2, 2, 1.7], "target": [5, 5, 1], "dwell_s": 2, "caption": "여기"},
                                            {"pos": [8, 2, 1.7], "target": [5, 5, 1], "dwell_s": 2, "caption": "저기"}]}]
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "yeobaek_tour.world.json"; src.write_text(json.dumps(w, ensure_ascii=False), encoding="utf-8")
            out = Path(d) / "site"; b = site.build(out, world_files=[src])
            self.assertEqual(sorted(p.name for p in (out / "works" / "yeobaek_tour").iterdir()), ["1_image_svg.svg", "2_plotter.svg"])
            handler = __import__("functools").partial(headless._Quiet, directory=str(out))
            with headless.http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as srv:
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                r = headless.run_live("http://127.0.0.1:%d/%s&headless=1&selftest=player&w=390&h=700" % (srv.server_address[1], b["worlds"][0]["url"]), 90, 390, 700)
                srv.shutdown()
        self.assertTrue(r["ok"], r.get("reason"))
        res = r["result"]
        print("\nPLAYER %s" % json.dumps({k: res[k] for k in ("attract_after_s", "attract_loops", "fullscreen", "wake")}, ensure_ascii=False), file=sys.stderr)
        self.assertEqual([(i["ok"], i["w"] > 0) for i in res["items"]], [(True, True), (True, True)])
        self.assertLessEqual(res["attract_after_s"], 5.5)                          # idle 5 s (test setting) -> the tour
        self.assertTrue(res["touring"]); self.assertGreaterEqual(res["attract_loops"], 2); self.assertTrue(res["cursor_hidden"])
        self.assertEqual(res["after_touch"], {"attract": False, "touring": False, "orbit": True})
        self.assertEqual(res["fullscreen"]["requested"], 1)                         # asked; headless refuses without a real tap
        self.assertTrue(res["big_opens"]); self.assertTrue(res["strip_inside"])

    def test_imported_files_for_the_artist_and_not_for_a_visitor(self):
        a = self.selftest(IMPORTED, "assets", assets=FILES, live=True)
        print("\nASSETS artist %s" % json.dumps({k: a[k] for k in ("model", "image", "audio")}, ensure_ascii=False), file=sys.stderr)
        self.assertEqual(a["model"], {"loaded": True, "size": [2, 1, 4], "placeholder": False})   # glTF y-up -> z-up, fitted to 4 m
        self.assertEqual(a["image"], {"has_map": True, "w": 8})
        self.assertEqual((a["audio"]["decoded"], a["audio"]["seconds"]), (1, [0.5]))
        self.assertEqual(sorted(a["requests"]), sorted("/assets/" + n for n in FILES))
        v = self.selftest(IMPORTED, "assets", live=True)                           # a visitor's page: no way to read them
        self.assertEqual(v["template"], None)
        self.assertEqual(v["model"], {"loaded": False, "size": [4, 4, 4], "placeholder": True})
        self.assertFalse(v["image"]["has_map"])
        self.assertEqual((v["audio"]["decoded"], v["audio"]["failed"]), (0, 1))
        self.assertEqual(v["requests"], [])
        self.assertIn("이 페이지에서는 파일을 들을 수 없어요", " ".join(v["captions"]))

    def test_editor_import_stays_in_the_browser(self):
        r = self.selftest(YEOBAEK, "editor_import", w=1280, h=800, page="editor.html",
                          assets={"box.glb": FILES["box.glb"], "pic.png": FILES["그림 1.png"], "tone.wav": FILES["tone.wav"]}, live=True)
        self.assertEqual([i["kind"] for i in r["imported"]], ["model", "image", "audio"])
        self.assertEqual(r["local_urls"], ["blob:"] * 3)
        self.assertEqual(r["model"], {"src": "asset:의자 (2).glb", "loaded": True})
        self.assertEqual(r["image"], {"material": {"color": "#ffffff", "image": "asset:wall pic.png"}, "has_map": True})
        self.assertEqual(r["sound"], ["asset:rain.wav"])
        self.assertFalse(r["export_has_blob"])                                      # the world names files, it never carries them
        self.assertLess(r["export_bytes"], 4000)
        self.assertEqual(WD.check(r["exported"]), [])

    def test_live_inputs_are_opt_in_and_stay_on_the_device(self):
        live = {"format": "world/1", "name": "live", "bounds": [6, 6, 3], "environment": {"env_map": None},
                "entities": [{"id": "listener", "type": "sphere", "radius": 0.5, "pos": [3, 3, 0], "behaviors": [{"type": "react", "input": "mic", "prop": "scale", "amount": 1}]},
                             {"id": "eye", "type": "box", "size": [1, 1, 1], "pos": [1, 1, 0], "material": {"color": "#333333", "emissive": "#ffffff", "emissive_intensity": 0.1},
                              "behaviors": [{"type": "react", "input": "camera", "prop": "glow"}]}]}
        r = self.selftest(live, "inputs", w=320, h=240, live=True, fake_media=True)
        print("\nINPUTS (Chromium fake devices) max levels %s" % r["max"], file=sys.stderr)
        self.assertEqual(sorted(r["wanted"]), ["camera", "mic"])
        self.assertEqual(r["requested_before_enable"], 0)                          # nothing asked until the visitor turns it on
        self.assertEqual(r["enabled"], {"mic": True, "camera": True})
        self.assertGreater(r["max"]["mic"], 0.05); self.assertGreater(r["max"]["camera"], 0.05)
        self.assertGreater(r["max"]["scale"], 1.05)                                 # a react body follows the room
        self.assertEqual(r["network_during_capture"], {"fetch": 0, "xhr": 0, "ws": 0, "beacon": 0})
        self.assertEqual(r["media_elements_in_page"], 0)
        self.assertEqual(sorted(r["tracks_on"]), ["audio:live", "video:live"])
        self.assertEqual(sorted(r["tracks_after_off"]), ["audio:ended", "video:ended"])
        self.assertEqual((r["levels_after_off"], r["scale_after_off"]), ({"mic": 0, "camera": 0}, 1))


if __name__ == "__main__":
    unittest.main()
