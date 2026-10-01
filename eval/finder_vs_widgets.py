"""Debugging yardstick: the page box finder against the blank's widget layer.

Case generation takes its boxes from the page (step2flat's finder on the
rendered blank), never from the AcroForm layer (Andrew, 2026-09-30). The
widget layer is still the best available truth about where the fillable
boxes ARE, so this reports, per form, which widgets the finder missed and
which finder boxes have no widget behind them. It feeds nothing; it tells
us where the finder needs work.

    PYTHONPATH=. venv/bin/python eval/finder_vs_widgets.py --tier core [--json out.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petey.synth.boxes import find_boxes, match_rect  # noqa: E402
from petey.validate.test_forms import forms  # noqa: E402


def widget_rects(pdf: Path) -> list[dict]:
    out = []
    doc = pymupdf.open(str(pdf))
    try:
        for pno, page in enumerate(doc, start=1):
            for w in page.widgets() or []:
                if w.field_type in (pymupdf.PDF_WIDGET_TYPE_SIGNATURE, pymupdf.PDF_WIDGET_TYPE_BUTTON):
                    continue
                kind = {pymupdf.PDF_WIDGET_TYPE_TEXT: "text", pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "option",
                        pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "option", pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "text",
                        pymupdf.PDF_WIDGET_TYPE_LISTBOX: "text"}.get(w.field_type, "other")
                out.append({"page": pno, "rect": [round(c, 2) for c in w.rect], "kind": kind, "path": w.field_name})
    finally:
        doc.close()
    return out


def compare(pdf: Path) -> dict:
    t0 = time.time()
    boxes = find_boxes(pdf)
    widgets = widget_rects(pdf)
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for b in boxes:
        by_page[b["page"]].append(b)
    hit = collections.Counter()
    missed = []
    used: set[str] = set()
    for w in widgets:
        m = match_rect(w["rect"], by_page.get(w["page"], []))
        if m is None:
            hit[f"miss_{w['kind']}"] += 1
            missed.append(w)
        else:
            hit[f"hit_{w['kind']}"] += 1
            used.add(m["id"])
    extras = [b for b in boxes if b["id"] not in used]
    n_text = sum(1 for w in widgets if w["kind"] == "text")
    n_opt = sum(1 for w in widgets if w["kind"] == "option")
    return {
        "form": pdf.name, "seconds": round(time.time() - t0, 1),
        "widgets": len(widgets), "finder_boxes": len(boxes),
        "text_recall": f"{hit['hit_text']}/{n_text}", "option_recall": f"{hit['hit_option']}/{n_opt}",
        "extras": len(extras),
        "extras_by_kind": dict(collections.Counter(b["kind"] for b in extras)),
        "missed": [{"page": w["page"], "kind": w["kind"], "rect": w["rect"], "path": w["path"].split(".")[-1]}
                   for w in missed],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tier", default="core")
    ap.add_argument("--forms", default=None, help="comma-separated stems instead of a tier")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    from petey.validate.test_forms import by_stem
    targets = [by_stem(s) for s in args.forms.split(",")] if args.forms else forms(args.tier)
    results = []
    for tf in targets:
        r = compare(tf.blank_path)
        results.append(r)
        print(f"{tf.stem:16} widgets {r['widgets']:4}  finder {r['finder_boxes']:4}  text {r['text_recall']:>9}  "
              f"options {r['option_recall']:>8}  extras {r['extras']:4} {r['extras_by_kind']}  {r['seconds']}s")
        for m in r["missed"][:12]:
            print(f"    missed p{m['page']} {m['kind']:6} {m['rect']} {m['path']}")
        if len(r["missed"]) > 12:
            print(f"    ... {len(r['missed']) - 12} more")
    if args.json:
        args.json.write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
