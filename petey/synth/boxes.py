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

# The finder's version (Andrew, 2026-10-01: a finder change is a versioned event, not a regeneration of the
# library; every blueprint, run and case set records the finder it was built with, and "rebuild it with the
# current finder" is the first step when a form misbehaves). Three parts:
#   FINDER_LABEL     bumped by hand when the finder's behaviour is meant to change (the comb tier, 2026-09-30);
#   FINDER_CODE_SHA  the sha of step2flat/*.py the label describes: code edited without a bump makes the version
#                    `<label>+code<sha>`, so caches re-key instead of serving boxes the code no longer produces;
#   FINDER_ENV       pymupdf (drawings, words) and tesseract (the raster reader erases OCR'd text before it looks
#                    for boxes) as the label was read; another environment makes the version `<label>+env<sha>`.
# `FINDER_VERSION` is the string every cache keys on; `finder_stamp()` is what provenance records.
FINDER_LABEL = "step2flat-3"     # line cues with a leading sign; checkbox squares drawn as glyphs (2026-10-01)
FINDER_CODE_SHA = "93d5efe257db"
FINDER_ENV = "pymupdf 1.28.2; tesseract 5.5.3"


def _code_sha() -> str:
    """The sha of step2flat's code as parsed, docstrings dropped: a comment or docstring edit is not a finder
    change and must not re-key every cache (Andrew, 2026-10-01). A file that does not parse hashes as bytes."""
    import ast
    h = hashlib.sha256()
    for p in sorted((REPO / "step2flat").glob("*.py")):
        src = p.read_bytes()
        try:
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                        and node.body and isinstance(node.body[0], ast.Expr) \
                        and isinstance(getattr(node.body[0], "value", None), ast.Constant) \
                        and isinstance(node.body[0].value.value, str):
                    node.body = node.body[1:] or [ast.Pass()]
            body = ast.dump(tree, include_attributes=False).encode()
        except SyntaxError:
            body = src
        h.update(p.name.encode() + b"\x00" + body + b"\x00")
    return h.hexdigest()[:12]


def _env() -> str:
    try:
        import pymupdf
        mu = pymupdf.__version__
    except Exception:
        mu = "unknown"
    try:
        import pytesseract
        tess = str(pytesseract.get_tesseract_version())
    except Exception:
        tess = "unknown"
    return f"pymupdf {mu}; tesseract {tess}"


def finder_stamp() -> dict:
    """`{label, code_sha, env, version, drift}`: `version` is the cache key; `drift` names what moved since the
    label was set (empty when the code and the environment are the ones the label describes)."""
    sha, env = _code_sha(), _env()
    drift, version = [], FINDER_LABEL
    if sha != FINDER_CODE_SHA:
        drift.append(f"code {FINDER_CODE_SHA} -> {sha}")
        version += f"+code{sha}"
    if env != FINDER_ENV:
        drift.append(f"env '{FINDER_ENV}' -> '{env}'")
        version += "+env" + hashlib.sha256(env.encode()).hexdigest()[:6]
    return {"label": FINDER_LABEL, "code_sha": sha, "env": env, "version": version, "drift": drift}


_STAMP = finder_stamp()
FINDER_VERSION = _STAMP["version"]
if _STAMP["drift"]:
    print(f"[finder] version {FINDER_VERSION}: {'; '.join(_STAMP['drift'])}. Caches re-key under this version. "
          f"If the change is meant, set FINDER_LABEL and FINDER_CODE_SHA / FINDER_ENV in petey/synth/boxes.py.",
          file=sys.stderr)


def _rect_key(page: int, rect) -> str:
    """A stable string key for a (page, rect): what cases and class maps are keyed by."""
    x0, y0, x1, y1 = rect
    return f"p{page}:{x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}"


def rect_key(box: dict) -> str:
    return _rect_key(box["page"], box["rect"])


def parse_rect_key(key: str) -> tuple[int, list[float]]:
    p, r = key.split(":", 1)
    return int(p[1:]), [float(c) for c in r.split(",")]


def widget_key(wb: dict) -> Optional[str]:
    """The key a blueprint widget's ground truth is stored under: its AcroForm path, or, on a blank with no form
    layer (`path: null`, a flat form; spec 5.9.1), `rect:` plus its page and rect. Every consumer that joins a
    case to the blueprint by path (`validate.rect_join`, `validate.score`, `validate.witness`) goes through this,
    so a path-less field scores and is tracked like any other (2026-10-05). None when the block has neither."""
    p = wb.get("path")
    if p:
        return p
    rect = wb.get("rect") or wb.get("box")
    if not rect or wb.get("page") is None:
        return None
    return "rect:" + _rect_key(int(wb["page"]), [float(c) for c in rect])


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
