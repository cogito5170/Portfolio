# -*- coding: utf-8 -*-
"""Scene -> {scene.json, plan.png?, page.html, view PNGs}. **The backend used is recorded per view.**

    r = run(scene, out_dir, "hongdae_F1", views=["aerial", "eye"])
    r["views"]["aerial"] == {"png": ".../hongdae_F1_aerial.png", "backend": "three.js r170 · headless chromium (CLI)", "reason": ""}
                         or {"png": ".../hongdae_F1_aerial.png", "backend": "matplotlib 대체(비실사)", "reason": "<why no browser>"}
                         or {"png": None, "backend": "없음", "reason": "<why no browser>; <why no matplotlib>"}

Why the backend is recorded: a matplotlib picture reported as a photoreal render is a false green, and a
missing picture reported as rendered is worse. The reader must be able to see which one it is.
"""
from __future__ import annotations

import os
from pathlib import Path

from worldengine import html as HTML
from worldengine import scene as S

FALLBACK = "matplotlib 대체(비실사)"
NONE = "없음"


def _why(e: BaseException) -> str:
    return "%s: %s" % (type(e).__name__, (str(e).splitlines() or [""])[0][:160])


def run(sc: dict, out_dir, stem: str, views=None, w: int = 1600, h: int = 1000, try_browser: "bool | None" = None) -> dict:
    """try_browser=None: follow the environment. WE_NO_BROWSER=1 skips the browser (fast path); the result then says so."""
    if try_browser is None:
        try_browser = os.environ.get("WE_NO_BROWSER") != "1"
    bad = S.check(sc)
    if bad:
        raise ValueError("invalid scene: " + "; ".join(bad[:5]))
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    r = {"scene": S.save(sc, out / (stem + ".scene.json")), "views": {}, "fidelity": sc.get("fidelity", "미표기"),
         "plan": None, "plan_reason": ""}
    try:
        from worldengine import plan
        r["plan"] = plan.render(sc, out / (stem + "_plan.png"))
    except ImportError as e:                         # matplotlib is optional; say it is missing
        r["plan_reason"] = _why(e)
    r["html"] = HTML.write(sc, out / (stem + ".html"))
    names = list(views or [v for v in ("aerial", "eye", "onboard") if v in sc.get("views", {})] or ["aerial"])
    for v in names:
        png = out / ("%s_%s.png" % (stem, v))
        rr = {"ok": False, "reason": "브라우저 시도 안 함"}
        if try_browser:
            from worldengine import headless
            rr = headless.render(r["html"], png, view=v, w=w, h=h)
        if rr.get("ok"):
            r["views"][v] = {"png": str(png), "backend": rr["backend"], "reason": ""}
            continue
        try:
            from worldengine import mpl3d
            mpl3d.render(sc, png, view=v)
            r["views"][v] = {"png": str(png), "backend": FALLBACK, "reason": rr.get("reason", "")}
        except ImportError as e:
            r["views"][v] = {"png": None, "backend": NONE, "reason": "%s; %s" % (rr.get("reason", ""), _why(e))}
    r["backend"] = sorted({x["backend"] for x in r["views"].values()})
    if sc.get("boxes") and sc.get("shell"):
        from worldengine import layout
        try:
            r["area"] = layout.area_program(sc)
        except ImportError as e:                     # numpy is optional too
            r["area_reason"] = _why(e)
    return r
