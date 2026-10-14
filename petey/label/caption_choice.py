"""Choose an option's printed caption from the text around its box, with `text_match` as the judge (Andrew,
2026-10-09: captions that are whole tooltip sentences, and page readings that took a neighbour or the question).

For each option of a group: the candidates are what is printed around its box (right of it, left of it, the
column header above, the nearest lines; `captions` and `field_chain` readers), the part of its tooltip that
differs from its siblings' ('34. ZONE STATUS. P.' -> 'P'), and its current caption when that is short. The
meaning is the group's name, the option key and the option's own tooltip (`text_match.option_desc`). The model
scores every (candidate, meaning) pair; within a group no two options take the same caption.

A caption the XFA declares or a person wrote is never replaced: publisher and person outrank inference (the
caption cascade, `auto_label.caption_options`). Everything else gets a proposal when the best candidate differs
from the current caption, scores at least `_SURE`, and beats the current caption by `_BETTER`.
"""
from __future__ import annotations

import collections
import re
from typing import Optional

from petey.label import captions as cap_mod
from petey.label import text_match as tm
from petey.validate.field_chain import candidate_captions

_SURE = 0.6            # 0.5 let column headers through ('SECONDARY' for a home-phone box at 0.52)
_BETTER = 0.2
_MAX_WORDS = 8          # a caption is a label; a sentence is a tooltip or the question
_TRUSTED = ("hand", "xfa", "claude")      # claude: eval/claude_pass_apply.py, checked by Andrew on the review page


def _norm(s: Optional[str]) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _despace(s: str) -> str:
    """'L L C' -> 'LLC', 'U S C I S' -> 'USCIS': screen-reader spelling in tooltips."""
    return re.sub(r"\b(?:[A-Za-z]\.? ){1,}[A-Za-z]\b\.?", lambda m: re.sub(r"[ .]", "", m.group(0)), s)


_FILLER = {"and", "or", "of", "the", "a", "an", "to", "for", "in", "on", "was", "is", "if", "by", "with", "check", "box"}
_ITEM = re.compile(r"^\(?\d{1,3}[a-z]?\.?[a-z]?\)?$", re.I)      # '8.c', '10.c', '(3)': the item's number


def _short(s: Optional[str]) -> Optional[str]:
    """A candidate that could be a caption: a label of a few words, not an item number, not a fragment that
    starts or ends on a filler word ('and Name', 'Yes check box, was')."""
    if not s:
        return None
    s = cap_mod._LEADERS.sub("", " ".join(s.split())).strip()
    s = cap_mod._END_PUNCT.sub("", s).strip(" ,;")
    if not s or cap_mod._JUNK.match(s) or len(s.split()) > _MAX_WORDS or not re.search(r"[A-Za-z0-9]", s):
        return None
    ws = re.findall(r"[a-z]+", s.lower())
    if _ITEM.match(s) or (ws and (ws[0] in _FILLER or ws[-1] in _FILLER) and len(ws) > 1):
        return None
    return s


def tooltip_slots(tips: dict[str, Optional[str]]) -> dict[str, Optional[str]]:
    """The part of each option's tooltip its siblings do not share: strip the common start and end (word by word)
    and leading numbering. A tooltip all siblings share is the question, not the option: no slot."""
    live = {k: _despace(t).split() for k, t in tips.items() if t}
    out: dict[str, Optional[str]] = {k: None for k in tips}
    if len(live) < 2 or len({" ".join(v).lower() for v in live.values()}) == 1:
        return out
    ws = list(live.values())
    p = 0
    while all(len(w) > p for w in ws) and len({w[p].lower() for w in ws}) == 1:
        p += 1
    q = 0
    while all(len(w) > p + q for w in ws) and len({w[-1 - q].lower().strip(".") for w in ws}) == 1:
        q += 1
    for k, w in live.items():
        core = " ".join(w[p:len(w) - q] if q else w[p:])
        core = re.sub(r"^\s*(?:\(?\d{1,3}[A-Za-z]{0,2}\d?\)?[.:)]|[A-Za-z]\d?\.)\s+", "", core).strip(" .:\"'“”")
        out[k] = _short(core)
    return out


def choose(group: str, spec: dict, page_words: dict[int, list], page_lines: dict[int, list],
           tooltips: dict[str, list[str]]) -> dict[str, dict]:
    """`{option key: {"current", "best", "score", "current_score", "propose": bool, "candidates": [...]}}` for one
    option group; empty when the group has no options or no model."""
    ws = spec.get("widgets") if isinstance(spec, dict) else None
    if not isinstance(ws, dict) or len(ws) < 2 or not tm.available():
        return {}
    declared = ((spec.get("x_petey_xfa") or {}).get("choices")) or {}
    tips = {k: tm.clean_text((tooltips.get(w.get("path") or "") or [None])[0]) for k, w in ws.items()}
    shared = collections.Counter(_norm(t) for t in tips.values() if t)
    slots = tooltip_slots(tips)
    rects_by_page: dict[int, list] = collections.defaultdict(list)
    for w in ws.values():
        if w.get("rect"):
            rects_by_page[int(w.get("page", 1))].append(w["rect"])
    cands: dict[str, list[str]] = {}
    meaning: dict[str, str] = {}
    for k, w in ws.items():
        pg, rect = int(w.get("page", 1)), w.get("rect")
        got: list[Optional[str]] = []
        if rect:
            words = page_words.get(pg, [])
            boxes = rects_by_page[pg]
            got += [cap_mod._right_of(words, rect, cap_mod._stop(rect, boxes)),
                    cap_mod._left_of(words, rect, boxes), cap_mod._header_above(words, rect, boxes)]
            got += candidate_captions(rect, page_lines.get(pg, []))[:3]
        got += [slots.get(k), w.get("caption")]
        seen, keep = set(), []
        for c in map(_short, got):
            if c and _norm(c) not in seen:
                seen.add(_norm(c))
                keep.append(c)
        cands[k] = keep
        own_tip = tips.get(k) if tips.get(k) and shared[_norm(tips[k])] == 1 else None
        meaning[k] = tm.option_desc(group, k, own_tip)
    pairs = [(c, meaning[k]) for k in ws for c in cands[k]]
    scores = dict(zip(pairs, tm.score_pairs(pairs) or []))
    # no two options share a caption: assign the surest (option, candidate) pairs first
    ranked = sorted(((scores[(c, meaning[k])], k, c) for k in ws for c in cands[k]), reverse=True)
    best: dict[str, tuple[str, float]] = {}
    taken: set[str] = set()
    for s, k, c in ranked:
        if k in best or _norm(c) in taken:
            continue
        best[k] = (c, s)
        taken.add(_norm(c))
    out = {}
    for k, w in ws.items():
        cur = w.get("caption")
        trusted = w.get("x_petey_caption_source") in _TRUSTED or (k in declared and cur == declared.get(k))
        b, s = best.get(k, (None, 0.0))
        cur_s = scores.get((_short(cur), meaning[k]), 0.0) if _short(cur) else 0.0
        propose = (not trusted and b is not None and _norm(b) != _norm(cur) and s >= _SURE
                   and s >= cur_s + _BETTER)
        out[k] = {"current": cur, "best": b, "score": round(s, 3), "current_score": round(cur_s, 3),
                  "propose": propose, "trusted": trusted, "candidates": cands[k]}
    return out


def page_context(blank) -> tuple[dict[int, list], dict[int, list]]:
    """`(words by page, lines by page)` for `choose`, read once per blank."""
    import pymupdf
    from petey.validate.field_chain import _page_lines
    doc = pymupdf.open(str(blank))
    try:
        words = {i + 1: cap_mod._words_on(p) for i, p in enumerate(doc)}
    finally:
        doc.close()
    return words, _page_lines(str(blank))
