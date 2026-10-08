# -*- coding: utf-8 -*-
"""python3 -m worldengine <command>     (run from engine/, or with engine/ on PYTHONPATH)

    example --list                       bundled scenes
    example <name> [--views aerial,eye]  render a bundled scene, e.g. hongdae/F1, store_module/tobe
    layout <file.json> [--key K]         your own layout file (for multiple floors, --key picks the floor)
    world <file.world.json|example:NAME> [--views aerial,eye] [--mode orbit|walk] [--eye adult|child]
                                         render a world through the modular runtime (engine/runtime)
    serve [--port 8000] [--host 0.0.0.0] serve engine/ so a phone or PC on the same network can open the runtime
    draw [--urdf U] [--svg F --scale S --center X,Y] [--views aerial,top] [--save-world]
                                         drawing robot: plan, verify (V-16), write a world, render it mid-drawing and done

Common: --out DIR (default engine/build), --w/--h (PNG size), --no-browser (skip headless rendering).
Prints "산출물: <path>" lines and a "=== 보고 ===" summary that names the backend of every image.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
OUT = ENGINE / "build"


def _summary_md(title: str, r: dict) -> str:
    L = ["# " + title, "", "- 충실도: %s" % r.get("fidelity", "미표기"),
         "- 평면: %s" % (Path(r["plan"]).name if r.get("plan") else "없음 — " + r.get("plan_reason", "")),
         "- 인터랙티브 3D: `%s` (브라우저로 열면 궤도 회전)" % Path(r["html"]).name]
    for k, v in r["views"].items():
        L.append("- 시점 `%s`: **%s**%s" % (k, v["backend"], (" — " + v["reason"]) if v["reason"] else ""))
    if r.get("area"):
        L += ["", "| 용도 | 면적(m²) |", "|---|---|"] + ["| %s | %.1f |" % (k, v) for k, v in r["area"].items() if v > 0]
    L += [""] + ["![%s](%s)" % (k, Path(v["png"]).name) for k, v in r["views"].items() if v.get("png")]
    return "\n".join(L) + "\n"


def _emit(title: str, out: Path, stem: str, r: dict) -> None:
    md = out / (stem + ".md")
    md.write_text(_summary_md(title, r), encoding="utf-8")
    files = [md, r["html"]] + ([r["plan"]] if r.get("plan") else []) + [v["png"] for v in r["views"].values() if v.get("png")]
    for p in files:
        print("산출물:", p)
    print("=== 보고 ===")
    print("%s — 3D %d장 · HTML 1 · 충실도 %s" % (title, sum(1 for v in r["views"].values() if v.get("png")), r.get("fidelity", "미표기")))
    print("백엔드: " + ", ".join(r["backend"]))
    if not r.get("plan"):
        print("평면 없음: %s" % r.get("plan_reason", ""))
    for k, v in r["views"].items():
        if not v["backend"].startswith("three.js"):
            print("**%s** %s 시점: %s (%s)" % ("그림 없음" if not v.get("png") else "실사 아님", k, v["backend"], v["reason"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="worldengine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("example", "layout"):
        a = sub.add_parser(name)
        if name == "example":
            a.add_argument("name", nargs="?"); a.add_argument("--list", action="store_true")
        else:
            a.add_argument("file"); a.add_argument("--key")
        a.add_argument("--views", default="aerial,eye")
        a.add_argument("--out", default=str(OUT))
        a.add_argument("--w", type=int, default=1600); a.add_argument("--h", type=int, default=1000)
        a.add_argument("--no-browser", action="store_true")
    a = sub.add_parser("world"); a.add_argument("src"); a.add_argument("--views", default="aerial,eye")
    a.add_argument("--mode", default="orbit", choices=["orbit", "walk"]); a.add_argument("--eye")
    a.add_argument("--out", default=str(OUT)); a.add_argument("--w", type=int, default=1280); a.add_argument("--h", type=int, default=800)
    a = sub.add_parser("serve"); a.add_argument("--port", type=int, default=8000); a.add_argument("--host", default="0.0.0.0")
    a = sub.add_parser("draw"); a.add_argument("--urdf", default=str(ENGINE.parent / "kinematics" / "planar_3_dof.urdf"))
    a.add_argument("--svg"); a.add_argument("--scale", type=float, default=0.001, help="m per SVG unit")
    a.add_argument("--center", default="1.9,0"); a.add_argument("--views", default="aerial,top")
    a.add_argument("--out", default=str(OUT)); a.add_argument("--w", type=int, default=1280); a.add_argument("--h", type=int, default=800)
    a.add_argument("--save-world", action="store_true", help="also write worlds/drawing_robot.world.json")
    a = ap.parse_args(argv)
    if a.cmd == "draw":
        return _draw(a)
    if a.cmd == "world":
        return _world(a)
    if a.cmd == "serve":
        return _serve(a)
    from worldengine import layout as LY, pipeline

    if a.cmd == "example":
        ex = LY.examples()
        if a.list or not a.name:
            print("\n".join(sorted(ex))); return 0
        if a.name not in ex:
            print("모르는 예제: %s (있는 것: %s)" % (a.name, ", ".join(sorted(ex)))); return 2
        L, stem = ex[a.name], a.name.replace("/", "_")
    else:
        d = json.loads(Path(a.file).read_text(encoding="utf-8"))
        L = d[a.key] if a.key else (d if "items" in d else d[sorted(d)[0]])
        stem = Path(a.file).stem + ("_" + a.key if a.key else "")
    sc = LY.to_scene(L)
    out = Path(a.out)
    r = pipeline.run(sc, out, stem, views=[v for v in a.views.split(",") if v], w=a.w, h=a.h,
                     try_browser=False if a.no_browser else None)
    _emit(sc["name"], out, stem, r)
    return 0


def _world(a) -> int:
    from worldengine import headless, layout as LY, world as WD
    if a.src.startswith("example:"):
        w, stem = WD.from_scene(LY.to_scene(LY.examples()[a.src[8:]])), a.src[8:].replace("/", "_")
    else:
        w, stem = WD.load(a.src), Path(a.src).name.split(".")[0]
    bad = WD.check(w)
    if bad:
        print("세계 파일 오류:\n  " + "\n  ".join(bad)); return 2
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    print("산출물:", WD.save(w, out / (stem + ".world.json")))
    backends = set()
    for v in [x for x in a.views.split(",") if x]:
        png = out / ("%s_%s_%s.png" % (stem, a.mode, v))
        r = headless.render_world(w, png, view=v, w=a.w, h=a.h, mode=a.mode, eye=a.eye)
        backends.add(r["backend"])
        print(("산출물: %s" % png) if r["ok"] else "**그림 없음** %s: %s" % (v, r["reason"]))
    print("=== 보고 ===")
    print("%s — 런타임 렌더 · 모드 %s · 백엔드: %s" % (w["name"], a.mode, ", ".join(sorted(backends))))
    return 0


def _draw(a) -> int:
    from worldengine import draw as D, headless, robot as RB, world as WD
    ch = RB.load_chain(a.urdf)
    c = [float(x) for x in a.center.split(",")]
    if a.svg:
        raw = D.svg_path(" ".join(__import__("re").findall(r'\sd="([^"]+)"', Path(a.svg).read_text(encoding="utf-8"))))
        xs = [p[0] for s in raw for p in s]; ys = [p[1] for s in raw for p in s]
        mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        strokes = [[[c[0] + (x - mx) * a.scale, c[1] - (y - my) * a.scale] for x, y in s] for s in raw]   # SVG y is down
    else:
        strokes = D.demo_strokes(tuple(c))
    q0, err = D.home(ch, [c[0], c[1], 0.0], [-0.6, 0.7, 0.6][:len(RB.active(ch))] + [0.0] * max(0, len(RB.active(ch)) - 3))
    p = D.plan(ch, strokes, {"origin": [0, 0, 0], "u": [1, 0, 0], "v": [0, 1, 0]}, q_home=q0)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    stem = "draw_" + (Path(a.svg).stem if a.svg else "demo")
    w = D.world(p)
    bad = WD.check(w)
    if bad:
        print("세계 파일 오류:", bad); return 2
    md = out / (stem + "_V16.md"); md.write_text(D.report_md(p, stem), encoding="utf-8")
    print("산출물:", WD.save(w, out / (stem + ".world.json"))); print("산출물:", md)
    if a.save_world:
        print("산출물:", WD.save(w, ENGINE / "worlds" / "drawing_robot.world.json"))
    dur = p["verify"]["duration_s"]
    for v in [x for x in a.views.split(",") if x]:
        for frac in (0.5, 1.0):
            png = out / ("%s_%s_%02d.png" % (stem, v, int(frac * 100)))
            r = headless.render_world(w, png, view=v, w=a.w, h=a.h, t=dur * frac)
            print(("산출물: %s" % png) if r["ok"] else "**그림 없음** %s: %s" % (v, r["reason"]))
    print("=== 보고 ===")
    print(md.read_text(encoding="utf-8"))
    return 0 if p["verify"]["pass"] else 1


def _serve(a) -> int:
    import functools
    import http.server
    import socket
    ip = "127.0.0.1"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]   # no packet is sent; picks the LAN interface
    except OSError:
        pass
    worlds = sorted(p.name for p in (ENGINE / "worlds").glob("*.world.json"))
    print("engine/ 을 서빙한다. 같은 네트워크의 휴대폰·PC 브라우저에서:")
    for wname in worlds:
        print("  http://%s:%d/runtime/index.html?world=../worlds/%s" % (ip, a.port, wname))
    print("(Ctrl+C 로 종료)")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ENGINE))
    with http.server.ThreadingHTTPServer((a.host, a.port), handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
