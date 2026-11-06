"""Printed-field candidates for the flat-structure benchmark's key (Andrew, 2026-10-31: a third field type, "printed":
"anything that is expected to be hand-written -- signatures, printed names, etc. this makes scoring more
straightforward"). Initials are printed; the date of signing and a signer's title stay text.

No blueprint says which fields are printed, and no one signal is right often enough to be the key (read-only check
2026-10-31, library pages, field names as the answer: caption words alone P 59% / R 59%), so this drafts candidates
from three and Andrew confirms them a page at a time on the review server's printed sheet (/printed):

    caption    the page's words beside, below, above or inside the field say sign / signature / initials / print name
    name       the field's validated name says signature / initials / printed name (library forms; the benchmark
               sets carry position names)
    widget     the original PDF has a signature widget there, or a widget whose name or tooltip says so (staging
               logs lead to the benchmark sets' fillable originals; library blanks have their widgets)

Only text fields of key pages are candidates. Writes runs/benchmark/printed/candidates.json:
{page id: {field id: [signal, ...]}}. What Andrew confirms is the printed sheet's record (`petey_dataset.FIELD_TYPES`).

    PYTHONPATH=. venv/bin/python eval/benchmark_printed.py
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import petey_dataset as D  # noqa: E402

ROOT = D.ROOT                      # the dataset; `originals()` also wants acquisition/ beside it (the scrape records)
KEY = D.KEY
OUT = D.PRINTED_CANDIDATES

PRINT = (r"print(ed)?\s*(full\s*)?names?|names?\s*\(?\s*(print|printed)|(type|typed)\s*(or|/)\s*print(ed)?"
         r"|print\s*(or|/)\s*type|initials|initial\s+here")
SAYS = re.compile(rf"\b(sign|signature|signatures|signed\s+by|{PRINT})\b", re.I)          # the page's words
WIDGET_SAYS = re.compile(rf"\b(signature|signatures|signed\s+by|sign\s+here|{PRINT})\b", re.I)   # a widget's name
NAME = re.compile(r"(^|_)(signature|signatures|sig|initials|printed)(_|$)|print(ed)?_(nm|name)")
NOT_NAME = re.compile(r"(_dt|_date|date_|_ind|_month|_day|_yr|_year)(_\d+)?$|middle_initial|_cd(_\d+)?$")


def caption(words: list, r: list) -> str:
    """The page's words beside the field `r` (points, top left): on its line to the left, just below, just above a
    short field, or inside it."""
    x0, y0, x1, y1 = r
    near = []
    for wx0, wy0, wx1, wy1, txt, *_ in words:
        cy = (wy0 + wy1) / 2
        inside = x0 - 1 <= wx0 and wx1 <= x1 + 1 and y0 - 1 <= wy0 and wy1 <= y1 + 1
        left = y0 - 3 <= cy <= y1 + 3 and wx1 <= x0 + 2 and x0 - wx1 < 160
        below = 0 <= wy0 - y1 < 12 and wx0 < x1 and wx1 > x0
        above = 0 <= y0 - wy1 < 10 and wx0 < x1 and wx1 > x0 and y1 - y0 < 30
        if inside or left or below or above:
            near.append((wy0, wx0, txt))
    return " ".join(t for *_, t in sorted(near))


def name_says(name: Optional[str]) -> bool:
    n = (name or "").lower()
    return bool(NAME.search(n)) and not NOT_NAME.search(n)


def _iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if inter <= 0:
        return 0.0
    area = lambda q: (q[2] - q[0]) * (q[3] - q[1])  # noqa: E731
    return inter / (area(a) + area(b) - inter)


def widget_marks(pdf: Path, page: int) -> list[list[float]]:
    """Rects of the page's widgets that are signatures or are named as one, or as a printed name (by the widget's name
    and a short tooltip; long tooltips mention signing in passing)."""
    import pymupdf
    out = []
    try:
        doc = pymupdf.open(str(pdf))
    except Exception:  # noqa: BLE001
        return out
    try:
        if page > len(doc):
            return out
        for w in doc[page - 1].widgets() or []:
            label = w.field_label or ""
            words = re.sub(r"[_.\[\]\d]+", " ", f"{w.field_name or ''} {label if len(label) <= 60 else ''}")
            words = re.sub(r"([a-z])([A-Z])", r"\1 \2", words)
            if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE or (
                    w.field_type == pymupdf.PDF_WIDGET_TYPE_TEXT and WIDGET_SAYS.search(words)
                    and not re.search(r"\bdate\b", words, re.I)):
                out.append([float(c) for c in w.rect])
    finally:
        doc.close()
    return out


def originals() -> dict[str, Path]:
    """{review id: fillable original} for the staged benchmark sets (acquisition/, git-ignored, local)."""
    sys.path.insert(0, str(ROOT / "acquisition"))
    try:
        import add_signature_fields as A
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for staged, fetched, orig_of in A.SOURCES:
        if not (staged.exists() and fetched.exists()):
            continue
        rows = {json.loads(ln)["url_id"]: json.loads(ln) for ln in fetched.open() if ln.strip()}
        for ln in staged.open():
            st = json.loads(ln)
            r = rows.get(st["url_id"])
            if r and st.get("kind", "fillable") == "fillable":
                out[A.review_id(ROOT / st["blueprint"])] = orig_of(r)
    return out


def draft(key_dir: Path = KEY) -> dict[str, dict[str, list[str]]]:
    import pymupdf
    paths, orig = D.blueprint_paths(), originals()
    out: dict[str, dict[str, list[str]]] = {}
    forms: dict[str, tuple] = {}
    for x in json.loads((key_dir / "index.json").read_text()):
        pid = x["page_id"]
        key = json.loads((key_dir / f"{pid}.json").read_text())
        form, pg = key["form"], int(key["page"])
        if form not in forms:
            bp = D.load(D.working_path(form, paths))
            names = {str(s.get("x_petey_id") if s.get("x_petey_id") is not None else n): n
                     for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
            blank = orig.get(form) or D.resolve_blank(bp)
            forms[form] = (names, blank)
        names, blank = forms[form]
        try:
            doc = pymupdf.open(str(key_dir / "pages" / f"{pid}.pdf"))
            words = doc[0].get_text("words")
            doc.close()
        except Exception:  # noqa: BLE001
            words = []
        marks = widget_marks(blank, pg) if blank else []
        got = {}
        for f in key["fields"]:
            if f["kind"] != "text":
                continue
            sig = []
            if SAYS.search(caption(words, f["rect"])):
                sig.append("caption")
            if name_says(names.get(f["id"].split(".")[0])):
                sig.append("name")
            if any(_iou(f["rect"], m) >= 0.5 for m in marks):
                sig.append("widget")
            if sig:
                got[f["id"]] = sig
        if got:
            out[pid] = got
    return out


def main() -> int:
    out = draft()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    c = collections.Counter(tuple(s) for page in out.values() for s in page.values())
    print(f"{sum(len(p) for p in out.values())} candidates on {len(out)} pages -> {OUT}")
    for s, n in c.most_common():
        print(f"  {'+'.join(s):22} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
