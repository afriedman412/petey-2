"""Geometry for a flat PDF borrowed from a fillable twin of the same form.

Many corpora carry both a print copy and a fillable copy of a form (the
Texas RRC publishes every form as `x-p.pdf` and `x-f.pdf`). When the
registry knows both, the twin's AcroForm rects are exact and cost
nothing — strictly better than estimating from the flat page. The gate is
layout identity: same page count, same page size, and the page-1 word
sets overlap by at least `MIN_JACCARD`.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Optional

import pymupdf

from petey.paths import REPO
from petey.registry_lookup import DB

MIN_JACCARD = 0.8


def _words(page) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", page.get_text().lower()))


def find_twin(pdf_path: Path, db: Path = DB) -> Optional[Path]:
    """A registered fillable PDF of the same form whose layout matches, or None."""
    if not Path(db).exists():
        return None
    import hashlib
    sha = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    row = conn.execute("""SELECT coalesce(s.form_id, i.form_id, i.canonical), s.pages FROM source_pdfs s
                          LEFT JOIN identities i ON i.sha256 = s.sha256 WHERE s.sha256=?""", (sha,)).fetchone()
    if not row or not row[0]:
        return None
    form_id, pages = row
    cands = conn.execute("""SELECT s.path FROM source_pdfs s LEFT JOIN identities i ON i.sha256 = s.sha256
                            WHERE coalesce(s.form_id, i.form_id, i.canonical)=? AND s.fillable=1 AND s.pages=? AND s.sha256!=?""",
                         (form_id, pages, sha)).fetchall()
    conn.close()
    if not cands:
        return None
    src = pymupdf.open(str(pdf_path))
    try:
        r1, w1 = src[0].rect, _words(src[0])
        for (p,) in cands:
            tp = REPO / p
            if not tp.exists():
                continue
            tw = pymupdf.open(str(tp))
            try:
                r2, w2 = tw[0].rect, _words(tw[0])
            finally:
                tw.close()
            if abs(r1.width - r2.width) < 2 and abs(r1.height - r2.height) < 2 \
                    and len(w1 & w2) / max(1, len(w1 | w2)) >= MIN_JACCARD:
                return tp
    finally:
        src.close()
    return None


def enumerate_fields(pdf_path: Path) -> tuple[list[dict], list[dict], Optional[Path]]:
    """`(widgets, dropped, twin)`; widgets carry the twin's paths so the blueprint can bind to it."""
    from petey.locate.acroform import enumerate_widgets
    twin = find_twin(pdf_path)
    if twin is None:
        return [], [], None
    widgets, dropped = enumerate_widgets(twin)
    for w in widgets:
        w["geometry_source"] = f"sibling:{twin.name}"
    return widgets, dropped, twin
