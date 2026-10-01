"""Each field's synthetic case, checked in the order it was built: box -> class -> value.

A case is a chain. The finder puts a box on the page, the classifier reads the box's caption and gives it a class,
and the bank writes a value of that class. A fault early in the chain makes everything after it wrong, so a signal
about a later link is only evidence about the blueprint when the earlier links hold (Andrew, 2026-09-30):

    box     the case box lines up with the blueprint field (inventory check: no `box_unreached`, `merged_box`,
            `tie`, and the field was generated). Otherwise nothing about this field's case says anything about the
            field.
    class   the classifier's caption for the box is the caption printed AT the widget: the nearest line of text on
            the blank, inside the widget or next to it (above, below, left, right), shares the caption's words.
            A caption that belongs to a neighbouring box (MA LIC100: the box under "C5. State" read as "B16. Name")
            makes the class, the bank's value, the class check, the regex check and the judge all wrong together;
            they are one misreading counted several times, not several opinions.
    value   only now do the regex check (`shape`) and the judge speak about the blueprint.

`verified` is True when the classifier's caption is one of the lines lined up with the widget and near it (above,
below, inside, left or right), False when there are such lines and it is none of them, None when there are none.

A misattributed caption holds the field at the class stage only when the class it produced disagrees with the
blueprint's type (the run's `class_disagreements.json`): then the blueprint or the caption is wrong and nothing
downstream can tell which. When the classes agree the caption changed nothing in the case (Andrew, 2026-10-01: a
checkbox is `option` from its shape and its value is a mark whatever the caption says; LA 7006's 54 checkboxes and
B106I's 43 amount cells, captioned one row off, were held for nothing) and the signals flow; the caption stays
unverified for the reviewer, which withholds it, and a rename on the field is contested.

Lined up, not merely near: Utah WC-122's `time_of_occurrence` sits directly under TIME OF OCCURRENCE, and the
classifier's DATE OF INJURY/ILLNESS only touches the box's corner. Any line at all, not the nearest one: forms put
captions above or below the box, and a section heading or the next row's caption is often nearer than the real one
(an earlier nearest-line rule marked 94 of 527 fields on six forms wrong, mostly where the classifier was right).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pymupdf

from petey.validate.name_caption import box_for, caption_boxes, tokens

BOX_FAIL = {"box_unreached", "merged_box", "tie"}
NEAR_PT = 36.0          # a caption farther than this from the widget is not its caption
TIE_PT = 1.5            # lines this close to the nearest count as equally near


@lru_cache(maxsize=32)
def _page_lines(blank: str) -> dict[int, list[tuple[tuple, str]]]:
    """Text lines of the blank, by page: ((x0, y0, x1, y1), text)."""
    out: dict[int, list] = {}
    doc = pymupdf.open(blank)
    try:
        for pno, page in enumerate(doc, start=1):
            lines = []
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    text = " ".join(s.get("text", "") for s in line.get("spans", [])).strip()
                    if text and re.search(r"[A-Za-z0-9]", text):
                        lines.append((tuple(line["bbox"]), text))
            out[pno] = lines
    finally:
        doc.close()
    return out


def _gap(a, b) -> float:
    """Distance between two rects; 0 when they touch or overlap."""
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


MIN_ALIGN = 0.5         # a line must be at least half over the widget's side (or the widget half under it)


def _alignment(rect, bb) -> float:
    """How lined up a text line is with the widget: the overlap of their horizontal extents (for a line above,
    below or inside) or vertical extents (for one to the left or right), over the SHORTER of the two, so a short
    caption over a wide box counts as lined up (DO-10 'Email Address' over its 142 pt box). 1 = lined up, 0 =
    touches a corner (WC-122: DATE OF INJURY/ILLNESS overlaps the TIME OF OCCURRENCE box by 11 pt of 79)."""
    xo = max(0.0, min(rect[2], bb[2]) - max(rect[0], bb[0])) / max(min(rect[2] - rect[0], bb[2] - bb[0]), 1e-6)
    yo = max(0.0, min(rect[3], bb[3]) - max(rect[1], bb[1])) / max(min(rect[3] - rect[1], bb[3] - bb[1]), 1e-6)
    return min(1.0, max(xo, yo))


def candidate_captions(rect, page_lines) -> list[str]:
    """Every text line that could be the widget's caption: within NEAR_PT and lined up with it (above, below,
    inside, left or right), nearest first. Forms print captions above the box (most) or below it (I-9), so no
    single position is right; a line that only touches a corner is not a caption (Utah WC-122:
    DATE OF INJURY/ILLNESS at the corner of the TIME OF OCCURRENCE box)."""
    scored = sorted((_gap(rect, bb), text) for bb, text in page_lines
                    if _gap(rect, bb) <= NEAR_PT and _alignment(rect, bb) >= MIN_ALIGN)
    return [t for _, t in scored]


COLUMN_PT = 300.0       # how far up a column header may sit over a table row


def column_header(rect, page_lines) -> Optional[str]:
    """The nearest line above the widget that is lined up with it horizontally, at any distance up to COLUMN_PT:
    a table's column header prints once, over the first row (TX DMV 1756: 'Year/Make' over fifteen rows). The
    nearest one only, so a row whose own caption sits directly above it is judged by that caption (MA LIC100:
    'C5. State', not 'B16. Name' two rows up)."""
    above = [(rect[1] - bb[3], text) for bb, text in page_lines
             if bb[3] <= rect[1] + 2 and rect[1] - bb[3] <= COLUMN_PT
             and max(0.0, min(rect[2], bb[2]) - max(rect[0], bb[0])) / max(min(rect[2] - rect[0], bb[2] - bb[0]), 1e-6)
             >= MIN_ALIGN]
    return min(above)[1] if above else None


ROW_PT = 420.0          # how far left a row label may sit from a table cell


def row_header(rect, page_lines) -> Optional[str]:
    """The nearest line to the left of the widget that is lined up with it vertically, up to ROW_PT: a table's row
    label (LA 7006: 'Excise - Gas Jobber' at the left of its Year(s) or Period(s) cell)."""
    left = [(rect[0] - bb[2], text) for bb, text in page_lines
            if bb[2] <= rect[0] + 2 and rect[0] - bb[2] <= ROW_PT
            and max(0.0, min(rect[3], bb[3]) - max(rect[1], bb[1])) / max(min(rect[3] - rect[1], bb[3] - bb[1]), 1e-6)
            >= MIN_ALIGN]
    return min(left)[1] if left else None


def _squash(t: str) -> str:
    return re.sub(r"[\W_]+", "", (t or "").lower())


def _agrees(label: str, texts: list[str]) -> bool:
    lt = tokens(label)
    sq = _squash(label)
    for t in texts:
        # letter-spaced small caps come out as 'Y EAR/ P ERIOD' (KS DO-41): compare without spaces too
        st = _squash(t)
        if sq and st and (sq in st or (len(st) >= 4 and st in sq)):
            return True
        tt = tokens(t)
        if lt and tt and len(lt & tt) >= max(1, (len(lt) + 1) // 2):
            return True
    return False


def field_chain(bpt: dict, case_dir: Path, blank: Optional[Path]) -> dict[str, dict]:
    """`{field: {stage, why, caption_classifier, caption_page, verified}}` for every blueprint field.
    `stage` is where the chain breaks ('box' or 'class'), or 'value' when the field's case holds."""
    fields = bpt.get("fields") or {}
    failed_box: dict[str, str] = {}
    inv = case_dir / "inventory_check.json"
    if inv.exists():
        for row in json.loads(inv.read_text()).get("rows", []):
            if row.get("class") in BOX_FAIL and row.get("field"):
                failed_box.setdefault(row["field"], row["class"])
    ur = case_dir / "case_unreached.json"
    if ur.exists():
        for f in json.loads(ur.read_text()):
            failed_box.setdefault(f, "box_unreached")
    boxes = caption_boxes(case_dir)
    lines = _page_lines(str(blank)) if blank and Path(blank).exists() else {}
    cd = case_dir / "class_disagreements.json"
    disagree: Optional[set] = ({row["field"] for row in json.loads(cd.read_text()) if row.get("field")}
                               if cd.exists() else None)       # None: no class check in this run; hold as before
    out: dict[str, dict] = {}
    for name, spec in fields.items():
        if name in failed_box:
            out[name] = {"stage": "box", "why": failed_box[name]}
            continue
        if spec.get("widgets"):      # option groups: their boxes are marks, the group question is checked elsewhere
            out[name] = {"stage": "value", "why": "option group"}
            continue
        box = box_for(spec, boxes)
        label = box.get("label")
        w = spec.get("widget") or {}
        pl = lines.get(w.get("page"), []) if w.get("rect") and lines else []
        near = candidate_captions(w["rect"], pl) if pl else []
        heads = [h for h in ((column_header(w["rect"], pl), row_header(w["rect"], pl)) if pl else ()) if h]
        if not label or (not near and not heads):
            verified = None
        else:
            verified = _agrees(label, near) or _agrees(label, heads)
        rec = {"caption_classifier": label, "caption_page": " | ".join(near[:3]) or None, "verified": verified}
        if verified is False and (disagree is None or name in disagree):
            rec.update(stage="class", why="the classifier's caption is not the text at the widget and its class "
                                          "disagrees with the blueprint")
        elif verified is False:
            rec.update(stage="value", why="caption misattributed but the class agrees with the blueprint")
        else:
            rec.update(stage="value", why=None)
        out[name] = rec
    return out


def chain_for_run(run_dir: Path, case: str = "case_001_intact") -> dict[str, dict]:
    """field_chain for a run's case, with the run's blueprint copy and its blank."""
    import yaml
    from petey.validate.retype import resolve_blank
    bp_path = run_dir / "blueprint.bpt"
    if not bp_path.exists():
        return {}
    bpt = yaml.safe_load(bp_path.read_text(encoding="utf-8")) or {}
    try:
        blank = resolve_blank(bpt)
    except Exception:
        blank = None
    return field_chain(bpt, run_dir / case, blank)
