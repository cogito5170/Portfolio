# -*- coding: utf-8 -*-
"""Sandbox for agent-written code (SPEC N-03). FAIL-CLOSED: if isolation cannot be set up, nothing runs.

    ok, why = available()
    r = run(code, lang="python"|"node", inputs={...})   -> {"ran", "exit", "stdout", "stderr", "result", "killed", "reason"}

Isolation (Linux):
  - runs as a dedicated unused uid (SANDBOX_UID) so RLIMIT_NPROC is enforced -- root would ignore it -- and the
    process quota belongs to the sandbox alone: fork bombs stop
  - new user + network + mount + PID namespaces (`unshare -rmnpf --kill-child`): no network interfaces, and
    every process the code starts dies with it (no leftover children eating the process quota)
  - every mount remounted read-only; a fresh 64 MB tmpfs on /tmp is the only writable place (cwd /tmp/w)
  - environment cleared (no API keys, no HOME of the parent)
  - limits: CPU seconds, address space (memory), processes, file size; wall-clock timeout kills the whole group;
    stdout/stderr truncated
  - node additionally runs with --permission (fs writes only under /tmp/w, no child processes)
The program reads its inputs from /tmp/w/input.json and prints one JSON object as its last stdout line.
"""
from __future__ import annotations

import base64
import json
import os
import resource
import shutil
import signal
import subprocess
from pathlib import Path

# A uid no other process uses, so RLIMIT_NPROC (counted per uid) is the sandbox's own quota. `nobody` was not
# enough: on CI runners other services already run as nobody and the quota was gone before the code started.
SANDBOX_UID = int(os.environ.get("WE_SANDBOX_UID") or 61333)
LIMITS = {"cpu_s": 5, "mem_mb": 512, "nproc": 32, "fsize_mb": 16, "wall_s": 15, "out_kb": 256}

_LAUNCH = r"""set -e
for m in $(awk '{print $2}' /proc/self/mounts | sort -r); do mount -o remount,ro,bind "$m" 2>/dev/null || true; done
mount -t tmpfs -o size=64m,mode=0777 sbx /tmp
mkdir /tmp/w && cd /tmp/w
printf %s "$WE_CODE" | base64 -d > main.$WE_EXT
printf %s "$WE_INPUT" | base64 -d > input.json
if [ "$WE_EXT" = js ]; then set -- "$WE_NODE" --max-old-space-size=$WE_HEAP --permission --allow-fs-read=* --allow-fs-write=/tmp/w main.js
else set -- "$WE_PY" -I main.py; fi
set +e
env -i PATH=/usr/bin:/bin HOME=/tmp/w TMPDIR=/tmp/w "$@"
echo "WE_EXIT:$?" >&2
"""


def _tools():
    return shutil.which("unshare"), shutil.which("python3"), shutil.which("node")


def _drop(lim, address_mb=None):
    def pre():
        os.setsid()
        mb = 1024 * 1024
        resource.setrlimit(resource.RLIMIT_CPU, (lim["cpu_s"], lim["cpu_s"]))
        a = address_mb or lim["mem_mb"]
        resource.setrlimit(resource.RLIMIT_AS, (a * mb, a * mb))
        resource.setrlimit(resource.RLIMIT_FSIZE, (lim["fsize_mb"] * mb, lim["fsize_mb"] * mb))
        if os.getuid() == 0:
            os.setgroups([]); os.setgid(SANDBOX_UID); os.setuid(SANDBOX_UID)
        resource.setrlimit(resource.RLIMIT_NPROC, (lim["nproc"], lim["nproc"]))
    return pre


_CACHE = {}


def _uid_of(proc_dir) -> "int | None":
    try:
        for line in (proc_dir / "status").read_text().splitlines():
            if line.startswith("Uid:"):
                return int(line.split()[1])
    except OSError:
        return None
    return None


def available() -> "tuple[bool, str]":
    """Can we isolate? Probed once by actually entering the namespaces as the sandbox user."""
    if "a" in _CACHE:
        return _CACHE["a"]
    unshare, py, _ = _tools()
    if os.name != "posix" or not unshare or not py:
        _CACHE["a"] = (False, "unshare 또는 python3 가 없다 (Linux 전용)")
        return _CACHE["a"]
    busy = [d.name for d in Path("/proc").iterdir() if d.name.isdigit() and _uid_of(d) == SANDBOX_UID]
    if busy:
        _CACHE["a"] = (False, "샌드박스 uid %d 를 다른 프로세스가 쓰고 있다 (%d개) — WE_SANDBOX_UID 로 바꿀 것" % (SANDBOX_UID, len(busy)))
        return _CACHE["a"]
    try:
        r = subprocess.run([unshare, "-rmn", "sh", "-c", "mount -t tmpfs t /tmp && ! ip link show 2>/dev/null | grep -q 'state UP'"],
                           capture_output=True, text=True, timeout=10, preexec_fn=_drop(LIMITS))
        _CACHE["a"] = (True, "") if r.returncode == 0 else (False, "격리를 만들 수 없다: " + (r.stderr.strip() or "unshare rc=%d" % r.returncode)[:200])
    except Exception as e:                                   # noqa: BLE001
        _CACHE["a"] = (False, "격리를 만들 수 없다: %s" % e)
    return _CACHE["a"]


def run(code: str, lang: str = "python", inputs: "dict | None" = None, limits: "dict | None" = None) -> dict:
    ok, why = available()
    if not ok:
        return {"ran": False, "reason": why}                # fail closed
    lim = {**LIMITS, **(limits or {})}
    unshare, py, node = _tools()
    if lang == "node" and not node:
        return {"ran": False, "reason": "node 가 없다"}
    env = {"PATH": "/usr/bin:/bin", "WE_EXT": "js" if lang == "node" else "py", "WE_PY": py, "WE_NODE": node or "",
           "WE_CODE": base64.b64encode(code.encode()).decode(), "WE_INPUT": base64.b64encode(json.dumps(inputs or {}).encode()).decode(),
           "WE_HEAP": str(max(32, lim["mem_mb"] // 2))}
    # V8 reserves a large virtual range up front, so node gets a wide address-space limit and a real heap cap instead.
    address_mb = max(lim["mem_mb"], 8192) if lang == "node" else None
    p = subprocess.Popen([unshare, "-rmnpf", "--kill-child", "sh", "-c", _LAUNCH], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, preexec_fn=_drop(lim, address_mb), cwd="/")
    killed = None
    try:
        out, err = p.communicate(timeout=lim["wall_s"])
    except subprocess.TimeoutExpired:
        killed = "wall_time"
        os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
    cap = lim["out_kb"] * 1024
    import re
    m = re.findall(rb"WE_EXIT:(\d+)", err)
    code_ = int(m[-1]) if m else p.returncode
    err = re.sub(rb"WE_EXIT:\d+\n?", b"", err)
    out_s, err_s = out[:cap].decode("utf-8", "replace"), err[:cap].decode("utf-8", "replace")
    if killed is None and code_ > 128:
        killed = {signal.SIGXCPU: "cpu_time", signal.SIGKILL: "killed", signal.SIGSEGV: "memory", signal.SIGXFSZ: "file_size"}.get(code_ - 128, "signal %d" % (code_ - 128))
    result = None
    for line in reversed(out_s.strip().splitlines()):
        try:
            result = json.loads(line); break
        except ValueError:
            continue
    return {"ran": True, "exit": code_ if killed is None or killed != "wall_time" else p.returncode, "stdout": out_s, "stderr": err_s, "result": result, "killed": killed,
            "truncated": len(out) > cap or len(err) > cap}
