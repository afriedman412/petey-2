"""Survey every source PDF page-by-page before deciding how to label it.

`auto_label.py` reads the TEXT LAYER to associate widgets with printed
labels. Whether that method applies is a property of the document, and
until now it was only checked in aggregate — which is not good enough,
because a document can carry text on some pages and none on others. A
whole-document average hides a page that will silently produce invented
labels.

This sweeps per page and reports both the document verdict and the pages
that disagree with it.

## Verdicts

  ready        has widgets, has a text layer on every widgeted page, and
               is within the page budget — label with auto_label.py
  oversized    ready but beyond --max-pages; deferred, not broken
  mixed        some widgeted pages have text and some do not; the
               text-layer pages are labelable, the rest are not
  needs_ocr    has widgets, no usable text layer. tile_and_ocr.py
               recovers 84-98% of words at ~3-4s/page, so this is a
               fallback rather than a dead end
  no_widgets   no AcroForm at all — vision_label.py territory

A page counts as having a text layer on an absolute word floor, NOT on
words-per-widget. Table pages legitimately carry few words per widget —
cbp_form_7501 page 2 governs 162 row widgets with about 8 column headers
— and a ratio test wrongly calls those blind.

Usage:
    python source_survey.py
    python source_survey.py --max-pages 10 --worklist
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import pymupdf

from petey.paths import REPO, SOURCE_PDFS
HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# A widgeted page with fewer native words than this has no usable text
# layer. Absolute, not a ratio to widget count: a table page legitimately
# carries few words per widget (cbp_form_7501 page 2 governs 162 row
# widgets with ~8 column headers), and a ratio test wrongly calls those
# blind. Measured across 512 widgeted pages the split is total — 2 pages
# under 5 words, none between 5 and 49, 510 at 50+.
MIN_PAGE_WORDS = 15


def survey_pdf(path: Path) -> dict:
    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        return {"file": path.name, "error": f"{type(e).__name__}: {e}"[:90]}
    pages = []
    try:
        for i, page in enumerate(doc, start=1):
            n_w = len(list(page.widgets()))
            n_t = len(page.get_text("words"))
            pages.append({"page": i, "widgets": n_w, "words": n_t})
    finally:
        doc.close()

    widgeted = [p for p in pages if p["widgets"] > 0]
    total_w = sum(p["widgets"] for p in pages)
    total_t = sum(p["words"] for p in pages)

    def has_text(p):
        return p["words"] >= MIN_PAGE_WORDS

    texted = [p for p in widgeted if has_text(p)]
    blind = [p for p in widgeted if not has_text(p)]

    return {
        "file": path.name,
        "pages": len(pages),
        "widgeted_pages": len(widgeted),
        "widgets": total_w,
        "words": total_t,
        "text_pages": len(texted),
        "blind_pages": [p["page"] for p in blind],
        "blind_widgets": sum(p["widgets"] for p in blind),
    }


def verdict(s: dict, max_pages: int) -> str:
    if s.get("error"):
        return "error"
    if not s["widgets"]:
        return "no_widgets"
    if not s["text_pages"]:
        return "needs_ocr"
    if s["blind_pages"]:
        return "mixed"
    if s["widgeted_pages"] > max_pages:
        return "oversized"
    return "ready"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=SOURCE_PDFS)
    ap.add_argument("--max-pages", type=int, default=10,
                    help="widgeted-page budget (default 10)")
    ap.add_argument("--worklist", action="store_true",
                    help="print the ready set as a comma-separated list")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    rows = []
    # rglob, not glob: source_pdfs/ was reorganised into vertical subdirs
    # (okcc/, tax/, us_courts/, ...) and a non-recursive glob silently
    # surveyed only the 31 files left at the top level.
    for p in sorted(args.src.rglob("*.pdf")):
        s = survey_pdf(p)
        s["verdict"] = verdict(s, args.max_pages)
        rows.append(s)

    by = collections.Counter(r["verdict"] for r in rows)
    print("=" * 76)
    print(f"SOURCE SURVEY — {len(rows)} PDFs, page budget {args.max_pages}")
    print("=" * 76)
    for k in ("ready", "oversized", "mixed", "needs_ocr", "no_widgets",
              "error"):
        if by[k]:
            print(f"  {k:<12} {by[k]:>4}")

    for kind, note in (
        ("needs_ocr", "no text layer on any widgeted page — "
                      "auto_label CANNOT work here"),
        ("mixed", "some widgeted pages have no text — those pages will "
                  "get invented labels"),
        ("oversized", f"beyond {args.max_pages} widgeted pages — deferred"),
    ):
        sel = [r for r in rows if r["verdict"] == kind]
        if not sel:
            continue
        print()
        print("-" * 76)
        print(f"{kind.upper()} ({len(sel)}) — {note}")
        print("-" * 76)
        for r in sorted(sel, key=lambda r: -r.get("blind_widgets", 0))[:20]:
            extra = ""
            if kind == "mixed":
                bp = r["blind_pages"]
                extra = (f"  blind pages {bp[:6]}"
                         f"{'...' if len(bp) > 6 else ''} "
                         f"({r['blind_widgets']} widgets)")
            print(f"  {r['file']:<34} {r['pages']:>3}pp "
                  f"{r['widgets']:>5}w {r['words']:>7} words{extra}")

    ready = [r for r in rows if r["verdict"] == "ready"]
    print()
    print("-" * 76)
    print(f"READY: {len(ready)} forms, "
          f"{sum(r['widgets'] for r in ready)} widgets")
    print("-" * 76)
    if args.worklist:
        print(",".join(r["file"].rsplit(".", 1)[0] for r in ready))

    if args.out:
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\n[ok] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
