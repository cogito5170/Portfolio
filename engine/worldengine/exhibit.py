# -*- coding: utf-8 -*-
"""`python3 -m worldengine exhibit --world W.json [--host 0.0.0.0] [--port 8200]`

Shows one work to visitors, with live character replies when ANTHROPIC_API_KEY is set (otherwise the characters
speak their scripted lines). Serves the runtime, the world, and POST /api/talk. Writes nothing to disk and keeps
no request log (CH-04); per-address rate limit; 4 KB request cap. The key never leaves this process.
"""
from __future__ import annotations

import http.server
import json
import mimetypes
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from worldengine import character as CH

ENGINE = Path(__file__).resolve().parent.parent
STATIC = {"runtime": ENGINE / "runtime", "vendor": ENGINE / "vendor"}
RATE = (20, 60.0)                 # requests per window (s) per address


def make_handler(world: dict, talk: "CH.Talk | None"):
    hits, lock = {}, threading.Lock()
    world_bytes = json.dumps(world, ensure_ascii=False).encode("utf-8")

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):                  # CH-04: no request log
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            if not parts:
                self.send_response(302); self.send_header("Location", "/runtime/index.html?world=/world.json" + ("&talk=/api/talk" if talk else "")); self.end_headers(); return
            if parts == ["world.json"]:
                return self._send(200, world_bytes)
            if parts[0] in STATIC:
                base = STATIC[parts[0]].resolve(); f = (STATIC[parts[0]] / "/".join(parts[1:])).resolve()
                if base in f.parents and f.is_file() and "tests" not in f.relative_to(base).parts:
                    return self._send(200, f.read_bytes(), (mimetypes.guess_type(f.name)[0] or "application/octet-stream").replace("text/javascript", "application/javascript"))
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/talk":
                return self._send(404, {"error": "not found"})
            if talk is None:
                return self._send(503, {"error": "이 전시는 대본 대사만 쓴다 (서버에 키 없음)"})
            n = int(self.headers.get("Content-Length", 0))
            if n > 4096:
                return self._send(413, {"error": "too large"})
            ip, now = self.client_address[0], time.monotonic()
            with lock:
                q = [t for t in hits.get(ip, []) if now - t < RATE[1]]
                if len(q) >= RATE[0]:
                    return self._send(429, {"error": "잠시 뒤에 다시 말 걸어 주세요"})
                hits[ip] = q + [now]
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
                r = talk.reply(str(body.get("sid", ""))[:64], str(body.get("text", "")), body.get("character"))
            except Exception:                         # noqa: BLE001 -- never leak internals to a visitor
                return self._send(502, {"error": "지금은 대답할 수 없어요"})
            return self._send(200, {k: v for k, v in r.items() if k in ("reply", "error", "filtered", "overhead_ms")})
    return H


def serve(world: dict, host="127.0.0.1", port=8200):
    from worldengine.studio import server as S
    client, why = S.make_client()
    talk = CH.Talk(world, client) if client else None
    srv = http.server.ThreadingHTTPServer((host, port), make_handler(world, talk))
    print("전시: http://%s:%d/" % ("localhost" if host == "127.0.0.1" else host, port))
    print("캐릭터:", "실시간 대답" if talk else "대본 대사만 — " + why)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
