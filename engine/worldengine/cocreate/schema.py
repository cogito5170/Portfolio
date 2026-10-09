# -*- coding: utf-8 -*-
"""Shared formats of the co-creation system (SPEC CC-02). Pydantic is the one source; the JSON Schema each model is
held to is generated from it (json_schema), so the two cannot drift.

    CreativeBrief   creative_brief/1 -- what every agent reads (the artist confirms or edits it first, CC-01)
    IdeaDraft       one lens's idea: premise, what it added that the artist did not say, self-check, a SKETCH
    RebuttalSet     round 2: one lens's objections to the OTHER lenses' ideas (CC-04)
    CuratorReport   reasons, clichés, collisions, a shortlist -- and no number anywhere (CC-05: no originality score)
    Realization     the chosen idea as a full world/1 (as JSON text, checked by the core) + production notes

A sketch is deliberately small (fixed axes, a few bodies of known types, named engine features) so ideas can be
measured against each other and drawn as a floor plan before anything is realised.
"""
from __future__ import annotations

import copy
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

BODY_TYPES = ("box", "cylinder", "cone", "sphere", "capsule", "torus", "plane", "arch", "text", "light", "sound", "person")
BEHAVIOURS = ("spin", "bob", "fall", "orbit", "react_mic", "react_camera")
FEATURES = {                                   # what the engine can do today, in the artist's words (CC-03 feasibility)
    "react_mic": "관객의 소리(마이크)에 반응", "react_camera": "관객의 움직임(카메라, 움직임의 양)에 반응",
    "tap": "누르면 반응", "near": "다가가면 반응", "spatial_sound": "위치에 따라 들리는 소리",
    "tour": "작가가 정한 카메라 투어(자막)", "talking_character": "관객과 말하는 캐릭터", "light": "빛과 그림자",
    "bloom": "빛 번짐", "physics": "중력·시간 흐름 바꾸기", "fly": "날아다니며 보기", "presence": "여러 관객이 서로 보임",
    "image": "그림 결과물(절차적)", "drawing": "선 그림·로봇 드로잉", "sound_work": "소리 결과물(절차적)",
}
MEDIA = ("web3d", "image", "drawing", "sound", "installation", "video", "print")
REBUT_KINDS = ("cliche", "breaks_brief", "not_feasible", "weak_effect", "contradiction", "other")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ brief (CC-01, CC-02)
class Forbidden(Strict):
    text: str = Field(description="작가가 한 말 그대로")
    check: Literal["machine", "judged"] = Field(description="machine: 엔진이 확실히 막을 수 있음 / judged: 사람이 판단해야 함")
    kind: Optional[Literal["type", "colour", "word"]] = Field(description="machine 일 때만: 막을 대상의 종류")
    value: Optional[str] = Field(description="machine 일 때만: 몸 종류, #rrggbb, 또는 단어")
    flag_types: list[str] = Field(description="judged 일 때: 나오면 표시할 몸 종류 (예: person)")
    flag_words: list[str] = Field(description="judged 일 때: 나오면 표시할 단어")

    @model_validator(mode="after")
    def _machine(self):
        if self.check == "machine":
            if not self.kind or not self.value:
                raise ValueError("machine 금지 조건에는 kind 와 value 가 있어야 한다")
            if self.kind == "colour" and not HEX.match(self.value):
                raise ValueError("colour 금지 조건의 value 는 #rrggbb")
        return self


class ArtistContext(Strict):
    environment: list[str] = Field(description="작업·전시 환경 (예: PC, 휴대폰, 전시장)")
    materials: list[str] = Field(description="쓸 수 있는 재료")
    budget: Optional[str]
    notes: Optional[str]


class Intent(Strict):
    theme: str
    desired_effect: str
    said: str = Field(description="작가의 말 원문")


class Constraints(Strict):
    forbidden: list[Forbidden]


class CreativeBrief(Strict):
    schema_: Literal["creative_brief/1"] = Field(alias="schema")
    artist: ArtistContext
    intent: Intent
    constraints: Constraints
    exploration: list[str]
    deliverables: list[str]
    uncertainties: list[str]
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def data(self) -> dict:
        return self.model_dump(by_alias=True)


# ------------------------------------------------------------------ ideas (CC-03)
class Axes(Strict):
    density: float
    colour: float
    form: float
    texture: float
    motion: float
    sound: float
    narrative: float

    @model_validator(mode="after")
    def _range(self):
        for k, v in self.model_dump().items():
            if not 0 <= v <= 1:
                raise ValueError("axes.%s must be in [0,1]: %s" % (k, v))
        return self


class Body(Strict):
    id: str
    type: Literal[BODY_TYPES]  # type: ignore[valid-type]
    pos: list[float] = Field(description="[x, y, z] 미터, z 가 위")
    size: Optional[list[float]] = Field(description="box: [가로, 세로, 높이], plane: [가로, 세로], text: [폭, 높이]")
    radius: Optional[float]
    height: Optional[float]
    color: Optional[str] = Field(description="#rrggbb")
    caption: Optional[str] = Field(description="글자·소리의 자막·누르면 나오는 말")
    behaviour: Optional[Literal[BEHAVIOURS]]  # type: ignore[valid-type]
    trigger: Optional[Literal["tap", "near"]]

    @field_validator("pos")
    @classmethod
    def _pos(cls, v):
        if len(v) != 3:
            raise ValueError("pos must be [x,y,z]")
        return v

    @field_validator("color")
    @classmethod
    def _hex(cls, v):
        if v is not None and not HEX.match(v):
            raise ValueError("color must be #rrggbb: %s" % v)
        return v


class Sketch(Strict):
    axes: Axes
    bounds: Optional[list[float]] = Field(description="[가로, 세로, 높이] 미터")
    bodies: list[Body]
    features: list[Literal[tuple(FEATURES)]]  # type: ignore[valid-type]
    needs: list[str] = Field(description="이 아이디어에 필요하지만 엔진에 아직 없는 것 (솔직하게)")


class SelfCheck(Strict):
    constraint: str
    kept: bool
    how: str


class IdeaDraft(Strict):
    title: str
    premise: str = Field(description="핵심 전제 2~4문장")
    departures: list[str] = Field(description="작가가 말하지 않았는데 이 렌즈가 더한 것 (CC-07)")
    audience_experience: str
    media: list[Literal[MEDIA]]  # type: ignore[valid-type]
    materials: list[str]
    selfcheck: list[SelfCheck]
    lens_note: str = Field(description="이 렌즈만의 기록 (감정의 순서, 뒤집은 전제 등)")
    sketch: Sketch


# ------------------------------------------------------------------ debate round 2 (CC-04)
class Rebuttal(Strict):
    target: str = Field(description="반박하는 아이디어의 id (자기 것은 안 됨)")
    kind: Literal[REBUT_KINDS]  # type: ignore[valid-type]
    point: str


class RebuttalSet(Strict):
    rebuttals: list[Rebuttal]


# ------------------------------------------------------------------ curator (CC-05)
class IdeaNote(Strict):
    idea: str
    strengths: list[str]
    weaknesses: list[str]
    cliche: list[str] = Field(description="흔한 데가 있다면 무엇이 왜")
    rebuttals_weighed: list[str] = Field(description="받은 반박 중 맞다고 본 것과 아니라고 본 것")
    feasibility: str


class Collision(Strict):
    a: str
    b: str
    note: str


class Pick(Strict):
    idea: str
    reason: str


class CuratorReport(Strict):
    notes: list[IdeaNote]
    collisions: list[Collision]
    shortlist: list[Pick]
    message_to_artist: str


# ------------------------------------------------------------------ realisation (CC-06)
class CannotDo(Strict):
    what: str
    why: str
    alternative: str


class Realization(Strict):
    world_json: str = Field(description="world/1 세계 전체를 JSON 문자열로")
    why: str = Field(description="고른 아이디어를 어떻게 세계로 옮겼는지 한두 문장")
    production_notes: list[str] = Field(description="제작 순서·주의점 (AI 가 쓴 메모로 표시된다)")
    cannot: list[CannotDo]


class BriefDraft(Strict):
    brief: CreativeBrief


# ------------------------------------------------------------------ JSON Schema for the models
_DROP = {"title", "default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength",
         "maxLength", "pattern", "minItems", "maxItems", "uniqueItems"}


def json_schema(model: "type[BaseModel]") -> dict:
    """Pydantic's schema in the subset structured outputs accept: every object closed (additionalProperties false),
    every property required (optional ones are nullable instead), no numeric/string/array bounds (checked by
    Pydantic on the way back in -- validate() below)."""
    s = model.model_json_schema(by_alias=True)

    def fix(n):
        if isinstance(n, dict):
            for k in list(n):
                if k in _DROP and not (k == "title" and isinstance(n.get(k), dict)):
                    del n[k]
            if n.get("type") == "object" or "properties" in n:
                n["additionalProperties"] = False
                n["required"] = list((n.get("properties") or {}).keys())
            for v in list(n.values()):
                fix(v)
        elif isinstance(n, list):
            for v in n:
                fix(v)
    s = copy.deepcopy(s)
    fix(s)
    return s


def validate(model: "type[BaseModel]", data):
    """Parse model output (dict or JSON text) into the model; raises pydantic.ValidationError / ValueError."""
    if isinstance(data, (str, bytes)):
        return model.model_validate_json(data)
    return model.model_validate(data)
