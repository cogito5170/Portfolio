# -*- coding: utf-8 -*-
"""Multi-visitor presence (SPEC XR-09): several visitors in the same world see each other as simple avatars.

A minimal WebSocket server (RFC 6455, standard library only) mounted on the exhibit server at /ws.
  - each visitor is an anonymous random id with a colour; no IP, name or anything else is relayed or kept
  - a visitor sends {"pos": [x,y,z], "yaw": rad, "eye": "child"|"adult"} at most ~20 times a second;
    malformed, oversized, non-finite or out-of-world states are dropped
  - the room broadcasts everyone else's latest state 10 times a second; a visitor silent for 10 s is dropped
  - nothing is logged or written; at most MAX_CLIENTS visitors per room
Cost/operations: solo works stay serverless (static site). Presence needs this process running (one small machine);
the README records what one process handled in this environment, not a production capacity.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import socket
import struct
import threading
import time

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_CLIENTS, MAX_MSG, MIN_INTERVAL_S, TICK_S, IDLE_S = 50, 512, 0.045, 0.1, 10.0


def accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()


def frame(payload: bytes, opcode: int = 1) -> bytes:
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def read_frame(sock, limit: int = MAX_MSG * 4) -> "tuple[int, bytes] | None":
    """limit guards the server against visitors; a client reading room frames (≈90 bytes per visitor) passes a larger one."""
    def exact(n):
        b = b""
        while len(b) < n:
            c = sock.recv(n - len(b))
            if not c:
                return None
            b += c
        return b
    h = exact(2)
    if h is None:
        return None
    opcode, masked, n = h[0] & 0x0F, h[1] & 0x80, h[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", exact(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", exact(8))[0]
    if n > limit:
        return (8, b"")                                  # absurd frame: treat as close
    mask = exact(4) if masked else None
    data = exact(n) if n else b""
    if data is None or (masked and mask is None):
        return None
    if masked and n:                                     # whole-buffer XOR (a per-byte Python loop was the bottleneck)
        key = (mask * (n // 4 + 1))[:n]
        data = (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(n, "big")
    return opcode, data


def clean_state(msg: dict, bounds) -> "dict | None":
    try:
        pos = [float(v) for v in msg["pos"]]
        yaw = float(msg.get("yaw", 0.0))
    except (KeyError, TypeError, ValueError):
        return None
    if len(pos) != 3 or not all(math.isfinite(v) for v in pos + [yaw]):
        return None
    W, D, H = bounds
    if not (-W <= pos[0] <= 2 * W and -D <= pos[1] <= 2 * D and -1 <= pos[2] <= 2 * H + 10):
        return None
    eye = msg.get("eye") if msg.get("eye") in ("child", "adult") else "adult"
    return {"pos": [round(v, 3) for v in pos], "yaw": round(yaw, 3), "eye": eye}


class Room:
    def __init__(self, bounds):
        self.bounds = bounds or [50, 50, 10]
        self.clients, self.lock, self.stats = {}, threading.Lock(), {"relayed": 0, "dropped": 0, "joined": 0}
        threading.Thread(target=self._tick, daemon=True).start()

    def join(self, sock) -> None:
        """Serve one upgraded socket until it closes (called on the request's own thread)."""
        with self.lock:
            if len(self.clients) >= MAX_CLIENTS:
                try:
                    sock.sendall(frame(json.dumps({"type": "full"}).encode()))
                finally:
                    sock.close()
                return
            cid = os.urandom(3).hex()
            self.clients[cid] = c = {"sock": sock, "state": None, "last": time.monotonic(), "sent": 0.0, "send_lock": threading.Lock(),
                                     "outbox": None, "wake": threading.Event(), "alive": True}
            self.stats["joined"] += 1
        threading.Thread(target=self._sender, args=(c,), daemon=True).start()
        self._send(c, {"type": "hello", "id": cid, "colour": "#" + hashlib.sha1(cid.encode()).hexdigest()[:6]})
        try:
            sock.settimeout(IDLE_S)
            while True:
                fr = read_frame(sock)
                if fr is None or fr[0] == 8:
                    break
                op, data = fr
                if op == 9:
                    with c["send_lock"]:
                        sock.sendall(frame(data, 10))
                    continue
                now = time.monotonic()
                c["last"] = now
                if op != 1 or len(data) > MAX_MSG or now - c["sent"] < MIN_INTERVAL_S:
                    self.stats["dropped"] += 1; continue
                c["sent"] = now
                try:
                    st = clean_state(json.loads(data.decode("utf-8")), self.bounds)
                except (ValueError, UnicodeDecodeError, AttributeError):
                    st = None
                if st is None:
                    self.stats["dropped"] += 1; continue
                c["state"] = st
        except (OSError, socket.timeout):
            pass
        finally:
            c["alive"] = False; c["wake"].set()
            with self.lock:
                self.clients.pop(cid, None)
            try:
                sock.close()
            except OSError:
                pass

    def _send(self, c, obj) -> bool:
        try:
            with c["send_lock"]:
                c["sock"].sendall(frame(json.dumps(obj, separators=(",", ":")).encode()))
            return True
        except OSError:
            return False

    def _sender(self, c):
        """One sender per visitor, holding only the LATEST room state: a slow visitor misses frames, it never
        holds up anyone else (the first version sent to everyone in one loop and one slow socket stalled the room)."""
        while c["alive"]:
            c["wake"].wait(); c["wake"].clear()
            payload, c["outbox"] = c["outbox"], None
            if payload is None or not c["alive"]:
                continue
            try:
                with c["send_lock"]:
                    c["sock"].sendall(payload)
            except OSError:
                c["alive"] = False

    def _tick(self):
        while True:
            time.sleep(TICK_S)
            with self.lock:
                snap = {k: (v["state"], v["last"]) for k, v in self.clients.items()}
                targets = list(self.clients.items())
            now = time.monotonic()
            everyone = [{"id": k, "colour": "#" + hashlib.sha1(k.encode()).hexdigest()[:6], **st} for k, (st, last) in snap.items()
                        if st and now - last < IDLE_S]
            for cid, c in targets:
                others = [o for o in everyone if o["id"] != cid]
                c["outbox"] = frame(json.dumps({"type": "room", "others": others, "count": len(snap)}, separators=(",", ":")).encode())
                c["wake"].set()
                self.stats["relayed"] += len(others)


def upgrade(handler, room: Room) -> None:
    """Called from a BaseHTTPRequestHandler on GET /ws with Upgrade: websocket."""
    key = handler.headers.get("Sec-WebSocket-Key")
    if not key or handler.headers.get("Upgrade", "").lower() != "websocket":
        handler.send_error(400); return
    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket"); handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", accept_key(key)); handler.end_headers()
    handler.wfile.flush()
    handler.close_connection = True
    room.join(handler.connection)
