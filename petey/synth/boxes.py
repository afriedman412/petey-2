"""Fillable boxes from the page, not from the AcroForm layer.

Case generation must take nothing from the widget layer (Andrew,
2026-09-30): not names, not export values, not types, not even where the
boxes are. `find_boxes` renders the blank as a printed page (step2flat's
flatten: widget appearances baked in, widgets stripped) and runs the
flat-form finder on it, so an AcroForm blank and a flat blank go through the
same path. Each box is `{id, page, rect, kind}` with `kind` the finder's
guess (text / checkbox / radio); the model that classifies boxes sees ids
and rects only.

`match_rect` is the join used everywhere a page box has to be lined up with
something else that carries a rect (a widget at fill time, a blueprint
field at scoring time): best overlap, not first hit, because neighbouring
widgets can share a strip (526EZ's disability table rows).

Cached per blank under `runs/_gen_cache/boxes/`; the finder takes 15-20 s a
page.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

from petey.paths import REPO, RUNS

CACHE_DIR = RUNS / "_gen_cache" / "boxes"
FINDER_VERSION = "step2flat-1"


def _rect_key(page: int, rect) -> str:
    """A stable string key for a (page, rect): what cases and class maps are keyed by."""
    x0, y0, x1, y1 = rect
    return f"p{page}:{x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}"


def rect_key(box: dict) -> str:
    return _rect_key(box["page"], box["rect"])


def parse_rect_key(key: str) -> tuple[int, list[float]]:
    p, r = key.split(":", 1)
    return int(p[1:]), [float(c) for c in r.split(",")]


def find_boxes(pdf_path: str | Path, cache_dir: Path = CACHE_DIR) -> list[dict]:
    """The page's fillable boxes, in reading order, ids 1..n across the form."""
    pdf_path = Path(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    h = hashlib.sha256(pdf_bytes + b"\x00boxes\x00" + FINDER_VERSION.encode()).hexdigest()
    cp = cache_dir / f"{h}.json"
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from step2flat import pipeline
    kept, _scored = pipeline.run(str(pdf_path))
    rows = sorted(kept, key=lambda r: (int(r["page"]), round(r["rect"][1] / 4), r["rect"][0]))
    boxes = []
    for i, r in enumerate(rows, start=1):
        page = int(r["page"]) + 1          # the finder counts pages from 0
        rect = [round(float(c), 2) for c in r["rect"]]
        boxes.append({"id": str(i), "page": page, "rect": rect, "kind": r["kind"],
                      "key": _rect_key(page, rect), "conf": round(float(r.get("conf", 0)), 2)})
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(boxes, indent=1))
    return boxes


def render_numbered_pages(pdf_path: str | Path, boxes: list[dict], dpi: int = 150) -> dict[int, bytes]:
    """Page PNGs with a numbered red rectangle on every finder box, drawn on
    the blank's own page so the rectangles sit on the page's geometry. Only
    pages that carry boxes are rendered. What the model sees, in both the
    classifier and the blind generator."""
    import pymupdf
    by_page: dict[int, list[dict]] = {}
    for bx in boxes:
        by_page.setdefault(bx["page"], []).append(bx)
    doc = pymupdf.open(str(pdf_path))
    out: dict[int, bytes] = {}
    try:
        for page_no, page in enumerate(doc, start=1):
            if page_no not in by_page:
                continue
            for bx in by_page[page_no]:
                r = pymupdf.Rect(*bx["rect"])
                page.draw_rect(r, color=(1, 0, 0), width=0.6)
                fs = 5 if r.height < 9 else 6
                page.insert_text(pymupdf.Point(r.x0 + 0.8, r.y0 + fs + 0.4), bx["id"],
                                 fontsize=fs, color=(1, 0, 0), fontname="helv")
            out[page_no] = page.get_pixmap(dpi=dpi).tobytes("png")
    finally:
        doc.close()
    return out


def overlap(a, b) -> float:
    """Intersection over the smaller rect's area."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    area_a = max((a[2] - a[0]) * (a[3] - a[1]), 1e-6)
    area_b = max((b[2] - b[0]) * (b[3] - b[1]), 1e-6)
    return inter / min(area_a, area_b)


def match_rect_scored(rect, candidates: list[dict], min_overlap: float = 0.5) -> list[tuple[float, dict]]:
    """Every candidate at or above `min_overlap`, best first. The caller sees
    ties (two candidates at 1.0 when both are contained) instead of having
    them resolved by list order."""
    scored = [(overlap(rect, c["rect"]), c) for c in candidates]
    scored = [(s, c) for s, c in scored if s >= min_overlap]
    scored.sort(key=lambda t: -t[0])
    return scored


def match_rect(rect, candidates: list[dict], min_overlap: float = 0.5) -> Optional[dict]:
    """The candidate whose rect best overlaps `rect` (each candidate carries
    `rect`), or None below `min_overlap` of the smaller area."""
    best, score = None, 0.0
    for c in candidates:
        s = overlap(rect, c["rect"])
        if s > score:
            best, score = c, s
    return best if score >= min_overlap else None
