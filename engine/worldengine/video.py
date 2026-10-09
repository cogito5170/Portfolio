# -*- coding: utf-8 -*-
"""Tour video (SPEC D-05): the artist's camera tour rendered frame by frame by the runtime, encoded with ffmpeg.
Captions (every tour stop has one) become a subtitle track in the MP4 and a .srt file beside it, so the video says
what the tour says, also without sound (XR-11).

    r = tour_video(world, "tour.mp4", tour=None, w=1280, h=720, fps=24)
    -> {"ok", "mp4", "srt", "frames", "seconds", "fps", "size", "encoder", "captions"} | {"ok": False, "reason"}
Frames are stepped at exactly 1/fps of world time, so a slow machine makes the same video, only later.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from worldengine import headless


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def srt(captions: "list[dict]", end_s: float) -> str:
    out = []
    for i, c in enumerate(captions):
        nxt = captions[i + 1]["t"] if i + 1 < len(captions) else end_s
        end = min(c["t"] + float(c.get("seconds") or 4), nxt, end_s)
        if end > c["t"]:
            out.append("%d\n%s --> %s\n%s\n" % (len(out) + 1, _ts(c["t"]), _ts(end), c["text"]))
    return "\n".join(out)


def tour_video(world, out_mp4, tour: "str | None" = None, w: int = 1280, h: int = 720, fps: int = 24, max_s: float = 120) -> dict:
    out_mp4 = Path(out_mp4)
    ff = shutil.which("ffmpeg")
    with tempfile.TemporaryDirectory() as d:
        r = headless.tour_frames(world, Path(d) / "f", tour, w, h, fps, max_s)
        if not r.get("ok"):
            return {"ok": False, "reason": r.get("reason")}
        res = r["result"]
        if res.get("error"):
            return {"ok": False, "reason": res["error"]}
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        sub = out_mp4.with_suffix(".srt")
        sub.write_text(srt(res["captions"], res["seconds"]), encoding="utf-8")
        if not ff:
            kept = out_mp4.with_suffix("")
            shutil.copytree(Path(d) / "f", kept, dirs_exist_ok=True)
            return {"ok": False, "reason": "ffmpeg 이 없다 — 프레임(JPEG)과 자막(.srt)만 남겼다: %s" % kept, "frames": res["frames"], "srt": str(sub)}
        enc = "libx264" if "libx264" in subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout else "mpeg4"
        cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(fps), "-i", str(Path(d) / "f" / "%05d.jpg"), "-i", str(sub),
               "-map", "0:v", "-map", "1:s", "-c:v", enc, "-pix_fmt", "yuv420p", "-c:s", "mov_text", "-metadata:s:s:0", "language=kor",
               "-movflags", "+faststart", str(out_mp4)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            return {"ok": False, "reason": "ffmpeg 실패: " + p.stderr[-300:]}
    return {"ok": True, "mp4": str(out_mp4), "srt": str(sub), "frames": res["frames"], "seconds": res["seconds"], "fps": fps,
            "size": res["size"], "encoder": enc, "tour": res["tour"], "ended": res["ended"], "captions": res["captions"]}


def probe(mp4) -> dict:
    """What the file says about itself (ffprobe), for tests and the artist."""
    fp = shutil.which("ffprobe")
    if not fp:
        return {}
    p = subprocess.run([fp, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,nb_frames:format=duration", "-of", "json", str(mp4)],
                       capture_output=True, text=True)
    return json.loads(p.stdout or "{}")
