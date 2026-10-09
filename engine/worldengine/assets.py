# -*- coding: utf-8 -*-
"""Imported files (E-02): the artist's own pictures, recordings and 3D models.

Where they live and where they may go:
  - in the artist's private data folder (studio config.data_dir(), outside the repository), content-addressed;
  - worlds name them, they never link them: "asset:<name>" (world.check refuses URLs);
  - the artist's own studio pages read them (token);
  - an APPROVED publish (A-06) copies the ones the published world uses -- and only those -- next to it.
Nothing else serves them: the exhibit server has no asset route, presence relays positions only, and a world sent
to a visitor's browser carries names, not bytes.

    st = Store(data_dir); st.put("의자.glb", data) -> {"ref": "asset:의자.glb", ...};  st.get(name) -> (bytes, media_type)
    refs(world) -> {names}      st.copy_referenced(world, dest) -> [names copied]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

from worldengine import world as WD

MAX_BYTES = 50 * 1024 * 1024
EXT = {"model/gltf-binary": "glb", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
       "audio/wav": "wav", "audio/mpeg": "mp3", "audio/ogg": "ogg"}


def sniff(data: bytes) -> "str | None":
    """The media type from the bytes themselves (never from the file name or what the client claims)."""
    if data[:4] == b"glTF":
        return "model/gltf-binary"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if data[:4] == b"OggS":
        return "audio/ogg"
    return None


def refs(world: dict) -> "set[str]":
    out = set()
    for m in (world.get("materials") or {}).values():
        if isinstance(m, dict) and WD.is_asset_ref(m.get("image")):
            out.add(m["image"][6:])

    def walk(es):
        for e in es or []:
            if not isinstance(e, dict):
                continue
            for v in (e.get("src"), (e.get("material") or {}).get("image") if isinstance(e.get("material"), dict) else None):
                if WD.is_asset_ref(v):
                    out.add(v[6:])
            walk(e.get("children"))
    walk(world.get("entities"))
    return out


class Store:
    def __init__(self, data_dir):
        self.dir = Path(data_dir) / "assets"
        self.manifest_path = self.dir / "manifest.json"

    def _manifest(self) -> dict:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def put(self, name: str, data: bytes) -> dict:
        name = str(name).strip()
        if not WD.is_asset_ref("asset:" + name):
            raise ValueError("파일 이름은 글자·숫자·공백·.()- 만 (최대 121자): %r" % name)
        if len(data) > MAX_BYTES:
            raise ValueError("파일이 너무 크다 (%d MB 까지)" % (MAX_BYTES // 1048576))
        mt = sniff(data)
        if mt is None:
            raise ValueError("glTF(.glb)·PNG·JPEG·WebP·WAV·MP3·Ogg 만 가져온다")
        sha = hashlib.sha256(data).hexdigest()
        self.dir.mkdir(parents=True, exist_ok=True)
        f = self.dir / ("%s.%s" % (sha, EXT[mt]))
        if not f.exists():
            f.write_bytes(data)
        m = self._manifest()
        m[name] = {"sha256": sha, "media_type": mt, "bytes": len(data), "file": f.name, "t": int(time.time())}
        self.manifest_path.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"name": name, "ref": "asset:" + name, "media_type": mt, "bytes": len(data), "sha256": sha}

    def get(self, name: str) -> "tuple[bytes, str] | None":
        e = self._manifest().get(name)
        if not e:
            return None
        f = self.dir / e["file"]
        return (f.read_bytes(), e["media_type"]) if f.is_file() else None

    def names(self) -> "list[dict]":
        return [{"name": k, "media_type": v["media_type"], "bytes": v["bytes"]} for k, v in sorted(self._manifest().items())]

    def copy_referenced(self, world: dict, dest) -> "list[str]":
        """Only the files this world names; a name the store does not have is skipped (the runtime shows it missing)."""
        dest, got = Path(dest), []
        for n in sorted(refs(world)):
            r = self.get(n)
            if r is None:
                continue
            dest.mkdir(parents=True, exist_ok=True)
            (dest / n).write_bytes(r[0])
            got.append(n)
        return got
