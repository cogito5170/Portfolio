# -*- coding: utf-8 -*-
"""Live replies for a world's talking character (CH-01..CH-04), used by `worldengine exhibit`.

CH-01 persona: built from the world itself -- its name, concepts (statements), narrative axis, and the character's
      own name/persona/lines. No personality is written in code.
CH-04 safety, in this order:
  - input capped at 300 characters; e-mail addresses, phone numbers and resident-registration-like numbers are
    replaced by [개인정보] before anything leaves the server (the model never sees them)
  - blocklist on the visitor's words -> a refusal line in the persona's voice, the model is not called
  - output capped (max_tokens and 400 characters); blocklist on the reply -> the refusal line instead
  - memory: the last 6 turns per page visit, in RAM only, dropped after 10 minutes. Nothing is written to disk.
CH-03: the server's own overhead (everything except the model call) is measured per reply; model latency needs
the real API and is measured by the user on the real network.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from worldengine.studio import config

MAX_IN, MAX_OUT_CHARS, MAX_TOKENS, KEEP_TURNS, TTL_S = 300, 400, 400, 6, 600
REFUSAL = "그 이야기는 여기서 나누지 않을게요. 이 세계에 대해 물어봐 주세요."
_PII = [(re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[개인정보]"),
        (re.compile(r"\b\d{6}\s*-\s*[1-4]\d{6}\b"), "[개인정보]"),
        (re.compile(r"(?:\+?82[-\s]?)?0?1[016789][-\s]?\d{3,4}[-\s]?\d{4}"), "[개인정보]"),
        (re.compile(r"\b0\d{1,2}[-\s]\d{3,4}[-\s]\d{4}\b"), "[개인정보]")]


def blocklist(extra=()) -> "list[str]":
    terms = [l.strip() for l in (Path(__file__).parent / "safety" / "blocklist.txt").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return [t.lower() for t in terms + list(extra)]


def blocked(text: str, terms) -> bool:
    flat = re.sub(r"\s+", "", text.lower())
    return any(t in flat for t in terms)


def redact(text: str) -> str:
    for pat, rep in _PII:
        text = pat.sub(rep, text)
    return text


def find_character(world: dict, name: "str | None" = None) -> "dict | None":
    def walk(es):
        for e in es or []:
            yield e; yield from walk(e.get("children"))
    cs = [e for e in walk(world.get("entities")) if e.get("type") == "character"]
    return next((c for c in cs if c.get("name") == name), cs[0] if cs else None)


def persona(world: dict, ch: dict) -> str:
    ax = (world.get("rules") or {}).get("axes") or {}
    cards = "\n".join("- %s: %s" % (c["title"], c["statement"]) for c in world.get("concepts") or [])
    lines = "\n".join("- " + l for l in ch.get("lines", [])[:8])
    return ("너는 '%s' 라는 세계 안의 존재 '%s'다. 관객과 짧게(두세 문장) 한국어로 이야기한다.\n"
            "이 세계의 개념:\n%s\n서사의 강도(0~1): %s\n%s"
            "네가 원래 하던 말(말투의 기준):\n%s\n"
            "규칙: 관객의 이름·연락처·사는 곳 같은 개인정보를 묻거나 기억하지 않는다. 폭력·성적인 이야기, 혐오, 위험한 행동 안내는 하지 않고 "
            "세계 이야기로 돌린다. 모르는 것은 모른다고 말한다. 세계 밖의 사실을 지어내지 않는다.") % (
        world["name"], ch.get("name", "캐릭터"), cards or "- (개념 카드 없음)", ax.get("narrative", "정하지 않음"),
        ("성격: %s\n" % ch["persona"]) if ch.get("persona") else "", lines)


class Talk:
    def __init__(self, world: dict, client, clock=time.monotonic):
        self.world, self.client, self.clock = world, client, clock
        self.mem = {}                                       # sid -> {"t": last, "turns": [...]}  (RAM only)

    def _gc(self):
        now = self.clock()
        for k in [k for k, v in self.mem.items() if now - v["t"] > TTL_S]:
            del self.mem[k]

    def reply(self, sid: str, text: str, character: "str | None" = None) -> dict:
        t0 = time.perf_counter()
        ch = find_character(self.world, character)
        if ch is None:
            return {"error": "이 세계에는 말하는 캐릭터가 없다"}
        terms = blocklist(ch.get("blocklist", []))
        clean = redact((text or "")[:MAX_IN])
        if not clean.strip():
            return {"reply": "…", "overhead_ms": 0.0}
        if blocked(clean, terms):
            return {"reply": ch.get("refusal", REFUSAL), "filtered": "input", "overhead_ms": round((time.perf_counter() - t0) * 1000, 2)}
        self._gc()
        m = self.mem.setdefault(sid[:64], {"t": self.clock(), "turns": []})
        m["t"] = self.clock()
        msgs = m["turns"][-2 * KEEP_TURNS:] + [{"role": "user", "content": clean}]
        t_call = time.perf_counter()
        r = self.client.messages.create(model=config.model(), max_tokens=MAX_TOKENS, system=persona(self.world, ch), messages=msgs)
        model_ms = (time.perf_counter() - t_call) * 1000
        blocks = r["content"] if isinstance(r, dict) else r.content
        out = "".join((b.get("text") if isinstance(b, dict) else getattr(b, "text", "")) or "" for b in blocks
                      if (b.get("type") if isinstance(b, dict) else getattr(b, "type", "")) == "text").strip()[:MAX_OUT_CHARS]
        filtered = None
        if not out or blocked(out, terms):
            out, filtered = ch.get("refusal", REFUSAL), ("output" if out else "empty")
        m["turns"] = (msgs + [{"role": "assistant", "content": out}])[-2 * KEEP_TURNS:]
        total = (time.perf_counter() - t0) * 1000
        return {"reply": out, "filtered": filtered, "overhead_ms": round(total - model_ms, 2), "model_ms": round(model_ms, 1)}
