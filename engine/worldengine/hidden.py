# -*- coding: utf-8 -*-
"""V-12 harness: run a HIDDEN request set that the developer never saw (SPEC 5절).

Only the sha256 of the sealed file is in the repository (eval/v12_sealed.sha256). The file itself is written and kept
by someone else and handed to this harness at run time (WE_V12_FILE=path). Without it the report says
'no hidden set' -- never a number.

File format (JSON): {"items": [{"id", "world", "request"}]}
Route of each item, read from what the agent did (SPEC N1..N5):
  N1 an existing tool's proposal | N2 several kinds of tools combined, or variants/interpretations/combination |
  N3 sandbox code (run_code / propose_plugin) | N4 an external bridge (none exists yet: never reached) | N5 cannot_do
Also: core files' sha256 manifest before and after the run (core changes must be 0), and V-15 substitutions --
items the agent ended without cannot_do although it had judged them impossible earlier in the turn.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
SEAL = ENGINE / "eval" / "v12_sealed.sha256"
CORE_GLOBS = ("worldengine/**/*.py", "runtime/src/**/*.js", "runtime/index.html")


def core_manifest() -> dict:
    files = sorted({f for g in CORE_GLOBS for f in ENGINE.glob(g) if "__pycache__" not in f.parts})
    return {str(f.relative_to(ENGINE)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


def route(turn: dict) -> str:
    names = [c["name"] for c in turn["tool_calls"]]
    if "cannot_do" in names and not turn["proposals"] and not turn["approvals"]:
        return "N5"
    if {"run_code", "propose_plugin"} & set(names):
        return "N3"
    kinds = {n for n in names if n.startswith("propose_") or n == "request_action"}
    if len(kinds) > 1 or {"propose_variants", "propose_interpretations", "propose_combination"} & kinds:
        return "N2"
    if kinds:
        return "N1"
    return "N5"                                   # no proposal and no honest refusal: counted as unmet


def load_sealed(path: "str | None" = None) -> dict:
    """{"status": "no hidden set" | "unsealed" | "hash mismatch" | "ok", "items"?}"""
    p = path or os.environ.get("WE_V12_FILE")
    if not SEAL.exists():
        return {"status": "unsealed", "detail": "eval/v12_sealed.sha256 가 아직 없다 (봉인한 사람이 해시를 보내야 한다)"}
    if not p or not Path(p).exists():
        return {"status": "no hidden set", "detail": "WE_V12_FILE 가 가리키는 봉인 파일이 없다"}
    data = Path(p).read_bytes()
    want = SEAL.read_text(encoding="utf-8").split()[0].strip().lower()
    if hashlib.sha256(data).hexdigest() != want:
        return {"status": "hash mismatch", "detail": "파일이 봉인된 것과 다르다"}
    return {"status": "ok", "items": json.loads(data.decode("utf-8"))["items"]}


def run(client_factory, path=None) -> dict:
    from worldengine import world as WD
    from worldengine.studio import agent as AG, session as SS
    s = load_sealed(path)
    if s["status"] != "ok":
        return {"status": s["status"], "detail": s["detail"]}
    before = core_manifest()
    rows = []
    for it in s["items"]:
        w = WD.load(ENGINE / "worlds" / (it["world"] + ".world.json"))
        sess = SS.Session(w)
        turn = AG.Agent(client_factory(), sess).send(it["request"])
        names = [c["name"] for c in turn["tool_calls"]]
        substituted = "cannot_do" in names and bool(turn["proposals"])     # said it can't, then proposed something else anyway
        rows.append({"id": it["id"], "route": route(turn), "substituted": substituted, "usage": turn["usage"]})
    split = {r: sum(1 for x in rows if x["route"] == r) for r in ("N1", "N2", "N3", "N4", "N5")}
    return {"status": "ok", "n": len(rows), "routes": split, "core_changes": sum(1 for k, v in core_manifest().items() if before.get(k) != v) + len(set(before) - set(core_manifest())),
            "substitutions": sum(r["substituted"] for r in rows), "rows": rows}
