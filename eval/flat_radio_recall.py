"""How many radio/checkbox option boxes does the flat-form geometry finder recover?

Runs step2flat (which flattens the PDF first) on AcroForm forms whose option
groups are known, and matches its box candidates to the AcroForm kids by
centre-in-rect. Reports recall per form and how the finder labelled the hits
(oval -> "radio", square -> "checkbox").

    PYTHONPATH=. venv/bin/python eval/flat_radio_recall.py "source_pdfs/VA Form 10-10EZ.pdf" ...
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from step2flat import pipeline  # noqa: E402


def option_kids(pdf: Path) -> list[dict]:
    doc = pymupdf.open(pdf)
    groups: dict[str, list] = collections.defaultdict(list)
    for pno in range(len(doc)):
        page = doc[pno]
        for w in page.widgets():
            if w.field_type_string in ("RadioButton", "CheckBox"):
                try:
                    on = w.on_state()
                except Exception:
                    on = None
                groups[w.field_name].append({"page": pno, "rect": list(w.rect), "on": on,
                                             "kind": w.field_type_string})
    out = []
    for name, kids in groups.items():
        states = {k["on"] for k in kids if k["on"]}
        if len(kids) > 1 and len(states) > 1:
            for k in kids:
                k["group"] = name
                out.append(k)
    return out


def main(paths: list[str]) -> int:
    for p in paths:
        p = Path(p)
        kids = option_kids(p)
        kept, scored = pipeline.run(str(p))
        cands = [r for r in kept if r["kind"] in ("radio", "checkbox")]
        allc = [r for r in scored if r["kind"] in ("radio", "checkbox")]
        hit = collections.Counter(); hit_kind = collections.Counter(); miss = 0
        for k in kids:
            cx, cy = (k["rect"][0] + k["rect"][2]) / 2, (k["rect"][1] + k["rect"][3]) / 2
            m = [r for r in cands if int(r["page"]) == k["page"] and r["rect"][0] <= cx <= r["rect"][2] and r["rect"][1] <= cy <= r["rect"][3]]
            if m:
                hit[k["kind"]] += 1; hit_kind[m[0]["kind"]] += 1
            else:
                m2 = [r for r in allc if int(r["page"]) == k["page"] and r["rect"][0] <= cx <= r["rect"][2] and r["rect"][1] <= cy <= r["rect"][3]]
                hit["below_threshold" if m2 else "not_found"] += 1
        groups = len({k["group"] for k in kids})
        n = len(kids)
        found = hit["RadioButton"] + hit["CheckBox"]
        print(f"{p.name[:34]:34s} groups={groups:3d} option boxes={n:3d} found={found:3d} ({100*found/max(n,1):.0f}%) "
              f"labelled {dict(hit_kind)} | below_threshold={hit['below_threshold']} not_found={hit['not_found']} "
              f"| finder kept {len(cands)} box candidates on the form")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
