# -*- coding: utf-8 -*-
"""python3 -m worldengine <command>     (run from engine/, or with engine/ on PYTHONPATH)

    example --list                       bundled scenes
    example <name> [--views aerial,eye]  render a bundled scene, e.g. hongdae/F1, store_module/tobe
    layout <file.json> [--key K]         your own layout file (for multiple floors, --key picks the floor)

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
    a = ap.parse_args(argv)
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


if __name__ == "__main__":
    sys.exit(main())
