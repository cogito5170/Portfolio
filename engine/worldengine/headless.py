# -*- coding: utf-8 -*-
"""html.py output -> PNG in headless Chromium. **Without a browser, say so. Do not pretend.**

    render(html_path, png_path, view="aerial", w=1600, h=1000) -> {"ok": bool, "backend": str, "reason": str}

Two backends, tried in order:

1. playwright (as in render3d): waits on window.__done / window.__err, screenshots the canvas.
2. Chromium command line (new in worldengine): for environments with a Chromium binary but no playwright.
   The served page reports its status with console.log("WE_STATUS:..."), which Chromium prints to stderr
   with --enable-logging=stderr; the screenshot is taken after a virtual-time budget.

three.js comes from the vendored copy (engine/vendor/three) unless WE_THREE_DIR points elsewhere, so
rendering works offline and where the CDN is blocked.
"""
from __future__ import annotations

import functools
import glob
import http.server
import os
import re
import shutil
import socketserver
import subprocess
import tempfile
import threading
from pathlib import Path

VENDORED_THREE = Path(__file__).resolve().parent.parent / "vendor" / "three"
_STATUS_JS = """<script>(function poll(){
  if (window.__done === true) { console.log('WE_STATUS:done'); return; }
  if (window.__err !== null && window.__err !== undefined) { console.log('WE_STATUS:err:' + window.__err); return; }
  setTimeout(poll, 50);
})();</script></body>"""


def _chromium() -> "str | None":
    p = os.environ.get("WE_CHROMIUM") or os.environ.get("SE_CHROMIUM")
    if p and os.path.exists(p):
        return p
    # Prefer the headless shell: its viewport is exactly --window-size. The full browser in --headless=new
    # counts invisible window chrome, which left a blank band at the bottom of screenshots.
    for pattern in ("/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell",
                    "/opt/pw-browsers/chromium-*/chrome-linux/chrome"):
        for c in sorted(glob.glob(pattern), reverse=True):
            return c
    for name in ("chromium", "chromium-browser", "google-chrome"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def _three_dir() -> "str | None":
    d = os.environ.get("WE_THREE_DIR") or os.environ.get("SE_THREE_DIR")
    if d and os.path.isdir(d):
        return d
    return str(VENDORED_THREE) if VENDORED_THREE.is_dir() else None


def _has_playwright() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:                              # noqa: BLE001
        return False


def available() -> "tuple[bool, str]":
    """(available?, why). Whether it can actually launch is only known by running render()."""
    if _has_playwright():
        return True, "playwright"
    if _chromium():
        return True, "chromium CLI (%s)" % _chromium()
    return False, "playwright 도 chromium 도 없다"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):                     # keep the server log out of stderr
        pass


def _stage(html_path) -> Path:
    """Copy the page into a temp dir next to a link to three.js, with the importmap pointing at /three/."""
    tmp = Path(tempfile.mkdtemp(prefix="worldengine_"))
    page_html = Path(html_path).read_text(encoding="utf-8")
    three_dir = _three_dir()
    if three_dir:
        os.symlink(os.path.abspath(three_dir), tmp / "three")
        page_html = re.sub(r'"three":"[^"]*build/three\.module\.js","three/addons/":"[^"]*examples/jsm/"',
                           '"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"', page_html)
    (tmp / "index.html").write_text(page_html.replace("</body>", _STATUS_JS, 1), encoding="utf-8")
    return tmp


def render(html_path, png_path, view: str = "aerial", w: int = 1600, h: int = 1000, timeout_s: float = 240.0) -> dict:
    ok, why = available()
    if not ok:
        return {"ok": False, "backend": "없음", "reason": why}
    tmp = _stage(html_path)
    try:
        handler = functools.partial(_Quiet, directory=str(tmp))
        with socketserver.TCPServer(("127.0.0.1", 0), handler) as srv:
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            url = "http://127.0.0.1:%d/index.html?view=%s&w=%d&h=%d&headless=1" % (port, view, w, h)
            try:
                if _has_playwright():
                    return _render_playwright(url, png_path, w, h, timeout_s)
                return _render_cli(url, png_path, w, h, timeout_s)
            finally:
                srv.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


def _render_playwright(url, png_path, w, h, timeout_s) -> dict:
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            kw = {"args": list(_ARGS)}
            if _chromium():
                kw["executable_path"] = _chromium()
            b = pw.chromium.launch(**kw)
            try:
                pg = b.new_page(viewport={"width": w, "height": h})
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(url)
                pg.wait_for_function("window.__done === true || window.__err !== null", timeout=timeout_s * 1000)
                err = pg.evaluate("window.__err") or (errs[0] if errs else None)
                if err and not pg.evaluate("window.__done === true"):
                    return {"ok": False, "backend": "없음", "reason": "페이지 오류: %s" % err[:200]}
                Path(png_path).parent.mkdir(parents=True, exist_ok=True)
                pg.locator("canvas").screenshot(path=str(png_path))
                return {"ok": True, "backend": "three.js r170 · headless chromium (playwright)", "reason": ""}
            finally:
                b.close()
    except Exception as e:                          # noqa: BLE001 -- timeouts etc. are 'not rendered' too
        return {"ok": False, "backend": "없음", "reason": "%s: %s" % (type(e).__name__, str(e).splitlines()[0][:160])}


def _render_cli(url, png_path, w, h, timeout_s) -> dict:
    exe = _chromium()
    Path(png_path).parent.mkdir(parents=True, exist_ok=True)
    out = Path(png_path).resolve()
    if out.exists():
        out.unlink()
    cmd = [exe, "--headless=new", "--no-sandbox", "--hide-scrollbars", *_ARGS,
           "--enable-logging=stderr", "--v=0", "--window-size=%d,%d" % (w, h),
           "--virtual-time-budget=%d" % int(min(timeout_s, 60) * 1000), "--screenshot=%s" % out, url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"ok": False, "backend": "없음", "reason": "chromium 시간 초과 (%ds)" % timeout_s}
    status = re.findall(r'WE_STATUS:([^"]*)"', p.stderr)
    if not status:
        return {"ok": False, "backend": "없음", "reason": "페이지가 완료 신호를 보내지 않았다 (chromium rc=%d)" % p.returncode}
    if status[0].startswith("err:"):
        return {"ok": False, "backend": "없음", "reason": "페이지 오류: %s" % status[0][4:200]}
    if not out.exists() or out.stat().st_size == 0:
        return {"ok": False, "backend": "없음", "reason": "스크린샷 파일이 없다"}
    return {"ok": True, "backend": "three.js r170 · headless chromium (CLI)", "reason": ""}
