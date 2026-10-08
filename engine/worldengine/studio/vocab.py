# -*- coding: utf-8 -*-
"""Per-artist vocabulary (A-04): what this artist meant when an interpretation had to be corrected.

Stored under config.data_dir()/vocab/<artist>.json -- outside the repository by default, owned by the artist.
It goes into the model's system prompt (server side) so the next interpretation is closer; it is never
served to the browser.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from worldengine.studio import config


def _safe(name: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣_-]", "_", name).strip("_")
    if not s:
        raise ValueError("artist name is empty after sanitising")
    return s


class Vocab:
    def __init__(self, artist: str, root: "Path | None" = None):
        self.path = Path(root or config.data_dir()) / "vocab" / (_safe(artist) + ".json")
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"artist": artist, "corrections": []}

    def record(self, said: str, proposed: dict, applied: dict, note: str = "") -> None:
        """The artist corrected an interpretation: keep what was said, what we proposed, what they actually wanted."""
        self.data["corrections"].append({"said": said, "proposed": proposed, "applied": applied, "note": note, "t": time.time()})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def prompt_lines(self, last: int = 20) -> "list[str]":
        out = []
        for c in self.data["corrections"][-last:]:
            out.append("- 작가가 \"%s\" 라고 했을 때 우리는 %s 로 이해했지만, 작가가 고친 값은 %s%s" % (
                c["said"], json.dumps(c["proposed"], ensure_ascii=False), json.dumps(c["applied"], ensure_ascii=False),
                (" (" + c["note"] + ")") if c.get("note") else ""))
        return out
