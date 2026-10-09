# -*- coding: utf-8 -*-
"""License table (SPEC R-03): what a work is made of, under which license, and whether commercial use is known to
be allowed. Facts only from what the repository holds; where it does not know, it says "확인 필요" (check needed)
-- the platform does not make legal judgements for the artist.

    table()            every component the platform ships or calls
    for_world(world)   only what a published work actually contains or used (runtime, three.js, its plugins)
    markdown(rows)     the same as a table (written as LICENSES.md into published sites and preservation bundles)

A plugin may declare PLUGIN["license"] and PLUGIN["uses_model"] ({"provider", "model", "terms"}); undeclared means
"이 저장소와 같음" and "AI 모델 없음 (절차적)" only when the plugin says it is procedural.
"""
from __future__ import annotations

from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
REPO = ENGINE.parent

YES, NO, CHECK = "가능", "불가", "확인 필요"


def repo_license() -> dict:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        f = REPO / name
        if f.is_file():
            first = next((l.strip() for l in f.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()), "")
            return {"license": first[:80], "file": name, "commercial": CHECK if "MIT" not in first and "Apache" not in first else YES}
    return {"license": "없음 — 저장소 주인이 정할 일", "file": None, "commercial": "정해지지 않음"}


def _three():
    lic = ENGINE / "vendor" / "three" / "LICENSE"
    first = lic.read_text(encoding="utf-8").splitlines()[0].strip() if lic.is_file() else "?"
    return {"component": "three.js r170 (vendor/three)", "kind": "runtime library", "license": first.replace("The ", "").replace(" License", ""),
            "commercial": YES if "MIT" in first else CHECK, "shipped": True,
            "notes": "MIT: 배포할 때 저작권 고지(vendor/three/LICENSE)를 함께 둔다 — 사이트·보존 묶음에 그대로 들어간다"}


def table() -> "list[dict]":
    from worldengine import plugins as PL
    from worldengine.studio import config
    own = repo_license()
    rows = [_three(),
            {"component": "worldengine core + runtime (engine/worldengine, engine/runtime)", "kind": "platform", "license": own["license"],
             "commercial": own["commercial"], "shipped": True, "notes": "저장소 자체의 라이선스"},
            {"component": "kinematics/ (reference URDF parser, FK)", "kind": "platform", "license": own["license"], "commercial": own["commercial"],
             "shipped": False, "notes": "같은 저장소; 사이트에는 들어가지 않는다 (Python 쪽 검증용)"},
            {"component": "render3d 에서 온 파일 (cogito5170/se_new, PROVENANCE.md)", "kind": "platform", "license": "출처 저장소의 라이선스",
             "commercial": CHECK, "shipped": False, "notes": "출처 커밋과 파일별 blob 은 PROVENANCE.md"}]
    for name, p in sorted(PL.discover().items()):
        rows.append(plugin_row(name, p, own))
    rows.append({"component": "스튜디오 대화 조수: %s (Anthropic API)" % config.model(), "kind": "AI model (studio only)",
                 "license": "Anthropic 이용약관", "commercial": CHECK, "shipped": False,
                 "notes": "작품 파일에는 들어가지 않는다; 조수가 제안하고 작가가 적용한 변경은 판 기록에 남는다. 상업적 이용 조건은 공급자 약관을 볼 것"})
    import os
    rows.append({"component": "공동 창작 모델: Google Gemini API (%s)" % (os.environ.get("WE_GEMINI_MODEL") or "설정 안 됨"), "kind": "AI model (studio only)",
                 "license": "Google 이용약관", "commercial": CHECK, "shipped": False,
                 "notes": "렌즈·큐레이터 역할에 쓸 때만. 작품 파일에는 들어가지 않는다; 실행마다 어느 역할에 어느 모델을 썼는지 기록된다 (CC-08)"})
    rows.append({"component": "pydantic (공동 창작 스키마)", "kind": "library (studio only)", "license": "MIT", "commercial": YES, "shipped": False,
                 "notes": "스튜디오의 공동 창작에서만 쓴다; 공개 사이트·보존 묶음에는 들어가지 않는다"})
    rows.append({"component": "Chromium · ffmpeg", "kind": "tool (headless render, tour video)", "license": "각 도구의 라이선스", "commercial": CHECK,
                 "shipped": False, "notes": "작업 도구일 뿐 결과물에 들어가지 않는다"})
    rows.append({"component": "글꼴 (Noto Sans KR 등)", "kind": "font", "license": "보는 기기에 설치된 글꼴", "commercial": CHECK, "shipped": False,
                 "notes": "이름으로만 부른다; 저장소·사이트에 글꼴 파일이 없다"})
    return rows


def plugin_row(name, p, own=None) -> dict:
    own = own or repo_license()
    m = p.get("uses_model")
    return {"component": "plugin %s v%s (%s)" % (name, p.get("version"), p.get("medium")), "kind": "generator",
            "license": p.get("license") or own["license"], "commercial": own["commercial"] if not p.get("license") else CHECK,
            "shipped": True, "uses_model": m,
            "notes": ("AI 모델: %s %s (%s)" % (m.get("provider"), m.get("model"), m.get("terms", "약관 확인 필요"))) if m
            else ("AI 모델 없음 (절차적)" if p.get("procedural") else "AI 모델 사용 여부를 밝히지 않음 — 확인 필요")}


def for_world(world: dict) -> "list[dict]":
    from worldengine import plugins as PL
    own = repo_license()
    P = PL.discover()
    used = sorted({e.get("plugin") for e in world.get("expressions") or [] if e.get("plugin")})
    rows = [r for r in table() if r["kind"] in ("runtime library",) or r["component"].startswith("worldengine core")]
    for n in used:
        rows.append(plugin_row(n, P[n], own) if n in P else {"component": "plugin %s" % n, "kind": "generator", "license": "?",
                                                             "commercial": CHECK, "shipped": False, "notes": "이 기계에 없는 플러그인"})
    return rows


def markdown(rows, title="라이선스 표 (R-03)") -> str:
    out = ["# " + title, "", "| 구성 요소 | 종류 | 라이선스 | 상업적 이용 | 결과물에 포함 | 메모 |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append("| %s | %s | %s | %s | %s | %s |" % (r["component"], r["kind"], r["license"], r["commercial"], "예" if r["shipped"] else "아니오", r["notes"]))
    out += ["", "플랫폼은 법적 판단을 하지 않는다. '확인 필요' 는 그 조건을 이 저장소가 모른다는 뜻이다."]
    return "\n".join(out) + "\n"
