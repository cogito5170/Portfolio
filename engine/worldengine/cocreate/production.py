# -*- coding: utf-8 -*-
"""Production plan (CC-06): what it takes to make the realised work, from the world itself. Numbers only where the
world fixes them (dimensions, areas, heights, counts, joints); everything the repository cannot know -- material
cost, weight, build time, power -- is written as "확인 필요", never estimated.

    p = plan(world, notes=())      -> {"bodies", "area", "materials", "sound", "light", "interaction", "devices", "unknown", "notes"}
    md = markdown(p)
"""
from __future__ import annotations

from worldengine import footprint as FP

CHECK = "확인 필요"
UNKNOWN = ("재료비", "무게 (재료 밀도가 세계에 없다)", "시공·제작 기간", "전기 용량", "설치 장소의 하중·안전 기준")


def _walk(es):
    for e in es or []:
        if isinstance(e, dict):
            yield e
            yield from _walk(e.get("children"))


def _height(e):
    t = e.get("type")
    if t == "box":
        s = e.get("size", [1, 1, 1])
        return s if isinstance(s, (int, float)) else s[2]
    if t in ("cylinder", "cone", "capsule", "person", "arch"):
        return e.get("height", {"person": 1.68, "arch": 2.4}.get(t, 1))
    if t == "sphere":
        return 2 * e.get("radius", 0.5)
    if t == "torus":
        return 2 * e.get("tube", 0.1)
    if t == "text":
        return (e.get("size") or [2, 0.5])[1]
    return None


def plan(world: dict, notes=()) -> dict:
    fps = {f["id"]: f for f in FP.footprints(world) if f.get("id")}
    mats = world.get("materials") or {}
    bodies, by_mat = [], {}
    for e in _walk(world.get("entities")):
        f = fps.get(e.get("id"))
        if f is None:
            continue
        m = e.get("material")
        label = m if isinstance(m, str) else ((m or {}).get("color") if isinstance(m, dict) else None)
        colour = (mats.get(m) or {}).get("color") if isinstance(m, str) else label
        bodies.append({"id": e.get("id"), "type": e.get("type"), "width_m": round(f["w"], 3), "depth_m": round(f["d"], 3),
                       "height_m": None if _height(e) is None else round(_height(e), 3), "footprint_m2": round(f["area"], 3),
                       "at_m": [round(v, 3) for v in (e.get("pos") or [0, 0, 0])], "material": label, "colour": colour})
        if label:
            b = by_mat.setdefault(label, {"material": label, "colour": colour, "bodies": 0, "footprint_m2": 0.0})
            b["bodies"] += 1; b["footprint_m2"] = round(b["footprint_m2"] + f["area"], 3)
    ents = list(_walk(world.get("entities")))
    sounds = [{"id": e.get("id"), "caption": e.get("caption"), "own_recording": isinstance(e.get("src"), str)} for e in ents if e.get("type") == "sound"]
    lights = [{"id": e.get("id"), "kind": e.get("kind"), "colour": e.get("color"), "intensity": e.get("intensity")} for e in ents if e.get("type") == "light"]
    inputs = sorted({b.get("input") for e in ents for b in e.get("behaviors") or [] if isinstance(b, dict) and b.get("type") == "react"})
    trig = sorted({t.get("on") for e in ents for t in e.get("triggers") or [] if isinstance(t, dict)})
    robots = [{"id": e.get("id"), "joints": len((e.get("chain") or {}).get("joints") or [])} for e in ents if (e.get("type") or "").startswith("robot")]
    devices = ["관객의 브라우저 (PC·휴대폰) — 웹 3D 세계"]
    devices += ["관객 기기의 마이크 — 관객이 켤 때만 (소리 크기 하나만 읽음, 저장·전송 없음)"] if "mic" in inputs else []
    devices += ["관객 기기의 카메라 — 관객이 켤 때만 (화면 앞 움직임의 양 하나만 읽음, 저장·전송 없음)"] if "camera" in inputs else []
    devices += ["스피커 또는 이어폰 — 소리 %d개 (모두 자막 있음)" % len(sounds)] if sounds else []
    devices += ["로봇 팔 %s — 실제 구동은 작가 승인과 장치 한계 검사 뒤에만" % ", ".join("%s(관절 %d)" % (r["id"], r["joints"]) for r in robots)] if robots else []
    return {"bodies": bodies, "area": FP.area_table(world), "bounds_m": world.get("bounds"), "materials": sorted(by_mat.values(), key=lambda m: -m["footprint_m2"]),
            "sound": sounds, "light": lights, "interaction": {"inputs": inputs, "triggers": trig}, "devices": devices,
            "unknown": [{"what": u, "value": CHECK} for u in UNKNOWN], "notes": [{"text": n, "by": "AI 메모 (측정값 아님)"} for n in notes]}


def markdown(p: dict, title: str = "제작 지침") -> str:
    a = p["area"]
    out = ["# " + title, "", "## 몸 (치수는 세계에서 그대로)", "", "| id | 종류 | 가로 m | 세로 m | 높이 m | 바닥 면적 m² | 위치 m | 재료 |", "|---|---|---|---|---|---|---|---|"]
    for b in p["bodies"]:
        out.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (b["id"], b["type"], b["width_m"], b["depth_m"], b["height_m"] if b["height_m"] is not None else "-",
                                                             b["footprint_m2"], b["at_m"], b["material"] or "-"))
    out += ["", "## 면적", "", "- 몸이 덮은 바닥: %s m² (겹침 제외), 합계 %s m² (겹침 포함)" % (a["covered_m2"], a["sum_m2"]),
            "- 바닥면(plane): %s m², 부지: %s m², 덮인 비율: %s" % (a["floors_m2"], a["site_m2"], a["coverage"])]
    if p["materials"]:
        out += ["", "## 재료별", ""] + ["- %s (%s): 몸 %d개, 바닥 %s m²" % (m["material"], m["colour"] or "-", m["bodies"], m["footprint_m2"]) for m in p["materials"]]
    out += ["", "## 장비", ""] + ["- " + d for d in p["devices"]]
    if p["interaction"]["inputs"] or p["interaction"]["triggers"]:
        out += ["- 반응: 입력 %s, 트리거 %s" % (", ".join(p["interaction"]["inputs"]) or "없음", ", ".join(p["interaction"]["triggers"]) or "없음")]
    out += ["", "## 모르는 것 (추정하지 않음)", ""] + ["- %s: %s" % (u["what"], u["value"]) for u in p["unknown"]]
    if p["notes"]:
        out += ["", "## 제작 메모 (AI 가 쓴 것 — 측정값이 아니다)", ""] + ["- " + n["text"] for n in p["notes"]]
    return "\n".join(out) + "\n"
