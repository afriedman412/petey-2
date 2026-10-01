"""Does a field's name agree with the caption printed for its box?

The page classifier (`synth.classify`) reads the caption of every box it numbers, keyed by page and rect. Joining
a blueprint field to its box by rect and comparing the name with that caption gives a cheap, judge-free signal:

  * a name that shares a word with its box's caption is about that box, so when the judge cannot find or misreads
    the value, the cause is the presentation (empty cells, columns) or the case value, not the name;
  * a name that shares nothing with a readable caption is a candidate misname (an opaque `control`, a widget the
    publisher put one row off, a swapped pair), worth a reviewer's look.

Crude by design (word stems, a few expansions for abbreviations); it gates and screens, it does not decide.
`None` when the caption carries no words (`5a(1)`), so the caller can stay conservative.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path
from typing import Optional

from petey.synth.boxes import match_rect, parse_rect_key

_ABBR = {"nm": "name", "no": "number", "num": "number", "dt": "date", "amt": "amount", "addr": "address",
         "cd": "code", "ind": "", "txt": "", "cnt": "count", "pct": "percent", "st": "state",
         "acct": "account", "emp": "employer", "tel": "phone", "ph": "phone", "yr": "year",
         "desc": "description", "qty": "quantity", "id": "identification", "twp": "township", "rge": "range",
         "sec": "section"}
# a name token that stands for several caption words
_EXPAND = {"ssn": {"social", "secur"}, "ein": {"emplo", "ident"}, "fein": {"emplo", "ident"},
           "dob": {"birth"}, "zip": {"postal"}, "tel": {"phone", "telep"}, "ptin": {"prepa"}}
_STOP = {"the", "of", "a", "an", "and", "or", "to", "for", "in", "on", "if", "any", "your", "is", "be", "by", "as",
         "at", "this", "that", "with", "from", "no", "yes", "mm", "dd", "yyyy", "line", "part", "section", "box"}


def tokens(s: str) -> set[str]:
    out: set[str] = set()
    for t in re.findall(r"[a-z]+", (s or "").lower()):
        out |= _EXPAND.get(t, set())
        t = _ABBR.get(t, t)
        if t and t not in _STOP and len(t) > 1:
            out.add(t[:5])            # crude stem: 'employer' ~ 'employee' ~ 'employment'
    return out


def name_matches_caption(name: str, caption: Optional[str]) -> Optional[bool]:
    """True / False when the caption has words to compare; None when it has none."""
    ct = tokens(caption or "")
    if not ct:
        return None
    return bool(tokens(name) & ct)


def caption_boxes(case_dir: Path) -> dict[int, list[dict]]:
    """The classifier's boxes for a case, by page: `{rect, label, class}`. Empty when the run has no class map."""
    cp = case_dir / "class_map.json"
    if not cp.exists():
        return {}
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for k, b in (json.loads(cp.read_text()).get("boxes") or {}).items():
        page, rect = parse_rect_key(k)
        by_page[page].append({"rect": rect, "label": b.get("label"), "class": b.get("class")})
    return by_page


def box_for(spec: dict, boxes: dict[int, list[dict]]) -> dict:
    """The classifier box a field's widget sits on (best overlap), or {}."""
    w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
    if not w.get("rect"):
        return {}
    return match_rect(w["rect"], boxes.get(w.get("page"), [])) or {}
