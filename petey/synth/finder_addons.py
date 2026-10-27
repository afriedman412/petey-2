"""Additive finder rules: boxes the finder (step2flat) misses, added on top of its output without changing it, so a
minor finder version (`boxes.FINDER_MINOR`) adds boxes without re-keying every cached finder run and class map
(Andrew, 2026-10-15: "can we do like a minor update ... so we don't demand a full rerun?").

A rule here only ever adds: a box that overlaps one the finder already has is left out, and added boxes are numbered
after the finder's, so every id the finder gave (case boxes, class maps, Add / remove dismissals `b<id>`) still points
at the same box. Rules that would change or remove the finder's boxes belong in step2flat with a full version bump.

  circles (minor 1)  radio circles drawn as Bezier curves (CMS-855A / 855I, OSHA 301): a stroked path of 4-8 curves,
                     checkbox-sized and nearly square; not a filled outline (DS-11's reversed-out letter O) and not a
                     ring with a dark dot inside (CA 540's printed markers). On 132 validated forms: 372 of 375 on a
                     real field, 362 of the 678 option boxes the finder missed recovered.

Minor 2 (2026-10-27; Andrew: "we aren't even detecting them and ruling them out", "we are just missing a lot of
[checkboxes]"). Read off the PDF's own drawings and characters, not the 150 dpi raster. On 47 benchmark forms (6 a
sector, pages <= 2, the originals' widgets as truth): text fields 84% -> 91%, option boxes 89% -> 94%; 703 boxes
added, 274 on a widget (the rest mostly section and table rulings, some signature lines with no widget). Candidates
for the screens that follow, not verdicts.
  glyphs             a character that prints a hollow square, judged by rendering it, whatever its code point
                     (Wingdings 'r', ZapfDingbats U+274F were outside step2flat's glyph list)
  squares            square rect paths 3.5-16 pt: the raster reader's 5 pt floor on the white inside drops ~5.5 pt
                     boxes; a dark fill with no stroke is a bullet
  underlines         horizontal strokes and typed underscore runs: the raster reader drops a line that "separates two
                     regions" (one end touching a rule or a printed '/'), and a run fused to its label (`Name:____`)
                     scores as printed text; the box is the open band above the line
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pymupdf

CLAIM = 0.5                    # an added box overlapping a finder box this much is the finder's already
SYMBOL_FONTS = ("ding", "wingding", "webding", "symbol")
LINE_BAND = 14.0               # pt: the tallest band above an underline taken as its field
LINE_MIN_W = 18.0              # pt: a shorter stroke is not a line to write on
LINE_MIN_H = 6.0               # pt: a band squeezed shorter than this sits between stacked rules (a table's ruling)


def circle_rects(page) -> list[pymupdf.Rect]:
    drawings = page.get_drawings()
    dots = [pymupdf.Rect(d["rect"]) for d in drawings
            if d.get("fill") is not None and "f" in (d.get("type") or "") and sum(d["fill"][:3]) / 3 < 0.5
            and pymupdf.Rect(d["rect"]).width < 12]
    rs = []
    for d in drawings:
        items = d.get("items") or []
        if not (4 <= len(items) <= 8) or any(it[0] != "c" for it in items) or "s" not in (d.get("type") or ""):
            continue
        r = pymupdf.Rect(d["rect"])
        if not (5 <= r.width <= 16 and 5 <= r.height <= 16 and abs(r.width - r.height) <= 1.5):
            continue
        if any(r.contains(x) and x.width < 0.8 * r.width for x in dots):
            continue
        rs.append(r)
    rs.sort(key=lambda r: -r.width * r.height)
    out: list[pymupdf.Rect] = []
    for r in rs:                   # a circle inside another (a ring with its dot) counts once, as the outer one
        if any(o.contains(r) or (abs(o.x0 - r.x0) < 1 and abs(o.y0 - r.y0) < 1) for o in out):
            continue
        out.append(r)
    return out


def _is_shape_char(c: str, symbol_font: bool) -> bool:
    o = ord(c)
    return symbol_font or 0x25A0 <= o <= 0x25FF or 0x2610 <= o <= 0x2612 or 0x2700 <= o <= 0x27BF \
        or 0xE000 <= o <= 0xF8FF


def glyph_square_rects(page) -> list[pymupdf.Rect]:
    """Characters that print a hollow square: a symbol-font, shape-block or private-use character whose ink, rendered,
    is a ring around an empty middle (a filled square, a check mark or a bullet is not)."""
    out = []
    for b in page.get_text("rawdict").get("blocks", []):
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                sym = any(k in sp["font"].lower() for k in SYMBOL_FONTS)
                for ch in sp.get("chars", []):
                    c = ch["c"]
                    if not c.strip() or (c.isalnum() and not sym) or not _is_shape_char(c, sym):
                        continue
                    r = pymupdf.Rect(ch["bbox"])
                    if not (3 <= r.width <= 24 and r.height <= 40):
                        continue
                    cy = (r.y0 + r.y1) / 2       # the bbox is the font's line height; the square is the advance width
                    sq = pymupdf.Rect(r.x0 - 1, cy - r.width / 2 - 1, r.x1 + 1, cy + r.width / 2 + 1)
                    pix = page.get_pixmap(clip=sq, dpi=300, colorspace=pymupdf.csGRAY)
                    ink = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w) < 128
                    ys, xs = np.nonzero(ink)
                    if len(xs) < 8:
                        continue
                    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
                    w, h = x1 - x0 + 1, y1 - y0 + 1
                    if w < 6 or h < 6 or not 0.6 <= w / h <= 1.6:
                        continue
                    a = ink[y0:y1 + 1, x0:x1 + 1]
                    middle = ink[y0 + h // 4:y1 - h // 4 + 1, x0 + w // 4:x1 - w // 4 + 1]
                    edges = np.mean([a[:2].any(axis=0).mean(), a[-2:].any(axis=0).mean(),
                                     a[:, :2].any(axis=1).mean(), a[:, -2:].any(axis=1).mean()])
                    if middle.mean() < 0.05 and edges > 0.8:
                        s = 300 / 72
                        out.append(pymupdf.Rect(sq.x0 + x0 / s, sq.y0 + y0 / s, sq.x0 + (x1 + 1) / s, sq.y0 + (y1 + 1) / s))
    return out


def square_rects(page) -> list[pymupdf.Rect]:
    """Square rect paths of checkbox size, stroked or lightly filled; a dark fill with no stroke is a bullet."""
    out = []
    for d in page.get_drawings():
        f = d.get("fill")
        stroked = d.get("color") is not None and "s" in (d.get("type") or "")
        if f is not None and sum(f[:3]) / 3 < 0.5 and not stroked:
            continue
        for it in d.get("items") or []:
            if it[0] != "re":
                continue
            r = pymupdf.Rect(it[1])
            if 3.5 <= r.width <= 16 and 3.5 <= r.height <= 16 and abs(r.width - r.height) <= 2:
                out.append(r)
    return out


def _h_strokes(page) -> list[list[float]]:
    """[x0, x1, y] of every horizontal stroke (lines, hairline rects) and typed underscore run (3+), collinear
    touching pieces joined."""
    segs = []
    for d in page.get_drawings():
        for it in d.get("items") or []:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 0.8 and abs(it[1].x - it[2].x) >= 3:
                segs.append([min(it[1].x, it[2].x), max(it[1].x, it[2].x), (it[1].y + it[2].y) / 2])
            elif it[0] == "re":
                r = pymupdf.Rect(it[1])
                if r.height < 1.5 and r.width >= 3:
                    segs.append([r.x0, r.x1, (r.y0 + r.y1) / 2])
    for b in page.get_text("rawdict").get("blocks", []):
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                run = []
                for ch in sp.get("chars", []) + [None]:
                    if ch is not None and ch["c"] == "_":
                        run.append(pymupdf.Rect(ch["bbox"]))
                        continue
                    if len(run) >= 3:            # the underscore's stroke sits near the bottom of its bbox
                        segs.append([run[0].x0, run[-1].x1, run[0].y1 - 0.15 * run[0].height])
                    run = []
    segs.sort(key=lambda s: (round(s[2]), s[0]))
    out: list[list[float]] = []
    for s in segs:
        if out and abs(out[-1][2] - s[2]) < 1 and s[0] - out[-1][1] <= 1.5:
            out[-1][1] = max(out[-1][1], s[1])
        else:
            out.append(list(s))
    return out


def underline_rects(page) -> list[pymupdf.Rect]:
    """The band above each line you write on, up to LINE_BAND tall, capped by a rule or text above it; a word on or
    near the line splits it (`Name ______ Date ______`)."""
    hs = _h_strokes(page)
    words = [pymupdf.Rect(w[:4]) for w in page.get_text("words") if "___" not in w[4]]
    out = []
    for x0, x1, y in hs:
        if x1 - x0 < LINE_MIN_W:
            continue
        top = y - LINE_BAND
        for a0, a1, ay in hs:
            if y - LINE_BAND < ay < y - 1 and min(a1, x1) - max(a0, x0) > 0.5 * (x1 - x0):
                top = max(top, ay + 0.5)
        if y - top < LINE_MIN_H:
            continue
        segs = [(x0, x1)]
        for w in words:
            if w.x1 <= x0 or w.x0 >= x1 or w.y1 <= top or w.y0 >= y:
                continue
            if w.y1 >= y - 4 or (w.y0 + w.y1) / 2 > top + 0.5 * (y - top):
                segs = [s for a0, a1 in segs for s in ((a0, min(a1, w.x0 - 1)), (max(a0, w.x1 + 1), a1)) if s[1] > s[0]]
            else:
                top = max(top, w.y1 + 0.5)
        for a0, a1 in segs:
            r = pymupdf.Rect(a0, top, a1, y) & page.rect
            if r.width >= LINE_MIN_W and r.height >= LINE_MIN_H:
                out.append(r)
    return out


# (rule, finder kind, conf) in the order they claim space: a mark before the line it may sit on
RULES = (("circles", circle_rects, "radio", 0.85), ("glyphs", glyph_square_rects, "checkbox", 0.75),
         ("squares", square_rects, "checkbox", 0.8), ("underlines", underline_rects, "text", 0.6))


def _overlap(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    if i <= 0:
        return 0.0
    return i / max(min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])), 1e-6)


def added_boxes(pdf_path: str | Path, boxes: list[dict], rect_key) -> list[dict]:
    """The boxes the additive rules find that the finder's `boxes` do not have, numbered after them. The page is
    flattened as the finder flattens it (widget appearances baked in), so a radio drawn by its widget is seen too."""
    from step2flat.pipeline import flatten
    nxt = max((int(b["id"]) for b in boxes), default=0) + 1
    out = []
    with tempfile.TemporaryDirectory() as td:
        flat = os.path.join(td, "flat.pdf")
        flatten(str(pdf_path), flat)
        doc = pymupdf.open(flat)
        try:
            for i, pg in enumerate(doc, start=1):
                have = [b["rect"] for b in boxes if b["page"] == i]
                for rule, find, kind, conf in RULES:
                    for r in find(pg):
                        rect = [round(float(c), 2) for c in r]
                        if any(_overlap(rect, h) >= CLAIM for h in have):
                            continue
                        out.append({"id": str(nxt), "page": i, "rect": rect, "kind": kind, "key": rect_key(i, rect),
                                    "conf": conf, "addon": rule})
                        have.append(rect)
                        nxt += 1
        finally:
            doc.close()
    return out
