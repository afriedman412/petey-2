"""Are these two boxes the same kind of box? (Andrew, 2026-10-27: "are these two boxes the same type", a small model in
the finder, so a repeated section's copies pick up the boxes the distance rule misses: fl__sd_6863766 BT9's "Was rent up
to date?" 23 pt off, bm__sd_2218681's "Reason for Leaving" a few points shorter in its third copy.)

A box in copy 1 of a block and a box in another copy, given where that copy's frame puts copy 1's box: the chance they
are the same position, from a logistic model of ten numbers (no library): the same kind (checkbox or radio alike,
`block_types.same_kind`), how far the box sits from where the frame puts it, across and down, absolutely and as a share
of the block, how much the sizes differ, and how much the two boxes' own captions share (the words just above a box over
its width, and the label printed right before it on its line). Two guards on top: a box of another kind never matches,
and past the distance rule's limit the captions must share `FAR_CAPTION` of their words (2026-10-27: without it a VA
21-686c date-of-birth part matched a phone-number part across the row, their captions sharing only "veteran").

Trained on the saved block types (`eval/same_box_train.py`; 2026-10-27: 192 forms, 7,157 positions, folds by form: the
true box ranked first among a copy's candidates for 7,098). Used after SIA has chosen its blocks
(`block_discovery.find`) and for a block's empty positions (`block_types.fill_blocks`); inside SIA's own growing it glued
neighbouring copies together (je__acord_80 lost 50 right pairs), so it never decides which copies there are.
Measured on 199 forms with saved blocks, after SIA: 4,908 -> 5,066 right pairs, wrong 1,804 -> 1,830.
"""
from __future__ import annotations

import math
import re
from typing import Optional

KEEP = 0.5                  # a pair at least this likely is the same position
FAR_CAPTION = 0.3           # past the distance limit, this share of the two captions' words in common
FEATS = ("same_kind", "log_dx", "log_dy", "dx_share", "dy_share", "width_diff", "log_height_diff", "caption",
         "no_caption", "caption_near")
MU = (0.8734, 4.1208, 3.2867, 0.3174, 0.4254, 0.8248, 0.7684, 0.0915, 0.1944, 0.0364)
SD = (0.3325, 1.9382, 1.6932, 0.2704, 0.3922, 0.9734, 1.1505, 0.2421, 0.3958, 0.1742)
W = (0.028, -1.8357, -1.5181, -0.0495, -0.6992, -0.3134, 0.075, -0.1847, 0.1325, 1.473)
BIAS = -4.6382

_WORD = re.compile(r"[a-z]{2,}")
_STOP = {"the", "of", "and", "or", "if", "to", "in", "a", "an", "for", "is", "are", "you", "your", "on", "at", "by"}


def caption(words: list, rect) -> set[str]:
    """A box's own caption as a set of words: those just above it over its width (a column or cell caption) and the
    label run printed right before it on its line (words chained leftward, gaps under 12 pt, the first within 40)."""
    x0, y0, x1, y1 = rect
    above = [w for w in words if y0 - 16 <= w[3] <= y0 + 1 and w[2] > x0 - 4 and w[0] < x1 + 4]
    line = sorted((w for w in words if w[3] > y0 - 3 and w[1] < y1 + 3 and w[2] <= x0 + 2), key=lambda w: -w[2])
    left, edge = [], x0
    for w in line:
        if edge - w[2] > (40 if not left else 12):
            break
        left.append(w)
        edge = w[0]
    return {t for t in _WORD.findall(" ".join(w[4] for w in left + above).lower()) if t not in _STOP}


def near_limit(height: float) -> float:
    """The distance rule's limit for a block this tall (block_types.label_copies' `near`)."""
    return max(8.0, 0.25 * height, 12.0)


def score(a: dict, b: dict, dx: float, dy: float, height: float, width: float, cap_a: set, cap_b: set) -> float:
    """The chance box `b` is the position box `a` holds in copy 1, where `b`'s copy sits (`dx`, `dy`) from copy 1;
    boxes are {rect, kind}; `height` / `width` the block's; `cap_a` / `cap_b` their captions (`caption`)."""
    from petey.validate.block_types import same_kind
    if not same_kind(a["kind"], b["kind"]):
        return 0.0
    ra, rb = a["rect"], b["rect"]
    rx, ry = rb[0] - ra[0] - dx, rb[1] - ra[1] - dy
    shared = (len(cap_a & cap_b) / len(cap_a | cap_b)) if (cap_a or cap_b) else -1.0
    if abs(rx) + abs(ry) > near_limit(height) and shared < FAR_CAPTION:
        return 0.0
    wa = ra[2] - ra[0]
    cap = max(shared, 0.0)
    f = (1.0, math.log1p(abs(rx)), math.log1p(abs(ry)), min(abs(rx) / max(width, 1), 2), min(abs(ry) / max(height, 1), 2),
         min(abs((rb[2] - rb[0]) - wa) / max(wa, 1), 3), math.log1p(abs((rb[3] - rb[1]) - (ra[3] - ra[1]))), cap,
         float(shared < 0), cap * math.exp(-(abs(rx) + abs(ry)) / 20))
    z = BIAS + sum(w * (x - m) / s for w, x, m, s in zip(W, f, MU, SD))
    return 1 / (1 + math.exp(-z))


class PageWords:
    """The blank's words per page, read once; captions per box, read once. Empty without a blank."""

    def __init__(self, bp: dict):
        from petey.validate.retype import resolve_blank
        self.doc = None
        blank = resolve_blank(bp)
        if blank is not None and blank.exists():
            import pymupdf
            self.doc = pymupdf.open(str(blank))
        self._words: dict[int, list] = {}
        self._caps: dict[str, set] = {}

    def words(self, page: int) -> list:
        if page not in self._words:
            ok = self.doc is not None and 1 <= page <= len(self.doc)
            self._words[page] = self.doc[page - 1].get_text("words") if ok else []
        return self._words[page]

    def caption(self, box: dict) -> set[str]:
        k = str(box["code"])
        if k not in self._caps:
            self._caps[k] = caption(self.words(box["page"]), box["rect"])
        return self._caps[k]

    def score(self, a: dict, b: dict, dx: float, dy: float, height: float, width: float) -> float:
        return score(a, b, dx, dy, height, width, self.caption(a), self.caption(b))


def best(a: dict, cands: list[dict], dx: float, dy: float, height: float, width: float,
         pw: PageWords) -> Optional[tuple[float, dict]]:
    """(chance, box) of the candidate most likely to be `a`'s position at least `KEEP` likely, or None."""
    top = None
    for c in cands:
        p = pw.score(a, c, dx, dy, height, width)
        if p >= KEEP and (top is None or p > top[0]):
            top = (p, c)
    return top
