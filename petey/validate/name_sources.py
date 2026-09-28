"""Publisher-written naming signal per widget: `/TU` tooltip and field name.

The labeler names each widget from positioned text spans near its rect —
proximity. Two other sources are written by the form's publisher and travel
inside the file itself:

  **`/TU`** — the tooltip. Surveyed already (51% of data widgets) and wired
  into the labeling prompt as of 2026-09-22.

  **The AcroForm field name** — `w.field_name`. Frequently prose: `E-Mail`,
  `Printed Name`, `Pool Code`, `Issuing Bank`, `Letter of Credit Number`.
  `auto_label.py` already sends it to the model, but as `"path"`, framed as
  an opaque identifier; nothing in the prompt says it may be readable.

Found by accident: `correct.py`'s orphan report prints the path of a widget
whose name was rebound away, and the paths came out legible.

## The two sources are complementary, not redundant

Coverage is anti-correlated across verticals, so the union is much larger
than either: `nd_ncid` carries tooltips on 2% of widgets and readable names
on 83%; `immigration` has both; `tax` has neither and is the vertical the
library is otherwise measured best on. A labeler told to use both therefore
gains most where it is currently weakest per-vertical, which is not where
the aggregate would predict.

## What counts as readable

The leaf component of the name, with XFA `[0]` indices stripped, must
contain an alphabetic run of three or more characters that is not itself a
widget-type word. This rejects generator defaults (`Text16`, `Button1`,
`fld_003`) and bare type words (`checkbox`), and accepts anything a person
plausibly typed. Deliberately generous: the question is whether there is
signal worth sending to a model, not whether the name is a good slug.

Usage:
    python name_sources.py
    python name_sources.py --src ../source_pdfs --out runs/name_sources.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

import pymupdf

from petey.paths import REPO, SOURCE_PDFS
HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# Widget names a PDF editor generates when the author typed nothing.
_OPAQUE = re.compile(r"""^(
    (text|button|check\s*box|checkbox|radio|field|fld|f|untitled|combobox|
     dropdown|listbox|signature|sig|image|undefined|edit|input|cell|box)
    [\s_.-]*\d*
)$""", re.I | re.X)

# Words that only restate the control, carrying no field meaning.
_TYPE_WORDS = {
    "text", "box", "check", "fld", "field", "btn", "button", "radio",
    "sub", "form", "page", "cell", "input", "edit", "item", "row", "col",
}

# Spelled-out numbers are POSITIONS, not meanings. XFA forms name widgets
# for the box they sit in — dd1155 carries `eight`, `eleven`, `sixteen`,
# `twenty7A` — and counting those as publisher-written prose overstates how
# much naming signal a form actually carries.
_NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth", "part", "section", "line", "no", "num",
}

# Pushbuttons hold no value (OBSERVATIONS class 12). Counting them would
# inflate coverage with `Print Form` / `Reset Form`, which are real prose
# and useless as field names.
_PUSHBUTTON_FLAG = 1 << 16


def leaf(path: str) -> str:
    """Last non-index component of a possibly XFA-style dotted path."""
    p = re.sub(r"\[\d+\]", "", path or "")
    return p.split(".")[-1].strip()


def is_readable(path: str) -> bool:
    l = leaf(path)
    if not l or _OPAQUE.match(l):
        return False
    words = [w for w in re.findall(r"[A-Za-z][a-z]{2,}|[A-Z]{3,}", l)
             if w.lower() not in _TYPE_WORDS
             and w.lower() not in _NUMBER_WORDS]
    return bool(words)


def is_pushbutton(w) -> bool:
    try:
        if w.field_type == pymupdf.PDF_WIDGET_TYPE_BUTTON:
            return True
        return bool((w.field_flags or 0) & _PUSHBUTTON_FLAG)
    except Exception:
        return False


def survey(src: Path) -> list[dict]:
    rows: list[dict] = []
    for vert in sorted(p for p in src.iterdir() if p.is_dir()):
        for pdf in sorted(vert.rglob("*.pdf")):
            try:
                doc = pymupdf.open(str(pdf))
            except Exception:
                continue
            try:
                for page in doc:
                    for w in (page.widgets() or []):
                        if is_pushbutton(w):
                            continue
                        name = w.field_name or ""
                        tip = (w.field_label or "").strip()
                        rows.append({
                            "vertical": vert.name,
                            "file": pdf.name,
                            "readable_name": is_readable(name),
                            "tooltip": bool(tip),
                        })
            except Exception:
                pass
            finally:
                doc.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=SOURCE_PDFS)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rows = survey(args.src)
    n = len(rows)
    if not n:
        print("no data widgets found")
        return 1

    def pct(f) -> float:
        return 100.0 * sum(1 for r in rows if f(r)) / len(rows)

    print("=" * 74)
    print("PUBLISHER-WRITTEN NAMING SIGNAL — data widgets only")
    print("=" * 74)
    print(f"data widgets (pushbuttons excluded): {n}")
    print(f"  readable AcroForm name : {pct(lambda r: r['readable_name']):5.1f}%")
    print(f"  /TU tooltip            : {pct(lambda r: r['tooltip']):5.1f}%")
    print(f"  EITHER                 : "
          f"{pct(lambda r: r['readable_name'] or r['tooltip']):5.1f}%")
    print(f"  BOTH                   : "
          f"{pct(lambda r: r['readable_name'] and r['tooltip']):5.1f}%")
    print(f"  NEITHER                : "
          f"{pct(lambda r: not r['readable_name'] and not r['tooltip']):5.1f}%")

    by_v: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_v[r["vertical"]].append(r)
    print()
    print(f"  {'vertical':16s} {'widgets':>8} {'name':>7} {'tooltip':>8} "
          f"{'either':>7}")
    for v, rs in sorted(by_v.items(), key=lambda kv: -len(kv[1])):
        m = len(rs)
        nm = 100.0 * sum(1 for r in rs if r["readable_name"]) / m
        tt = 100.0 * sum(1 for r in rs if r["tooltip"]) / m
        ei = 100.0 * sum(
            1 for r in rs if r["readable_name"] or r["tooltip"]) / m
        print(f"  {v:16s} {m:8d} {nm:6.0f}% {tt:7.0f}% {ei:6.0f}%")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\n[ok] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
