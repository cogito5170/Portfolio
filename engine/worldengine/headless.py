# -*- coding: utf-8 -*-
"""Pages -> PNG in headless Chromium. **Without a browser, say so. Do not pretend.**

    render(html_path, png_path, view="aerial", w=1600, h=1000) -> {"ok": bool, "backend": str, "reason": str}
        a single-file page from html.py (legacy renderer)
    render_world(world, png_path, view, w, h, mode="orbit"|"walk", eye=None, t=0, selftest=None) -> same (+ "result")
        a world through the modular runtime (engine/runtime); selftest=<name> returns the page's measurements

Two backends, tried in order:

1. playwright (as in render3d): waits on window.__done / window.__err, screenshots the canvas.
2. Chromium command line (new in worldengine): for environments with a Chromium binary but no playwright.
   The served page reports its status with console.log("WE_STATUS:..."), which Chromium prints to stderr
   with --enable-logging=stderr; the screenshot is taken after a virtual-time budget.

three.js comes from the vendored copy (engine/vendor/three) unless WE_THREE_DIR points elsewhere, so
rendering works offline and where the CDN is blocked.
"""
from __future__ import annotations

import base64
import functools
import glob
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote

VENDORED_THREE = Path(__file__).resolve().parent.parent / "vendor" / "three"
RUNTIME = Path(__file__).resolve().parent.parent / "runtime"
_STATUS_JS = """<script>(function poll(){
  if (window.__done === true) { console.log('WE_VIEWPORT:' + innerWidth + ',' + innerHeight); console.log('WE_STATUS:done'); return; }
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
    """A single-file page from html.py (legacy renderer)."""
    ok, why = available()
    if not ok:
        return {"ok": False, "backend": "없음", "reason": why}
    tmp = _stage(html_path)
    try:
        return _shoot(tmp, "index.html?view=%s&w=%d&h=%d&headless=1" % (view, w, h), png_path, w, h, timeout_s)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_world(world, png_path, view: str = "aerial", w: int = 1280, h: int = 800, mode: str = "orbit",
                 eye: "str | None" = None, t: float = 0.0, selftest: "str | None" = None, timeout_s: float = 240.0,
                 query: "dict | None" = None, page: str = "index.html", assets: "dict | None" = None,
                 real_time_s: "float | None" = None, live: bool = False, fake_media: bool = False) -> dict:
    """A world (dict or path to world JSON) through the modular runtime (engine/runtime). Same honesty rules.
    page="editor.html" opens the same world in the world editor instead of the visitor runtime.
    assets={name: bytes}: imported files this page may read (E-02), served at /assets/<name>.
    real_time_s: run on the wall clock for that long (see render_url) instead of virtual time.
    live=True: run on the wall clock until the page reports, without a screenshot (see run_live).

    With selftest=<name>, the page runs that in-browser test and its measurements come back as r["result"]."""
    ok, why = available()
    if not ok:
        return {"ok": False, "backend": "없음", "reason": why}
    tmp = Path(tempfile.mkdtemp(prefix="worldengine_rt_"))
    try:
        os.symlink(RUNTIME, tmp / "runtime")
        (tmp / "vendor").mkdir()
        os.symlink(os.path.abspath(_three_dir()), tmp / "vendor" / "three")
        data = world if isinstance(world, dict) else json.loads(Path(world).read_text(encoding="utf-8"))
        (tmp / "world.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if assets:
            (tmp / "assets").mkdir()
            for n, b in assets.items():
                (tmp / "assets" / n).write_bytes(b)
            query = {**(query or {}), "assets": quote("/assets/{name}", safe="")}
        q = "runtime/%s?world=/world.json&view=%s&mode=%s&w=%d&h=%d&t=%g&headless=1" % (page, view, mode, w, h, t)
        if eye:
            q += "&eye=" + eye
        if selftest:
            q += "&selftest=" + selftest
        for k, v in (query or {}).items():
            q += "&%s=%s" % (k, v)
        if live:
            handler = functools.partial(_Quiet, directory=str(tmp))
            with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as srv:
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                try:
                    return run_live("http://127.0.0.1:%d/%s" % (srv.server_address[1], q), timeout_s, w, h, fake_media)
                finally:
                    srv.shutdown()
        return _shoot(tmp, q, png_path, w, h, timeout_s, real_time_s)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


FAKE_MEDIA = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"]


def render_url(url: str, png_path, w: int = 640, h: int = 400, timeout_s: float = 120, real_time_s: "float | None" = None,
               fake_media: bool = False) -> dict:
    """A page already served elsewhere (e.g. the exhibit server), same honesty rules and self-test results.
    real_time_s: let the page run on the wall clock for that long instead of Chromium's virtual time (needed when
    the page waits for real network messages, e.g. WebSocket presence -- virtual time would skip the wait).
    fake_media: Chromium's own fake camera and microphone, permission granted (tests of opt-in live inputs, M-03)."""
    ok, why = available()
    if not ok:
        return {"ok": False, "backend": "없음", "reason": why}
    extra = FAKE_MEDIA if fake_media else []
    if _has_playwright():
        return _render_playwright(url, png_path, w, h, timeout_s, extra)
    return _render_cli(url, png_path, w, h, timeout_s, real_time_s, extra)


def run_live(url: str, timeout_s: float = 60, w: int = 640, h: int = 400, fake_media: bool = False) -> dict:
    """The page on the wall clock until it reports WE_STATUS, then the browser is stopped. No screenshot.
    Why: in Chromium's own --timeout mode the page's timers stop once a camera, microphone or audio stream starts
    (measured: a 300 ms setInterval never fires again after getUserMedia), and virtual time never resolves audio
    decoding. Live inputs and recordings are tested this way."""
    ok, why = available()
    if not ok:
        return {"ok": False, "backend": "없음", "reason": why}
    import signal
    cmd = [_chromium(), "--headless=new", "--no-sandbox", "--hide-scrollbars", *_ARGS, *(FAKE_MEDIA if fake_media else []),
           "--enable-logging=stderr", "--v=0", "--window-size=%d,%d" % (w, h), "--remote-debugging-port=0", url]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, start_new_session=True)
    lines, t0 = [], time.monotonic()
    reader = threading.Thread(target=lambda: [lines.append(x) for x in p.stderr], daemon=True)
    reader.start()
    try:
        while time.monotonic() - t0 < timeout_s and not any("WE_STATUS:" in x for x in lines) and p.poll() is None:
            time.sleep(0.05)
        time.sleep(0.3)                                   # let the last console lines arrive
    finally:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.wait(timeout=10)
        reader.join(timeout=5)
        p.stderr.close()
    err = "".join(lines)
    status = re.findall(r'WE_STATUS:(.*?)", source:', err)
    if not status:
        return {"ok": False, "backend": "없음", "reason": "페이지가 %ds 안에 완료 신호를 보내지 않았다 (live)" % timeout_s}
    if status[0].startswith("err:"):
        return {"ok": False, "backend": "없음", "reason": "페이지 오류: %s" % status[0][4:200]}
    r = {"ok": True, "backend": "three.js r170 · headless chromium (live)", "reason": ""}
    res = re.findall(r'WE_RESULT:([A-Za-z0-9+/=]+)"', err)
    parts = re.findall(r'WE_RESULT_PART:(\d+)/(\d+):([A-Za-z0-9+/=]+)"', err)
    if parts:
        n = int(parts[0][1]); got = {int(i): d for i, _, d in parts}
        if sorted(got) != list(range(n)):
            return {"ok": False, "backend": "없음", "reason": "결과 조각이 빠졌다 (%d/%d)" % (len(got), n)}
        res = ["".join(got[i] for i in range(n))]
    if res:
        r["result"] = json.loads(base64.b64decode(res[0]).decode("utf-8"))
    return r


def _shoot(root: Path, rel_url: str, png_path, w, h, timeout_s, real_time_s=None) -> dict:
    handler = functools.partial(_Quiet, directory=str(root))
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as srv:      # parallel requests: matters on the wall clock
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:%d/%s" % (port, rel_url)
        try:
            if _has_playwright():
                return _render_playwright(url, png_path, w, h, timeout_s)
            return _render_cli(url, png_path, w, h, timeout_s, real_time_s)
        finally:
            srv.shutdown()


_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


def _render_playwright(url, png_path, w, h, timeout_s, extra=()) -> dict:
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            kw = {"args": list(_ARGS) + list(extra)}
            if _chromium():
                kw["executable_path"] = _chromium()
            b = pw.chromium.launch(**kw)
            try:
                pg = b.new_page(viewport={"width": w, "height": h})
                errs, logs = [], []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.on("console", lambda m: logs.append(m.text))
                pg.goto(url)
                pg.wait_for_function("window.__done === true || window.__err !== null", timeout=timeout_s * 1000)
                err = pg.evaluate("window.__err") or (errs[0] if errs else None)
                if err and not pg.evaluate("window.__done === true"):
                    return {"ok": False, "backend": "없음", "reason": "페이지 오류: %s" % err[:200]}
                Path(png_path).parent.mkdir(parents=True, exist_ok=True)
                pg.screenshot(path=str(png_path))
                r = {"ok": True, "backend": "three.js r170 · headless chromium (playwright)", "reason": ""}
                for line in logs:
                    if line.startswith("WE_RESULT:"):
                        r["result"] = json.loads(base64.b64decode(line[10:]).decode("utf-8"))
                return r
            finally:
                b.close()
    except Exception as e:                          # noqa: BLE001 -- timeouts etc. are 'not rendered' too
        return {"ok": False, "backend": "없음", "reason": "%s: %s" % (type(e).__name__, str(e).splitlines()[0][:160])}


_VIEWPORT_PAD: "dict[str, tuple[int, int]]" = {}   # per browser binary: window size minus viewport size, measured


def _render_cli(url, png_path, w, h, timeout_s, real_time_s=None, extra=()) -> dict:
    """The full browser in --headless=new gives the page a viewport smaller than --window-size but screenshots
    the whole window, which leaves a flat band at the bottom. The page reports its viewport (WE_VIEWPORT); if it
    is short, shoot again with the window enlarged by the difference and crop to w x h. headless_shell needs no pad."""
    exe = _chromium()
    pad = _VIEWPORT_PAD.get(exe, (0, 0))
    r = _cli_once(exe, url, png_path, w + pad[0], h + pad[1], timeout_s, real_time_s, extra)
    vp = r.get("_viewport")
    if r["ok"] and vp and (vp[0] < w or vp[1] < h):                 # short viewport: enlarge the window once
        _VIEWPORT_PAD[exe] = pad = (pad[0] + max(0, w - vp[0]), pad[1] + max(0, h - vp[1]))
        r = _cli_once(exe, url, png_path, w + pad[0], h + pad[1], timeout_s, real_time_s, extra)
        vp = r.get("_viewport")
        if r["ok"] and vp and (vp[0] < w or vp[1] < h):
            return {"ok": False, "backend": "없음", "reason": "뷰포트를 %dx%d 로 맞추지 못했다 (%s)" % (w, h, vp)}
    if r["ok"]:
        from worldengine import png
        png.crop(png_path, w, h)          # the canvas is w x h at the top left; drop any window area around it
        r["viewport"] = list(vp) if vp else None
        # The full browser has a minimum window width (500 px here): a narrower request still renders a w x h
        # canvas, but the page's own viewport is wider. Recorded so a phone-width result is not over-claimed.
    r.pop("_viewport", None)
    return r


def _cli_once(exe, url, png_path, ww, wh, timeout_s, real_time_s=None, extra=()) -> dict:
    Path(png_path).parent.mkdir(parents=True, exist_ok=True)
    out = Path(png_path).resolve()
    if out.exists():
        out.unlink()
    cmd = [exe, "--headless=new", "--no-sandbox", "--hide-scrollbars", *_ARGS, *extra,
           "--enable-logging=stderr", "--v=0", "--window-size=%d,%d" % (ww, wh),
           ("--timeout=%d" % int(real_time_s * 1000)) if real_time_s else ("--virtual-time-budget=%d" % int(min(timeout_s, 60) * 1000)),
           "--screenshot=%s" % out, url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"ok": False, "backend": "없음", "reason": "chromium 시간 초과 (%ds)" % timeout_s}
    status = re.findall(r'WE_STATUS:(.*?)", source:', p.stderr)
    if not status:
        return {"ok": False, "backend": "없음", "reason": "페이지가 완료 신호를 보내지 않았다 (chromium rc=%d)" % p.returncode}
    if status[0].startswith("err:"):
        return {"ok": False, "backend": "없음", "reason": "페이지 오류: %s" % status[0][4:200]}
    if not out.exists() or out.stat().st_size == 0:
        return {"ok": False, "backend": "없음", "reason": "스크린샷 파일이 없다"}
    r = {"ok": True, "backend": "three.js r170 · headless chromium (CLI)", "reason": ""}
    vp = re.findall(r'WE_VIEWPORT:(\d+),(\d+)"', p.stderr)
    if vp:
        r["_viewport"] = (int(vp[0][0]), int(vp[0][1]))
    res = re.findall(r'WE_RESULT:([A-Za-z0-9+/=]+)"', p.stderr)
    parts = re.findall(r'WE_RESULT_PART:(\d+)/(\d+):([A-Za-z0-9+/=]+)"', p.stderr)
    if parts:
        n = int(parts[0][1]); got = {int(i): d for i, _, d in parts}
        if sorted(got) != list(range(n)):
            return {"ok": False, "backend": "없음", "reason": "결과 조각이 빠졌다 (%d/%d)" % (len(got), n)}
        res = ["".join(got[i] for i in range(n))]
    if res:
        r["result"] = json.loads(base64.b64decode(res[0]).decode("utf-8"))
    return r
