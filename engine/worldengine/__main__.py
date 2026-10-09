# -*- coding: utf-8 -*-
"""python3 -m worldengine <command>     (run from engine/, or with engine/ on PYTHONPATH)

    example --list                       bundled scenes
    example <name> [--views aerial,eye]  render a bundled scene, e.g. hongdae/F1, store_module/tobe
    layout <file.json> [--key K]         your own layout file (for multiple floors, --key picks the floor)
    world <file.world.json|example:NAME> [--views aerial,eye] [--mode orbit|walk] [--eye adult|child]
                                         render a world through the modular runtime (engine/runtime)
    serve [--port 8000] [--host 0.0.0.0] serve engine/ so a phone or PC on the same network can open the runtime
    conform [--plugins DIR ...] [--out DIR]   conformance kit (G-05) for every plugin on the reference worlds + V-04 measurement
    generate <world.json> --plugin NAME [--out DIR]   one plugin, one world: artifact + recipe (G-01)
    studio --world W.json --artist NAME [--host 0.0.0.0] [--port 8100]   conversational studio (needs ANTHROPIC_API_KEY for the agent)
    exhibit --world W.json [--host 0.0.0.0] [--port 8200]   show a work to visitors; live character replies if a key is set
    v12 [--yes]                          hidden request set (sealed file via WE_V12_FILE; only its hash is in the repo)
    sandbox-probe                        can this machine isolate agent code? (prints the reason when not)
    combine A.json B.json --bodies MODE [--out F]   contradiction synthesis + recognisability (K-06)
    v13 [--limit N] [--yes]              intent-evaluation run against the real model (costs money: prints the bound first)
    site [--out DIR] [--no-smoke]        static site (runtime + three.js + worlds + landing page); smoke-loads every world
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
    a.add_argument("--concept", default="klee", help="klee (demo concept card) | none | path to a JSON list of concept cards")
    a = sub.add_parser("site"); a.add_argument("--out", default=str(ENGINE / "build" / "site")); a.add_argument("--no-smoke", action="store_true")
    a = sub.add_parser("conform"); a.add_argument("--plugins", nargs="*", default=[]); a.add_argument("--out", default=str(OUT))
    a = sub.add_parser("generate"); a.add_argument("world"); a.add_argument("--plugin", required=True); a.add_argument("--out", default=str(OUT))
    a = sub.add_parser("studio"); a.add_argument("--world", required=True); a.add_argument("--artist", required=True)
    a.add_argument("--host", default="127.0.0.1"); a.add_argument("--port", type=int, default=8100)
    a = sub.add_parser("v13"); a.add_argument("--limit", type=int); a.add_argument("--yes", action="store_true"); a.add_argument("--out", default=str(OUT))
    a = sub.add_parser("exhibit"); a.add_argument("--world", required=True); a.add_argument("--host", default="127.0.0.1"); a.add_argument("--port", type=int, default=8200)
    a.add_argument("--no-presence", action="store_true")
    a = sub.add_parser("gltf"); a.add_argument("world"); a.add_argument("--out", required=True)
    a = sub.add_parser("tour-video"); a.add_argument("world"); a.add_argument("--out", required=True); a.add_argument("--tour")
    a.add_argument("--w", type=int, default=1280); a.add_argument("--h", type=int, default=720); a.add_argument("--fps", type=int, default=24)
    a = sub.add_parser("preserve"); a.add_argument("world"); a.add_argument("--out", required=True)
    a = sub.add_parser("replay"); a.add_argument("bundle")
    a = sub.add_parser("licenses"); a.add_argument("world", nargs="?")
    a = sub.add_parser("urdf"); a.add_argument("world"); a.add_argument("--out", required=True); a.add_argument("--id")
    a = sub.add_parser("v12"); a.add_argument("--yes", action="store_true")
    a = sub.add_parser("sandbox-probe")
    a = sub.add_parser("combine"); a.add_argument("a"); a.add_argument("b"); a.add_argument("--bodies", default="juxtapose", choices=["juxtapose", "layer", "seam", "viewpoint"]); a.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "sandbox-probe":
        from worldengine import sandbox
        ok, why = sandbox.available()
        print(json.dumps({"sandbox_available": ok, "reason": why}, ensure_ascii=False))
        return 0
    if a.cmd == "combine":
        from worldengine import combine as KB, world as WD
        A, B = WD.load(a.a), WD.load(a.b)
        C = KB.combine(A, B, {"bodies": a.bodies})
        print(json.dumps(KB.recognisability(C, A, B), ensure_ascii=False))
        if a.out:
            print("산출물:", WD.save(C, a.out))
        return 0
    if a.cmd == "v12":
        from worldengine import hidden
        from worldengine.studio import server
        st = hidden.load_sealed()
        if st["status"] != "ok":
            print("V-12: %s — %s (숫자 없음)" % (st["status"], st["detail"])); return 2
        if not a.yes:
            print("봉인 세트 %d개 확인. 비용이 드는 실행이다: --yes 로 실행한다." % len(st["items"])); return 2
        client, why = server.make_client()
        if client is None:
            print("실행 못 함:", why); return 2
        print(json.dumps(hidden.run(lambda: client), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "exhibit":
        from worldengine import exhibit, world as WD
        exhibit.serve(WD.load(a.world), a.host, a.port, presence=not a.no_presence)
        return 0
    if a.cmd == "tour-video":
        from worldengine import video
        r = video.tour_video(a.world, a.out, a.tour, a.w, a.h, a.fps)
        print(json.dumps({k: v for k, v in r.items() if k != "captions"}, ensure_ascii=False))
        return 0 if r["ok"] else 1
    if a.cmd == "preserve":
        from worldengine import preserve
        r = preserve.bundle(a.world, a.out)
        print(json.dumps(r, ensure_ascii=False)); return 0 if r["ok"] else 1
    if a.cmd == "replay":
        from worldengine import preserve
        r = preserve.replay(a.bundle)
        print(json.dumps(r, ensure_ascii=False)); return 0 if r.get("ok") else 1
    if a.cmd == "licenses":
        from worldengine import licenses as LC, world as WD
        print(LC.markdown(LC.for_world(WD.load(a.world)) if a.world else LC.table(), "라이선스 표 (R-03)" + (" — " + a.world if a.world else "")))
        return 0
    if a.cmd == "urdf":
        from worldengine import robot as RB, world as WD
        arms = [e for e in WD.load(a.world).get("entities") or [] if e.get("type") == "robot.arm" and (a.id is None or e.get("id") == a.id)]
        if not arms:
            print("이 세계에 로봇 팔이 없다" + (" (id %s)" % a.id if a.id else "")); return 2
        Path(a.out).write_text(RB.to_urdf(arms[0]["chain"]), encoding="utf-8")
        print("URDF:", a.out, "(관절 %d개, 운동학만)" % len(arms[0]["chain"]["joints"]))
        return 0
    if a.cmd == "gltf":
        from worldengine import gltf
        r = gltf.export(a.world, a.out)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r["ok"] else 1
    if a.cmd == "studio":
        from worldengine import world as WD
        from worldengine.studio import server
        server.serve(WD.load(a.world), a.artist, a.host, a.port)
        return 0
    if a.cmd == "v13":
        return _v13(a)
    if a.cmd == "conform":
        return _conform(a)
    if a.cmd == "generate":
        from worldengine import plugins as PL, world as WD
        w, p = WD.load(a.world), PL.discover()[a.plugin]
        r = PL.generate(p, w)
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        stem = "%s_%s" % (Path(a.world).name.split(".")[0], a.plugin)
        ext = {"image/svg+xml": ".svg"}.get(r["media_type"], ".bin")
        art = out / (stem + ext)
        (art.write_text if isinstance(r["artifact"], str) else art.write_bytes)(r["artifact"])
        (out / (stem + ".recipe.json")).write_text(json.dumps(r["recipe"], ensure_ascii=False, indent=1), encoding="utf-8")
        print("산출물:", art); print("산출물:", out / (stem + ".recipe.json"))
        print("=== 보고 ===\n%s · %s" % (r["media_type"], r.get("notes", "")))
        return 0
    if a.cmd == "site":
        from worldengine import site
        r = site.build(a.out)
        print("산출물:", r["out"])
        bad = []
        if not a.no_smoke:
            for s_ in site.smoke(a.out):
                print("%s %s%s" % ("열림" if s_["ok"] else "**안 열림**", s_["file"], "" if s_["ok"] else " — " + s_["reason"]))
                bad += [] if s_["ok"] else [s_["file"]]
        print("=== 보고 ===")
        print("작품 %d개 · 스모크 %s" % (len(r["worlds"]), "생략" if a.no_smoke else ("모두 열림" if not bad else "실패 %d" % len(bad))))
        return 1 if bad else 0
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


REFERENCE = ("ref_yeobaek", "ref_festival_baroque", "ref_modulor")


def _v13(a) -> int:
    from worldengine.studio import config, server, v13
    data = v13.load()
    items = data["items"][: a.limit] if a.limit else data["items"]
    b = v13.bound(len(items))
    print("세트:", data["label"])
    print("모델 %s · 항목 %d · 요청 상한 %d · 출력 토큰 상한 %d (WE_MAX_TURNS=%d, WE_MAX_TOKENS=%d). 입력 토큰은 실행 후 실측해 보고한다."
          % (config.model(), b["items"], b["max_requests"], b["max_output_tokens"], config.MAX_TURNS, config.MAX_TOKENS))
    if not a.yes:
        print("비용이 드는 실행이다. 위 상한을 확인했으면 --yes 를 붙여 다시 실행한다."); return 2
    client, why = server.make_client()
    if client is None:
        print("실행 못 함:", why); return 2
    rows = v13.run(items, lambda: client)
    ok = sum(r["ok"] for r in rows)
    tin = sum(r["usage"]["input_tokens"] for r in rows); tout = sum(r["usage"]["output_tokens"] for r in rows)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rep = out / "v13_run.json"
    rep.write_text(json.dumps({"label": data["label"], "model": config.model(), "rows": rows, "input_tokens": tin, "output_tokens": tout}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("산출물:", rep); print("=== 보고 ===")
    for r in rows:
        print("%s %s %s %s" % ("맞음" if r["ok"] else "틀림", r["id"], r["tools"], "; ".join(r["why"])))
    print("범위 안 해석 %d/%d (개발자 작성 시드 세트 기준) · 바꿔치기(V-15) %d · 실제 토큰 입력 %d / 출력 %d" % (ok, len(rows), sum(r["substituted"] for r in rows), tin, tout))
    return 0


def _conform(a) -> int:
    from worldengine import conformance as CF, measure as MS, plugins as PL, world as WD
    worlds = {n: WD.load(ENGINE / "worlds" / (n + ".world.json")) for n in REFERENCE}
    P = PL.discover(extra_dirs=a.plugins)
    rows, res = [], []
    for pn, p in P.items():
        rows += CF.run(p, list(worlds.values()))
        res += [{"plugin": pn, "world": n, "svg": PL.generate(p, w)["artifact"]} for n, w in worlds.items() if p["medium"] in ("image", "drawing")]
    d = MS.distinctness(res, worlds)
    L = ["# 적합성 시험 (G-05) · 기준 세계 %d개 · 플러그인 %d개" % (len(worlds), len(P)), "", "| 플러그인 | 세계 | 조항 | 결과 | 내용 |", "|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s |" % (r["plugin"], r["world"], r["clause"], "통과" if r["ok"] else "**실패**", r["detail"]) for r in rows]
    L += ["", "# V-04 첫 측정 (목표 미정)", "", "측정기: `worldengine/measure.py` — 결과물 SVG 만 읽는다, 플러그인을 부르지 않는다. 방법은 그 파일 머리말.", "",
          "| 플러그인 | 세계 | 측정 축 (밀도·색·형태·질감·움직임) | 가장 가까운 세계 | 자기 세계 순위 |", "|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %d |" % (r["plugin"], r["world"], " · ".join("%.2f" % r["measured"][k] for k in MS.MEASURED), r["nearest"], r["own_rank"]) for r in d]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    md = out / "conformance.md"; md.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("산출물:", md); print("=== 보고 ==="); print("\n".join(L))
    return 0 if all(r["ok"] for r in rows) else 1


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
    from worldengine import concept as CP
    concepts = {"klee": [CP.KLEE_WALK], "none": []}.get(a.concept)
    if concepts is None:
        concepts = json.loads(Path(a.concept).read_text(encoding="utf-8"))
    effects, opts, strokes = CP.apply(concepts, "arm", strokes)
    q0, err = D.home(ch, [c[0], c[1], 0.0], [-0.6, 0.7, 0.6][:len(RB.active(ch))] + [0.0] * max(0, len(RB.active(ch)) - 3))
    p = D.plan(ch, strokes, {"origin": [0, 0, 0], "u": [1, 0, 0], "v": [0, 1, 0]}, q_home=q0, opts=opts)
    concept_ok = CP.measure(effects, p["verify"])
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    stem = "draw_" + (Path(a.svg).stem if a.svg else "demo")
    w = D.world(p, concepts=concepts, effects=effects)
    bad = WD.check(w)
    if bad:
        print("세계 파일 오류:", bad); return 2
    md = out / (stem + "_V16.md"); md.write_text(D.report_md(p, stem, effects), encoding="utf-8")
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
    if not concept_ok:
        print("**개념 규칙을 지키지 못했다**: " + ", ".join(e["param"] for e in effects if e["met"] is False))
    return 0 if p["verify"]["pass"] and concept_ok else 1


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
