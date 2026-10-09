# -*- coding: utf-8 -*-
"""Preservation bundle (SPEC N-06): one zip that plays and regenerates a work years later, with the versions that
made it -- not with whatever the engine has become.

    r = bundle(world, "work.zip", assets=None)     -> {"ok", "zip", "files", "bytes", "works"}
    r = replay("work.zip")                          -> {"ok", "integrity", "works": [{"plugin", "identical"}], "engine": <where the code ran from>}

Inside (mirrors the repository, so the code runs as it did):
  index.html                      opens the work in the bundled runtime (any static server; no network needed)
  work/world.json                 the world, byte for byte;  work/works/*  the generated works;  work/works.json
  work/assets/*                   the imported files this world names (only those), when a store is given
  engine/worldengine/             the Python core that made the works (generator wrapper, rules, recipes)
  engine/plugins/<name>/          the plugins this world uses, as they were
  engine/runtime/, engine/vendor/three/   the visitor runtime and three.js (with its MIT notice)
  kinematics/                     the reference kinematics the robot plugins use
  LICENSES.md                     what the work is made of (R-03)
  MANIFEST.json                   sha256 of every file, plugin versions, recipes, engine commit, Python version
  replay.py                       checks every hash, then regenerates every work with the BUNDLED code and compares
"""
from __future__ import annotations

import datetime
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
REPO = ENGINE.parent
FORMAT = "bundle/1"

REPLAY = r'''# -*- coding: utf-8 -*-
"""Replay this bundle: python3 replay.py   (standard library only; runs the bundled engine, not an installed one)."""
import hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "engine"))
m = json.loads((HERE / "MANIFEST.json").read_text(encoding="utf-8"))
bad = [p for p, h in m["files"].items() if hashlib.sha256((HERE / p).read_bytes()).hexdigest() != h]
import worldengine, worldengine.plugins as PL
world = json.loads((HERE / "work" / "world.json").read_text(encoding="utf-8"))
P = PL.discover()
works = []
for w in m["works"]:
    r = PL.regenerate(P[w["plugin"]], w["recipe"], world, enforce=False)
    data = r["artifact"].encode("utf-8") if isinstance(r["artifact"], str) else r["artifact"]
    works.append({"plugin": w["plugin"], "identical": hashlib.sha256(data).hexdigest() == w["recipe"]["artifact_sha256"]})
out = {"ok": not bad and all(x["identical"] for x in works), "integrity": {"files": len(m["files"]), "changed": bad},
       "works": works, "engine": str(Path(worldengine.__file__).resolve().parent), "python": sys.version.split()[0]}
print(json.dumps(out, ensure_ascii=False))
sys.exit(0 if out["ok"] else 1)
'''

INDEX = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__ — 보존 묶음</title><style>:root{--bg:#f4f1ea;--ink:#1f2328;--sub:#5b616b}@media (prefers-color-scheme:dark){:root{--bg:#15171b;--ink:#e8e6e1;--sub:#a3a8b0}}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--ink);font:16px/1.6 "Noto Sans KR",system-ui,sans-serif;max-width:640px}
a{display:block;min-height:44px;line-height:44px}p{color:var(--sub)}</style></head><body>
<h1>__NAME__</h1><p>보존 묶음 (N-06) · __DATE__ · 엔진 __COMMIT__</p>
<a href="engine/runtime/index.html?world=../../work/world.json&amp;works=../../work/works.json__ASSETS__">작품 열기</a>
<a href="engine/runtime/index.html?world=../../work/world.json&amp;works=../../work/works.json__ASSETS__&amp;player=1">전시 모드로 열기</a>
<p>정적 서버로 연다 (예: 이 폴더에서 <code>python3 -m http.server</code>). 결과물 다시 만들기: <code>python3 replay.py</code>.</p>
</body></html>"""


def _commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _copy(src: Path, dst: Path):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))


def bundle(world, out_zip, assets=None) -> dict:
    from worldengine import licenses as LC, plugins as PL, works as WK, world as WD
    w = world if isinstance(world, dict) else json.loads(Path(world).read_text(encoding="utf-8"))
    bad = WD.check(w)
    if bad:
        return {"ok": False, "reason": "세계 형식 오류: " + "; ".join(bad[:3])}
    P = PL.discover()
    used = sorted({e.get("plugin") for e in w.get("expressions") or [] if e.get("plugin")})
    missing = [n for n in used if n not in P]
    if missing:
        return {"ok": False, "reason": "이 기계에 없는 플러그인: " + ", ".join(missing)}
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "b"
        (root / "work" / "works").mkdir(parents=True)
        (root / "engine" / "plugins").mkdir(parents=True)
        (root / "work" / "world.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
        _copy(ENGINE / "worldengine", root / "engine" / "worldengine")
        _copy(ENGINE / "runtime", root / "engine" / "runtime")
        _copy(ENGINE / "vendor" / "three", root / "engine" / "vendor" / "three")
        _copy(REPO / "kinematics", root / "kinematics")
        for n in used:
            _copy(Path(P[n]["path"]).parent, root / "engine" / "plugins" / n)
        items, works = WK.render(w, P), []
        for it in items:
            if it["ok"]:
                f = "%d_%s.%s" % (it["index"], it["plugin"], WK.EXT.get(it["media_type"], "bin"))
                data = it["artifact"].encode("utf-8") if isinstance(it["artifact"], str) else it["artifact"]
                (root / "work" / "works" / f).write_bytes(data)
                works.append({"plugin": it["plugin"], "file": "work/works/" + f, "recipe": it["recipe"]})
        (root / "work" / "works.json").write_text(json.dumps(WK.index(items, lambda it: "works/%d_%s.%s" % (it["index"], it["plugin"], WK.EXT.get(it["media_type"], "bin"))),
                                                             ensure_ascii=False, indent=1), encoding="utf-8")
        copied = assets.copy_referenced(w, root / "work" / "assets") if assets is not None else []
        (root / "LICENSES.md").write_text(LC.markdown(LC.for_world(w), "이 작품의 라이선스 표 (R-03)"), encoding="utf-8")
        (root / "replay.py").write_text(REPLAY, encoding="utf-8")
        date, commit = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"), _commit()
        (root / "index.html").write_text(INDEX.replace("__NAME__", w["name"]).replace("__DATE__", date).replace("__COMMIT__", commit[:12])
                                         .replace("__ASSETS__", "&amp;assets=..%2F..%2Fwork%2Fassets%2F%7Bname%7D" if copied else ""), encoding="utf-8")
        files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}
        manifest = {"format": FORMAT, "created": date, "engine_commit": commit, "python": platform.python_version(),
                    "world": {"name": w["name"], "version": w.get("version"), "hash": PL.world_hash(w)},
                    "plugins": {n: {"version": P[n]["version"], "sha256": files["engine/plugins/%s/plugin.py" % n]} for n in used},
                    "works": works, "refused": [{"plugin": it["plugin"], "reason": it["reason"]} for it in items if not it["ok"]],
                    "assets": copied, "files": files}
        (root / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        out_zip = Path(out_zip); out_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(root))
    return {"ok": True, "zip": str(out_zip), "files": len(files) + 1, "bytes": out_zip.stat().st_size, "works": len(works), "assets": copied}


def replay(zip_path, keep: "str | None" = None) -> dict:
    """Unpack and run the bundle's own replay.py in a fresh, isolated Python (-I: no site packages, no cwd on path)."""
    d = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="worldengine_replay_"))
    try:
        with zipfile.ZipFile(zip_path) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in Path(n).parts:
                    return {"ok": False, "reason": "묶음 안의 경로가 이상하다: %s" % n}
            z.extractall(d)
        p = subprocess.run([sys.executable, "-I", str(d / "replay.py")], capture_output=True, text=True, timeout=600, cwd=str(d))
        try:
            r = json.loads(p.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"ok": False, "reason": "replay.py 실패: " + (p.stderr or p.stdout)[-400:]}
        r["dir"] = str(d)
        return r
    finally:
        if not keep:
            shutil.rmtree(d, ignore_errors=True)
