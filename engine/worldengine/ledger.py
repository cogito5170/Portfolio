# -*- coding: utf-8 -*-
"""Unmet-request ledger (SPEC N-05). Every request the platform could not serve is recorded privately (the artist's
data dir, never the repo); the roadmap reads an export that drops the artist's own words unless they consented.

    L = Ledger(artist); L.record(said, route, kind, reason, alternatives)
    L.export(consent=False) -> [{"route", "kind", "alternatives_n", "t_day"}]   # fixed categories only: no free text
    L.export(consent=True)  -> adds "said" and "reason"
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from worldengine.studio import config, vocab

ROUTES = ("N1", "N2", "N3", "N4", "N5")   # existing feature, composition, sandbox code, external bridge, cannot yet
KINDS = ("medium_missing", "hardware_missing", "capability_missing", "policy", "other")


class Ledger:
    def __init__(self, artist: str, root=None):
        self.path = Path(root or config.data_dir()) / "ledger" / (vocab._safe(artist) + ".jsonl")

    def record(self, said: str, route: str, kind: str, reason: str, alternatives=()) -> None:
        if route not in ROUTES:
            raise ValueError("route must be one of %s" % ", ".join(ROUTES))
        if kind not in KINDS:
            kind = "other"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "said": said, "route": route, "kind": kind, "reason": reason, "alternatives": list(alternatives)}, ensure_ascii=False) + "\n")

    def entries(self) -> "list[dict]":
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def export(self, consent: bool = False) -> "list[dict]":
        out = []
        for e in self.entries():
            row = {"route": e["route"], "kind": e["kind"], "alternatives_n": len(e["alternatives"]),
                   "t_day": time.strftime("%Y-%m-%d", time.gmtime(e["t"]))}
            if consent:
                row["said"], row["reason"] = e["said"], e["reason"]
            out.append(row)
        return out
