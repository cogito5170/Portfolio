# -*- coding: utf-8 -*-
"""Static site: runtime + vendored three.js + worlds + a landing page, all relative paths, no server code (XR-06).

    build(out_dir) -> {"out", "worlds": [{"file", "name", "url"}]}
    smoke(out_dir) -> [{"file", "ok", "reason"}]          # loads every world from the built folder in headless Chromium

Any static host works (GitHub Pages, a USB stick + `python3 -m http.server`). Opening index.html from file://
does not: browsers block module scripts and fetch() there.
"""
from __future__ import annotations

import html
import json
import shutil
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent

_PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>World Platform — 작품 목록</title>
<style>
:root{--bg:#f4f1ea;--ink:#1f2328;--sub:#5b616b;--card:#ffffff;--line:#e3dfd6;--accent:#1b6ef3}
@media (prefers-color-scheme:dark){:root{--bg:#15171b;--ink:#e8e6e1;--sub:#a3a8b0;--card:#1e2126;--line:#2c3036;--accent:#7aa7ff}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Noto Sans KR",system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px}p.lead{color:var(--sub);margin:0 0 20px}
a.card{display:block;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:0 0 12px;color:inherit;text-decoration:none}
a.card:active,a.card:hover{border-color:var(--accent)}
.card b{font-size:17px}.card .about{color:var(--sub);font-size:14px;margin-top:4px}.card .meta{font-size:13px;color:var(--accent);margin-top:6px}
footer{color:var(--sub);font-size:13px;margin-top:24px}
</style></head><body><main>
<h1>World Platform</h1>
<p class="lead">링크를 누르면 브라우저에서 바로 열린다. PC: 끌기·WASD, 휴대폰: 손가락·조이스틱.</p>
__CARDS__
<footer>three.js r170 (MIT) · 생성: python3 -m worldengine site</footer>
</main></body></html>
"""


def build(out_dir) -> dict:
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(ENGINE / "runtime", out / "runtime", ignore=shutil.ignore_patterns("tests"))
    shutil.copytree(ENGINE / "vendor" / "three", out / "vendor" / "three")
    (out / "worlds").mkdir()
    worlds, cards = [], []
    for f in sorted((ENGINE / "worlds").glob("*.world.json")):
        w = json.loads(f.read_text(encoding="utf-8"))
        shutil.copy(f, out / "worlds" / f.name)
        url = "runtime/index.html?world=../worlds/%s%s" % (f.name, "&card=1" if w.get("concepts") else "")
        worlds.append({"file": f.name, "name": w["name"], "url": url})
        v16 = (w.get("verify") or {}).get("V-16")
        meta = ("V-16 %s · 획 오차 최대 %.3f mm" % ("통과" if v16["pass"] else "실패", v16["stroke_err_max_m"] * 1e3)) if v16 else ""
        if w.get("concepts"):
            meta += (" · " if meta else "") + "개념: " + ", ".join(c["title"] for c in w["concepts"])
        cards.append('<a class="card" href="%s"><b>%s</b><div class="about">%s</div>%s</a>' % (
            html.escape(url), html.escape(w["name"]), html.escape(w.get("about", "")),
            '<div class="meta">%s</div>' % html.escape(meta) if meta else ""))
    (out / "index.html").write_text(_PAGE.replace("__CARDS__", "\n".join(cards)), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")       # GitHub Pages: serve files as they are
    (out / "site.json").write_text(json.dumps({"worlds": worlds}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"out": str(out), "worlds": worlds}


def smoke(out_dir, w: int = 390, h: int = 844) -> "list[dict]":
    """Load every listed world from the built folder exactly as a visitor would (same relative URL)."""
    from worldengine import headless
    out = Path(out_dir)
    res = []
    for wd in json.loads((out / "site.json").read_text(encoding="utf-8"))["worlds"]:
        with tempfile.TemporaryDirectory() as d:
            r = headless._shoot(out, wd["url"] + "&headless=1&w=%d&h=%d" % (w, h), Path(d) / "s.png", w, h, 120)
        res.append({"file": wd["file"], "ok": r["ok"], "reason": r["reason"]})
    return res
