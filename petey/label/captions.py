"""Printed caption for an option box, read from the page.

A radio or checkbox option's caption is the text the publisher printed
beside its box: to the right on almost every form, below on a few grids.
When neither the XFA template nor the on-state names the option (ordinal
states on a non-XFA form; a fallback join we refuse to trust), this is the
only document-grounded source left.

Measured on 2026-09-30 against options whose caption the XFA declares
(10-10EZ, 526EZ exact joins): see eval in RESULTS.md "Option groups".
"""
from __future__ import annotations

import re
from typing import Optional

import pymupdf

_STOP_GAP = 12.0     # pt of horizontal whitespace that ends a caption
_MAX_REACH = 220.0   # pt to the right we will read at most
_MAX_WORDS = 6       # a caption is a label, not a sentence
_HEADER_REACH = 170.0  # six grid rows; not the top of the page
_END_PUNCT = re.compile(r"[.:;]$")
# the two fallback guards in `caption_options_from_page` (claimed words, write-ins): off until they measure better
# than without (2026-10-07: +81 captions that fit their key, +77 that do not; the write-in rule lost 42 real ones)
GUARDS = False


def _words_on(page: pymupdf.Page) -> list[tuple]:
    # (x0, y0, x1, y1, text, block, line, word) — keep the reading order
    return [tuple(w[:8]) for w in page.get_text("words")]


def _overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _right_of(words, rect, stop_x) -> Optional[str]:
    out = _right_words(words, rect, stop_x)
    return " ".join(w[4] for w in out) if out else None


def _right_words(words, rect, stop_x) -> Optional[list]:
    x0, y0, x1, y1 = rect
    limit = min(x1 + _MAX_REACH, stop_x if stop_x is not None else x1 + _MAX_REACH)
    cands = []
    for w in words:
        if w[0] < x1 - 1 or w[0] > limit:
            continue
        # on the box's line: the word's vertical span overlaps the box's by
        # at least half the smaller of the two — a line above or below the
        # box (the question text, an item number) does not
        ov = _overlap(y0, y1, w[1], w[3])
        centred = abs((w[1] + w[3]) / 2 - (y0 + y1) / 2) <= 0.5 * (y1 - y0)
        if ov < 0.5 * min(y1 - y0, w[3] - w[1]) and not centred:
            continue
        cands.append(w)
    if not cands:
        return None
    # order by line (top to bottom) then x: a caption wrapped onto two
    # lines reads NATIONAL / GUARD, not by whichever block pymupdf made
    cands.sort(key=lambda w: (round((w[1] + w[3]) / 2 / 3), w[0]))
    if cands[0][0] - x1 > _STOP_GAP * 2:
        return None  # nothing adjacent; the text belongs to something else
    out = [cands[0]]
    for w in cands[1:]:
        prev = out[-1]
        same_line = abs((w[1] + w[3]) / 2 - (prev[1] + prev[3]) / 2) < 3
        if same_line and w[0] - prev[2] > _STOP_GAP:
            break  # a gap on the same line ends the caption
        if not same_line and w[0] > x1 + _STOP_GAP * 2:
            break  # the next line does not start beside the box: not a wrap
        out.append(w)
    if len(out) > _MAX_WORDS:
        return None  # a sentence beside the box (the next question), not its caption
    return out


def _header_above(words, rect, options_rects) -> Optional[str]:
    """Column header: the nearest short text line directly above the box's
    column (yes/no grids: one YES / NO header serves every row)."""
    x0, y0, x1, y1 = rect
    cx = (x0 + x1) / 2
    cands = [w for w in words if w[3] <= y0 + 1 and w[3] >= y0 - _HEADER_REACH and w[0] - 3 <= cx <= w[2] + 3]
    if not cands:
        return None
    nearest = max(cands, key=lambda w: w[3])
    line = sorted((w for w in cands if w[5] == nearest[5] and w[6] == nearest[6]), key=lambda w: w[7])
    if len(line) > 3:
        return None
    return " ".join(w[4] for w in line)


_LEADERS = re.compile(r"\s*\.{3,}.*$")  # dot leaders and whatever follows them (a line number)
_JUNK = re.compile(r"^[\(\[]?(https?://|www\.)|^[\$\(\)\[\]\.,;:]+$")  # a URL or bare punctuation is never a caption
_ITEM_LABEL = re.compile(r"^(\d{1,2}[A-Z]?|[A-Z])\.?(\s|$)")  # "14A", "E. HAVE YOU": the next item, not a caption


def _left_of(words, rect, options_rects) -> Optional[str]:
    """Caption printed LEFT of the box ("YES [ ]"): the words on the box's
    line ending just before it, back to a gap or the previous option box."""
    x0, y0, x1, y1 = rect
    floor = max([r[2] for r in options_rects if r[2] <= x0 - 1 and _overlap(y0, y1, r[1], r[3]) > 0] + [x0 - _MAX_REACH])
    cands = [w for w in words if w[2] <= x0 + 1 and w[2] >= floor
             and _overlap(y0, y1, w[1], w[3]) >= 0.5 * min(y1 - y0, w[3] - w[1])]
    if not cands:
        return None
    cands.sort(key=lambda w: -w[2])
    if x0 - cands[0][2] > _STOP_GAP * 2:
        return None
    out = [cands[0]]
    for w in cands[1:]:
        if out[-1][0] - w[2] > _STOP_GAP:
            break
        out.append(w)
    out.reverse()
    if len(out) > _MAX_WORDS:
        return None
    cap = " ".join(w[4] for w in out)
    return None if _ITEM_LABEL.match(cap) else cap


def caption_right_of(page: pymupdf.Page, rect, stop_x: Optional[float] = None,
                     words=None, options_rects=None, claimed=None, writein: bool = False) -> Optional[str]:
    """The printed caption of an option box: the words on its line just
    right of it; else just left of it; else the short column header above
    it. None when nothing qualifies — never a guess. The two fallbacks skip
    `claimed` words (another option's caption, read right of its own box),
    and a `writein` box (a text field follows it) has no fallback at all."""
    words = words if words is not None else _words_on(page)
    rest = [w for w in words if w not in claimed] if claimed else words
    cap = None
    finders = [lambda: _right_of(words, rect, stop_x)]
    if not writein:
        finders += [lambda: _left_of(rest, rect, options_rects or []),
                    lambda: _header_above(rest, rect, options_rects or [])]
    for finder in finders:
        c = finder()
        if c and not _ITEM_LABEL.match(c) and not _JUNK.match(c):
            cap = c
            break
    if not cap:
        return None
    cap = _LEADERS.sub("", cap.strip())          # "Other.........70" -> "Other"
    cap = _END_PUNCT.sub("", cap.strip()).strip()
    if not cap or _JUNK.match(cap):
        return None
    return cap


def text_rects(fields: dict) -> dict[int, list]:
    """{page: [rect]} of a blueprint's text fields, for `caption_options_from_page`."""
    out: dict[int, list] = {}
    for s in fields.values():
        w = s.get("widget") if isinstance(s, dict) else None
        if w and w.get("widget_type") == "text" and w.get("rect") and w.get("page"):
            out.setdefault(int(w["page"]), []).append(w["rect"])
    return out


def _same_line(a, b) -> bool:
    return _overlap(a[1], a[3], b[1], b[3]) >= 0.5 * min(a[3] - a[1], b[3] - b[1])


def _stop(rect, rects) -> Optional[float]:
    """Where reading right of `rect` ends: the nearest box to its right on its line."""
    xs = [r[0] for r in rects if r[0] > rect[2] + 2 and abs((r[1] + r[3]) / 2 - (rect[1] + rect[3]) / 2) < (rect[3] - rect[1])]
    return min(xs) if xs else None


def caption_options_from_page(doc: pymupdf.Document, widgets: dict[str, dict],
                              other_rects_by_page: Optional[dict[int, list]] = None,
                              text_rects_by_page: Optional[dict[int, list]] = None) -> int:
    """Fill missing `caption`s of an option map from the page text. Returns
    how many were filled. Never overwrites a caption already present.

    Two guards on the left / header fallbacks (Andrew, 2026-10-07, ACORD 140
    secondary heat: BOILER [ ] SOLID FUEL [ ] [ ]______ lost SOLID FUEL, read
    again left of the last box, and the duplicate rule then dropped both):
    words another option box reads right of itself are its caption, not a
    fallback for this one; and a box with a text field just right of it, no
    printed words between (`text_rects_by_page`: "Other ______"), is a
    write-in option and gets no fallback caption."""
    n = 0
    opts, texts = other_rects_by_page or {}, text_rects_by_page or {}
    page_words: dict[int, list] = {}
    for st, block in widgets.items():
        if block.get("caption"):
            continue
        pno = int(block.get("page", 1)) - 1
        if pno < 0 or pno >= len(doc):
            continue
        page = doc[pno]
        words = page_words.setdefault(pno, _words_on(page))
        rect = block["rect"]
        boxes = opts.get(pno + 1, []) + [b["rect"] for b in widgets.values() if int(b.get("page", 1)) == pno + 1]
        stop = _stop(rect, boxes)                # text fields do not end the reading; they only mark write-ins
        claimed = set()                     # words a sibling reads right of itself as its caption
        for k, b in widgets.items():
            if k == st or int(b.get("page", 1)) != pno + 1:
                continue
            got = _right_words(words, b["rect"], _stop(b["rect"], boxes)) or []
            text = " ".join(w[4] for w in got)
            if got and (not b.get("caption") or b["caption"].strip().lower() == text.lower()):
                claimed.update(got)
        writein = any(-1 <= t[0] - rect[2] <= 2 * _STOP_GAP and _same_line(rect, t)
                      and _right_of(words, rect, t[0]) is None for t in texts.get(pno + 1, []))
        cap = caption_right_of(page, rect, stop_x=stop, words=words, options_rects=opts.get(pno + 1, []),
                               claimed=claimed if GUARDS else None, writein=writein and GUARDS)
        if cap:
            block["caption"] = cap
            block["x_petey_caption_source"] = "page_text"
            n += 1
    # a caption must tell the options apart: the same text on two options
    # of one group (a section header above both, a misread) names neither
    seen: dict[str, list[str]] = {}
    for st, block in widgets.items():
        if block.get("x_petey_caption_source") == "page_text":
            seen.setdefault(block["caption"].lower(), []).append(st)
    for cap, sts in seen.items():
        if len(sts) > 1:
            for st in sts:
                widgets[st].pop("caption", None)
                widgets[st].pop("x_petey_caption_source", None)
                n -= 1
    return n
