"""Printed fields from the page alone (the light path's Part A, Andrew 2026-11-04): a text field is printed, meant to be
hand-written (a signature, initials; `printed_fields`), when its OWN caption says so and does not also say date or
title (the date of signing and a signer's title stay text). A "print name" box is text (Andrew, 2026-11-04).

A field's own caption is read the way the split detector reads captions (`compound_values._own_words`): the words
just above the field, inside it, the label before it on its line, and the words under it; a word between two rows
belongs to the nearer field. That gives each caption to one field by position (Andrew: "each has their own caption"): the
caption under a signature line is that line's, not the next row's; "Date" under the box beside the signature is the
date's. Measured on the tuning set 2026-11-04: P 72 / R 78 against the S forms, from P 45 / R 77 for the words
anywhere beside a box with print-name cues.

    find(bp, words_of)   the names of the printed text fields (one box each; option groups are never printed): the
                         printed model's call (`printed_model`, trained on the tuning set) once it is fitted, else
                         the caption rule `says`
    mark(bp, words_of)   writes `printed_fields.TAG` on them ({source, when}) and clears the tag this source left on
                         fields that no longer qualify; other sources' tags are kept

`words_of(page) -> words` (pymupdf "words" tuples); by default the blank's words (`same_box.PageWords`).
"""
from __future__ import annotations

import datetime
import re
from typing import Callable, Optional

from petey.validate import block_types as bt
from petey.validate import compound_values as cv
from petey.validate import printed_fields as pf

SOURCE = "light_caption"
# signatures and initials; a "print name" box is NOT printed (Andrew, 2026-11-04: "'printed name' is not printed, my
# bad ... I meant it like 'likely to be hand-written, not typed'"; on the S forms print-name boxes are text)
CUE = re.compile(r"\b(sign|signs|signed|signature|signatures|signed\s+by|initials|initial\s+here)\b", re.I)
NOT = re.compile(r"\b(date|dated|title)\b", re.I)


def says(caption: str) -> bool:
    """A caption that marks a hand-written field: a signing cue and no date / title word."""
    return bool(CUE.search(caption)) and not NOT.search(caption)


def _own(b: dict, words: list, page: list) -> list:
    """The field's own caption words: above, inside, the label before it, and under it; a word between two rows goes
    to the nearer field (the detector's "below" reading does this for the words under a field; the words above it
    are read the same way here, else the caption under one signature line is also the next row's)."""
    y0 = b["rect"][1]
    above = [w for w in cv._own_words(b, words, "above", page)
             if not (w[3] <= y0 + 1 and any(o["rect"][3] <= w[1] + 1 and w[1] - o["rect"][3] < y0 - w[3]
                                            and min(o["rect"][2], w[2]) > max(o["rect"][0], w[0]) for o in page))]
    return above + cv._own_words(b, words, "below", page)


def find(bp: dict, words_of: Optional[Callable[[int], list]] = None,
         size_of: Optional[Callable[[int], tuple]] = None) -> list[str]:
    """The printed model's call when it is fitted (`printed_model.WEIGHTS`, Andrew 2026-11-04: train local models),
    else the caption rule (`says`). `size_of(page) -> (width, height)` in points, for the model's place features."""
    from petey.validate import printed_model as pm
    if words_of is None or (size_of is None and pm.WEIGHTS is not None):
        from petey.validate.same_box import PageWords
        pw = PageWords(bp)
        words_of = words_of or pw.words
        if size_of is None:
            size_of = lambda pg: ((pw.doc[pg - 1].rect.width, pw.doc[pg - 1].rect.height)   # noqa: E731
                                  if pw.doc is not None and 1 <= pg <= len(pw.doc) else (612.0, 792.0))
    boxes = bt._boxes(bp)
    by_page: dict[int, list] = {}
    for b in boxes:
        by_page.setdefault(b["page"], []).append(b)
    out = []
    for pg, bs in sorted(by_page.items()):
        words = words_of(pg)
        if not words:
            continue
        size = size_of(pg) if size_of else (612.0, 792.0)
        for b in bs:
            if not pf.is_text(bp["fields"][b["name"]]):
                continue
            if pm.WEIGHTS is not None:
                if pm.score(b, words, bs, size) >= pm.CUT:
                    out.append(b["name"])
            elif says(cv._text(_own(b, words, bs))):
                out.append(b["name"])
    return out


def mark(bp: dict, words_of: Optional[Callable[[int], list]] = None, source: str = SOURCE,
         size_of: Optional[Callable[[int], tuple]] = None) -> int:
    hits = set(find(bp, words_of, size_of))
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict):
            continue
        tag = s.get(pf.TAG)
        if n in hits:
            if not tag:
                s[pf.TAG] = {"source": source, "when": when}
        elif isinstance(tag, dict) and tag.get("source") == source:
            del s[pf.TAG]
    return len(hits)
