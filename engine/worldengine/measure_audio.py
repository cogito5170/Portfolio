# -*- coding: utf-8 -*-
"""Independent sound measurer for V-04 on the sound medium. Reads a WAV and estimates style axes from what is heard;
it never imports or calls the plugin that made it.

Method (fixed before any sound numbers were looked at; constants are part of the method):
  frames   = 20 ms, energy = mean square of the frame
  onset    = a frame whose energy is > 1.8 x the previous frame's and > 2 % of the loudest frame's,
             at least 60 ms after the previous onset
  sound    = rms of the whole file / 0.25                                            clipped to [0,1]
  colour   = zero crossings per second / 2 / 2000 Hz (brightness)                    clipped to [0,1]
  density  = onsets per second / 4                                                   clipped to [0,1]
  motion   = (tempo - 60) / 100, tempo from the autocorrelation of the onset train over eighth-note lags
             0.1875..0.5 s (60..160 bpm), each onset widened to +-1 frame, taking the SHORTEST lag within 10 % of
             the best (its multiples score as well), then the mean of the matched onset intervals at that lag
             (finer than one frame); not reported with fewer than 4 onsets or when no two onsets are an eighth-note
             lag apart (no beat to hear)                                                       clipped to [0,1]
  (Changed once, after the known-signal test and the first numbers: the first version used exact frames and the
   best lag, so 0.25 s onsets -- 12.5 frames -- split between two lags and the 0.5 s multiple won: 60 bpm for 120.)
Axes it cannot hear (form, texture, narrative) are not reported.
"""
from __future__ import annotations

import io
import math
import struct
import wave

FRAME_S = 0.02


def _samples(wav_bytes: bytes):
    r = wave.open(io.BytesIO(wav_bytes), "rb")
    sr, ch, sw, n = r.getframerate(), r.getnchannels(), r.getsampwidth(), r.getnframes()
    raw = r.readframes(n); r.close()
    if sw != 2:
        raise ValueError("16-bit PCM only")
    s = struct.unpack("<%dh" % (len(raw) // 2), raw)
    return [x / 32768 for x in s[::ch]], sr


def axes(wav_bytes: bytes) -> dict:
    s, sr = _samples(wav_bytes)
    if not s:
        return {}
    dur = len(s) / sr
    cl = lambda x: max(0.0, min(1.0, x))  # noqa: E731
    rms = math.sqrt(sum(x * x for x in s) / len(s))
    zc = sum(1 for a, b in zip(s, s[1:]) if (a < 0) != (b < 0))
    fl = int(FRAME_S * sr)
    E = [sum(x * x for x in s[i:i + fl]) / fl for i in range(0, len(s) - fl + 1, fl)]
    top = max(E) if E else 0
    onsets, last = [], -1e9
    for i in range(1, len(E)):
        t = i * FRAME_S
        if E[i] > 1.8 * E[i - 1] and E[i] > 0.02 * top and t - last >= 0.06:
            onsets.append(i); last = t
    out = {"sound": cl(rms / 0.25), "colour": cl(zc / dur / 2 / 2000), "density": cl(len(onsets) / dur / 4),
           "onsets": len(onsets), "seconds": round(dur, 3)}
    on = set(onsets)
    lags = range(int(round(0.1875 / FRAME_S)), int(round(0.5 / FRAME_S)) + 1)
    score = {lag: sum(1 for i in onsets if {i + lag - 1, i + lag, i + lag + 1} & on) for lag in lags} if len(onsets) >= 4 else {}
    best = max(score.values(), default=0)
    if best > 0:
        lag_best = min(lag for lag in lags if score[lag] >= 0.9 * best)
        gaps = [d for i in onsets for d in (lag_best - 1, lag_best, lag_best + 1) if (i + d) in on]
        bpm = 60 / (2 * (sum(gaps) / len(gaps)) * FRAME_S)
        out["tempo_bpm"] = round(bpm, 1)
        out["motion"] = cl((bpm - 60) / 100)
    return out


MEASURED = ("sound", "colour", "density", "motion")


def distinctness(results: "list[dict]", worlds: "dict[str, dict]") -> "list[dict]":
    """results: [{"world", "wav"}]. Measured axes, RMS distance to every world's axes on the axes heard, own rank."""
    rows = []
    for r in results:
        m = axes(r["wav"])
        d = {}
        for name, w in worlds.items():
            wa = (w.get("rules") or {}).get("axes") or {}
            keys = [k for k in MEASURED if k in m and k in wa]
            d[name] = math.sqrt(sum((m[k] - wa[k]) ** 2 for k in keys) / len(keys)) if keys else None
        ranked = sorted((k for k in d if d[k] is not None), key=lambda k: d[k])
        rows.append({"world": r["world"], "measured": m, "distance": d, "nearest": ranked[0] if ranked else None,
                     "own_rank": ranked.index(r["world"]) + 1 if r["world"] in ranked else None})
    return rows
