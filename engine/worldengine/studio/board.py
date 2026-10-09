# -*- coding: utf-8 -*-
"""Variant board (D-01..D-04): one page per variant set -- each variant side by side with its interpretation, the
"what changes" summary against the base version, measured axes of a quick image preview, a 3D view (when a
browser is available), a floor plan with an area table and the area change against the base (D-02), and its
recipe (base version + world hash + generator recipe).

    html = board.build(session, "v1", out_dir, render=True)
"""
from __future__ import annotations

import base64
import html
import tempfile
from pathlib import Path

from worldengine import footprint as FP, headless, measure as MS, plugins as PL
from worldengine.studio import diff as DF

AX = ["density", "colour", "form", "texture", "motion", "sound", "narrative"]


def build(s, set_id: str, out_dir=None, render: bool = True) -> str:
    vs = next(v for v in s.variant_sets if v["id"] == set_id)
    base = s.versions[vs["base"]]["world"]
    base_area = FP.area_table(base)
    img = PL.discover()["image_svg"]
    cols = []
    for pid in vs["proposals"]:
        p = s.proposals[pid]
        w = p["world"]
        prev = PL.generate(img, w, enforce=False)           # the board shows rule breaks as review items, it does not hide the variant
        m = MS.axes(prev["artifact"])
        shot = ""
        if render and headless.available()[0]:
            with tempfile.TemporaryDirectory() as d:
                r = headless.render_world(w, Path(d) / "v.png", view="aerial", w=480, h=300, timeout_s=120)
                if r["ok"]:
                    shot = '<img alt="3D" src="data:image/png;base64,%s">' % base64.b64encode((Path(d) / "v.png").read_bytes()).decode()
                else:
                    shot = '<p class="no">3D 없음: %s</p>' % html.escape(r["reason"])
        wa = (w.get("rules") or {}).get("axes") or {}
        ba = (base.get("rules") or {}).get("axes") or {}
        at, bt = FP.area_table(w), base_area
        area = "<table><tr><th>면적 m²</th><th>지금</th><th>시안</th></tr>%s</table>" % "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (html.escape(lbl), _a(bt[k]), "<b>%s</b>" % _a(at[k]) if at[k] != bt[k] else _a(at[k]))
            for lbl, k in (("몸이 덮은 바닥 (겹침 한 번)", "covered_m2"), ("몸 바닥 합 (겹침 두 번)", "sum_m2"), ("바닥면", "floors_m2"), ("부지", "site_m2")))
        area += "".join('<div class="st">%s %d개 · %s m²</div>' % (html.escape(t), v["count"], _a(v["area_m2"])) for t, v in at["by_type"].items())
        rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            DF.AXIS_KO.get(a, a), _f(ba.get(a)), "<b>%s</b>" % _f(wa.get(a)) if wa.get(a) != ba.get(a) else _f(wa.get(a)), _f(m.get(a))) for a in AX)
        cols.append("""<section><h2>%s</h2><p class="why">%s</p><ul>%s</ul>%s
<div class="svg">%s</div><div class="svg">%s</div>%s
<table><tr><th>축</th><th>지금</th><th>시안</th><th>미리보기 측정</th></tr>%s</table>
<details><summary>레시피 (D-03)</summary><pre>%s</pre></details><p class="st">상태: %s%s</p></section>""" % (
            html.escape(p.get("label", pid)), html.escape(p["why"]), "".join("<li>%s</li>" % html.escape(x) for x in DF.summary_ko(p["diff"])),
            shot, prev["artifact"].replace("<svg ", '<svg style="width:100%;height:auto" ', 1),
            FP.plan_svg(w).replace("<svg ", '<svg role="img" aria-label="평면도" style="width:100%;height:auto" ', 1), area, rows,
            html.escape("기준 판: %d\n세계 해시: %s\n미리보기 레시피: %s" % (vs["base"], prev["recipe"]["world_hash"], prev["recipe"])),
            {"pending": "고르는 중", "applied": "적용됨", "rejected": "버림"}[p["status"]],
            html.escape(" · 검토 필요: 미리보기가 규칙 %d개를 어긴다 (%s)" % (len(prev["rules"]["violations"]), ", ".join(sorted({x["kind"] for x in prev["rules"]["violations"]}))))
            if prev["rules"]["violations"] else ""))
    page = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>시안 비교 보드</title><style>
:root{--bg:#f4f1ea;--ink:#1f2328;--sub:#5b616b;--card:#fff;--line:#e3dfd6}
@media (prefers-color-scheme:dark){:root{--bg:#15171b;--ink:#e8e6e1;--sub:#a3a8b0;--card:#1e2126;--line:#2c3036}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Noto Sans KR",system-ui,sans-serif}
main{padding:16px;display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
h1{font-size:18px;margin:16px 16px 0}p.lead{margin:4px 16px 0;color:var(--sub)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;min-width:0}
h2{font-size:16px;margin:0 0 4px}.why{color:var(--sub);margin:0 0 6px}img{width:100%;border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}td,th{border-bottom:1px solid var(--line);padding:2px 4px;text-align:left}
pre{white-space:pre-wrap;font-size:11px}.no{color:#b00}.st{font-size:13px;color:var(--sub)}
</style></head><body><h1>시안 비교 보드 — __SET__</h1><p class="lead">__WHY__</p><main>__COLS__</main></body></html>"""
    page = page.replace("__SET__", html.escape(set_id)).replace("__WHY__", html.escape(vs["why"])).replace("__COLS__", "".join(cols))
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / ("board_%s.html" % set_id)).write_text(page, encoding="utf-8")
    return page


def _a(v):
    return "—" if v is None else "%.2f" % v


def _f(v):
    return "—" if v is None else "%.2f" % v
