"""Is there ink in this box? A local, model-free read of a checkbox or radio option.

Renders the option's rectangle from the filled page and from the blank page
at the same dpi, converts both to grey, and counts the pixels that turned
dark. Borders, pre-printed glyphs and nearby text are in both renders and
cancel; only added ink counts. `ink_delta` is that count as a share of the
box area; `is_marked` compares it with a threshold set by
eval/ink_marks.py (2026-09-30).
"""
from __future__ import annotations

import numpy as np
import pymupdf

DPI = 200
INSET = 0.0         # no trim: a mark shifted half a box out still counts; borders cancel against the blank anyway
THRESHOLD = 0.01    # mean darkening of the box; eval/ink_marks.py 2026-09-30: precision 0.984, recall 0.952 on rendered pages (recalibrate for scans)


def _grey(page: pymupdf.Page, rect, dpi: int) -> np.ndarray:
    r = pymupdf.Rect(*rect)
    dx, dy = r.width * INSET, r.height * INSET
    clip = pymupdf.Rect(r.x0 + dx, r.y0 + dy, r.x1 - dx, r.y1 - dy)
    pix = page.get_pixmap(dpi=dpi, clip=clip, colorspace=pymupdf.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).astype(np.int16)


def ink_delta(filled_page: pymupdf.Page, blank_page: pymupdf.Page, rect, dpi: int = DPI) -> float:
    """How much darker the inner box got, 0..1: mean darkening over the box,
    where a pixel's darkening is (blank - filled) / 255 clipped at 0. A black
    check covering a tenth of the box scores ~0.10; a faint pencil check the
    same size ~0.03; an untouched box ~0."""
    a = _grey(filled_page, rect, dpi)
    b = _grey(blank_page, rect, dpi)
    if a.shape != b.shape or a.size == 0:
        return 0.0
    d = np.clip(b - a, 0, 255)
    return float(d.mean()) / 255.0


def is_marked(filled_page, blank_page, rect, threshold: float = THRESHOLD, dpi: int = DPI) -> bool:
    return ink_delta(filled_page, blank_page, rect, dpi) >= threshold


def selected_option(filled_page, blank_page, option_rects: dict, threshold: float = THRESHOLD):
    """For a group `{on_state: rect}`: the option with the most added ink, if
    it clears the threshold; else None."""
    best, best_d = None, 0.0
    for st, rect in option_rects.items():
        d = ink_delta(filled_page, blank_page, rect)
        if d > best_d:
            best, best_d = st, d
    return best if best_d >= threshold else None
