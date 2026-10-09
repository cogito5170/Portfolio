# -*- coding: utf-8 -*-
"""Conversation loop over the Anthropic Messages API (manual tool loop: the client is injected so tests run a
scripted fake with no network and no key, and so approval gating stays in our hands).

    agent = Agent(anthropic.Anthropic(), session, vocab)
    turn = agent.send("좀 더 비워 줘", images=[("image/jpeg", b64)])
    turn -> {"reply", "tool_calls", "proposals", "approvals", "refusals", "variant_sets", "usage", "stop_reason"}
"""
from __future__ import annotations

import json

from worldengine import interpret as IN
from worldengine.studio import config, tools as T

SYSTEM = """너는 World Platform 스튜디오의 조수다. 상대는 코딩을 하지 않는 작가이고, 한국어로 말하거나 이미지를 보여 준다.
규칙:
1. 무엇이든 바꾸기 전에 describe_world 로 현재 세계를 본다.
2. 너는 제안만 한다. propose_* 도구가 만든 제안은 작가가 '적용'을 눌러야 반영된다. 제안할 때 why 에 작가의 말을 어떻게 이해했는지 한 문장으로 쓴다.
3. 요청이 여러 뜻으로 읽히면 질문하지 말고 propose_variants 로 해석이 다른 시안 2~3개를 낸다.
4. "아까가 나았어" 같은 말에는 history 를 보고 propose_revert 를 쓴다.
5. 고해상도 렌더, 작품 삭제, 외부 공개, 실제 장치 구동은 request_action 으로만 요청한다. 직접 실행하지 않는다.
6. 할 수 없는 요청은 cannot_do 로 말하고 대안을 준다. 비슷한 다른 것으로 바꿔치기하지 않는다.
7. 작가의 미적 판단을 평균적인 취향으로 끌고 가지 않는다. 작가의 단어를 그대로 존중한다.
8. 개념을 규칙으로 옮겨 달라는 요청에는 propose_interpretations 로 해석 카드 2~3개를 낸다. 두 세계를 합치는 요청에는 propose_combination 을 쓰고 평균 내지 않는다.
9. 기존 도구로 안 되면 run_code 로 샌드박스에서 시험하고, 쓸 만하면 propose_plugin 으로 등록을 제안한다 (작가 승인 필요). 그래도 안 되면 cannot_do.
10. 세계의 glossary(용어집)에 있는 말은 그 뜻으로 읽는다. forbidden(금지 목록)에 있는 것은 제안하지 않는다. 규칙을 끄는 것은 작가만 한다 — 규칙 때문에 안 되면 그렇게 말한다.
11. 답은 짧은 한국어로."""


def _get(b, k, d=None):
    return b.get(k, d) if isinstance(b, dict) else getattr(b, k, d)


class Agent:
    def __init__(self, client, session, vocab=None, model: "str | None" = None):
        self.client, self.session, self.vocab = client, session, vocab
        self.model = model or config.model()
        self.messages = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "requests": 0}

    def system(self) -> str:
        lines = self.vocab.prompt_lines() if self.vocab else []
        return SYSTEM + ("\n\n이 작가의 단어 (이전에 고친 해석):\n" + "\n".join(lines) if lines else "")

    def send(self, text: str, images=()) -> dict:
        content = [{"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}} for mt, data in images]
        content.append({"type": "text", "text": text})
        self.messages.append({"role": "user", "content": content})
        out = {"reply": "", "tool_calls": [], "proposals": [], "approvals": [], "refusals": [], "variant_sets": [], "stop_reason": None,
               "warnings": [w for w in [IN.copy_risk(text)] if w]}          # CT-04: shown to the artist, never blocks
        self.session.last_request = text
        for _ in range(config.MAX_TURNS):
            r = self.client.messages.create(model=self.model, max_tokens=config.MAX_TOKENS, system=self.system(),
                                            tools=T.TOOLS, thinking={"type": "adaptive"}, messages=self.messages)
            u = _get(r, "usage")
            if u is not None:
                self.usage["input_tokens"] += _get(u, "input_tokens", 0) or 0
                self.usage["output_tokens"] += _get(u, "output_tokens", 0) or 0
            self.usage["requests"] += 1
            blocks = _get(r, "content") or []
            self.messages.append({"role": "assistant", "content": blocks})      # passed back unmodified (thinking blocks too)
            stop = _get(r, "stop_reason")
            out["stop_reason"] = stop
            texts = [_get(b, "text") for b in blocks if _get(b, "type") == "text"]
            if texts:
                out["reply"] = "\n".join(t for t in texts if t)
            calls = [b for b in blocks if _get(b, "type") == "tool_use"]
            if stop == "pause_turn":
                continue
            if stop != "tool_use" or not calls:
                break
            results = []
            for c in calls:
                name, inp = _get(c, "name"), _get(c, "input") or {}
                res = T.run_json(self.session, name, inp)
                parsed = json.loads(res)
                out["tool_calls"].append({"name": name, "input": inp, "result": parsed})
                if parsed.get("proposal"):
                    out["proposals"].append(parsed["proposal"])
                if parsed.get("variant_set"):
                    out["variant_sets"].append(parsed["variant_set"])
                    out["proposals"] += [v["proposal"] for v in parsed["variants"] if v.get("proposal")]
                if parsed.get("approval"):
                    out["approvals"].append(parsed["approval"])
                if name == "cannot_do":
                    out["refusals"].append(parsed.get("shown_to_artist"))
                results.append({"type": "tool_result", "tool_use_id": _get(c, "id"), "content": res, **({"is_error": True} if parsed.get("ok") is False else {})})
            self.messages.append({"role": "user", "content": results})
        else:
            out["stop_reason"] = "max_turns"
        out["usage"] = dict(self.usage)
        return out
