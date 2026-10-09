# -*- coding: utf-8 -*-
"""glTF bridge (SPEC XR-10): export a world to .glb through the runtime (three.js GLTFExporter, so the file holds
exactly what a visitor sees), and validate a .glb independently of three.js.

    r = export(world_or_path, "out.glb")   -> {"ok", "bytes", "summary"|reason}
    validate("out.glb")                    -> {"ok", "problems": [...], "nodes", "meshes", "materials", "triangles", ...}
USD is not produced (no exporter available here); the README says so.
"""
from __future__ import annotations

import base64
import json
import struct
import tempfile
from pathlib import Path

COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
SIZES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}


def validate(path) -> dict:
    data = Path(path).read_bytes()
    bad = []
    if len(data) < 20 or data[:4] != b"glTF":
        return {"ok": False, "problems": ["not a GLB (magic)"]}
    version, length = struct.unpack("<II", data[4:12])
    if version != 2:
        bad.append("GLB version %d" % version)
    if length != len(data):
        bad.append("header length %d != file %d" % (length, len(data)))
    pos, chunks = 12, []
    while pos + 8 <= len(data):
        n, kind = struct.unpack("<I4s", data[pos:pos + 8])
        chunks.append((kind, data[pos + 8:pos + 8 + n])); pos += 8 + n
    if not chunks or chunks[0][0] != b"JSON":
        return {"ok": False, "problems": bad + ["first chunk is not JSON"]}
    g = json.loads(chunks[0][1].decode("utf-8"))
    binc = next((c for k, c in chunks if k == b"BIN\x00"), b"")
    if g.get("asset", {}).get("version") != "2.0":
        bad.append("asset.version is not 2.0")
    buffers = g.get("buffers", [])
    if buffers and buffers[0].get("byteLength", 0) > len(binc):
        bad.append("buffer 0 longer than BIN chunk")
    for i, bv in enumerate(g.get("bufferViews", [])):
        if bv.get("byteOffset", 0) + bv["byteLength"] > buffers[bv["buffer"]]["byteLength"]:
            bad.append("bufferView %d out of range" % i)
    for i, a in enumerate(g.get("accessors", [])):
        bv = g["bufferViews"][a["bufferView"]] if "bufferView" in a else None
        if bv is not None:
            need = a.get("byteOffset", 0) + a["count"] * COMPONENTS[a["type"]] * SIZES[a["componentType"]]
            if need > bv["byteLength"] and not bv.get("byteStride"):
                bad.append("accessor %d overruns its view" % i)
    tris = 0
    for m in g.get("meshes", []):
        for prim in m["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            if "indices" in prim:
                tris += g["accessors"][prim["indices"]]["count"] // 3
            else:
                tris += g["accessors"][prim["attributes"]["POSITION"]]["count"] // 3
            if "POSITION" not in prim["attributes"]:
                bad.append("primitive without POSITION")
    lights = len(g.get("extensions", {}).get("KHR_lights_punctual", {}).get("lights", []))
    return {"ok": not bad, "problems": bad, "bytes": len(data), "nodes": len(g.get("nodes", [])), "meshes": len(g.get("meshes", [])),
            "materials": len(g.get("materials", [])), "images": len(g.get("images", [])), "triangles": tris, "lights": lights,
            "extensions": sorted(g.get("extensionsUsed", []))}


def export(world, out_path, timeout_s: float = 180) -> dict:
    from worldengine import headless
    with tempfile.TemporaryDirectory() as d:
        r = headless.render_world(world, Path(d) / "x.png", w=320, h=200, selftest="gltf", timeout_s=timeout_s)
    if not r["ok"]:
        return {"ok": False, "reason": r["reason"]}
    raw = base64.b64decode(r["result"]["glb_b64"])
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(raw)
    v = validate(out_path)
    return {"ok": v["ok"], "bytes": len(raw), "scene_meshes": r["result"]["scene_meshes"], "summary": v}
