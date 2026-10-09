# -*- coding: utf-8 -*-
"""Model providers for the co-creation agents (CC-08): Anthropic and Gemini, chosen per role so the lenses do not
all think with the same model. Every call returns a Pydantic object that passed validation, or raises.

    p = Anthropic(client, model)            client injected (tests run a scripted fake: no network, no key)
    p = Gemini(key, model, post=None)       REST generateContent over the standard library; `post` injectable
    obj, meta = p.complete(system, prompt, Model)       meta = {"provider", "model", "usage", "attempts"}
    R = Router({"emotion": p1, "form": p2, ...}, default=p1)   R.of(role)

Anthropic is held to the schema by structured outputs (output_config.format). Gemini is asked for JSON and given
the same schema in the prompt; both are validated here with Pydantic, and one retry carries the validation error.
Keys stay in this process: nothing here is ever sent to a browser.
"""
from __future__ import annotations

import json
import os
import urllib.request

from pydantic import ValidationError

from worldengine.cocreate import schema as S

MAX_TOKENS = int(os.environ.get("WE_COCREATE_MAX_TOKENS") or 16000)


class ProviderError(RuntimeError):
    pass


def _get(b, k, d=None):
    return b.get(k, d) if isinstance(b, dict) else getattr(b, k, d)


class _Base:
    name = "?"

    def __init__(self, model: str):
        self.model = model

    def _once(self, system: str, prompt: str, schema: dict) -> "tuple[str, dict]":
        raise NotImplementedError

    def complete(self, system: str, prompt: str, model_cls):
        schema = S.json_schema(model_cls)
        usage, err = {"input_tokens": 0, "output_tokens": 0}, None
        for attempt in (1, 2):
            p = prompt if err is None else prompt + "\n\n앞의 답은 형식 검사에서 떨어졌다. 고칠 것:\n" + err[:1500]
            text, u = self._once(system, p, schema)
            usage = {k: usage[k] + (u.get(k) or 0) for k in usage}
            try:
                return S.validate(model_cls, text), {"provider": self.name, "model": self.model, "usage": usage, "attempts": attempt}
            except (ValidationError, ValueError) as e:
                err = str(e)
        raise ProviderError("%s %s: 형식에 맞는 답을 두 번 다 받지 못했다: %s" % (self.name, self.model, err[:300]))


class Anthropic(_Base):
    name = "anthropic"

    def __init__(self, client, model: str):
        super().__init__(model)
        self.client = client

    def _once(self, system, prompt, schema):
        r = self.client.messages.create(model=self.model, max_tokens=MAX_TOKENS, system=system,
                                        messages=[{"role": "user", "content": prompt}],
                                        output_config={"format": {"type": "json_schema", "schema": schema}})
        stop = _get(r, "stop_reason")
        if stop in ("refusal", "max_tokens"):
            raise ProviderError("anthropic: stop_reason=%s" % stop)
        text = "".join(_get(b, "text") or "" for b in (_get(r, "content") or []) if _get(b, "type") == "text")
        u = _get(r, "usage")
        return text, {"input_tokens": _get(u, "input_tokens", 0) if u is not None else 0,
                      "output_tokens": _get(u, "output_tokens", 0) if u is not None else 0}


def _http_post(url: str, headers: dict, body: dict, timeout: float = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class Gemini(_Base):
    """generateContent (v1beta). Not yet run against the real service from this repository (no key here): the
    request shape is tested against a fake transport only -- see README."""
    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"

    def __init__(self, key: str, model: str, post=None):
        super().__init__(model)
        self._key, self._post = key, post or _http_post

    def _once(self, system, prompt, schema):
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt + "\n\n답은 이 JSON Schema 를 따르는 JSON 하나만:\n" + json.dumps(schema, ensure_ascii=False)}]}],
                "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": MAX_TOKENS}}
        try:
            r = self._post(self.URL % self.model, {"Content-Type": "application/json", "x-goog-api-key": self._key}, body)
        except OSError as e:
            raise ProviderError("gemini: %s" % e) from None
        cands = r.get("candidates") or []
        if not cands:
            raise ProviderError("gemini: 답이 없다 (%s)" % json.dumps(r.get("promptFeedback") or {}, ensure_ascii=False)[:200])
        fin = cands[0].get("finishReason")
        if fin not in (None, "STOP"):
            raise ProviderError("gemini: finishReason=%s" % fin)
        text = "".join(p.get("text", "") for p in (cands[0].get("content") or {}).get("parts") or [])
        u = r.get("usageMetadata") or {}
        return text, {"input_tokens": u.get("promptTokenCount", 0), "output_tokens": u.get("candidatesTokenCount", 0)}


class Router:
    """role -> provider. Records what actually ran, so a run never claims two models when it used one."""

    def __init__(self, by_role: "dict | None" = None, default=None):
        self.by_role, self.default = dict(by_role or {}), default

    def of(self, role: str):
        p = self.by_role.get(role) or self.default
        if p is None:
            raise ProviderError("이 역할에 연결된 모델이 없다: %s" % role)
        return p

    def describe(self) -> dict:
        return {r: "%s %s" % (p.name, p.model) for r, p in sorted(self.by_role.items()) if p is not None}


ROLES = ("brief", "emotion", "form", "invert", "audience", "curator", "realizer")
SPREAD = {"emotion": "anthropic", "form": "gemini", "invert": "anthropic", "audience": "gemini", "curator": "anthropic",
          "realizer": "anthropic", "brief": "anthropic"}


def from_env(anthropic_client=None) -> "tuple[Router | None, str]":
    """The real router, or (None, why). Gemini lanes fall back to Anthropic when Gemini is not configured -- and
    say so (the run's providers list is shown to the artist). WE_COCREATE_<ROLE>=anthropic|gemini overrides."""
    from worldengine.studio import config
    a = Anthropic(anthropic_client, config.model()) if anthropic_client is not None else None
    gk, gm = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"), os.environ.get("WE_GEMINI_MODEL")
    g = Gemini(gk, gm) if gk and gm else None
    if a is None and g is None:
        return None, "모델이 연결돼 있지 않다 (ANTHROPIC_API_KEY, 또는 GEMINI_API_KEY 와 WE_GEMINI_MODEL)"
    by, notes = {}, []
    for role in ROLES:
        want = (os.environ.get("WE_COCREATE_" + role.upper()) or SPREAD[role]).lower()
        p = {"anthropic": a, "gemini": g}.get(want) or a or g
        if p is not None and p.name != want:
            notes.append("%s: %s 이 없어 %s 로 대신" % (role, want, p.name))
        by[role] = p
    return Router(by, a or g), "; ".join(notes)
