# -*- coding: utf-8 -*-
"""World diff (D-04) -- also the "이렇게 이해했다" text the artist sees before anything is applied (A-02)."""
from __future__ import annotations


def _walk(es, out=None):
    out = {} if out is None else out
    for i, e in enumerate(es or []):
        out[e.get("id") or "#%d:%s" % (i, e.get("type"))] = e
        _walk(e.get("children"), out)
    return out


def diff(a: dict, b: dict) -> dict:
    ax_a, ax_b = (a.get("rules") or {}).get("axes") or {}, (b.get("rules") or {}).get("axes") or {}
    axes = {k: [ax_a.get(k), ax_b.get(k)] for k in sorted(set(ax_a) | set(ax_b)) if ax_a.get(k) != ax_b.get(k)}
    ea, eb = _walk(a.get("entities")), _walk(b.get("entities"))
    added = sorted(set(eb) - set(ea))
    removed = sorted(set(ea) - set(eb))
    edited = {}
    for k in sorted(set(ea) & set(eb)):
        fa, fb = {f: v for f, v in ea[k].items() if f != "children"}, {f: v for f, v in eb[k].items() if f != "children"}
        ch = sorted(f for f in set(fa) | set(fb) if fa.get(f) != fb.get(f))
        if ch:
            edited[k] = {f: [fa.get(f), fb.get(f)] for f in ch}
    ma, mb = a.get("materials") or {}, b.get("materials") or {}
    mats = sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k))
    ca, cb = {c["id"] for c in a.get("concepts") or []}, {c["id"] for c in b.get("concepts") or []}
    other = sorted(k for k in set(a) | set(b) if k not in ("rules", "entities", "materials", "concepts") and a.get(k) != b.get(k))
    ra, rb = dict(a.get("rules") or {}), dict(b.get("rules") or {})
    ra.pop("axes", None); rb.pop("axes", None)
    return {"axes": axes, "entities_added": added, "entities_removed": removed, "entities_edited": edited,
            "materials_changed": mats, "concepts_added": sorted(cb - ca), "concepts_removed": sorted(ca - cb),
            "constraints_changed": ra != rb, "other_fields": other}


AXIS_KO = {"density": "밀도", "colour": "색", "form": "형태", "texture": "질감", "motion": "움직임", "sound": "소리", "narrative": "서사"}


def summary_ko(d: dict) -> "list[str]":
    L = []
    for k, (x, y) in d["axes"].items():
        L.append("%s 축 %s → %s" % (AXIS_KO.get(k, k), "없음" if x is None else "%.2f" % x, "없음" if y is None else "%.2f" % y))
    if d["entities_added"]:
        L.append("추가: " + ", ".join(d["entities_added"]))
    if d["entities_removed"]:
        L.append("제거: " + ", ".join(d["entities_removed"]))
    for k, f in d["entities_edited"].items():
        L.append("수정 %s: %s" % (k, ", ".join(f)))
    if d["materials_changed"]:
        L.append("재질: " + ", ".join(d["materials_changed"]))
    if d["concepts_added"]:
        L.append("개념 추가: " + ", ".join(d["concepts_added"]))
    if d["concepts_removed"]:
        L.append("개념 제거: " + ", ".join(d["concepts_removed"]))
    if d["constraints_changed"]:
        L.append("세계 규칙(제약) 변경")
    if d["other_fields"]:
        L.append("기타: " + ", ".join(d["other_fields"]))
    return L or ["바뀐 것 없음"]
