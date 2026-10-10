"""A finder change measured before it lands: the same yardstick as `finder_vs_widgets.py`, with the change
monkeypatched in and the boxes written to a scratch cache, so nothing in `runs/_gen_cache/` moves.

The first experiment (2026-10-01): B106I page 2's 44 missed amount cells are `fz:underline` candidates at 0.40
because the text layer carries the word `$___________`, a typed-underscore line cue with a currency sign in
front; `features.LINE_CUE` only excludes words made purely of line characters, so the word counts as printed
text (tcov 0.58) and `text_filled` sinks the cell. The patch lets one leading non-word character precede the run.

    PYTHONPATH=. venv/bin/python eval/finder_experiment.py --list runs/judge_eval/forms44.txt \
        --json runs/judge_eval/finder_vs_widgets_after_linecue.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import finder_vs_widgets as yard  # noqa: E402
from step2flat import features  # noqa: E402

# A checkbox square that is a text glyph: ZapfDingbats '■' (LA 7006, 68 boxes), Wingdings2 0xF0A3 (TX RRC R-32, 78),
# Wingdings 0xF071 / 0xF06F (B410, KS DO-41). The frozen raster reader erases text before it looks for boxes, so
# the square leaves no candidate; the lattice's candidate over it is 'text_filled' and 'header' (the glyph is bold)
# and sinks to 0.45. The patch drops such glyphs from the words the features count and adds each as a candidate.
GLYPH_CHARS = set("■□☐☑☒❑❒▢◻◼▪▫")


def _is_glyph(ch: str) -> bool:
    return len(ch) == 1 and (ch in GLYPH_CHARS or 0xE000 <= ord(ch) <= 0xF8FF)


def _glyph_rects(page) -> list:
    import pymupdf
    out = []
    for b in page.get_text("rawdict").get("blocks", []):
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                for c in sp.get("chars", []):
                    if _is_glyph(c["c"]):
                        r = pymupdf.Rect(c["bbox"])
                        if 4 <= r.width <= 20 and 4 <= r.height <= 20:
                            out.append(r)
    return out


def patch_glyph():
    import pymupdf
    from step2flat import confidence, lattice
    orig_info = features._page_info
    orig_fields = lattice.lattice_fields

    def page_info(pa):
        W, fills, bold, rect, zebra = orig_info(pa)
        W = [(r, t) for r, t in W if not _is_glyph(t)]
        return W, fills, bold, rect, zebra

    def lattice_fields(doc):
        P = orig_fields(doc)
        for pg in range(len(doc)):
            for r in _glyph_rects(doc[pg]):
                # the character bbox is the font's line height (10.7 x 13.3 for Wingdings at this size); the drawn
                # square is about the advance width, so take a square of the width centred on the bbox. With the
                # full bbox, KS DO-41's 7 pt radios and DO-10's sat inside boxes over 3x their area (in_region 10
                # and 5); with the width square, 0 (2026-10-01).
                side = r.width
                cy = (r.y0 + r.y1) / 2
                sq = pymupdf.Rect(r.x0, cy - side / 2, r.x0 + side, cy + side / 2)
                P.append(dict(page=pg, rect=list(sq), kind="checkbox", source="glyph", caption=""))
        return P

    features._page_info = page_info
    lattice.lattice_fields = lattice_fields
    confidence.TIER["lat:glyph"] = 0.75


PATCHES = {
    "linecue": lambda: setattr(features, "LINE_CUE", re.compile(r'[^\w\s]?[_.…·\-]{3,}')),
    "glyph": patch_glyph,
    "both": lambda: (PATCHES["linecue"](), patch_glyph()),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", required=True)
    ap.add_argument("--patch", default="linecue", choices=sorted(PATCHES))
    ap.add_argument("--cache-dir", type=Path, default=None, help="scratch box cache (default under runs/judge_eval)")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    PATCHES[args.patch]()
    cache = args.cache_dir or (Path("runs/judge_eval") / f"_boxes_{args.patch}")
    results = []
    tot: collections.Counter = collections.Counter()
    for line in Path(args.list).read_text().splitlines():
        if "|" not in line:
            continue
        stem, rel = line.strip().split("|", 1)
        r = yard.compare(yard.SOURCE_PDFS / rel, cache_dir=cache)
        r["stem"] = stem
        results.append(r)
        for k in ("widgets", "finder_boxes", "n_text", "n_option", "hit_text", "hit_option", "in_region", "part",
                  "miss", "region_boxes", "widgets_in_regions", "extras"):
            tot[k] += r[k]
        print(f"{stem[:28]:28} widgets {r['widgets']:4} finder {r['finder_boxes']:4} text {r['text_recall']:>9} "
              f"options {r['option_recall']:>8} in_region {r['in_region']:3} miss {r['miss']:3} extras {r['extras']:3} "
              f"{r['seconds']}s", flush=True)
    print(f"TOTAL text {tot['hit_text']}/{tot['n_text']} options {tot['hit_option']}/{tot['n_option']} "
          f"in_region {tot['in_region']} part {tot['part']} miss {tot['miss']} extras {tot['extras']}")
    if args.json:
        args.json.write_text(json.dumps({"patch": args.patch, "forms": results, "totals": dict(tot)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
