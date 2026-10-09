# -*- coding: utf-8 -*-
"""sound_synth -- procedural sound (SPEC M-02): FM notes over granular texture, rendered to a WAV file.
Deterministic (seeded); standard library only.

Axis -> parameter translation (G-02, editable):
  motion    -> tempo_bpm                 density -> note_p (chance of a note on each eighth)
  colour    -> fm_index (brightness)     form    -> fm_ratio (1, 2 harmonic ... 2.7, 3.41 inharmonic)
  texture   -> grain (granular noise)    sound   -> volume          narrative -> bars (length)
The world's own colours become its pitches (hue -> pitch class, lightness -> octave) when it has a palette, so
the same world sounds like its picture looks; otherwise a minor pentatonic from 220 Hz. Length is capped at 12 s.
"""
from __future__ import annotations

import colorsys
import io
import math
import random
import struct
import wave

SR = 16000
MAX_S = 12.0
RATIOS = (1.0, 2.0, 3.0, 1.5, 2.7, 3.41)


def translate(axes: dict) -> dict:
    a = lambda k, d=0.5: float(axes.get(k, d))
    return {"tempo_bpm": round(60 + 100 * a("motion"), 1), "note_p": round(0.12 + 0.8 * a("density"), 4),
            "fm_index": round(0.2 + 5 * a("colour"), 3), "fm_ratio": RATIOS[int(round(5 * a("form")))],
            "grain": round(a("texture"), 3), "volume": round(0.15 + 0.7 * a("sound"), 3),
            "bars": 2 + int(round(6 * a("narrative"))), "seed": 1}


def _palette(world):
    for c in (world.get("rules") or {}).get("constraints") or []:
        if c["kind"] == "palette" and c.get("enabled", True) is not False:
            return list(c["colours"])
    return None


def pitches(world) -> "list[float]":
    pal = _palette(world)
    if not pal:
        return [220.0 * 2 ** (s / 12) for s in (0, 3, 5, 7, 10, 12)]
    out = set()
    for c in pal:
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
        h, l, _s = colorsys.rgb_to_hls(r, g, b)
        out.add(round(220.0 * 2 ** ((round(h * 12) % 12 + 12 * int(l * 2.99) - 12) / 12), 3))
    ps = sorted(out)
    while len(ps) < 3:                                   # one or two colours: add the fifth above
        ps.append(round(ps[-1] * 1.5, 3))
    return ps


def _length(params):
    beats = 4 * int(params["bars"])
    return min(MAX_S, beats * 60.0 / float(params["tempo_bpm"]))


def generate(world: dict, intent: dict, params: dict) -> dict:
    rng = random.Random(int(params.get("seed", 1)) * 104729 + int(intent.get("seed", 0)))
    dur = _length(params)
    n = int(dur * SR)
    buf = [0.0] * n
    step = 60.0 / float(params["tempo_bpm"]) / 2                     # eighth notes
    ps, I, ratio = pitches(world), float(params["fm_index"]), float(params["fm_ratio"])
    notes = 0
    t = 0.0
    while t < dur - 1e-9:
        if rng.random() < float(params["note_p"]):
            f, length = rng.choice(ps), step * rng.choice((1, 1, 2, 3))
            i0, i1 = int(t * SR), min(n, int((t + length) * SR))
            for i in range(i0, i1):
                tt = (i - i0) / SR
                env = min(1.0, tt / 0.005) * math.exp(-tt * 4.0 / length)
                buf[i] += 0.5 * env * math.sin(2 * math.pi * f * tt + I * env * math.sin(2 * math.pi * f * ratio * tt))
            notes += 1
        for _ in range(int(round(6 * float(params["grain"])))):          # grains: 30 ms windowed noise
            g0 = int((t + rng.random() * step) * SR)
            glen = int(0.03 * SR)
            for k in range(glen):
                if g0 + k < n:
                    buf[g0 + k] += 0.12 * (0.5 - 0.5 * math.cos(2 * math.pi * k / glen)) * (rng.random() * 2 - 1)
        t += step
    peak = max(1e-9, max(abs(x) for x in buf))
    k = float(params["volume"]) / peak
    pcm = struct.pack("<%dh" % n, *(int(max(-1.0, min(1.0, x * k)) * 32767) for x in buf))
    out = io.BytesIO()
    w = wave.open(out, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm); w.close()
    return {"artifact": out.getvalue(), "media_type": "audio/wav",
            "notes": "%.2f s, %d notes at %.0f bpm, %d pitches" % (dur, notes, params["tempo_bpm"], len(ps))}


def self_assess(world: dict, artifact) -> dict:
    """The plugin's own check: is the file as long as its tempo and bars say, and not silent?"""
    p = translate((world.get("rules") or {}).get("axes") or {})
    r = wave.open(io.BytesIO(artifact), "rb")
    got = r.getnframes() / r.getframerate()
    frames = r.readframes(r.getnframes()); r.close()
    s = struct.unpack("<%dh" % (len(frames) // 2), frames)
    rms = math.sqrt(sum(x * x for x in s) / max(1, len(s))) / 32767
    want = _length(p)
    score = max(0.0, 1 - abs(got - want) / want) * (1.0 if rms > 0.005 else 0.0)
    return {"score": round(score, 4), "notes": "%.2f s / intended %.2f s, rms %.3f" % (got, want, rms)}


def ports(world: dict, params: dict) -> dict:
    return {"palette": _palette(world) or [], "tempo_bpm": float(params["tempo_bpm"]), "events": ["beat", "note_on"]}


PLUGIN = {"name": "sound_synth", "version": "1", "medium": "sound", "translate": translate, "generate": generate,
          "self_assess": self_assess, "ports": ports}
