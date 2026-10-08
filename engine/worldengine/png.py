# -*- coding: utf-8 -*-
"""Minimal stdlib PNG reader/writer (8-bit RGB/RGBA, non-interlaced): check a render is not blank, crop a screenshot."""
from __future__ import annotations

import struct
import zlib


def read(path) -> "tuple[int, int, int, bytes]":
    """-> (width, height, channels, raw pixel bytes row-major)."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, w = 8, b"", None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or interlace:
                raise ValueError("unsupported PNG: depth=%d color=%d interlace=%d" % (depth, ctype, interlace))
            ch = 3 if ctype == 2 else 4
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw, stride = zlib.decompress(idat), w * ch
    out, prev = bytearray(), bytearray(stride)
    for y in range(h):
        f, row = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = row[i - ch] if i >= ch else 0
            b, c = prev[i], prev[i - ch] if i >= ch else 0
            if f == 1:
                row[i] = (row[i] + a) & 255
            elif f == 2:
                row[i] = (row[i] + b) & 255
            elif f == 3:
                row[i] = (row[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += row
        prev = row
    return w, h, ch, bytes(out)


def stats(path, step: int = 7) -> dict:
    """Sampled statistics: distinct colours and luminance spread over the frame, and distinct colours in the
    bottom 5% of rows alone (a mis-sized viewport leaves a flat band there)."""
    w, h, ch, px = read(path)
    cols, lum = set(), []
    for y in range(0, h, step):
        for x in range(0, w, step):
            o = (y * w + x) * ch
            r, g, b = px[o], px[o + 1], px[o + 2]
            cols.add((r, g, b)); lum.append(0.2126 * r + 0.7152 * g + 0.0722 * b)
    mean = sum(lum) / len(lum)
    sd = (sum((v - mean) ** 2 for v in lum) / len(lum)) ** 0.5
    band = {tuple(px[(y * w + x) * ch:(y * w + x) * ch + 3]) for y in range(h - max(1, h // 20), h) for x in range(0, w, step)}
    return {"w": w, "h": h, "distinct": len(cols), "lum_sd": sd, "bottom_distinct": len(band)}


def write(path, w: int, h: int, ch: int, px: bytes) -> None:
    rows = b"".join(b"\x00" + px[y * w * ch:(y + 1) * w * ch] for y in range(h))
    chunk = lambda k, d: struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2 if ch == 3 else 6, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def crop(path, w: int, h: int) -> None:
    """Keep the top-left w x h of the image at path (in place)."""
    W, H, ch, px = read(path)
    if (W, H) == (w, h):
        return
    if W < w or H < h:
        raise ValueError("image %dx%d is smaller than %dx%d" % (W, H, w, h))
    write(path, w, h, ch, b"".join(px[y * W * ch:y * W * ch + w * ch] for y in range(h)))
