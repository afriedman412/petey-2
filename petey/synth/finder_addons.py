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
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pymupdf

CLAIM = 0.5                    # an added box overlapping a finder box this much is the finder's already


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
                for r in circle_rects(pg):
                    rect = [round(float(c), 2) for c in r]
                    if any(_overlap(rect, h) >= CLAIM for h in have):
                        continue
                    out.append({"id": str(nxt), "page": i, "rect": rect, "kind": "radio", "key": rect_key(i, rect),
                                "conf": 0.85, "addon": "circles"})
                    have.append(rect)
                    nxt += 1
        finally:
            doc.close()
    return out
